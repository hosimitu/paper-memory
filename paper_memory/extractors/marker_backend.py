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
MarkerBackend — marker-pdf を用いた高精度抽出バックエンド

特徴:
  - LaTeX 数式・複雑なレイアウトを高精度でテキスト化
  - 処理時間が長い（数十分）ため、厳密な抽出が必要な場合のみ使用
  - marker_single コマンドが PATH に存在する必要がある
  - marker-pdf は必要時にユーザーが手動でインストール
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import ExtractionResult, ExtractorBackend


class MarkerBackend(ExtractorBackend):
    """marker-pdf を使用した高精度抽出バックエンド"""

    def extract(
        self,
        pdf_path: Path,
        output_dir: Path,
        light_mode: bool = False,
        **options,
    ) -> ExtractionResult:
        """
        marker-pdf で PDF を高精度解析し、Markdown を生成する。

        Args:
            pdf_path: 入力 PDF ファイルのパス
            output_dir: 出力先ディレクトリ（extracted/論文名/）
            light_mode: True の場合、CPU のみ・OCR なしの軽量モードで実行
        """
        if not shutil.which("marker_single"):
            raise RuntimeError(
                "marker_single コマンドが見つかりません。\n"
                "marker-pdf をインストールしてください: pip install marker-pdf"
            )

        print(f"[marker] 高精度解析を開始します: {pdf_path.name} (light_mode={light_mode})")
        print("[marker] ※ 処理に数十分かかる場合があります。")

        # 一時出力先
        temp_dir = Path("scratch") / "marker_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # marker_single 実行
        import os
        env = os.environ.copy()
        if light_mode:
            env["TORCH_DEVICE"] = "cpu"
            env["OCR_ENGINE"] = "None"
            env["EXTRACT_IMAGES"] = "True"

        cmd = [
            "marker_single",
            str(pdf_path),
            "--output_dir", str(temp_dir),
            "--output_format", "markdown",
        ]
        print(f"[marker] 実行コマンド: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"marker_single が終了コード {result.returncode} で失敗しました。\n"
                f"STDERR: {result.stderr}"
            )

        # marker_single の出力先は temp_dir / pdf_stem / pdf_stem.md
        pdf_stem = pdf_path.stem
        generated_md = temp_dir / pdf_stem / f"{pdf_stem}.md"

        if not generated_md.exists():
            raise RuntimeError(f"marker_single の出力ファイルが見つかりません: {generated_md}")

        # output_dir にコピー
        md_dest = output_dir / f"{output_dir.name}.md"
        shutil.copy2(generated_md, md_dest)

        # 画像もコピー
        saved_images: list[Path] = []
        img_src_dir = temp_dir / pdf_stem / "images"
        if img_src_dir.exists():
            img_dest_dir = output_dir / "images"
            img_dest_dir.mkdir(parents=True, exist_ok=True)
            for img_file in img_src_dir.iterdir():
                if img_file.is_file():
                    dest = img_dest_dir / img_file.name
                    shutil.copy2(img_file, dest)
                    saved_images.append(dest)

        # 一時ファイルの削除
        shutil.rmtree(temp_dir)

        markdown_content = md_dest.read_text(encoding="utf-8")

        print(f"[marker] 抽出完了: {md_dest}")

        return ExtractionResult(
            markdown=markdown_content,
            images=saved_images,
            table_images=[],
            output_dir=output_dir,
            backend_name="marker",
        )
