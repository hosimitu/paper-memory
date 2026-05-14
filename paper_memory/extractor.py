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
Extractor — PDF抽出の共通エントリーポイント

バックエンドを選択し、extract() で一貫したインターフェースを提供する。

バックエンド優先順位:
  1. docling（デフォルト）: 図・表の画像化、表画像 LLM 解析に対応
  2. pypdf（--use-pypdf）:  軽量テキスト抽出。docling 失敗時のフォールバック
  3. marker（--use-marker）: 高精度・低速。LaTeX 数式・複雑レイアウト向け

使用例 (CLI):
    python -m paper_memory extract "pdf/paper.pdf"
    python -m paper_memory extract "pdf/paper.pdf" --analyze-tables
    python -m paper_memory extract "pdf/paper.pdf" --use-pypdf
    python -m paper_memory extract "pdf/paper.pdf" --use-marker --light

使用例 (Python):
    from paper_memory.extractor import extract
    result = extract("pdf/paper.pdf", backend="docling", analyze_tables=True)
    print(result.markdown[:200])
"""
from __future__ import annotations

import sys
from pathlib import Path

from .extractors.base import ExtractionResult, ExtractorBackend


def extract(
    pdf_path: str | Path,
    backend: str = "docling",
    analyze_tables: bool = False,
    light_mode: bool = False,
    base_dir: str = "extracted",
    **options,
) -> ExtractionResult:
    """
    PDF を解析し、Markdown + 画像を extracted/ に出力する。

    Args:
        pdf_path:       入力 PDF ファイルのパス
        backend:        使用するバックエンド ("docling" / "pypdf" / "marker")
        analyze_tables: True の場合、docling バックエンドで表画像を LLM 解析する
        light_mode:     marker バックエンド使用時に CPU のみ・OCR なしで実行
        base_dir:       出力先のベースディレクトリ（デフォルト: "extracted"）

    Returns:
        ExtractionResult: 抽出結果（markdown, images, table_images, output_dir）

    Raises:
        FileNotFoundError: PDF ファイルが見つからない場合
        ImportError: 必要なライブラリがインストールされていない場合
        RuntimeError: 抽出処理に失敗した場合
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF ファイルが見つかりません: {pdf_path}")

    # バックエンドの選択
    extractor = _get_backend(backend)

    # 出力先ディレクトリの準備（extracted/論文名/）
    output_dir = extractor.prepare_output_dir(pdf_path, base_dir)

    # 抽出実行
    if backend == "docling":
        return extractor.extract(
            pdf_path,
            output_dir,
            analyze_tables=analyze_tables,
            **options,
        )
    elif backend == "marker":
        return extractor.extract(
            pdf_path,
            output_dir,
            light_mode=light_mode,
            **options,
        )
    else:
        return extractor.extract(pdf_path, output_dir, **options)


def _get_backend(backend: str) -> ExtractorBackend:
    """バックエンド名からバックエンドインスタンスを返す"""
    if backend == "docling":
        from .extractors.docling_backend import DoclingBackend
        return DoclingBackend()
    elif backend == "pypdf":
        from .extractors.pypdf_backend import PyPDFBackend
        return PyPDFBackend()
    elif backend == "marker":
        from .extractors.marker_backend import MarkerBackend
        return MarkerBackend()
    else:
        raise ValueError(
            f"不明なバックエンドです: '{backend}'\n"
            "使用可能なバックエンド: docling / pypdf / marker"
        )


def main_extract(args) -> None:
    """
    __main__.py の extract サブコマンドから呼び出されるエントリーポイント。

    Args:
        args: argparse.Namespace（pdf_path, use_pypdf, use_marker, analyze_tables, light, base_dir）
    """
    # バックエンド選択
    if args.use_marker:
        backend = "marker"
    elif args.use_pypdf:
        backend = "pypdf"
    else:
        backend = "docling"

    print(f"\n📄 PDF 解析を開始します")
    print(f"  ファイル    : {args.pdf_path}")
    print(f"  バックエンド: {backend}")
    if backend == "docling" and args.analyze_tables:
        print(f"  表画像解析  : 有効 (LLM)")

    try:
        result = extract(
            pdf_path=args.pdf_path,
            backend=backend,
            analyze_tables=getattr(args, "analyze_tables", False),
            light_mode=getattr(args, "light", False),
            base_dir=getattr(args, "base_dir", "extracted"),
        )

        print(f"\n✅ 解析完了！")
        print(f"  出力先     : {result.output_dir.absolute()}")
        print(f"  画像数     : {len(result.images)} 枚")
        if result.table_images:
            print(f"  表画像数   : {len(result.table_images)} 枚（LLM 解析済み）")

    except FileNotFoundError as e:
        print(f"\n❌ エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except ImportError as e:
        print(f"\n❌ ライブラリエラー: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n❌ 実行エラー: {e}", file=sys.stderr)
        sys.exit(1)
