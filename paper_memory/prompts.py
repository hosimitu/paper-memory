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
Prompts — AI用プロンプトの一元管理モジュール / Centralized prompt management module for AI
"""

def get_table_fix_prompt(table_md: str) -> str:
    """
    [使用箇所 / Location] scripts/extract_pdf.py -> fix_table_with_llm()
    [用途 / Purpose] PDFから抽出した崩れたMarkdown表をLLMで修復するためのプロンプト / Prompt to repair broken Markdown tables extracted from PDFs using LLM
    """
    return f"""The following Markdown table was extracted from a PDF, but cell merges (especially vertical merges) were not processed correctly. Multiple values are crammed into single cells separated by '<br>', causing the layout to break.

Please reconstruct this table into a properly split, flat Markdown table.
- If multiple values are combined with '<br>', split them into appropriate rows and columns.
- Fix any missing headers or misaligned columns.
- Strictly follow the Markdown table format (e.g., |---|---|).
- Output ONLY the fixed Markdown table. Do not include any other explanations or greetings.

Original broken table:
{table_md}
"""

def get_qa_assistant_prompt(context_str: str, query_text: str, lang: str = "ja") -> str:
    """
    [使用箇所 / Location] paper_memory/server.py -> handle_api_post()
    [用途 / Purpose] ダッシュボードのQA機能で、ノートの内容をもとに回答する / Provide answers based on note contents for the dashboard's QA feature
    """
    if lang == "en":
        return f"""You are a research assistant.
Answer the user's query in English based ONLY on the "Provided Knowledge Notes" below.

## Output Rules (CRITICAL):
1. Immediately before your answer, you MUST output a marker line: "===Answer Start===". Start your actual answer text from the next line.
2. NEVER include guesses or general knowledge that is not stated in the provided notes.
3. If the provided information is insufficient to answer the query, output exactly: "I cannot tell from the provided information."
4. Append source citation numbers like [1], [2] to the relevant parts of your answer based on the note sources.
5. Do NOT include a reference list at the end.

## Example Output:
(Your thinking process can be placed here)
===Answer Start===
Based on the provided information, the answer is as follows.

* Method A: Thin film processing using XX is possible [1].
* Method B: By using YY... [2].

---
[Provided Knowledge Notes]
{context_str}

[User Query]
{query_text}
"""
    else:
        return f"""You are a research assistant.
Answer the user's query in Japanese based ONLY on the "Provided Knowledge Notes" below.

## Output Rules (CRITICAL):
1. Immediately before your answer, you MUST output a marker line: "===回答開始===" (===Answer Start===). Start your actual answer text from the next line.
2. NEVER include guesses or general knowledge that is not stated in the provided notes.
3. If the provided information is insufficient to answer the query, output exactly: "提供された情報からは分かりません" (I cannot tell from the provided information).
4. Append source citation numbers like [1], [2] to the relevant parts of your answer based on the note sources.
5. Do NOT include a reference list at the end.

## Example Output:
(Your thinking process can be placed here)
===回答開始===
提供された情報に基づく回答は以下の通りです。

* 手法A: 〇〇による薄膜化が可能です [1]。
* 手法B: △△を用いることで... [2]。

---
[Provided Knowledge Notes]
{context_str}

[User Query]
{query_text}
"""

def get_autolink_prompt(target_json: str, candidates_json: str) -> str:
    """
    [使用箇所 / Location] paper_memory/autolinker.py -> evaluate_links()
    [用途 / Purpose] ノート間の意味的な繋がりを評価し、リンク候補を抽出する / Evaluate semantic connections between notes and extract link candidates
    """
    return f"""You are an assistant for building links in a Zettelkasten-style academic research database.
Read the "Target Note" and the list of potential "Candidate Notes" below. Identify candidate notes that have a meaningful or logical connection (e.g., complement, conflict, premise, application) with the target note.
Do not just match keywords; prioritize whether connecting these two notes generates new insights or context.

Output MUST be ONLY a JSON array following the schema below (Do NOT include Markdown formatting like ```json).
[
  {{
    "target_id": "Candidate note ID",
    "is_linked": true,
    "reason": {{
      "en": "Brief reason for the link in English (1-2 sentences)",
      "ja": "関連する理由（日本語で、簡潔に1〜2文で）"
    }}
  }}
]
If there is no connection, set `is_linked` to false. You MUST return an array with the exact same number of elements as there are candidate notes.

---
Target Note:
{target_json}

Candidate Notes List:
{candidates_json}
"""


def get_table_image_analysis_prompt() -> str:
    """
    [使用箇所 / Location] paper_memory/extractors/docling_backend.py -> _analyze_table_images()
    [用途 / Purpose] PDFから抽出した表の画像を LLM で解析し、構造化 Markdown 表に変換する / Analyze table images extracted from PDFs using LLM and convert them into structured Markdown tables
    """
    return """This image is a table extracted from an academic research paper PDF.
Carefully analyze the image and accurately convert the table contents into Markdown table format.

## Critical Rules (Highest Priority):
- NEVER miss the "negative sign (-)" in exponents of powers or units.
  - Example: Accurately write `s⁻¹` or `s^-1` as `s<sup>-1</sup>`.
  - Example: Write `10⁻³` as `10<sup>-3</sup>`.
- Accurately transcribe numerical signs, decimal points, and scientific notation (10^n).

## Basic Rules:
- Accurately identify the header row of the table.
- Precisely transcribe the text inside cells (including numbers, units, superscripts, and subscripts).
- Represent subscripts (e.g., ₂ in CO₂) using `<sub>2</sub>` and superscripts using `<sup>a</sup>`.
- Properly expand merged cells (vertical and horizontal) and convert them into a flat table.
- Escape any `|` characters found inside cell content as `\\|`.
- Strictly follow the Markdown table format (`| --- |`).
- Output ONLY the converted Markdown table. Do not include any explanations or greetings.
"""

def get_formula_image_analysis_prompt() -> str:
    """
    [使用箇所 / Location] paper_memory/extractors/docling_backend.py -> _analyze_formula_images()
    [用途 / Purpose] PDFから抽出した数式の画像を LLM で解析し、LaTeX形式（Markdown内）に変換する / Analyze formula images extracted from PDFs using LLM and convert them into LaTeX format (within Markdown)
    """
    return r"""This image is a mathematical or chemical formula extracted from a research paper.
Carefully analyze the image and accurately convert it into LaTeX format.

## Rules:
- Output the formula as a Markdown equation using the `$$ ... $$` or `$ ... $` format.
- For chemical equations, accurately reproduce arrows (\rightarrow, \leftrightarrow), sub/superscripts, and charges (^+, -).
- Use standard LaTeX notation wherever possible.
- Output ONLY the converted formula. Do not include any explanations or greetings.
"""
