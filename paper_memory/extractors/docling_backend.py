# Copyright 2026 hosimitu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding: utf-8 -*-
"""
DoclingBackend — docling を用いた PDF 抽出バックエンド（デフォルト）

特徴:
  - 図・表の画像化（generate_picture_images / generate_table_images）
  - 表画像を Gemini マルチモーダルで解析し、高精度 Markdown 表に変換（--analyze-tables 時）
  - 出力先は extracted/論文名/ に統一
  - チャンク分割変換による大規模PDF（30ページ超）のOOM対策
    - pypdf で総ページ数を取得し、chunk_size ページ単位で page_range を指定して分割変換
    - 各チャンク処理後に gc.collect() でメモリを解放
    - 画像IDはグローバル連番で管理（チャンク間のファイル名衝突を回避）
"""

from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path

from .base import ExtractionResult, ExtractorBackend

# チャンクサイズのデフォルト値（ページ数）
# 大規模PDFのOOM対策として、このページ数ずつ分割して変換する
DEFAULT_CHUNK_SIZE = 15


def _get_total_pages(pdf_path: Path) -> int | None:
    """pypdf で PDF の総ページ数を取得する。取得に失敗した場合は None を返す。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except ImportError:
        print(
            "  [docling] pypdf がインストールされていないため、ページ数の自動取得をスキップします。",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(
            f"  [docling] ページ数の取得に失敗しました: {e}",
            file=sys.stderr,
        )
        return None


class DoclingBackend(ExtractorBackend):
    """docling ライブラリを使用した PDF 抽出バックエンド"""

    def extract(
        self,
        pdf_path: Path,
        output_dir: Path,
        analyze_tables: bool = False,
        images_scale: float = 3.0,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        **options,
    ) -> ExtractionResult:
        """
        docling で PDF を解析し、Markdown + 画像を output_dir に出力する。

        大規模PDFのOOM対策として、chunk_size ページ単位で分割して変換する。
        各チャンク処理後に gc.collect() でメモリを解放する。

        Args:
            pdf_path: 入力 PDF ファイルのパス
            output_dir: 出力先ディレクトリ（extracted/論文名/）
            analyze_tables: True の場合、表画像を LLM でさらに解析して Markdown を精緻化
            images_scale: 画像の解像度スケール（デフォルト 3.0）
            chunk_size: 1回の変換で処理するページ数（デフォルト 15）。
                        0 または None を指定すると一括変換（旧挙動）になる。
        """
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling_core.types.doc import PictureItem, TableItem, FormulaItem
        except ImportError as e:
            raise ImportError(
                "docling がインストールされていません。\n"
                "pip install docling docling-core を実行してください。"
            ) from e

        print(f"[docling] 変換を開始します: {pdf_path.name}")

        import tempfile
        import shutil

        # Windows での HuggingFace シンボリックリンクエラーを回避
        os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

        # 特殊文字による docling のエラーを回避するため、安全な名前の一時ファイルにコピーして処理する
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_pdf_path = Path(tmp.name)

        try:
            shutil.copy2(pdf_path, tmp_pdf_path)

            # 総ページ数を pypdf で取得し、チャンク分割の要否を判断する
            total_pages = _get_total_pages(tmp_pdf_path)
            use_chunked = chunk_size and chunk_size > 0 and total_pages is not None

            if use_chunked:
                print(
                    f"[docling] 総ページ数: {total_pages} ページ。"
                    f"チャンクサイズ {chunk_size} ページで分割変換します。"
                )
            else:
                print("[docling] 一括変換モードで処理します。")

            # 1. パイプライン設定（チャンク間で共有）
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True  # 図を画像化
            pipeline_options.generate_table_images = True  # 表を画像化
            pipeline_options.generate_page_images = (
                True  # 数式のクロップ用にページ画像を生成
            )
            pipeline_options.do_formula_enrichment = (
                False  # 重いローカル解析はオフ（Gemini で行うため）
            )
            pipeline_options.images_scale = images_scale

            # 2. DocumentConverter の初期化（チャンク間で再利用）
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )

            # 3. 画像ディレクトリ準備
            image_dir = output_dir / "images"
            image_dir.mkdir(parents=True, exist_ok=True)

            # 4. チャンク分割ループで変換・画像保存・Markdown 収集
            all_markdown_parts: list[str] = []
            all_saved_pictures: list[Path] = []
            all_table_images: list[Path] = []
            all_formula_images: list[Path] = []

            # 画像IDのグローバル連番（チャンク間でのファイル名衝突を防ぐ）
            global_picture_idx = 0
            global_table_idx = 0
            global_formula_idx = 0

            if use_chunked:
                # チャンク単位で変換
                chunk_ranges = [
                    (start, min(start + chunk_size - 1, total_pages))
                    for start in range(1, total_pages + 1, chunk_size)
                ]
                total_chunks = len(chunk_ranges)

                for chunk_num, (chunk_start, chunk_end) in enumerate(chunk_ranges, 1):
                    print(
                        f"[docling] チャンク {chunk_num}/{total_chunks} を処理中"
                        f" (ページ {chunk_start}〜{chunk_end})..."
                    )

                    result = converter.convert(
                        tmp_pdf_path, page_range=(chunk_start, chunk_end)
                    )
                    doc = result.document

                    chunk_md, global_picture_idx, global_table_idx, global_formula_idx = (
                        self._process_chunk(
                            doc=doc,
                            result=result,
                            image_dir=image_dir,
                            saved_pictures=all_saved_pictures,
                            table_images=all_table_images,
                            formula_images=all_formula_images,
                            global_picture_idx=global_picture_idx,
                            global_table_idx=global_table_idx,
                            global_formula_idx=global_formula_idx,
                        )
                    )
                    all_markdown_parts.append(chunk_md)

                    # チャンク終了後にメモリを明示的に解放する
                    del result, doc
                    gc.collect()
                    print(f"[docling] チャンク {chunk_num}/{total_chunks} 完了。メモリを解放しました。")

            else:
                # 一括変換（旧来の挙動）
                result = converter.convert(tmp_pdf_path)
                doc = result.document

                chunk_md, global_picture_idx, global_table_idx, global_formula_idx = (
                    self._process_chunk(
                        doc=doc,
                        result=result,
                        image_dir=image_dir,
                        saved_pictures=all_saved_pictures,
                        table_images=all_table_images,
                        formula_images=all_formula_images,
                        global_picture_idx=global_picture_idx,
                        global_table_idx=global_table_idx,
                        global_formula_idx=global_formula_idx,
                    )
                )
                all_markdown_parts.append(chunk_md)

                del result, doc
                gc.collect()

            # 5. 全チャンクの Markdown を結合
            markdown_content = "\n\n".join(
                part for part in all_markdown_parts if part.strip()
            )

            # 6. 表・数式の LLM 解析（オプション）
            if analyze_tables:
                if all_table_images:
                    print(
                        f"  [LLM] {len(all_table_images)} 個の表画像を解析し、置換します..."
                    )
                    markdown_content = self._analyze_table_images(
                        markdown_content, all_table_images
                    )

                if all_formula_images:
                    print(
                        f"  [LLM] {len(all_formula_images)} 個の数式画像を解析し、置換します..."
                    )
                    markdown_content = self._analyze_formula_images(
                        markdown_content, all_formula_images
                    )

            # 7. Markdown ファイルを保存
            md_path = output_dir / f"{output_dir.name}.md"
            md_path.write_text(markdown_content, encoding="utf-8")

            print(f"[docling] 抽出完了: {md_path}")
            print(f"[docling] 画像保存先: {image_dir}")

            return ExtractionResult(
                markdown=markdown_content,
                images=all_saved_pictures + all_table_images + all_formula_images,
                table_images=all_table_images,
                output_dir=output_dir,
                backend_name="docling",
            )
        finally:
            if tmp_pdf_path.exists():
                try:
                    tmp_pdf_path.unlink()
                except Exception as e:
                    print(
                        f"  [Warning] 一時ファイルの削除に失敗しました: {e}",
                        file=sys.stderr,
                    )

    def _process_chunk(
        self,
        doc,
        result,
        image_dir: Path,
        saved_pictures: list[Path],
        table_images: list[Path],
        formula_images: list[Path],
        global_picture_idx: int,
        global_table_idx: int,
        global_formula_idx: int,
    ) -> tuple[str, int, int, int]:
        """
        1チャンク分のドキュメントから画像を抽出・保存し、Markdown を返す。

        Args:
            doc: docling の Document オブジェクト
            result: docling の ConversionResult オブジェクト
            image_dir: 画像保存先ディレクトリ
            saved_pictures: 全チャンク通しの図画像リスト（追記される）
            table_images: 全チャンク通しの表画像リスト（追記される）
            formula_images: 全チャンク通しの数式画像リスト（追記される）
            global_picture_idx: 図のグローバル連番（ファイル名重複防止）
            global_table_idx: 表のグローバル連番
            global_formula_idx: 数式のグローバル連番

        Returns:
            (チャンクの Markdown テキスト, 更新後の picture_idx, table_idx, formula_idx)
        """
        try:
            from docling_core.types.doc import PictureItem, TableItem, FormulaItem
        except ImportError as e:
            raise ImportError(
                "docling-core がインストールされていません。\n"
                "pip install docling-core を実行してください。"
            ) from e

        # このチャンクで保存した画像（Markdownプレースホルダー置換用）
        chunk_pictures: list[Path] = []

        for item, _level in doc.iterate_items():
            if isinstance(item, (PictureItem, TableItem, FormulaItem)):
                img = None
                if hasattr(item, "image") and item.image:
                    img = item.image.pil_image

                # 画像がない（または数式）場合は、ページ画像からクロップを試みる
                if not img and item.prov:
                    try:
                        page_no = item.prov[0].page_no
                        page = result.pages[page_no - 1]
                        if page.image:
                            img = item.get_image(result.document)
                    except Exception as e:
                        print(
                            f"  [docling] 画像の取得に失敗しました ({item.self_ref}): {e}"
                        )

                if img:
                    if isinstance(item, PictureItem):
                        item_type_label = "picture"
                        item_idx = global_picture_idx
                        global_picture_idx += 1
                    elif isinstance(item, TableItem):
                        item_type_label = "table"
                        item_idx = global_table_idx
                        global_table_idx += 1
                    else:
                        item_type_label = "formula"
                        item_idx = global_formula_idx
                        global_formula_idx += 1

                    filename = f"{item_type_label}-{item_idx}.png"
                    save_path = image_dir / filename
                    img.save(save_path)

                    if isinstance(item, PictureItem):
                        saved_pictures.append(save_path)
                        chunk_pictures.append(save_path)
                    elif isinstance(item, TableItem):
                        table_images.append(save_path)
                    else:
                        formula_images.append(save_path)

                    print(f"  [docling] 画像を保存しました: {filename}")

        # Markdown エクスポート
        chunk_markdown = doc.export_to_markdown(
            image_placeholder="![image](images/{image_id}.png)"
        )

        # プレースホルダー {image_id} を「図」の ID で順番に置換
        for img_path in chunk_pictures:
            item_id = img_path.stem
            chunk_markdown = chunk_markdown.replace("{image_id}", item_id, 1)

        return chunk_markdown, global_picture_idx, global_table_idx, global_formula_idx

    def _analyze_table_images(self, markdown: str, table_images: list[Path]) -> str:
        """表画像を Gemini で解析し置換する (15 RPM 対応)"""
        return self._analyze_images_with_gemini(
            markdown,
            table_images,
            "table",
            r"(?:(?:^|[ \t]*)\|[^\n]*\n(?:[ \t]*\|[ \t]*[:\-]+[ \t]*)+\|[^\n]*\n(?:(?:[ \t]*\|[^\n]*\n?)*))",
        )

    def _analyze_formula_images(self, markdown: str, formula_images: list[Path]) -> str:
        """数式画像を Gemini で解析し置換する (15 RPM 対応)"""
        return self._analyze_images_with_gemini(
            markdown, formula_images, "formula", r"<!-- formula-not-decoded -->"
        )

    def _analyze_images_with_gemini(
        self, markdown: str, image_paths: list[Path], item_type: str, text_pattern: str
    ) -> str:
        """
        Gemini を用いた汎用的な画像解析・置換ロジック (15 RPM 対応)
        """
        try:
            from PIL import Image
            from ..gemini_client import generate_content_with_retry
            from google.genai import types
            import io
            import re
        except ImportError as e:
            print(f"  [LLM] ライブラリ不足: {e}", file=sys.stderr)
            return markdown

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return markdown

        from ..ai_models import TABLE_IMAGE_MODEL, FORMULA_IMAGE_MODEL
        from ..prompts import (
            get_table_image_analysis_prompt,
            get_formula_image_analysis_prompt,
        )

        if item_type == "table":
            model_name = TABLE_IMAGE_MODEL
            prompt_func = get_table_image_analysis_prompt
            placeholder_pattern = r"!\[image\]\(images/table-\d+\.png\)"
        else:
            model_name = FORMULA_IMAGE_MODEL
            prompt_func = get_formula_image_analysis_prompt
            placeholder_pattern = r"!\[image\]\(images/formula-\d+\.png\)"

        combined_pattern = re.compile(
            f"({placeholder_pattern}|{text_pattern})", re.MULTILINE
        )
        matches = list(combined_pattern.finditer(markdown))

        if len(matches) != len(image_paths):
            print(
                f"  [LLM] 警告: {item_type} ターゲット数 ({len(matches)}) と画像数 ({len(image_paths)}) が不一致です。",
                file=sys.stderr,
            )

        updated_md = markdown
        last_request_time = 0.0
        # 15 RPM = 4秒に1回
        INTERVAL = 4.0

        for i, match in enumerate(reversed(matches)):
            idx = len(matches) - 1 - i
            if idx >= len(image_paths):
                continue

            img_path = image_paths[idx]
            img_id = img_path.stem

            if last_request_time > 0:
                elapsed = time.time() - last_request_time
                if elapsed < INTERVAL:
                    sleep_time = INTERVAL - elapsed
                    print(
                        f"  [LLM] RPM 制限 (15 RPM) のため {sleep_time:.1f} 秒待機します..."
                    )
                    time.sleep(sleep_time)

            fallback = False
            try:
                print(
                    f"  [LLM] {item_type} 画像を解析中 ({idx + 1}/{len(image_paths)}): {img_id}"
                )
                img = Image.open(img_path)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                image_part = types.Part.from_bytes(
                    data=buf.getvalue(), mime_type="image/png"
                )
                prompt = prompt_func()

                last_request_time = time.time()
                response = generate_content_with_retry(
                    model=model_name, contents=[prompt, image_part], max_retries=3
                )

                if not response:
                    fallback = True
                else:
                    result_text = response.text.strip()

                    if item_type == "table":
                        table_match = re.search(
                            r"((?:[ \t]*\|[^\n]*\n?)+)", result_text
                        )
                        content = (
                            table_match.group(1).strip() if table_match else result_text
                        )
                    else:
                        # 数式の場合は LaTeX ブロックを抽出
                        formula_match = re.search(
                            r"(\$\$.*?\$\$|\$.*?\$)", result_text, re.DOTALL
                        )
                        content = (
                            formula_match.group(1).strip()
                            if formula_match
                            else result_text
                        )

                    start, end = match.span()
                    marker = f"<!-- LLM解析済み{item_type}: {img_id} -->"
                    updated_md = (
                        updated_md[:start] + f"{marker}\n{content}\n" + updated_md[end:]
                    )
                    print(f"  [LLM] {item_type} を置換しました: {img_id}")

            except Exception as e:
                print(f"  [LLM] 解析エラー ({img_id}): {e}", file=sys.stderr)
                fallback = True

            if fallback:
                if item_type == "formula":
                    start, end = match.span()
                    fallback_content = f"![image](images/{img_id}.png)"
                    updated_md = (
                        updated_md[:start] + fallback_content + updated_md[end:]
                    )

        return updated_md
