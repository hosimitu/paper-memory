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
Base — 抽出バックエンドの共通データ構造と抽象基底クラス
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractionResult:
    """PDF抽出結果の共通データ構造"""
    markdown: str
    """抽出された Markdown テキスト"""
    images: list[Path] = field(default_factory=list)
    """保存された図画像ファイル一覧（figures）"""
    table_images: list[Path] = field(default_factory=list)
    """保存された表画像ファイル一覧（LLM解析用）"""
    output_dir: Path | None = None
    """出力先ディレクトリ（extracted/論文名/）"""
    backend_name: str = ""
    """使用したバックエンド名（docling / pypdf / marker）"""


class ExtractorBackend(ABC):
    """PDF抽出バックエンドの抽象基底クラス"""

    @abstractmethod
    def extract(self, pdf_path: Path, output_dir: Path, **options) -> ExtractionResult:
        """PDFを解析し、Markdown + 画像を出力する"""
        ...

    def prepare_output_dir(self, pdf_path: Path, base_dir: str = "extracted") -> Path:
        """
        extracted/ 配下に論文名ベースの出力ディレクトリを作成する。
        PDFファイル名から安全なディレクトリ名を生成する（非ASCII文字は削除）。
        """
        # 1. 拡張子を除いたファイル名を取得
        stem = pdf_path.stem
        # 2. 非ASCII文字を除去（互換性のため）
        safe_stem = stem.encode('ascii', 'ignore').decode('ascii')
        if not safe_stem.strip():
            # もし全て非ASCIIだった場合は fallback
            safe_stem = "paper"
        # 3. 記号を削除し、スペースをアンダースコアに置換
        clean_name = re.sub(r'[^a-zA-Z0-9\s_-]', '', safe_stem).strip().replace(' ', '_')
        # 4. 長すぎる場合は切り詰め（Windows MAX_PATH 考慮）
        if len(clean_name) > 80:
            clean_name = clean_name[:80].rstrip('_')
        
        output_dir = Path(base_dir) / clean_name
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "images").mkdir(parents=True, exist_ok=True)
        return output_dir
