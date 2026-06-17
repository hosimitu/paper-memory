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

from .config import DEFAULT_LANGUAGE, get_language_name
import json


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


def get_search_rewrite_prompt(query: str) -> str:
    """検索クエリ補正用のプロンプトを返す。"""
    return (
        "You are a search query reformulator for an academic note database. "
        "Given a user query, generate 3 to 5 concise search queries that are likely to match note content. "
        "Prefer explicit technical terms, acronyms, and full-name expansions when they are implied by the query. "
        "Do not invent facts that are not present in the query. "
        "Return ONLY a JSON array of strings. Do not include any reasoning, explanation, markdown, code fences, or extra text. "
        "The output must be valid JSON and must contain only the rewritten queries.\n\n"
        f"User query: {query}"
    )


def _stringify_qa_value(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_qa_context(context) -> str:
    if isinstance(context, str):
        return context

    if not isinstance(context, dict):
        return _stringify_qa_value(context)

    metadata = context.get("metadata", {})
    nodes = context.get("nodes", [])
    edges = context.get("edges", [])

    lines = [
        "## Knowledge Graph Context",
        f"- Query: {_stringify_qa_value(metadata.get('query'))}",
        f"- Search method: {_stringify_qa_value(metadata.get('search_method', 'unknown'))}",
        f"- Link depth: {_stringify_qa_value(metadata.get('link_depth', 0))}",
        f"- Expand same-paper notes: {_stringify_qa_value(metadata.get('expand_paper', False))}",
        "",
        "## Nodes",
    ]

    for node in nodes:
        lines.append(f"[{node.get('citation_id')}] Paper: {node.get('paper_title', 'Unknown Paper')}")
        lines.append(f"  Note type: {node.get('note_type', 'other')}")
        lines.append(f"  Source: {node.get('source_type', 'direct')}")
        lines.append(f"  Depth: {node.get('depth', 0)}")
        if node.get("linked_from_citation_id") is not None:
            lines.append(f"  Linked From: [{node.get('linked_from_citation_id')}]")
        if node.get("same_paper_sources"):
            lines.append(f"  Same paper sources: {', '.join(f'[{cid}]' for cid in node.get('same_paper_sources'))}")
        if node.get("link_reason"):
            lines.append(f"  Link reason: {node.get('link_reason')}")
        lines.append(f"  Content: {_stringify_qa_value(node.get('content', ''))}")
        lines.append(f"  Context: {_stringify_qa_value(node.get('context', ''))}")
        lines.append("")

    if edges:
        lines.extend(["## Relationships"])
        for edge in edges:
            lines.append(
                f"- [{edge.get('from')}] -> [{edge.get('to')}] ({edge.get('relation_type', 'related')}, depth {edge.get('depth', 0)})"
            )
            if edge.get("reason"):
                lines.append(f"  Reason: {edge.get('reason')}")
        lines.append("")

    return "\n".join(lines).strip()


def get_qa_assistant_prompt(context, query_text: str, mode: str = "fact", lang: str = DEFAULT_LANGUAGE) -> str:
    """
    [使用箇所 / Location] paper_memory/server.py -> handle_api_post()
    [用途 / Purpose] ダッシュボードのQA機能で、ノートの内容をもとに回答する / Provide answers based on note contents for the dashboard's QA feature
    """
    context_str = _format_qa_context(context)
    target_language = get_language_name(lang)

    if mode == "insight":
        return f"""You are a research assistant tasked with helping the user solve problems by finding connections and insights across different research notes.
Answer the user's query in {target_language} based on the "Provided Knowledge Notes" below.

## Output Rules (CRITICAL):
1. Immediately before your answer, you MUST output a marker line: "===Answer Start===". Start your actual answer text from the next line.
2. Synthesize the provided notes to find analogies, potential applications, or combinations of methods that could address the user's query.
3. Suggest creative solutions or possibilities (e.g., "The method from Paper A could potentially be applied to solve the issue in Paper B because...") based on the provided notes.
4. While you are encouraged to propose insights, do NOT bring in completely unrelated external facts or general knowledge that is not grounded in the notes. Your hypotheses must be logical extensions of the provided content.
5. Append source citation numbers like [1], [2] to the relevant parts of your answer to show which notes inspired your ideas.
6. Do NOT include a reference list at the end.
7. The provided context is a knowledge graph. Leverage both explicit links and same-paper relations to draw connections.

## Example Output:
(Your thinking process can be placed here)
===Answer Start===
To improve polymer strength, we can consider applying the method described in [2] (which uses carbon nanotubes) to the polymer system in [1]. Since [1] details the synthesis of polyimide, incorporating the functionalization techniques from [2] might enhance tensile strength because...

---
[Provided Knowledge Notes]
{context_str}

[User Query]
{query_text}
"""

    return f"""You are a research assistant.
Answer the user's query in {target_language} based ONLY on the "Provided Knowledge Notes" below.

## Output Rules (CRITICAL):
1. Immediately before your answer, you MUST output a marker line: "===Answer Start===". Start your actual answer text from the next line.
2. NEVER include guesses or general knowledge that is not stated in the provided notes.
3. If the provided information is insufficient to answer the query, output exactly a short phrase meaning "I cannot tell from the provided information" in {target_language}.
4. Append source citation numbers like [1], [2] to the relevant parts of your answer based on the note sources.
5. Do NOT include a reference list at the end.
6. The provided context is a knowledge graph. Treat linked notes as explicitly related context, and treat same-paper nodes as supplementary context from the same paper.
7. When you use a linked or same-paper note, preserve the graph relation in your explanation and cite the source node number(s).

## Example Output:
(Your thinking process can be placed here)
===Answer Start===
(Your answer in {target_language} here)

* Method A: ... [1].
* Method B: ... [2].

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
[
  {{
    "target_id": "Candidate note ID",
    "is_linked": true,
    "reason": {{
      "en": "Brief reason for the link in English (1-2 sentences)",
      "local": "Reason in the local language (1-2 sentences)"
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

def get_rerank_prompt(query: str, items_json: str) -> str:
    """
    [使用箇所 / Location] paper_memory/store.py -> _rerank_with_llm()
    [用途 / Purpose] ハイブリッド検索結果のリランキング（再ランク付け）を行う / Re-rank hybrid search results based on relevance to the query
    """
    return f"""You are an expert at evaluating the relevance of search results for a given query in an academic context.
Given the User Query and a list of Candidate Notes (in JSON format), evaluate how well each candidate answers or relates to the query.
Assign a relevance score from 0 to 100 for each candidate (100 being perfectly relevant, 0 being completely irrelevant).

Output MUST be ONLY a JSON array of objects, containing "id" and "score" for each candidate.
Do NOT include Markdown formatting like ```json.
Example:
[
  {{"id": "note-id-1", "score": 95}},
  {{"id": "note-id-2", "score": 40}}
]

---
User Query:
{query}

Candidate Notes:
{items_json}
"""
