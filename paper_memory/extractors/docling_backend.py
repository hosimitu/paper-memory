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
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .base import ExtractionResult, ExtractorBackend


class DoclingBackend(ExtractorBackend):
    """docling ライブラリを使用した PDF 抽出バックエンド"""

    def extract(
        self,
        pdf_path: Path,
        output_dir: Path,
        analyze_tables: bool = False,
        images_scale: float = 3.0,
        **options,
    ) -> ExtractionResult:
        """
        docling で PDF を解析し、Markdown + 画像を output_dir に出力する。

        Args:
            pdf_path: 入力 PDF ファイルのパス
            output_dir: 出力先ディレクトリ（extracted/論文名/）
            analyze_tables: True の場合、表画像を LLM でさらに解析して Markdown を精緻化
            images_scale: 画像の解像度スケール（デフォルト 2.0）
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

        # Windows での HuggingFace シンボリックリンクエラーを回避
        os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

        # 1. パイプライン設定
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True  # 図を画像化
        pipeline_options.generate_table_images = True    # 表を画像化
        pipeline_options.generate_page_images = True     # 数式のクロップ用にページ画像を生成
        pipeline_options.do_formula_enrichment = False   # 重いローカル解析はオフ（Gemini で行うため）
        pipeline_options.images_scale = images_scale

        # 2. 変換実行
        converter = DocumentConverter(format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        })
        result = converter.convert(pdf_path)
        doc = result.document

        # 3. 画像ディレクトリ準備
        image_dir = output_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)

        # 4. 図・表・数式の画像を保存
        saved_pictures: list[Path] = []
        table_images: list[Path] = []
        formula_images: list[Path] = []

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
                            # 座標を取得してクロップ
                            bbox = item.prov[0].bbox
                            # get_rect() または直接座標を使用
                            # docling 2.x の bbox.as_tuple() は [x0, y0, x1, y1] (bottom-up) の場合がある
                            # PIL は [left, top, right, bottom] (top-down)
                            # page.image.pil_image は既に images_scale が適用されている可能性があるため注意
                            img = item.get_image(result.document)
                    except Exception as e:
                        print(f"  [docling] 画像の取得に失敗しました ({item.self_ref}): {e}")

                if img:
                    if isinstance(item, PictureItem):
                        item_type_label = "picture"
                    elif isinstance(item, TableItem):
                        item_type_label = "table"
                    else:
                        item_type_label = "formula"
                    
                    ref_parts = item.self_ref.strip("#/").split("/")
                    item_index = ref_parts[-1]
                    filename = f"{item_type_label}-{item_index}.png"
                    save_path = image_dir / filename
                    img.save(save_path)
                    
                    if isinstance(item, PictureItem):
                        saved_pictures.append(save_path)
                    elif isinstance(item, TableItem):
                        table_images.append(save_path)
                    else:
                        formula_images.append(save_path)
                    
                    print(f"  [docling] 画像を保存しました: {filename}")

        # 5. Markdown エクスポート
        markdown_content = doc.export_to_markdown(
            image_placeholder="![image](images/{image_id}.png)"
        )

        # プレースホルダー {image_id} を「図」の ID で順番に置換
        for img_path in saved_pictures:
            item_id = img_path.stem
            markdown_content = markdown_content.replace("{image_id}", item_id, 1)

        # 6. 表・数式の LLM 解析（オプション）
        if analyze_tables:
            if table_images:
                print(f"  [LLM] {len(table_images)} 個の表画像を解析し、置換します...")
                markdown_content = self._analyze_table_images(markdown_content, table_images)
            
            if formula_images:
                print(f"  [LLM] {len(formula_images)} 個の数式画像を解析し、置換します...")
                markdown_content = self._analyze_formula_images(markdown_content, formula_images)

        # 7. Markdown ファイルを保存
        md_path = output_dir / f"{output_dir.name}.md"
        md_path.write_text(markdown_content, encoding="utf-8")

        print(f"[docling] 抽出完了: {md_path}")
        print(f"[docling] 画像保存先: {image_dir}")

        return ExtractionResult(
            markdown=markdown_content,
            images=saved_pictures + table_images + formula_images,
            table_images=table_images,
            output_dir=output_dir,
            backend_name="docling",
        )

    def _analyze_table_images(self, markdown: str, table_images: list[Path]) -> str:
        """表画像を Gemini で解析し置換する (15 RPM 対応)"""
        return self._analyze_images_with_gemini(
            markdown, 
            table_images, 
            "table", 
            r'(?:(?:^|[ \t]*)\|[^\n]*\n(?:[ \t]*\|[ \t]*[:\-]+[ \t]*)+\|[^\n]*\n(?:(?:[ \t]*\|[^\n]*\n?)*))'
        )

    def _analyze_formula_images(self, markdown: str, formula_images: list[Path]) -> str:
        """数式画像を Gemini で解析し置換する (15 RPM 対応)"""
        return self._analyze_images_with_gemini(
            markdown, 
            formula_images, 
            "formula", 
            r'<!-- formula-not-decoded -->'
        )

    def _analyze_images_with_gemini(self, markdown: str, image_paths: list[Path], item_type: str, text_pattern: str) -> str:
        """
        Gemini を用いた汎用的な画像解析・置換ロジック (15 RPM 対応)
        """
        try:
            from PIL import Image
            import google.generativeai as genai
            import re
        except ImportError as e:
            print(f"  [LLM] ライブラリ不足: {e}", file=sys.stderr)
            return markdown

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return markdown

        genai.configure(api_key=api_key)

        from ..ai_models import TABLE_IMAGE_MODEL, FORMULA_IMAGE_MODEL
        from ..prompts import get_table_image_analysis_prompt, get_formula_image_analysis_prompt

        if item_type == "table":
            model_name = TABLE_IMAGE_MODEL
            prompt_func = get_table_image_analysis_prompt
            placeholder_pattern = r'!\[image\]\(images/table-\d+\.png\)'
        else:
            model_name = FORMULA_IMAGE_MODEL
            prompt_func = get_formula_image_analysis_prompt
            placeholder_pattern = r'!\[image\]\(images/formula-\d+\.png\)'

        model = genai.GenerativeModel(model_name)
        
        combined_pattern = re.compile(f'({placeholder_pattern}|{text_pattern})', re.MULTILINE)
        matches = list(combined_pattern.finditer(markdown))
        
        if len(matches) != len(image_paths):
            print(f"  [LLM] 警告: {item_type} ターゲット数 ({len(matches)}) と画像数 ({len(image_paths)}) が不一致です。", file=sys.stderr)

        updated_md = markdown
        last_request_time = 0.0
        # 15 RPM = 4秒に1回
        INTERVAL = 4.0

        for i, match in enumerate(reversed(matches)):
            idx = len(matches) - 1 - i
            if idx >= len(image_paths): continue
            
            img_path = image_paths[idx]
            img_id = img_path.stem
            
            if last_request_time > 0:
                elapsed = time.time() - last_request_time
                if elapsed < INTERVAL:
                    sleep_time = INTERVAL - elapsed
                    print(f"  [LLM] RPM 制限 (15 RPM) のため {sleep_time:.1f} 秒待機します...")
                    time.sleep(sleep_time)

            try:
                print(f"  [LLM] {item_type} 画像を解析中 ({idx+1}/{len(image_paths)}): {img_id}")
                img = Image.open(img_path)
                prompt = prompt_func()
                
                max_retries = 3
                response = None
                for attempt in range(max_retries):
                    try:
                        last_request_time = time.time()
                        response = model.generate_content([prompt, img])
                        break
                    except Exception as e:
                        if ("429" in str(e) or "quota" in str(e).lower()) and attempt < max_retries - 1:
                            wait_sec = 10 * (attempt + 1)
                            print(f"  [LLM] レート制限発生。{wait_sec} 秒待機 (試行 {attempt + 1})...")
                            time.sleep(wait_sec)
                            continue
                        raise e

                if not response: continue
                result_text = response.text.strip()

                if item_type == "table":
                    table_match = re.search(r'((?:[ \t]*\|[^\n]*\n?)+)', result_text)
                    content = table_match.group(1).strip() if table_match else result_text
                else:
                    # 数式の場合は LaTeX ブロックを抽出
                    formula_match = re.search(r'(\$\$.*?\$\$|\$.*?\$)', result_text, re.DOTALL)
                    content = formula_match.group(1).strip() if formula_match else result_text

                start, end = match.span()
                marker = f"<!-- LLM解析済み{item_type}: {img_id} -->"
                updated_md = updated_md[:start] + f"{marker}\n{content}\n" + updated_md[end:]
                print(f"  [LLM] {item_type} を置換しました: {img_id}")

            except Exception as e:
                print(f"  [LLM] 解析エラー ({img_id}): {e}", file=sys.stderr)

        return updated_md
