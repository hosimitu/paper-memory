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
Prompts — AI用プロンプトの一元管理モジュール
"""

def get_table_fix_prompt(table_md: str) -> str:
    """
    [使用箇所] scripts/extract_pdf.py -> fix_table_with_llm()
    [用途] PDFから抽出した崩れたMarkdown表をLLMで修復するためのプロンプト
    """
    return f"""以下のMarkdown表は、PDFから抽出された際にセル結合（特に縦方向のマージ）が正しく処理されず、
1つのセル内に複数の値が '<br>' で詰め込まれてレイアウトが崩れています。

この表を、正しく列が分割されたフラットなMarkdown表として再構築してください。
- 複数の値が '<br>' で結合されている場合は、適切な行と列に分割してください。
- 欠落しているヘッダーや列のズレがあれば修正してください。
- マークダウンの表の形式（|---|---|）を厳密に守ってください。
- 修正後のMarkdown表「のみ」を出力してください。それ以外の挨拶や説明は一切不要です。

元の崩れた表:
{table_md}
"""

def get_qa_assistant_prompt(context_str: str, query_text: str) -> str:
    """
    [使用箇所] paper_memory/server.py -> handle_api_post()
    [用途] ダッシュボードのQA機能で、ノートの内容をもとに回答する
    """
    return f"""あなたは研究を支援するアシスタントです。
以下の「提供された知識ノート」のみを情報源として、ユーザーの質問に日本語で回答してください。

## 出力ルール（重要）:
1. 回答の直前に必ず「===回答開始===」というマーカーを1行で出力し、その次の行から実際の回答本文を書き始めてください。
2. 知識ノートに記載されていない推測や一般的な知識は、絶対に含めないでください。
3. 提供された情報で回答できない場合は、「提供された情報からは分かりません」と回答してください。
4. 回答文の中に、根拠となる情報源の番号を [1] のように付与してください。
5. 末尾に文献リストを含めないでください。

## 出力例:
（ここに思考プロセスがあっても構いません）
===回答開始===
提供された情報に基づく回答は以下の通りです。

* 手法A: 〇〇による薄膜化が可能です [1]。
* 手法B: △△を用いることで... [2]。

---
[提供された知識ノート]
{context_str}

[ユーザーの質問]
{query_text}
"""

def get_autolink_prompt(target_json: str, candidates_json: str) -> str:
    """
    [使用箇所] paper_memory/autolinker.py -> evaluate_links()
    [用途] ノート間の意味的な繋がりを評価し、リンク候補を抽出する
    """
    return f"""あなたは学術論文の知識データベースにおける「Zettelkasten」のリンク構築アシスタントです。
以下の「ターゲットノート」と、関連する可能性のある「候補ノート」のリストを読み、
意味的・論理的な繋がり（補完、対立、前提、応用など）がある候補ノートを特定してください。
単なるキーワードの一致ではなく、「この2つを繋ぐことで新たな知見や文脈が生まれるか」を重視してください。

出力は以下のJSONスキーマに従う配列（リスト）のみを出力してください（Markdownの```jsonなどの修飾は不要です）。
[
  {{
    "target_id": "候補ノートのID",
    "is_linked": true,
    "reason": "関連する理由（日本語で、簡潔に1〜2文で）"
  }}
]
関連がない場合は is_linked を false にしてください。必ず候補ノートの数と同じ要素数の配列を返してください。

---
ターゲットノート:
{target_json}

候補ノートリスト:
{candidates_json}
"""


def get_table_image_analysis_prompt() -> str:
    """
    [使用箇所] paper_memory/extractors/docling_backend.py -> _analyze_table_images()
    [用途] PDFから抽出した表の画像を LLM で解析し、構造化 Markdown 表に変換する
    """
    return """この画像は研究論文のPDFから抽出した表（テーブル）です。
画像を注意深く解析し、表の内容を正確な Markdown 表形式に変換してください。

## 重要ルール（最優先）:
- べき乗の指数部や単位に含まれる「負の符号（-）」を絶対に見落とさないでください。
  - 例: `s⁻¹` や `s^-1` は `s<sup>-1</sup>` と正確に記述する。
  - 例: `10⁻³` は `10<sup>-3</sup>` と記述する。
- 数値の符号、小数点の位置、指数表記（10^n）を正確に転写してください。

## 基本ルール:
- 表のヘッダー行を正確に特定してください。
- セル内のテキストを正確に転写してください（数値、単位、上付き・下付き文字を含む）。
- 下付き文字（例: CO₂ の ₂）は `<sub>2</sub>` 形式、上付き文字は `<sup>a</sup>` 形式で表現してください。
- 結合セル（縦・横）は適切に展開し、フラットな表に変換してください。
- `|` を含むセル内容は `\\|` とエスケープしてください。
- Markdown 表の形式（`| --- |`）を厳密に守ってください。
- 変換後の Markdown 表「のみ」を出力してください。説明文や挨拶は一切不要です。
"""

def get_formula_image_analysis_prompt() -> str:
    """
    [使用箇所] paper_memory/extractors/docling_backend.py -> _analyze_formula_images()
    [用途] PDFから抽出した数式の画像を LLM で解析し、LaTeX形式（Markdown内）に変換する
    """
    return r"""この画像は研究論文から抽出された数式（または化学反応式）です。
画像を注意深く解析し、正確な LaTeX 形式に変換してください。

## ルール:
- 出力は `$$ ... $$` または `$ ... $` 形式の Markdown 数式として出力してください。
- 化学反応式の場合、矢印（\rightarrow, \leftrightarrow）や、上下付き文字、電荷（^+, -）を正確に再現してください。
- 可能な限り、標準的な LaTeX 記法を使用してください。
- 変換後の数式「のみ」を出力してください。説明文や挨拶は一切不要です。
"""
