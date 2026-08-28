"""Generate a paper summary Markdown from an extracted paper Markdown file."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from .ai_models import SUMMARY_MODEL
from .config import DEFAULT_LANGUAGE, get_language_name
from .gemini_client import generate_content_with_retry


SUMMARY_FILENAME = "summary.md"
TEMPLATE_DIR = Path(__file__).parent / "summary_resources"


def _json_text(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _yaml_quote(value: str) -> str:
    return '"' + str(value or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _authors(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return _authors(parsed)
    except (TypeError, json.JSONDecodeError):
        return [str(value)]


def _doi_url(doi: str) -> str:
    if not doi:
        return ""
    return doi if str(doi).startswith("http") else f"https://doi.org/{doi}"


def _source_markdown_path(project_root: Path, pdf_path: str, title: str) -> Path | None:
    """Resolve only the extracted source Markdown, never summary.md."""
    from .analyzer import clean_paper_name

    candidates = []
    if pdf_path:
        candidates.append(project_root / "extracted" / clean_paper_name(Path(pdf_path).stem))
    if title:
        candidates.append(project_root / "extracted" / clean_paper_name(Path(title).stem))
    for directory in candidates:
        source = directory / f"{directory.name}.md"
        if source.is_file():
            return source
    return None


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S).strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


def _render_template(meta: dict, generated: dict, source_text: str, pdf_path: str, is_review: bool) -> str:
    now = datetime.datetime.now()
    title = meta.get("title") or "タイトル不明"
    authors = _authors(meta.get("authors"))
    doi = _doi_url(meta.get("doi", ""))
    journal = meta.get("journal", "")
    year = meta.get("year", "")
    author_lines = "\n".join(f"#99_著者名/{a.replace(' ', '_')}" for a in authors) or "（著者情報なし）"
    tags = generated.get("tags", [])
    if not isinstance(tags, list):
        tags = [str(tags)]
    tag_lines = "\n".join(f"#03_論文/{str(t).replace(' ', '_')}" for t in tags if t) or "#03_論文"
    paper_pdf = pdf_path or ""
    if is_review:
        body = f"""## 🇯🇵このレビューの要点
{generated.get('key_points', '（生成結果なし）')}

## 📝レビューの範囲と目的
{generated.get('scope_purpose', '（生成結果なし）')}

## 📚主要なトピックと議論
{generated.get('topics', '（生成結果なし）')}

## 🔍著者らが示す今後の展望や課題
{generated.get('future_challenges', '（生成結果なし）')}

## 🎓著者一覧
{author_lines}

## 🏷️タグ
{tag_lines}

## 📌abstracts
{generated.get('abstract_original', '（本文から抽出できませんでした）')}

## 🇯🇵abstracts の日本語訳
{generated.get('abstract_translation', '（生成結果なし）')}
"""
    else:
        body = f"""## 📰文献の PDF
[論文PDF]({paper_pdf})

## 🇯🇵abstracts の日本語訳
{generated.get('abstract_translation', '（生成結果なし）')}

## 💬コメント

## 🤔どんな論文？
{generated.get('what_is_it', '（生成結果なし）')}

## 💡これまでの論文と何が違うか
{generated.get('novelty', '（生成結果なし）')}

## 👓技術や手法のキモはどこ？
{generated.get('key_method', '（生成結果なし）')}

## ⚗どうやって有効だと検証した？
{generated.get('validation', '（生成結果なし）')}

## 🗯議論はある？課題はある？
{generated.get('discussion_limitations', '（生成結果なし）')}

## 🔜次に読むべき論文は？
{generated.get('next_papers', '（該当する文献なし）')}

## 🎓著者一覧
{author_lines}

## 🏷️タグ
{tag_lines}

## 🔎入手経路

## 📌abstracts
{generated.get('abstract_original', '（本文から抽出できませんでした）')}
"""
    return f"""---
title: {_yaml_quote('📜 ' + title)}
authors: {_yaml_quote(', '.join(authors))}
journal: {_yaml_quote(journal or str(year))}
tags:
{''.join(f'  - {_yaml_quote(str(t))}\n' for t in tags if t)}doi: {_yaml_quote(doi)}
cssclass: ronbun
UID: {now.strftime('%Y%m%d-%H%M%S')}
date: {now.strftime('%Y-%m-%d')}
modified:
---

{body.strip()}
"""


def generate_summary(project_root: Path, paper: dict, force: bool = False, progress_callback=None) -> dict:
    """Generate and save summary.md for one database paper."""
    from .analyzer import clean_paper_name

    source = _source_markdown_path(project_root, paper.get("pdf_path", ""), paper.get("title", ""))
    if source is None:
        raise FileNotFoundError("抽出済み Markdown が見つかりません")
    summary_path = source.parent / SUMMARY_FILENAME
    if summary_path.exists() and not force:
        return {"summary_url": f"/extracted/{source.parent.name}/{SUMMARY_FILENAME}", "existing": True}

    if progress_callback:
        progress_callback("generating_summary", "AIによる summary を生成中...")
    source_text = source.read_text(encoding="utf-8")
    # Keep the bundled skill templates as the single documented template source.
    # The renderer supplies project-specific paths and metadata around these sections.
    template_name = "template_review.md" if "review" in source_text[:12000].lower() else "template.md"
    template_path = TEMPLATE_DIR / template_name
    if not template_path.is_file():
        raise FileNotFoundError(f"summary template が見つかりません: {template_name}")
    template_text = template_path.read_text(encoding="utf-8")
    dictionary_text = (TEMPLATE_DIR / "dictionary.md").read_text(encoding="utf-8")
    from .summary_resources.convert_units import convert
    conversion_examples = (
        f"1 GPU = {convert(1, 'gpu'):.4e} mol/m2skPa; "
        f"1 Barrer = {convert(1, 'barrer'):.4e} molm/m2skPa"
    )
    authors = _authors(paper.get("authors"))
    language = get_language_name(DEFAULT_LANGUAGE)
    prompt = f"""You are a CO2 separation membrane researcher. Analyze the extracted paper Markdown below and produce JSON only.
Use Japanese for all generated prose. Determine whether it is a review paper.
Follow these rules: preserve numeric values and conditions; for Permeance/Permeability values include the original unit and convert using the provided conversion rules; use backticks around ionic-liquid notation such as [TBP][SCN]. Do not invent DOI or references.
Conversion rules (calculated with the bundled convert_units utility): {conversion_examples}.
Return keys: is_review, title, authors, year, journal, doi, abstract_original, abstract_translation, tags,
what_is_it, novelty, key_method, validation, discussion_limitations, next_papers,
key_points, scope_purpose, topics, future_challenges.
For list-like sections, return Markdown text. The default language is {language}.
Tentative metadata: {json.dumps({'title': paper.get('title'), 'authors': authors, 'year': paper.get('year'), 'journal': paper.get('journal'), 'doi': paper.get('doi')}, ensure_ascii=False)}
Template selected: {template_name}
Template reference:
{template_text[:12000]}
Translation dictionary:
{dictionary_text}

EXTRACTED MARKDOWN:
{source_text[:200000]}
"""
    response = generate_content_with_retry(model=SUMMARY_MODEL, contents=prompt, max_retries=1)
    generated = _extract_json(response.text)
    if not generated:
        raise ValueError("AI の summary 応答を JSON として解釈できませんでした")
    meta = {
        "title": generated.get("title") or paper.get("title"),
        "authors": generated.get("authors") or paper.get("authors"),
        "year": generated.get("year") or paper.get("year"),
        "journal": generated.get("journal") or paper.get("journal"),
        "doi": generated.get("doi") or paper.get("doi"),
    }
    content = _render_template(meta, generated, source_text, paper.get("pdf_path", ""), bool(generated.get("is_review")))
    summary_path.write_text(content, encoding="utf-8")
    return {"summary_url": f"/extracted/{source.parent.name}/{SUMMARY_FILENAME}", "existing": False}
