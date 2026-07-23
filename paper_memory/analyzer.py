# -*- coding: utf-8 -*-
"""
Analyzer — Web UI経由でアップロードされた論文の自動解析モジュール
"""

import os
import sys
import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable


def _parse_json_field(value):
    """DB に保存された JSON 文字列を安全にデコードする。"""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text
    return value


from .config import DEFAULT_LANGUAGE, get_language_name
from .ai_models import ANALYSIS_MODEL
from .gemini_client import generate_content_with_retry
from .extractor import extract
from .store import NoteStore
from .note import PaperNote, SourcePaper
from .reference import Reference, ReferenceStore
from .doi_fetcher import fetch_doi_by_title_and_authors


def _extract_json(text: str) -> Optional[dict]:
    """テキストからJSON部分を抽出して辞書としてパースする"""
    text = text.strip()
    # ```json ... ``` または ``` ... ``` を探す
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # {} または [] を探す
        match_brace = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match_brace:
            json_str = match_brace.group(1).strip()
        else:
            json_str = text

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # パースに失敗した場合はNone
        return None


def _normalize_title_key(value: str | None) -> str:
    """タイトル比較用に正規化する。"""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _candidate_keys_from_path(output_dir: Path) -> list[str]:
    """フォルダ名と PDF/Markdown stem から比較用キー候補を生成する。

    NOTE: 個別単語への分割は行わない。フォルダ名・ファイル名の完全正規化キーのみを
    返すことで、単語1つの部分一致による誤マッチを防ぐ。
    """
    keys = []
    raw_names = [output_dir.name]
    for md_path in output_dir.glob("*.md"):
        raw_names.append(md_path.stem)
    for pdf_path in output_dir.glob("*.pdf"):
        raw_names.append(pdf_path.stem)

    for name in raw_names:
        if not name:
            continue
        norm = _normalize_title_key(name)
        if norm:
            keys.append(norm)
    return list(dict.fromkeys([k for k in keys if k]))


# Jaccard類似度の閾値（この値以上で同一論文と判定する）
_JACCARD_THRESHOLD = 0.5


def _word_set_jaccard(text_a: str, text_b: str) -> float:
    """2つの文字列間の単語集合Jaccard類似度を計算する。

    正規化済み文字列（英小文字・数字のみ）を3文字以上のトークンに分割し、
    その積集合 / 和集合で類似度を算出する。

    Args:
        text_a: 比較元の正規化済み文字列
        text_b: 比較先の正規化済み文字列

    Returns:
        0.0〜1.0 の類似度スコア（単語集合が完全一致なら 1.0）
    """
    # 正規化前の生文字列でもトークン分割できるよう、非英数字で分割する
    words_a = set(re.findall(r"[a-z0-9]{3,}", text_a))
    words_b = set(re.findall(r"[a-z0-9]{3,}", text_b))
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union


def _looks_like_same_paper(
    candidates: list[str],
    title_key: str,
    pdf_key: str,
    raw_folder_name: str = "",
    raw_paper_title: str = "",
    raw_pdf_path: str = "",
) -> bool:
    """同一論文と見なせるかを判定する。

    判定基準（いずれかを満たせば True）:
    1. 完全一致: 正規化済みキーが完全に一致する
    2. 前方一致: candidate が title_key / pdf_key の前方部分と一致する
       （フォルダ名がタイトルの先頭部分で切り詰められているケースに対応）
    3. Jaccard類似度: フォルダ名・MDファイル名の単語集合と、論文タイトル・
       PDFパスの単語集合の類似度が _JACCARD_THRESHOLD 以上

    Args:
        candidates:       フォルダ名・ファイル名から生成した正規化済みキーのリスト
        title_key:        DB上の論文タイトルの正規化済みキー
        pdf_key:          DB上のPDFパスの正規化済みキー
        raw_folder_name:  Jaccard計算用の生のフォルダ名（任意）
        raw_paper_title:  Jaccard計算用の生の論文タイトル（任意）
        raw_pdf_path:     Jaccard計算用の生のPDFパス（任意）
    """
    if not candidates:
        return False
    if not title_key and not pdf_key:
        return False

    for candidate in candidates:
        if not candidate:
            continue

        # --- 判定1: 完全一致 ---
        if candidate == title_key or candidate == pdf_key:
            return True

        # --- 判定2: 前方一致（フォルダ名がタイトルの前方部分で切れているケース）---
        # candidate が title_key の前方にある（DB側タイトルが長い）場合に対応
        if title_key and title_key.startswith(candidate) and len(candidate) >= 20:
            return True
        if pdf_key and pdf_key.startswith(candidate) and len(candidate) >= 20:
            return True

    # --- 判定3: Jaccard類似度 ---
    # フォルダ名（または最初の候補）と DB 側タイトル・PDF パスの単語集合を比較する
    # 生のフォルダ名が渡されていない場合は candidates の先頭を使う
    folder_repr = (
        raw_folder_name if raw_folder_name else (candidates[0] if candidates else "")
    )
    for db_repr in filter(None, [raw_paper_title, raw_pdf_path, title_key, pdf_key]):
        score = _word_set_jaccard(folder_repr, db_repr)
        if score >= _JACCARD_THRESHOLD:
            return True

    return False


def _infer_state_from_database(
    output_dir: Path, project_root: Optional[Path] = None
) -> Optional[dict]:
    """analysis_state.json がない場合に SQLite で解析済みかどうかを推定する。"""
    if project_root is None:
        project_root = Path(__file__).parent.parent

    db_path = project_root / "paper_memory.db"
    if not db_path.exists():
        return None

    md_candidates = [p for p in output_dir.glob("*.md") if p.is_file()]
    md_exists = bool(md_candidates)
    candidate_keys = _candidate_keys_from_path(output_dir)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # 【修正点1】JSONで必要となるカラム(authors, year, doi, journal)をSELECT文に明記
        papers = conn.execute(
            "SELECT id, title, pdf_path, authors, year, doi, journal FROM papers"
        ).fetchall()

        matched = None
        raw_folder_name = output_dir.name
        for paper in papers:
            title_key = _normalize_title_key(paper["title"])
            pdf_key = _normalize_title_key(paper["pdf_path"])
            if not _looks_like_same_paper(
                candidate_keys,
                title_key,
                pdf_key,
                raw_folder_name=raw_folder_name,
                raw_paper_title=paper["title"] or "",
                raw_pdf_path=paper["pdf_path"] or "",
            ):
                continue
            matched = paper
            break

        if not matched:
            return None

        paper_id = matched["id"]

        # notesとreferences_tableからレコードを取得（ORDER BYで順序を保証）
        note_rows = conn.execute(
            "SELECT * FROM notes WHERE paper_id = ? ORDER BY timestamp",
            (paper_id,),
        ).fetchall()
        ref_rows = conn.execute(
            "SELECT * FROM references_table WHERE cited_by = ? OR cited_by_pdf = ? ORDER BY created_at",
            (matched["title"], matched["pdf_path"]),
        ).fetchall()

    note_count = len(note_rows)
    ref_count = len(ref_rows)

    # Markdown があっても、DBに成果物（ノートや文献）がなければ未完了とする
    if note_count <= 0 and ref_count <= 0:
        return None

    # 【修正点2】提示されたJSONのネスト構造（en/local）に合わせてマッピング
    partial_notes = []
    for row in note_rows:
        note_payload = {
            "content": _parse_json_field(
                row["content"]
            ),  # 内部で {"en": "...", "local": "..."} を想定
            "element_type": row["element_type"],
            "keywords": _parse_json_field(row["keywords"])
            or [],  # 内部で [{"en": "...", "local": "..."}, ...] を想定
            "context": _parse_json_field(
                row["context"]
            ),  # 内部で {"en": "...", "local": "..."} を想定
            "tags": _parse_json_field(row["tags"]) or [],
            "source_paper": {
                "title": matched["title"],
                "authors": _parse_json_field(matched["authors"]) or [],
                "year": matched["year"],
                "doi": matched["doi"] or "",
                "journal": matched["journal"] or "",
                "pdf_path": matched["pdf_path"] or "",
            },
        }
        partial_notes.append(note_payload)

    # 【修正点3】参考文献リストもJSONの形に合わせて構造化
    partial_refs = []
    for row in ref_rows:
        ref_payload = {
            "title": row["title"],
            "authors": _parse_json_field(row["authors"]) or [],
            "year": row["year"],
            "doi": row["doi"] or "",
            "journal": row["journal"] or "",
            "relevance": row["relevance"],
            "reason": _parse_json_field(
                row["reason"]
            ),  # 内部で {"en": "...", "local": "..."} を想定
            "keywords": _parse_json_field(row["keywords"])
            or [],  # 内部で [{"en": "...", "local": "..."}, ...] を想定
            "cited_by": row["cited_by"] or matched["title"],
            "cited_by_pdf": row["cited_by_pdf"] or matched["pdf_path"],
        }
        partial_refs.append(ref_payload)

    # 【修正点4】目標とするJSONのメタデータ構造（pdf_path等）を最上位に配置
    inferred_state = {
        "status": "completed",
        "pdf_path": matched["pdf_path"] or "",
        "docling_completed": md_exists,
        "completed_turns": [1, 2, 3],
        "partial_notes": partial_notes,
        "partial_refs": partial_refs,
        "error_message": None,
        "started_at": note_rows[0]["timestamp"]
        if note_count > 0
        else None,  # 最初のノート時間から推定
        "updated_at": datetime.now().isoformat(),
        "last_step": "completed",
    }
    return inferred_state


def load_state(output_dir: Path, project_root: Optional[Path] = None) -> dict:
    """状態管理ファイルを読み込む。存在しない場合は DB/Markdown から推定する。"""
    state_path = output_dir / "analysis_state.json"
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                loaded.setdefault("status", "new")
                loaded.setdefault("docling_completed", False)
                loaded.setdefault("completed_turns", [])
                loaded.setdefault("partial_notes", [])
                loaded.setdefault("partial_refs", [])
                loaded.setdefault("error_message", None)
                loaded.setdefault("started_at", None)
                loaded.setdefault("updated_at", None)
                loaded.setdefault("last_step", None)
                return loaded
        except Exception:
            pass

    inferred_state = _infer_state_from_database(output_dir, project_root=project_root)
    if inferred_state is not None:
        save_state(output_dir, inferred_state)
        return inferred_state

    md_exists = False
    if output_dir.exists():
        md_exists = any(p.suffix == ".md" for p in output_dir.iterdir() if p.is_file())

    if md_exists:
        state = {
            "status": "in_progress",
            "docling_completed": True,
            "completed_turns": [],
            "partial_notes": [],
            "partial_refs": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_step": "docling_completed",
        }
        save_state(output_dir, state)
        return state

    return {
        "status": "new",
        "docling_completed": False,
        "completed_turns": [],
        "partial_notes": [],
        "partial_refs": [],
        "error_message": None,
        "started_at": None,
        "updated_at": None,
        "last_step": None,
    }


def save_state(output_dir: Path, state: dict) -> None:
    """状態管理ファイルを保存する。"""
    state_path = output_dir / "analysis_state.json"
    state["updated_at"] = datetime.now().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_analysis_prompt(markdown_text: str, source_paper_info: dict) -> str:
    """全ての知識要素・書誌情報・参考文献を1ターンで抽出するプロンプトを構築する"""
    lang_name = get_language_name(DEFAULT_LANGUAGE)
    paper_title = source_paper_info.get("title", "Unknown Title")

    # 共通の制約指示
    system_instruction = (
        f"You are a professional research assistant. Analyze the provided research paper markdown and extract academic knowledge notes.\n"
        f"This project is a knowledge extraction and organization system based on the Zettelkasten principles (atomicity, linking, evolution).\n"
        f"You MUST write all multilingual fields (such as 'content', 'context', 'reason', and 'keywords') in both English ('en') and the user's preferred language, which is {lang_name} ('local').\n"
        f"Ensure all extracted notes are independent and self-contained. Include exact metrics, experimental details, and parameters with units where applicable.\n"
        f"Output ONLY a raw JSON. Do not include markdown code fences, explanations, or introductory text."
    )

    return f"""{system_instruction}

[Task]
Extract ALL of the following knowledge elements from the paper in a single pass:
- `background` (Background, prior work, problems solved)
- `method` (Methodology, design, algorithms, materials, parameters used)
- `definition` (Crucial technical terms or system components defined in the paper)
- `result` (Experimental results, performance data, comparison metrics)
- `discussion` (Interpretation of results, justifications, why things worked)
- `conclusion` (Overall findings and take-aways)
- `limitation` (Identified bottlenecks, trade-offs, constraints)
- `future_work` (Suggested directions, open research questions)
- `insight` (Novel ideas, inspirations, or critical perspectives)

Also:
1. Extract the accurate bibliographic information of the paper (title, authors, year, doi, journal) from the markdown text.
   The provided tentative title "{paper_title}" might be a filename. Please correct it to the actual title found in the text.
2. Extract references (reading list) that are central or foundational to the methodology, or directly compared against in the paper.
   Exclude casual background literature citations. If no critical references are found, return "references": [].

Output JSON schema:
{{
  "source_paper": {{
    "title": "Exact Title Found in the Paper",
    "authors": ["Author 1", "Author 2"],
    "year": 2023,
    "doi": "10.xxxx/xxxx",
    "journal": "Journal/Conference Name",
    "pdf_path": "{source_paper_info.get("pdf_path", "")}"
  }},
  "notes": [
    {{
      "content": {{
        "en": "English summary of this note.",
        "local": "Summary in {lang_name}."
      }},
      "element_type": "background" | "method" | "definition" | "result" | "discussion" | "conclusion" | "limitation" | "future_work" | "insight",
      "keywords": [
        {{ "en": "keyword", "local": "キーワード" }}
      ],
      "context": {{
        "en": "Context description.",
        "local": "Context description in {lang_name}."
      }},
      "tags": ["tag1", "tag2"]
    }}
  ],
  "references": [
    {{
      "title": "Reference Paper Title",
      "authors": ["Author 1", "Author 2"],
      "year": 2023,
      "doi": "",
      "journal": "Journal Name",
      "relevance": "high" | "medium",
      "reason": {{
        "en": "Reason for inclusion in English.",
        "local": "Reason in {lang_name}."
      }},
      "keywords": [
        {{ "en": "keyword", "local": "キーワード" }}
      ]
    }}
  ]
}}

Paper markdown:
{markdown_text[:200000]}
"""


def analyze_paper(
    pdf_path_str: str,
    status_callback: Optional[Callable[[str, str, Optional[dict]], None]] = None,
    resume: bool = False,
    force: bool = False,
    stop_after_extract: bool = False,
) -> dict:
    """PDF抽出、AI分析（1ターン一括）、DB登録までを一気通貫で実行する"""
    pdf_path = Path(pdf_path_str)

    # 論文名の決定
    stem = pdf_path.stem

    # 【修正】ASCII変換を廃止し、éや各国語を残す設定に変更
    # OSのファイルパスで禁止される記号（\ / : * ? " < > |）のみを排除します
    safe_stem = re.sub(r"[^\w\s_-]", "", stem).strip()
    if not safe_stem:
        safe_stem = "paper"

    # スペースをアンダースコアに統一
    clean_name = safe_stem.replace(" ", "_")
    if len(clean_name) > 80:
        clean_name = clean_name[:80].rstrip("_")

    project_root = Path(__file__).parent.parent
    output_dir = project_root / "extracted" / clean_name

    # 状態のロード
    state = load_state(output_dir)
    if not force and state.get("status") == "completed" and not resume:
        with sqlite3.connect(project_root / "paper_memory.db") as conn:
            conn.row_factory = sqlite3.Row
            paper_row = conn.execute(
                "SELECT title FROM papers WHERE title = ?",
                (state.get("db_paper_title") or "",),
            ).fetchone()
        if paper_row is not None:
            return {
                "status": "success",
                "paper_title": paper_row["title"],
                "notes_count": state.get("db_note_count", 0),
                "refs_count": state.get("db_ref_count", 0),
            }

    if force:
        state = {
            "status": "processing",
            "pdf_path": str(pdf_path),
            "docling_completed": False,
            "completed_turns": [],
            "partial_notes": [],
            "partial_refs": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_step": None,
        }
    elif state.get("status") in {"new", None} or not resume:
        state = {
            "status": "processing",
            "pdf_path": str(pdf_path),
            "docling_completed": False,
            "completed_turns": [],
            "partial_notes": [],
            "partial_refs": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_step": None,
        }

    state["status"] = "processing"
    state.setdefault("partial_notes", [])
    state.setdefault("partial_refs", [])
    state.setdefault("completed_turns", [])
    state.setdefault("docling_completed", False)
    state["pdf_path"] = str(pdf_path)
    if resume and state.get("last_step") is None:
        state["last_step"] = "extracting"
    state["updated_at"] = datetime.now().isoformat()
    save_state(output_dir, state)

    try:
        # Step 1: PDF テキスト抽出 (Docling)
        md_file_path = output_dir / f"{clean_name}.md"

        if not state["docling_completed"] or not md_file_path.exists():
            state["last_step"] = "extracting"
            state["status"] = "processing"
            save_state(output_dir, state)
            if status_callback:
                status_callback(
                    "extracting",
                    "PDFからテキストと図表の抽出を実行中（これには数分かかる場合があります）...",
                    None,
                )

            # extractを実行
            result = extract(
                pdf_path=pdf_path,
                backend="docling",
                analyze_tables=False,
                base_dir="extracted",
                progress_callback=lambda step, msg: (
                    status_callback(step, msg, None) if status_callback else None
                ),
            )
            state["docling_completed"] = True
            state["last_step"] = "extracting_completed"
            save_state(output_dir, state)

        markdown_text = md_file_path.read_text(encoding="utf-8")

        # タイトル・著者等の初期情報抽出
        # 暫定的にファイル名から推定、または最初の1000文字から推測する
        source_paper_info = {
            "title": stem.replace("_", " ").replace("-", " "),
            "authors": [],
            "year": None,
            "doi": "",
            "journal": "",
            "pdf_path": f"pdf/{pdf_path.name}",
        }

        if stop_after_extract:
            state["status"] = "in_progress"
            state["last_step"] = "docling_completed"
            save_state(output_dir, state)
            return {
                "paper_title": source_paper_info["title"],
                "notes_count": 0,
                "refs_count": 0,
            }

        # 1ターン統合解析
        if 1 not in state["completed_turns"]:
            state["last_step"] = "turn_1"
            state["status"] = "processing"
            save_state(output_dir, state)
            if status_callback:
                status_callback(
                    "turn_1",
                    "AI解析（全セクション一括）を実行中...",
                    {"completed_turns": state["completed_turns"]},
                )

            prompt = get_analysis_prompt(markdown_text, source_paper_info)
            response = generate_content_with_retry(
                model=ANALYSIS_MODEL, contents=prompt, max_retries=2
            )

            if not response or not response.text:
                raise RuntimeError("AIからの応答が空です")

            parsed = _extract_json(response.text)
            if not parsed:
                raise RuntimeError("AIの出力をJSONとしてパースできませんでした")

            # 書誌情報を更新
            if "source_paper" in parsed:
                sp = parsed["source_paper"]
                for k in ["title", "authors", "year", "doi", "journal"]:
                    if k in sp and sp[k]:
                        source_paper_info[k] = sp[k]

            # ノートを蓄積
            if "notes" in parsed:
                state["partial_notes"].extend(parsed["notes"])

            # 参考文献を蓄積
            if "references" in parsed:
                state["partial_refs"].extend(parsed["references"])

            state["completed_turns"].append(1)
            state["last_step"] = "turn_1_completed"
            save_state(output_dir, state)

        # 全てのAI解析が完了したらDB登録
        if status_callback:
            status_callback(
                "registering",
                "データベースへノートおよび参考文献を登録中...",
                {"completed_turns": state["completed_turns"]},
            )

        store = NoteStore()
        ref_store = ReferenceStore()

        # DOIの自動補完 (もしDOIがなければ)
        if source_paper_info.get("title") and not source_paper_info.get("doi"):
            try:
                doi = fetch_doi_by_title_and_authors(
                    source_paper_info["title"],
                    source_paper_info.get("authors"),
                    source_paper_info.get("year"),
                )
                if doi:
                    source_paper_info["doi"] = doi
            except Exception:
                pass

        # ノートの追加
        notes_to_add = []
        for raw_note in state["partial_notes"]:
            raw_note["source_paper"] = source_paper_info
            # element_type の整合性をチェック
            note_obj = PaperNote.from_dict(raw_note)
            notes_to_add.append(note_obj)

        added_notes = store.add_batch(notes_to_add)

        # 参考文献の追加
        added_refs_count = 0
        for raw_ref in state["partial_refs"]:
            raw_ref["cited_by"] = source_paper_info["title"]
            raw_ref["cited_by_pdf"] = source_paper_info["pdf_path"]
            # DOI補完
            if raw_ref.get("title") and not raw_ref.get("doi"):
                try:
                    r_doi = fetch_doi_by_title_and_authors(
                        raw_ref["title"], raw_ref.get("authors"), raw_ref.get("year")
                    )
                    if r_doi:
                        raw_ref["doi"] = r_doi
                except Exception:
                    pass
            ref_obj = Reference.from_dict(raw_ref)
            ref_store.add(ref_obj)
            added_refs_count += 1

        # 状態の更新
        state["status"] = "completed"
        state["last_step"] = "completed"
        save_state(output_dir, state)

        # 自動リンク評価のトリガー
        try:
            # autolink
            from .autolinker import evaluate_links

            # 登録された各ノートを周辺候補と自動リンク
            for note in added_notes:
                candidates = store.find_neighbors(note.id, n_results=10)
                if candidates:
                    evaluations = evaluate_links(note.to_dict(), candidates)
                    for ev in evaluations:
                        if ev.get("is_linked"):
                            store.add_link(
                                note.id, ev.get("target_id"), ev.get("reason", "")
                            )
        except Exception as e:
            print(f"[WARNING] 自動リンク生成に失敗しました: {e}", file=sys.stderr)

        return {
            "status": "success",
            "paper_title": source_paper_info["title"],
            "notes_count": len(added_notes),
            "refs_count": added_refs_count,
        }

    except Exception as e:
        import traceback

        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        state["status"] = "error"
        state["error_message"] = error_msg
        state["last_step"] = state.get("last_step") or "error"
        save_state(output_dir, state)
        raise e
