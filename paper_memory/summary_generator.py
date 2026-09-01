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


def _yaml_tag_value(value: str) -> str:
    val_str = str(value or "").strip()
    if ":" in val_str or "#" in val_str:
        return _yaml_quote(val_str)
    return val_str


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


def _format_reason(reason_val) -> str:
    if not reason_val:
        return ""
    if isinstance(reason_val, dict):
        return (
            reason_val.get("ja")
            or reason_val.get("local")
            or reason_val.get("en")
            or next(iter(reason_val.values()), "")
        )
    if isinstance(reason_val, str):
        cleaned = reason_val.strip()
        if cleaned.startswith(("{", "[")):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return (
                        parsed.get("ja")
                        or parsed.get("local")
                        or parsed.get("en")
                        or next(iter(parsed.values()), "")
                    )
            except Exception:
                pass
        return reason_val
    return str(reason_val)


def _format_relevance_badge(relevance: str) -> str:
    rel = (relevance or "").lower()
    if rel == "high":
        return "🔴 high"
    elif rel == "medium":
        return "🟡 medium"
    elif rel == "low":
        return "⚪ low"
    return f"⚪ {relevance or 'unspecified'}"


def _fetch_references_for_paper(project_root: Path, paper: dict) -> list[dict]:
    db_path = project_root / "paper_memory.db"
    if not db_path.exists():
        return []

    title = (paper.get("title") or "").strip()
    pdf_path = (paper.get("pdf_path") or "").strip()
    if not title and not pdf_path:
        return []

    query = """
    SELECT id, title, authors, year, doi, journal, cited_by, cited_by_pdf, relevance, reason, keywords
    FROM references_table
    WHERE (cited_by != '' AND LOWER(cited_by) = LOWER(?))
       OR (cited_by_pdf != '' AND LOWER(cited_by_pdf) = LOWER(?))
    ORDER BY 
        CASE LOWER(relevance)
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 3
            ELSE 4
        END,
        created_at ASC
    """
    try:
        import sqlite3

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (title, pdf_path)).fetchall()

            if not rows and (title or pdf_path):
                alt_query = """
                SELECT id, title, authors, year, doi, journal, cited_by, cited_by_pdf, relevance, reason, keywords
                FROM references_table
                WHERE (? != '' AND LOWER(cited_by) LIKE '%' || LOWER(?) || '%')
                   OR (? != '' AND LOWER(cited_by_pdf) LIKE '%' || LOWER(?) || '%')
                ORDER BY 
                    CASE LOWER(relevance)
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                    END,
                    created_at ASC
                """
                pdf_name = Path(pdf_path).name if pdf_path else ""
                rows = conn.execute(
                    alt_query, (title, title, pdf_name, pdf_name)
                ).fetchall()

            return [dict(r) for r in rows]
    except Exception:
        return []


def _build_next_papers_section(
    references: list[dict], generated_next_papers: str = ""
) -> str:
    if not references:
        return generated_next_papers or "（該当する文献なし）"

    lines = []
    for ref in references:
        title = ref.get("title") or "無題"
        doi = ref.get("doi") or ""
        doi_url = _doi_url(doi) if doi else ""
        title_part = f"[{title}]({doi_url})" if doi_url else title

        authors = _authors(ref.get("authors"))
        if len(authors) > 1:
            author_str = f"{authors[0]} et al."
        elif authors:
            author_str = authors[0]
        else:
            author_str = "著者不明"

        year_str = str(ref.get("year") or "")
        meta_str = f" ({author_str}, {year_str})" if year_str else f" ({author_str})"

        relevance_badge = _format_relevance_badge(ref.get("relevance", ""))
        reason = _format_reason(ref.get("reason"))

        lines.append(f"- **{title_part}**{meta_str}")
        lines.append(f"  - **重要度**: {relevance_badge}")
        if reason:
            lines.append(f"  - **選定理由 / 補足**: {reason}")
        else:
            lines.append("  - **選定理由 / 補足**: （本文中での重要参照文献）")

    gen_text = (generated_next_papers or "").strip()
    if gen_text and gen_text != "（該当する文献なし）":
        lines.append("")
        lines.append("### 💡 AIによる補足・今後の読書方針")
        lines.append(gen_text)

    return "\n".join(lines)


def _source_markdown_path(project_root: Path, pdf_path: str, title: str) -> Path | None:
    """Resolve only the extracted source Markdown, never summary.md."""
    from .analyzer import clean_paper_name

    candidates = []
    if pdf_path:
        candidates.append(
            project_root / "extracted" / clean_paper_name(Path(pdf_path).stem)
        )
    if title:
        candidates.append(
            project_root / "extracted" / clean_paper_name(Path(title).stem)
        )
    for directory in candidates:
        source = directory / f"{directory.name}.md"
        if source.is_file():
            return source
    return None


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S
        ).strip()
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


def _render_template(
    meta: dict,
    generated: dict,
    source_text: str,
    pdf_path: str,
    source_md_filename: str,
    is_review: bool,
) -> str:
    now = datetime.datetime.now()
    title = meta.get("title") or "タイトル不明"
    authors = _authors(meta.get("authors"))
    doi = _doi_url(meta.get("doi", ""))
    journal = meta.get("journal", "")
    year = meta.get("year", "")
    author_lines = (
        "\n".join(f"#99_著者名/{a.replace(' ', '_')}" for a in authors)
        or "（著者情報なし）"
    )
    tags = generated.get("tags", [])
    if not isinstance(tags, list):
        tags = [str(tags)]
    tag_lines = (
        "\n".join(f"#03_論文/{str(t).replace(' ', '_')}" for t in tags if t)
        or "#03_論文"
    )
    paper_pdf = pdf_path or ""
    markdown_link = f"[論文Markdown](./{source_md_filename})"
    if is_review:
        body = f"""# {title}
        
## 📰文献の Markdown
{markdown_link}
        
## 🇯🇵このレビューの要点
{generated.get("key_points", "（生成結果なし）")}

## 📝レビューの範囲と目的
{generated.get("scope_purpose", "（生成結果なし）")}

## 📚主要なトピックと議論
{generated.get("topics", "（生成結果なし）")}

## 🔍著者らが示す今後の展望や課題
{generated.get("future_challenges", "（生成結果なし）")}

## 🎓著者一覧
{author_lines}

## 🏷️タグ
{tag_lines}

## 📌abstracts
{generated.get("abstract_original", "（本文から抽出できませんでした）")}

## 🇯🇵abstracts の日本語訳
{generated.get("abstract_translation", "（生成結果なし）")}
"""
    else:
        body = f"""# {title}
        
## 📰文献の Markdown
{markdown_link}

## 🇯🇵abstracts の日本語訳
{generated.get("abstract_translation", "（生成結果なし）")}

## 💬コメント

## 🤔どんな論文？
{generated.get("what_is_it", "（生成結果なし）")}

## 💡これまでの論文と何が違うか
{generated.get("novelty", "（生成結果なし）")}

## 👓技術や手法のキモはどこ？
{generated.get("key_method", "（生成結果なし）")}

## ⚗どうやって有効だと検証した？
{generated.get("validation", "（生成結果なし）")}

## 🗯議論はある？課題はある？
{generated.get("discussion_limitations", "（生成結果なし）")}

## 🔜次に読むべき論文は？
{generated.get("next_papers", "（該当する文献なし）")}

## 🎓著者一覧
{author_lines}

## 🏷️タグ
{tag_lines}

## 🔎入手経路

## 📌abstracts
{generated.get("abstract_original", "（本文から抽出できませんでした）")}
"""
    return f"""---
title: {_yaml_quote("📜 " + title)}
authors: {_yaml_quote(", ".join(authors))}
journal: {_yaml_quote(journal or str(year))}
tags:
{"".join(f"  - {_yaml_tag_value(str(t))}\n" for t in tags if t)}doi: {_yaml_quote(doi)}
cssclass: ronbun
UID: {now.strftime("%Y%m%d-%H%M%S")}
date: {now.strftime("%Y-%m-%d")}
modified:
---

{body.strip()}
"""


def generate_summary(
    project_root: Path, paper: dict, force: bool = False, progress_callback=None
) -> dict:
    """Generate and save summary.md for one database paper."""
    from .analyzer import clean_paper_name

    source = _source_markdown_path(
        project_root, paper.get("pdf_path", ""), paper.get("title", "")
    )
    if source is None:
        raise FileNotFoundError("抽出済み Markdown が見つかりません")
    summary_path = source.parent / SUMMARY_FILENAME
    if summary_path.exists() and not force:
        return {
            "summary_url": f"/extracted/{source.parent.name}/{SUMMARY_FILENAME}",
            "existing": True,
        }

    if progress_callback:
        progress_callback("generating_summary", "AIによる summary を生成中...")
    source_text = source.read_text(encoding="utf-8")
    # Keep the bundled skill templates as the single documented template source.
    # The renderer supplies project-specific paths and metadata around these sections.
    template_name = (
        "template_review.md"
        if "review" in source_text[:12000].lower()
        else "template.md"
    )
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
    references = _fetch_references_for_paper(project_root, paper)
    db_refs_section = ""
    if references:
        ref_items = []
        for r in references:
            r_title = r.get("title", "")
            r_authors = ", ".join(_authors(r.get("authors")))
            r_year = r.get("year") or ""
            r_doi = r.get("doi") or ""
            r_rel = r.get("relevance") or "medium"
            r_reason = _format_reason(r.get("reason"))
            ref_items.append(
                f"- タイトル: {r_title}\n"
                f"  著者: {r_authors}\n"
                f"  年: {r_year}\n"
                f"  DOI: {r_doi}\n"
                f"  重要度: {r_rel}\n"
                f"  選定理由: {r_reason}"
            )
        db_refs_section = (
            "\nDATABASE REFERENCES (Reading List for this paper):\n"
            + "\n".join(ref_items)
            + "\nFor 'next_papers', reference the above database references and provide concise Japanese commentary on key reading points and their relation to this paper. If no database references are provided, extract candidate recommendations from the markdown text.\n"
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
Tentative metadata: {json.dumps({"title": paper.get("title"), "authors": authors, "year": paper.get("year"), "journal": paper.get("journal"), "doi": paper.get("doi")}, ensure_ascii=False)}
Template selected: {template_name}
Template reference:
{template_text[:12000]}
Translation dictionary:
{dictionary_text}
{db_refs_section}
EXTRACTED MARKDOWN:
{source_text[:200000]}
"""
    response = generate_content_with_retry(
        model=SUMMARY_MODEL, contents=prompt, max_retries=3
    )
    generated = _extract_json(response.text)
    if not generated:
        raise ValueError("AI の summary 応答を JSON として解釈できませんでした")
    if not generated.get("is_review"):
        generated["next_papers"] = _build_next_papers_section(
            references, generated.get("next_papers", "")
        )
    meta = {
        "title": generated.get("title") or paper.get("title"),
        "authors": generated.get("authors") or paper.get("authors"),
        "year": generated.get("year") or paper.get("year"),
        "journal": generated.get("journal") or paper.get("journal"),
        "doi": generated.get("doi") or paper.get("doi"),
    }
    content = _render_template(
        meta,
        generated,
        source_text,
        paper.get("pdf_path", ""),
        source.name,
        bool(generated.get("is_review")),
    )
    summary_path.write_text(content, encoding="utf-8")
    return {
        "summary_url": f"/extracted/{source.parent.name}/{SUMMARY_FILENAME}",
        "existing": False,
    }
