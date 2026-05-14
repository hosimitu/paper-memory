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
PyPDFBackend — pypdf を用いた軽量フォールバック抽出バックエンド

特徴:
  - docling が使用できない場合や、軽量テキスト抽出が必要な場合に使用
  - 画像・表のスタイル情報は抽出しない（テキストのみ）
  - 依存パッケージが少なく、常に利用可能
"""
from __future__ import annotations

from pathlib import Path

from .base import ExtractionResult, ExtractorBackend


class PyPDFBackend(ExtractorBackend):
    """pypdf を使用した軽量テキスト抽出バックエンド"""

    def extract(
        self,
        pdf_path: Path,
        output_dir: Path,
        **options,
    ) -> ExtractionResult:
        """
        pypdf で PDF からテキストを抽出し、Markdown 形式で保存する。

        Args:
            pdf_path: 入力 PDF ファイルのパス
            output_dir: 出力先ディレクトリ（extracted/論文名/）
        """
        try:
            import pypdf
        except ImportError as e:
            raise ImportError(
                "pypdf がインストールされていません。\n"
                "pip install pypdf を実行してください。"
            ) from e

        print(f"[pypdf] テキスト抽出を開始します: {pdf_path.name}")

        reader = pypdf.PdfReader(str(pdf_path))

        lines: list[str] = []

        # メタデータを先頭に付加
        meta = reader.metadata
        if meta:
            title = meta.get('/Title', '')
            author = meta.get('/Author', '')
            if title:
                lines.append(f"# {title}")
            if author:
                lines.append(f"**著者:** {author}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # ページごとにテキストを抽出
        for i, page in enumerate(reader.pages):
            lines.append(f"## ページ {i + 1}")
            text = page.extract_text()
            if text:
                lines.append(text.strip())
            else:
                lines.append("*(テキストを抽出できませんでした)*")
            lines.append("")

        markdown_content = "\n".join(lines)

        # Markdown ファイルを保存
        md_path = output_dir / f"{output_dir.name}.md"
        md_path.write_text(markdown_content, encoding="utf-8")

        print(f"[pypdf] 抽出完了: {md_path}")

        return ExtractionResult(
            markdown=markdown_content,
            images=[],
            table_images=[],
            output_dir=output_dir,
            backend_name="pypdf",
        )
