# -*- coding: utf-8 -*-
"""
Analyzer — Web UI経由でアップロードされた論文の自動解析モジュール
"""
import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

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

def load_state(output_dir: Path) -> dict:
    """状態管理ファイルを読み込む。存在しない場合は初期状態を返す。"""
    state_path = output_dir / "analysis_state.json"
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "status": "new",
        "docling_completed": False,
        "completed_turns": [],
        "partial_notes": [],
        "partial_refs": [],
        "error_message": None,
        "started_at": None,
        "updated_at": None
    }

def save_state(output_dir: Path, state: dict) -> None:
    """状態管理ファイルを保存する。"""
    state_path = output_dir / "analysis_state.json"
    state["updated_at"] = datetime.now().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_analysis_prompt(markdown_text: str, turn_number: int, source_paper_info: dict) -> str:
    """ターン番号に応じた解析プロンプトを構築する"""
    lang_name = get_language_name(DEFAULT_LANGUAGE)
    paper_title = source_paper_info.get("title", "Unknown Title")
    
    # 共通の制約指示
    system_instruction = (
        f"You are a professional research assistant. Analyze the provided research paper markdown and extract academic knowledge notes.\n"
        f"You MUST write all multilingual fields (such as 'content', 'context', 'reason', and 'keywords') in both English ('en') and the user's preferred language, which is {lang_name} ('local').\n"
        f"Ensure all extracted notes are independent and self-contained. Include exact metrics, experimental details, and parameters with units where applicable.\n"
        f"Output ONLY a raw JSON. Do not include markdown code fences, explanations, or introductory text."
    )

    if turn_number == 1:
        return f"""{system_instruction}

[Turn 1 Task]
Extract knowledge elements of the following types:
- `background` (Background, prior work, problems solved)
- `method` (Methodology, design, algorithms, materials, parameters used)
- `definition` (Crucial technical terms or system components defined in the paper)

Output JSON schema:
{{
  "source_paper": {{
    "title": "{paper_title}",
    "authors": {json.dumps(source_paper_info.get("authors", []))},
    "year": {source_paper_info.get("year") or "null"},
    "doi": "{source_paper_info.get("doi", "")}",
    "journal": "{source_paper_info.get("journal", "")}",
    "pdf_path": "{source_paper_info.get("pdf_path", "")}"
  }},
  "notes": [
    {{
      "content": {{
        "en": "English summary of this note.",
        "local": "Summary in {lang_name}."
      }},
      "element_type": "background" | "method" | "definition",
      "keywords": [
        {{ "en": "keyword", "local": "キーワード" }}
      ],
      "context": {{
        "en": "Context description.",
        "local": "Context description in {lang_name}."
      }},
      "tags": ["tag1", "tag2"]
    }}
  ]
}}

Paper markdown:
{markdown_text[:60000]}
"""
    elif turn_number == 2:
        return f"""{system_instruction}

[Turn 2 Task]
Extract knowledge elements of the following types:
- `result` (Experimental results, performance data, comparison metrics)
- `discussion` (Interpretation of results, justifications, why things worked)

Output JSON schema:
{{
  "notes": [
    {{
      "content": {{
        "en": "English summary of this note.",
        "local": "Summary in {lang_name}."
      }},
      "element_type": "result" | "discussion",
      "keywords": [
        {{ "en": "keyword", "local": "キーワード" }}
      ],
      "context": {{
        "en": "Context description.",
        "local": "Context description in {lang_name}."
      }},
      "tags": ["tag1", "tag2"]
    }}
  ]
}}

Paper markdown:
{markdown_text[:60000]}
"""
    else:  # Turn 3
        return f"""{system_instruction}

[Turn 3 Task]
Extract knowledge elements of the following types:
- `conclusion` (Overall findings and take-aways)
- `limitation` (Identified bottlenecks, trade-offs, constraints)
- `future_work` (Suggested directions, open research questions)
- `insight` (Novel ideas, inspirations, or critical perspectives)

Also extract references (reading list) that are central or foundational to the methodology, or directly compared against in the paper.
Exclude casual background literature citations. If no critical references are found, return "references": [].

Output JSON schema:
{{
  "notes": [
    {{
      "content": {{
        "en": "English summary of this note.",
        "local": "Summary in {lang_name}."
      }},
      "element_type": "conclusion" | "limitation" | "future_work" | "insight",
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
{markdown_text[:60000]}
"""

def analyze_paper(
    pdf_path_str: str,
    status_callback: Optional[Callable[[str, str, Optional[dict]], None]] = None,
    resume: bool = False,
    force: bool = False,
) -> dict:
    """PDF抽出、AI分析(3ターン)、DB登録までを一気通貫で実行する"""
    pdf_path = Path(pdf_path_str)
    
    # 論文名の決定
    stem = pdf_path.stem
    safe_stem = stem.encode('ascii', 'ignore').decode('ascii')
    if not safe_stem.strip():
        safe_stem = "paper"
    clean_name = re.sub(r'[^a-zA-Z0-9\s_-]', '', safe_stem).strip().replace(' ', '_')
    if len(clean_name) > 80:
        clean_name = clean_name[:80].rstrip('_')
        
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "extracted" / clean_name
    
    # 状態のロード
    state = load_state(output_dir)
    if force or state.get("status") == "new" or not resume:
        state = {
            "status": "processing",
            "pdf_path": str(pdf_path),
            "docling_completed": False,
            "completed_turns": [],
            "partial_notes": [],
            "partial_refs": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    state["status"] = "processing"
    save_state(output_dir, state)

    try:
        # Step 1: PDF テキスト抽出 (Docling)
        md_file_path = output_dir / f"{clean_name}.md"
        
        if not state["docling_completed"] or not md_file_path.exists():
            if status_callback:
                status_callback("extracting", "PDFからテキストと図表の抽出を実行中（これには数分かかる場合があります）...", None)
            
            # extractを実行
            result = extract(
                pdf_path=pdf_path,
                backend="docling",
                analyze_tables=False,
                base_dir="extracted"
            )
            state["docling_completed"] = True
            save_state(output_dir, state)
        
        markdown_text = md_file_path.read_text(encoding="utf-8")
        
        # タイトル・著者等の初期情報抽出
        # 暫定的にファイル名から推定、または最初の1000文字から推測する
        source_paper_info = {
            "title": stem.replace('_', ' ').replace('-', ' '),
            "authors": [],
            "year": None,
            "doi": "",
            "journal": "",
            "pdf_path": f"pdf/{pdf_path.name}"
        }

        # 3ターンのループ
        for turn in [1, 2, 3]:
            if turn in state["completed_turns"]:
                continue
                
            if status_callback:
                status_callback(f"turn_{turn}", f"AI解析ステップ {turn}/3 を実行中...", {"completed_turns": state["completed_turns"]})
            
            prompt = get_analysis_prompt(markdown_text, turn, source_paper_info)
            response = generate_content_with_retry(model=ANALYSIS_MODEL, contents=prompt, max_retries=2)
            
            if not response or not response.text:
                raise RuntimeError(f"AIからの応答が空です (Turn {turn})")
                
            parsed = _extract_json(response.text)
            if not parsed:
                raise RuntimeError(f"AIの出力をJSONとしてパースできませんでした (Turn {turn})")
            
            # 各ターンの結果を状態にマージ
            if turn == 1:
                # 論文書誌情報を更新
                if "source_paper" in parsed:
                    sp = parsed["source_paper"]
                    for k in ["title", "authors", "year", "doi", "journal"]:
                        if k in sp and sp[k]:
                            source_paper_info[k] = sp[k]
                if "notes" in parsed:
                    state["partial_notes"].extend(parsed["notes"])
            elif turn == 2:
                if "notes" in parsed:
                    state["partial_notes"].extend(parsed["notes"])
            elif turn == 3:
                if "notes" in parsed:
                    state["partial_notes"].extend(parsed["notes"])
                if "references" in parsed:
                    state["partial_refs"].extend(parsed["references"])
            
            state["completed_turns"].append(turn)
            save_state(output_dir, state)

        # 全てのAI解析が完了したらDB登録
        if status_callback:
            status_callback("registering", "データベースへノートおよび参考文献を登録中...", {"completed_turns": state["completed_turns"]})

        store = NoteStore()
        ref_store = ReferenceStore()

        # DOIの自動補完 (もしDOIがなければ)
        if source_paper_info.get("title") and not source_paper_info.get("doi"):
            try:
                doi = fetch_doi_by_title_and_authors(
                    source_paper_info["title"],
                    source_paper_info.get("authors"),
                    source_paper_info.get("year")
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
                        raw_ref["title"],
                        raw_ref.get("authors"),
                        raw_ref.get("year")
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
        save_state(output_dir, state)

        # 自動リンク評価のトリガー
        try:
            # autolink
            from .autolinker import evaluate_links
            # 登録された各ノートを周辺候補と自動リンク
            for note in added_notes:
                candidates = store.find_neighbors(note.id, n=10)
                if candidates:
                    evaluations = evaluate_links(note.to_dict(), candidates)
                    for ev in evaluations:
                        if ev.get("is_linked"):
                            store.add_link(note.id, ev.get("target_id"), ev.get("reason", ""))
        except Exception:
            pass # autolink失敗は処理全体を落とさない

        return {
            "status": "success",
            "paper_title": source_paper_info["title"],
            "notes_count": len(added_notes),
            "refs_count": added_refs_count
        }

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        state["status"] = "error"
        state["error_message"] = error_msg
        save_state(output_dir, state)
        raise e
