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
ストレージ管理 — SQLite永続化 + ChromaDBベクトル検索

ノートのCRUD操作、セマンティック検索、リンク管理を担当する。
"""

import ast
import json
import os
import sys
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from .note import PaperNote, SourcePaper, normalize_reason
from .database import Database
from .ai_models import EMBEDDING_MODEL, SEARCH_REWRITE_MODEL
from .prompts import get_search_rewrite_prompt


class NoteStore:
    """
    論文ノートのストレージ管理クラス

    - SQLiteによる永続化 (database.py経由)
    - ChromaDBへのベクトル登録・検索
    """

    def __init__(self, base_dir: str = "."):
        """
        Args:
            base_dir: プロジェクトルートディレクトリ
        """
        self.base_dir = Path(base_dir)
        
        self.db = Database(str(self.base_dir / "paper_memory.db"))
        self.db.initialize()

    # ========================================
    # DB <-> Object マッピング
    # ========================================

    def _parse_maybe_json(self, val):
        if not val:
            return ""
        try:
            if isinstance(val, str) and val.strip().startswith(('{', '[')):
                return json.loads(val)
        except:
            pass
        return val

    def _row_to_note(self, row) -> PaperNote:
        """DB の Row を PaperNote オブジェクトに変換"""
        sp = SourcePaper(
            title=row["title"],
            authors=json.loads(row["authors"]) if row["authors"] else [],
            year=row["year"],
            doi=row["doi"] or "",
            journal=row["journal"] or "",
            pdf_path=row["pdf_path"] or ""
        )
        
        # リンク先の取得
        links = []
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT target_id FROM note_links WHERE source_id = ?", (row["id"],))
            links = [r["target_id"] for r in cur.fetchall()]
            
        note = PaperNote(
            id=row["id"],
            content=self._parse_maybe_json(row["content"]),
            source_paper=sp,
            element_type=row["element_type"],
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            context=self._parse_maybe_json(row["context"]),
            tags=json.loads(row["tags"]) if row["tags"] else [],
            links=links,
            timestamp=row["timestamp"],
            last_accessed=row["last_accessed"] or "",
            evolution_history=json.loads(row["evolution_history"]) if row["evolution_history"] else [],
            retrieval_count=row["retrieval_count"] or 0
        )
        return note

    def _save_note(self, note: PaperNote) -> None:
        """PaperNote オブジェクトを DB に保存 (UPSERT)"""
        # source_paper が SourcePaper オブジェクトでない場合の防衛処理
        if not isinstance(note.source_paper, SourcePaper):
            if isinstance(note.source_paper, dict):
                note.source_paper = SourcePaper.from_dict(note.source_paper)
            elif isinstance(note.source_paper, str):
                note.source_paper = SourcePaper(title=note.source_paper)
            else:
                note.source_paper = SourcePaper()

        note.evolution_history = [
            {
                **event,
                "reason": normalize_reason(event.get("reason", ""))
            } if isinstance(event, dict) else event
            for event in note.evolution_history
        ]

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            sp = note.source_paper
            title = sp.title if sp.title else "Unknown Paper"
            
            cur.execute("""
            INSERT INTO papers (title, authors, year, doi, journal, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                authors=excluded.authors,
                year=excluded.year,
                doi=excluded.doi,
                journal=excluded.journal,
                pdf_path=excluded.pdf_path
            """, (
                title,
                json.dumps(sp.authors, ensure_ascii=False),
                sp.year,
                sp.doi,
                sp.journal,
                sp.pdf_path
            ))
            
            cur.execute("SELECT id FROM papers WHERE title = ?", (title,))
            paper_id = cur.fetchone()["id"]
            
            save_content = json.dumps(note.content, ensure_ascii=False) if not isinstance(note.content, str) else note.content
            save_context = json.dumps(note.context, ensure_ascii=False) if not isinstance(note.context, str) else note.context
            
            cur.execute("""
            INSERT INTO notes (id, content, paper_id, element_type, keywords, context, tags, timestamp, last_accessed, retrieval_count, evolution_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                paper_id=excluded.paper_id,
                element_type=excluded.element_type,
                keywords=excluded.keywords,
                context=excluded.context,
                tags=excluded.tags,
                timestamp=excluded.timestamp,
                last_accessed=excluded.last_accessed,
                retrieval_count=excluded.retrieval_count,
                evolution_history=excluded.evolution_history
            """, (
                note.id,
                save_content,
                paper_id,
                note.element_type,
                json.dumps(note.keywords, ensure_ascii=False),
                save_context,
                json.dumps(note.tags, ensure_ascii=False),
                note.timestamp,
                note.last_accessed,
                note.retrieval_count,
                json.dumps(note.evolution_history, ensure_ascii=False)
            ))
            
            # リンクの同期（既存を削除して再登録）
            cur.execute("DELETE FROM note_links WHERE source_id = ?", (note.id,))
            for target_id in note.links:
                reason = ""
                created_at = datetime.now().isoformat()
                for event in reversed(note.evolution_history):
                    if event.get("action") == "link_added" and event.get("target_id") == target_id:
                        reason = event.get("reason", "")
                        created_at = event.get("timestamp", created_at)
                        break
                # 多言語対応: reason が dict 等の場合は JSON 文字列として保存
                save_reason = reason
                if not isinstance(reason, str):
                    save_reason = json.dumps(reason, ensure_ascii=False)

                cur.execute("""
                INSERT INTO note_links (source_id, target_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                """, (note.id, target_id, save_reason, created_at))
            conn.commit()

    def _index_note(self, note: PaperNote, search_text: str = None) -> None:
        """ノートを全文検索およびベクトル検索のインデックスに登録"""
        if not search_text:
            search_text = self._build_search_text(note)
        
        from .gemini_client import embed_content_with_retry
        try:
            embeddings = embed_content_with_retry(
                model=EMBEDDING_MODEL,
                contents=[search_text],
                task_type="RETRIEVAL_DOCUMENT"
            )
            embedding = embeddings[0] if embeddings else None
        except Exception as e:
            print(f"⚠️ Embeddings API エラー: {e}", file=sys.stderr)
            embedding = None

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            
            # FTS5 へ登録
            cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note.id,))
            cur.execute("""
            INSERT INTO notes_fts(note_id, search_text)
            VALUES (?, ?)
            """, (note.id, search_text))
            
            # note_vectors (sqlite-vec) へ登録
            if embedding:
                cur.execute("SELECT rowid FROM notes WHERE id = ?", (note.id,))
                row = cur.fetchone()
                if row:
                    note_rowid = row["rowid"]
                    try:
                        import sqlite_vec
                        emb_bytes = sqlite_vec.serialize_float32(embedding)
                        cur.execute("DELETE FROM note_vectors WHERE rowid = ?", (note_rowid,))
                        cur.execute("""
                        INSERT INTO note_vectors(rowid, embedding)
                        VALUES (?, ?)
                        """, (note_rowid, emb_bytes))
                    except ImportError:
                        pass
                    except Exception as e:
                        print(f"⚠️ sqlite-vec への登録をスキップしました: {e}", file=sys.stderr)
            conn.commit()

    # ========================================
    # CRUD操作
    # ========================================

    def add(self, note: PaperNote) -> PaperNote:
        """ノートを追加・保存"""
        self._save_note(note)
        self._index_note(note)
        return note

    def add_batch(self, notes: list[PaperNote]) -> list[PaperNote]:
        """複数ノートを一括追加"""
        from .gemini_client import embed_content_with_retry
        
        for note in notes:
            self._save_note(note)
            
        search_texts = [self._build_search_text(note) for note in notes]
        try:
            embeddings = embed_content_with_retry(
                model=EMBEDDING_MODEL,
                contents=search_texts,
                task_type="RETRIEVAL_DOCUMENT"
            )
        except Exception as e:
            print(f"⚠️ Batch Embeddings API エラー: {e}", file=sys.stderr)
            embeddings = [None] * len(notes)
            
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            for note, search_text, emb in zip(notes, search_texts, embeddings):
                cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note.id,))
                cur.execute("""
                INSERT INTO notes_fts(note_id, search_text)
                VALUES (?, ?)
                """, (note.id, search_text))
                
                if emb:
                    cur.execute("SELECT rowid FROM notes WHERE id = ?", (note.id,))
                    row = cur.fetchone()
                    if row:
                        note_rowid = row["rowid"]
                        try:
                            import sqlite_vec
                            emb_bytes = sqlite_vec.serialize_float32(emb)
                            cur.execute("DELETE FROM note_vectors WHERE rowid = ?", (note_rowid,))
                            cur.execute("""
                            INSERT INTO note_vectors(rowid, embedding)
                            VALUES (?, ?)
                            """, (note_rowid, emb_bytes))
                        except Exception:
                            pass
            conn.commit()
            
        return notes

    def get(self, note_id: str) -> Optional[PaperNote]:
        """IDでノートを取得"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT n.*, p.title, p.authors, p.year, p.doi, p.journal, p.pdf_path
            FROM notes n
            JOIN papers p ON n.paper_id = p.id
            WHERE n.id = ?
            """, (note_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            note = self._row_to_note(row)
            note.record_access()
            self._save_note(note)
            return note

    def update(self, note: PaperNote) -> PaperNote:
        """ノートを更新"""
        self._save_note(note)
        self._index_note(note)
        return note

    def delete(self, note_id: str) -> bool:
        """ノートを削除"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT rowid FROM notes WHERE id = ?", (note_id,))
            row = cur.fetchone()
            if not row:
                return False
            note_rowid = row["rowid"]
            
            cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
            cur.execute("DELETE FROM note_vectors WHERE rowid = ?", (note_rowid,))
            conn.commit()
            
        return True

    def add_link(self, source_id: str, target_id: str, reason: str = "") -> bool:
        """指定したノート間にリンクを追加する"""
        source = self.get(source_id)
        if not source:
            return False
            
        target = self.get(target_id)
        if not target:
            return False
            
        source.add_link(target_id, reason)
        self.update(source)
        return True

    def remove_link(self, source_id: str, target_id: str) -> bool:
        """指定したノート間のリンクを削除する"""
        source = self.get(source_id)
        if not source:
            return False
            
        source.remove_link(target_id)
        self.update(source)
        return True

    def _delete_extracted_markdown(self, pdf_path_str: str, title: str) -> None:
        import shutil
        extracted_dir = self.base_dir / "extracted"
        if not extracted_dir.exists():
            return
            
        target_dir = None
        if pdf_path_str:
            stem = Path(pdf_path_str).stem
            safe_stem = stem.encode('ascii', 'ignore').decode('ascii')
            if not safe_stem.strip():
                safe_stem = "paper"
            clean_name = re.sub(r'[^a-zA-Z0-9\s_-]', '', safe_stem).strip().replace(' ', '_')
            if len(clean_name) > 80:
                clean_name = clean_name[:80].rstrip('_')
            
            candidate = extracted_dir / clean_name
            if candidate.exists() and candidate.is_dir():
                target_dir = candidate
                
        if not target_dir and title:
            alphanum_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
            if alphanum_title:
                search_term = alphanum_title[:30]
                for d in extracted_dir.iterdir():
                    if d.is_dir():
                        alphanum_dir = re.sub(r'[^a-zA-Z0-9]', '', d.name).lower()
                        if search_term in alphanum_dir:
                            target_dir = d
                            break
                            
        if target_dir and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                print(f"⚠️ 抽出済みMarkdownフォルダの削除に失敗しました {target_dir}: {e}", file=sys.stderr)

    def delete_paper(self, paper_id: int) -> dict:
        """論文とその全ノート、抽出済みテキストを一括削除"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("SELECT title, pdf_path FROM papers WHERE id = ?", (paper_id,))
            paper_row = cur.fetchone()
            if not paper_row:
                return {"deleted_notes": 0, "deleted_paper": False}
                
            title = paper_row["title"]
            pdf_path = paper_row["pdf_path"]
            
            cur.execute("SELECT id FROM notes WHERE paper_id = ?", (paper_id,))
            note_ids = [r["id"] for r in cur.fetchall()]
            
            # FTS5 and note_vectors delete
            if note_ids:
                placeholders = ','.join('?' * len(note_ids))
                cur.execute(f"DELETE FROM notes_fts WHERE note_id IN ({placeholders})", note_ids)
                # We also need rowids for note_vectors
                cur.execute("SELECT rowid FROM notes WHERE paper_id = ?", (paper_id,))
                note_rowids = [r["rowid"] for r in cur.fetchall()]
                if note_rowids:
                    rowid_placeholders = ','.join('?' * len(note_rowids))
                    cur.execute(f"DELETE FROM note_vectors WHERE rowid IN ({rowid_placeholders})", note_rowids)
            
            cur.execute("DELETE FROM notes WHERE paper_id = ?", (paper_id,))
            cur.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            conn.commit()

                    
        self._delete_extracted_markdown(pdf_path, title)
        
        return {"deleted_notes": len(note_ids), "deleted_paper": True}

    def list_all(self) -> list[PaperNote]:
        """全ノートを返す"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT n.*, p.title, p.authors, p.year, p.doi, p.journal, p.pdf_path
            FROM notes n
            JOIN papers p ON n.paper_id = p.id
            """)
            return [self._row_to_note(r) for r in cur.fetchall()]

    def list_by_paper(self, paper_title: str) -> list[PaperNote]:
        """論文タイトルでフィルタ"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT n.*, p.title, p.authors, p.year, p.doi, p.journal, p.pdf_path
            FROM notes n
            JOIN papers p ON n.paper_id = p.id
            WHERE LOWER(p.title) LIKE ?
            """, (f"%{paper_title.lower()}%",))
            return [self._row_to_note(r) for r in cur.fetchall()]

    def list_by_paper_id(self, paper_id: int) -> list[PaperNote]:
        """論文IDでフィルタ"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT n.*, p.title, p.authors, p.year, p.doi, p.journal, p.pdf_path
            FROM notes n
            JOIN papers p ON n.paper_id = p.id
            WHERE n.paper_id = ?
            """, (paper_id,))
            return [self._row_to_note(r) for r in cur.fetchall()]

    def list_by_type(self, element_type: str) -> list[PaperNote]:
        """要素タイプでフィルタ"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT n.*, p.title, p.authors, p.year, p.doi, p.journal, p.pdf_path
            FROM notes n
            JOIN papers p ON n.paper_id = p.id
            WHERE n.element_type = ?
            """, (element_type,))
            return [self._row_to_note(r) for r in cur.fetchall()]

    def get_stats(self) -> dict:
        """統計情報を取得"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM notes")
            total_notes = cur.fetchone()["c"]
            
            cur.execute("SELECT COUNT(*) as c FROM papers")
            total_papers = cur.fetchone()["c"]
            
            cur.execute("SELECT COUNT(*) as c FROM note_links")
            total_links = cur.fetchone()["c"]
            
            cur.execute("SELECT element_type, COUNT(*) as c FROM notes GROUP BY element_type")
            type_distribution = {r["element_type"]: r["c"] for r in cur.fetchall()}
            
        return {
            "total_notes": total_notes,
            "total_papers": total_papers,
            "total_links": total_links,
            "type_distribution": type_distribution,
        }

    # ========================================
    # QA履歴管理
    # ========================================

    def add_qa_history(self, query: str, answer: str, references: list, threshold: float, search_method: str = "vector", link_depth: int = 1, expand_paper: bool = False, n: int = 15, rewritten_queries: Optional[list[str]] = None, output_file: Optional[str] = None) -> None:
        """QAのやり取りを履歴に保存する"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO qa_history (query, answer, references_json, threshold, timestamp, search_method, link_depth, expand_paper, n, rewritten_query, output_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query,
                answer,
                json.dumps(references, ensure_ascii=False),
                threshold,
                datetime.now().isoformat(),
                search_method,
                link_depth,
                1 if expand_paper else 0,
                n,
                json.dumps(rewritten_queries or [], ensure_ascii=False),
                output_file,
            ))
            
            conn.commit()

    def get_qa_history(self, limit: int = 10, offset: int = 0) -> list[dict]:
        """QA履歴を新しい順に取得する"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM qa_history ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cur.fetchall()
            
            history = []
            for row in rows:
                rewritten_query_value = row["rewritten_query"] if "rewritten_query" in row.keys() else None
                rewritten_queries = []
                if rewritten_query_value:
                    try:
                        parsed = json.loads(rewritten_query_value)
                        if isinstance(parsed, list):
                            rewritten_queries = [str(q).strip() for q in parsed if str(q).strip()]
                        else:
                            rewritten_queries = [str(rewritten_query_value).strip()] if str(rewritten_query_value).strip() else []
                    except Exception:
                        rewritten_queries = [str(rewritten_query_value).strip()] if str(rewritten_query_value).strip() else []

                history.append({
                    "id": row["id"],
                    "query": row["query"],
                    "answer": row["answer"],
                    "references": json.loads(row["references_json"]) if row["references_json"] else [],
                    "threshold": row["threshold"],
                    "timestamp": row["timestamp"],
                    "search_method": row["search_method"] if "search_method" in row.keys() else "vector",
                    "link_depth": row["link_depth"] if "link_depth" in row.keys() else 1,
                    "expand_paper": bool(row["expand_paper"]) if "expand_paper" in row.keys() else False,
                    "n": row["n"] if "n" in row.keys() else 15,
                    "rewritten_queries": rewritten_queries,
                    "output_file": row["output_file"] if "output_file" in row.keys() else None,
                })
            return history

    def clear_qa_history(self) -> None:
        """QA履歴を全削除する"""
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM qa_history")
            conn.commit()

    def delete_qa_history_item(self, history_id: int) -> bool:
        """指定されたIDのQA履歴を削除する"""
        with self.db.get_connection() as conn:
            cur = conn.execute("DELETE FROM qa_history WHERE id = ?", (history_id,))
            conn.commit()
            return cur.rowcount > 0

    # ========================================
    # セマンティック検索（ChromaDB）
    # ========================================

    def _parse_rewrite_candidates(self, raw_text: str) -> list[str]:
        cleaned = raw_text.strip()
        if not cleaned:
            return []

        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        def _normalize_candidates(parsed):
            if isinstance(parsed, list):
                return [str(q).strip() for q in parsed if str(q).strip()]
            if isinstance(parsed, str) and parsed.strip():
                return [parsed.strip()]
            return []

        parsed = None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(cleaned)
                break
            except Exception:
                parsed = None

        normalized = _normalize_candidates(parsed)
        if normalized:
            return normalized

        bracket_candidates = []
        for match in re.finditer(r'\[[\s\S]*?\]', cleaned):
            candidate_text = match.group(0)
            try:
                parsed_candidate = json.loads(candidate_text)
            except Exception:
                try:
                    parsed_candidate = ast.literal_eval(candidate_text)
                except Exception:
                    continue
            normalized_candidate = _normalize_candidates(parsed_candidate)
            if normalized_candidate:
                bracket_candidates.append(normalized_candidate)

        if bracket_candidates:
            return bracket_candidates[0]

        candidates = []
        for token in re.split(r'[\n,;]+', cleaned):
            token = token.strip()
            if not token:
                continue
            token = re.sub(r'^[\-\*\d\.\)\s]+', '', token)
            token = token.strip().strip('"').strip("'")
            if token and token not in candidates:
                candidates.append(token)

        return candidates

    def _rewrite_ambiguous_query(self, query: str) -> list[str]:
        if not query:
            return []

        try:
            from .gemini_client import generate_content_with_retry
            prompt = get_search_rewrite_prompt(query)
            response = generate_content_with_retry(
                model=SEARCH_REWRITE_MODEL,
                contents=prompt
            )
            if not response:
                return []
            raw_text = response.text.strip()
            return self._parse_rewrite_candidates(raw_text)
        except Exception as e:
            print(f"⚠️ クエリ補正に失敗しました: {e}", file=sys.stderr)
            return []

    def _hybrid_search(self, query: str, n_results: int, element_type_filter: Optional[str] = None) -> list[dict]:
        """FTS5 と sqlite-vec によるハイブリッド検索を行い RRF で統合"""
        from .gemini_client import embed_content_with_retry
        
        # 1. Generate query embedding
        try:
            embeddings = embed_content_with_retry(
                model=EMBEDDING_MODEL,
                contents=[query],
                task_type="RETRIEVAL_QUERY"
            )
            query_emb = embeddings[0] if embeddings else None
        except Exception as e:
            print(f"⚠️ Query Embeddings API エラー: {e}", file=sys.stderr)
            query_emb = None

        vec_ranks = {}
        fts_ranks = {}
        
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            
            type_condition = ""
            # Wrap query in double quotes to prevent FTS5 syntax errors with reserved keywords
            escaped_query = query.replace('"', '""')
            fts_query = f'"{escaped_query}"'
            params_fts = [fts_query]
            if element_type_filter:
                type_condition = "AND n.element_type = ?"
                params_fts.append(element_type_filter)
                
            # FTS5 Search (Ranked)
            cur.execute(f"""
                SELECT f.note_id
                FROM notes_fts f
                JOIN notes n ON n.id = f.note_id
                WHERE notes_fts MATCH ? {type_condition}
                ORDER BY rank
                LIMIT 50
            """, params_fts)
            for i, row in enumerate(cur.fetchall()):
                fts_ranks[row["note_id"]] = i + 1

            # Vector Search (sqlite-vec)
            if query_emb:
                try:
                    import sqlite_vec
                    query_emb_bytes = sqlite_vec.serialize_float32(query_emb)
                    
                    if element_type_filter:
                        # Vector search with filter
                        cur.execute("""
                            SELECT n.id
                            FROM note_vectors v
                            JOIN notes n ON n.rowid = v.rowid
                            WHERE v.embedding MATCH ? AND v.k = 50 AND n.element_type = ?
                            ORDER BY v.distance
                        """, (query_emb_bytes, element_type_filter))
                    else:
                        cur.execute("""
                            SELECT n.id
                            FROM note_vectors v
                            JOIN notes n ON n.rowid = v.rowid
                            WHERE v.embedding MATCH ? AND v.k = 50
                            ORDER BY v.distance
                        """, (query_emb_bytes,))
                        
                    for i, row in enumerate(cur.fetchall()):
                        vec_ranks[row["id"]] = i + 1
                except Exception as e:
                    print(f"⚠️ sqlite-vec 検索エラー: {e}", file=sys.stderr)

        # RRF (Reciprocal Rank Fusion) Calculation
        k = 60
        combined_scores = {}
        all_ids = set(fts_ranks.keys()).union(set(vec_ranks.keys()))
        for note_id in all_ids:
            score = 0.0
            if note_id in fts_ranks:
                score += 1.0 / (k + fts_ranks[note_id])
            if note_id in vec_ranks:
                score += 1.0 / (k + vec_ranks[note_id])
            combined_scores[note_id] = score

        # Sort by RRF score descending
        sorted_ids = sorted(combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True)
        top_candidates = sorted_ids[:max(n_results * 3, 30)] # Fetch more for reranking
        
        # Load notes
        results = []
        for note_id in top_candidates:
            note = self.get(note_id)
            if note:
                results.append({
                    "note": note.to_dict(),
                    "distance": None, # Distance is replaced by score later
                    "rrf_score": combined_scores[note_id]
                })
                
        return results

    def _rerank_with_llm(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """Gemini 3.1 Flash Lite を用いて検索結果をリランキングする"""
        if not candidates:
            return []
            
        from .gemini_client import generate_content_with_retry
        from .ai_models import RERANK_MODEL
        from .prompts import get_rerank_prompt
        
        # Prepare minimal JSON for LLM to save tokens
        items_for_llm = []
        for c in candidates:
            n = c["note"]
            items_for_llm.append({
                "id": n["id"],
                "content": str(n.get("content", ""))[:500], # truncate to fit
                "context": str(n.get("context", ""))[:200]
            })
            
        prompt = get_rerank_prompt(query, json.dumps(items_for_llm, ensure_ascii=False))
        try:
            response = generate_content_with_retry(
                model=RERANK_MODEL,
                contents=prompt
            )
            if not response or not response.text:
                return candidates[:top_k]
                
            # Parse LLM response
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            scored_items = json.loads(raw_text)
            
            score_map = {str(item["id"]): float(item.get("score", 0)) for item in scored_items if "id" in item}
            
            # Update scores and sort
            for c in candidates:
                nid = str(c["note"]["id"])
                # Fallback to RRF relative score if LLM missed it
                c["llm_score"] = score_map.get(nid, 0.0)
                
            candidates.sort(key=lambda x: x.get("llm_score", 0.0), reverse=True)
            return candidates[:top_k]
            
        except Exception as e:
            print(f"⚠️ リランキングに失敗しました: {e}", file=sys.stderr)
            return candidates[:top_k]

    def search(
        self,
        query: str,
        n_results: int = 10,
        element_type_filter: Optional[str] = None,
        distance_threshold: Optional[float] = None,
        rewritten_queries: Optional[list[str]] = None,
        use_ai_rewrite: bool = False,
    ) -> dict:
        if rewritten_queries is None:
            rewritten_queries = self._rewrite_ambiguous_query(query) if use_ai_rewrite else []
        elif not use_ai_rewrite:
            rewritten_queries = []

        query_candidates = [query]
        if rewritten_queries:
            query_candidates = list(dict.fromkeys([query, *rewritten_queries]))
            
        all_candidates = []
        for q in query_candidates:
            # 1次検索: ハイブリッド検索(RRF)
            res = self._hybrid_search(q, n_results, element_type_filter)
            for r in res:
                if not any(c["note"]["id"] == r["note"]["id"] for c in all_candidates):
                    all_candidates.append(r)
                    
        # 2次検索: LLM リランキング
        final_results = self._rerank_with_llm(query, all_candidates, n_results)

        if not final_results:
            print(f"ℹ️ セマンティック検索でヒットしなかったため、キーワード検索に切り替えます: {query}", file=sys.stderr)
            return {"results": self._keyword_search(query, n_results), "method": "keyword", "rewritten_queries": rewritten_queries}

        return {"results": final_results, "method": "hybrid", "rewritten_queries": rewritten_queries}

    def _keyword_search(self, query: str, n_results: int = 5) -> list[dict]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            escaped_query = query.replace('"', '""')
            fts_query = f'"{escaped_query}"'
            cur.execute("""
                SELECT f.note_id
                FROM notes_fts f
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, n_results))
            results = []
            for row in cur.fetchall():
                note = self.get(row["note_id"])
                if note:
                    results.append({"note": note.to_dict(), "distance": None})
            return results


    def find_neighbors(
        self,
        note_id: str,
        n_results: int = 5,
        element_type_filter: Optional[str] = None
    ) -> list[dict]:
        """指定したノートに類似するノートをベクトル検索で探す"""
        note = self.get(note_id)
        if not note:
            return []

        results = []
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    SELECT v.rowid, v.embedding
                    FROM note_vectors v
                    JOIN notes n ON n.rowid = v.rowid
                    WHERE n.id = ?
                """, (note_id,))
                row = cur.fetchone()
                
                if row and row["embedding"]:
                    emb_bytes = row["embedding"]
                    
                    if element_type_filter:
                        cur.execute("""
                            SELECT n.id, v.distance
                            FROM note_vectors v
                            JOIN notes n ON n.rowid = v.rowid
                            WHERE v.embedding MATCH ? AND v.k = ? AND n.element_type = ? AND n.id != ?
                            ORDER BY v.distance
                        """, (emb_bytes, n_results + 5, element_type_filter, note_id))
                    else:
                        cur.execute("""
                            SELECT n.id, v.distance
                            FROM note_vectors v
                            JOIN notes n ON n.rowid = v.rowid
                            WHERE v.embedding MATCH ? AND v.k = ? AND n.id != ?
                            ORDER BY v.distance
                        """, (emb_bytes, n_results + 5, note_id))
                        
                    for r in cur.fetchall():
                        neighbor = self.get(r["id"])
                        if neighbor:
                            results.append({
                                "note": neighbor.to_dict(),
                                "distance": r["distance"]
                            })
                            if len(results) >= n_results:
                                break
        except Exception as e:
            print(f"⚠️ sqlite-vec 検索エラー: {e}", file=sys.stderr)
                            
        if not results:
            # Embeddingがない場合は、テキストからLLMで埋め込みを取得して検索
            from .gemini_client import embed_content_with_retry
            search_text = self._build_search_text(note)
            try:
                embeddings = embed_content_with_retry(
                    model=EMBEDDING_MODEL,
                    contents=[search_text],
                    task_type="RETRIEVAL_QUERY"
                )
                if embeddings:
                    query_emb = embeddings[0]
                    import sqlite_vec
                    emb_bytes = sqlite_vec.serialize_float32(query_emb)
                    with self.db.get_connection() as conn:
                        cur = conn.cursor()
                        if element_type_filter:
                            cur.execute("""
                                SELECT n.id, v.distance
                                FROM note_vectors v
                                JOIN notes n ON n.rowid = v.rowid
                                WHERE v.embedding MATCH ? AND v.k = ? AND n.element_type = ? AND n.id != ?
                                ORDER BY v.distance
                            """, (emb_bytes, n_results + 5, element_type_filter, note_id))
                        else:
                            cur.execute("""
                                SELECT n.id, v.distance
                                FROM note_vectors v
                                JOIN notes n ON n.rowid = v.rowid
                                WHERE v.embedding MATCH ? AND v.k = ? AND n.id != ?
                                ORDER BY v.distance
                            """, (emb_bytes, n_results + 5, note_id))
                            
                        for r in cur.fetchall():
                            neighbor = self.get(r["id"])
                            if neighbor:
                                results.append({
                                    "note": neighbor.to_dict(),
                                    "distance": r["distance"]
                                })
                                if len(results) >= n_results:
                                    break
            except Exception as e:
                print(f"⚠️ フォールバック検索エラー: {e}", file=sys.stderr)
                        
        return results

    def _build_search_text(self, note: PaperNote) -> str:
        """ノートの内容から検索用テキストを構築する"""
        parts = []
        if note.source_paper and note.source_paper.title:
            parts.append(f"Title: {note.source_paper.title}")
            if note.source_paper.authors:
                parts.append(f"Authors: {', '.join(str(a) for a in note.source_paper.authors)}")
                
        parts.append(f"Type: {note.element_type}")
        
        if note.keywords:
            parts.append(f"Keywords: {', '.join(str(k) for k in note.keywords)}")
            
        if isinstance(note.content, str):
            parts.append(note.content)
        elif isinstance(note.content, dict):
            for k, v in note.content.items():
                if isinstance(v, str):
                    parts.append(f"{k}: {v}")
                elif isinstance(v, list):
                    parts.append(f"{k}: {', '.join(str(x) for x in v)}")
                    
        return "\n".join(parts)

    def reindex(self, batch_size: int = 50) -> int:
        """既存の全ノートから全文検索およびベクトル検索インデックスを再構築する"""
        notes_list = self.list_all()
        total = len(notes_list)
        count = 0
        import sys
        
        print(f"🔄 {total}件のノートを再インデックスします（バッチサイズ: {batch_size}）...", file=sys.stderr)
        
        # Clear existing indexes
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM notes_fts")
            try:
                conn.execute("DELETE FROM note_vectors")
            except Exception:
                pass
            conn.commit()
            
        for i in range(0, total, batch_size):
            batch = notes_list[i:i + batch_size]
            self.add_batch(batch)
            count += len(batch)
            print(f"✅ {count}/{total} 件完了...", file=sys.stderr)
                
        return count

    def search_with_graph(
        self,
        query: str,
        n_results: int = 10,
        link_depth: int = 1,
        expand_paper: bool = False,
        distance_threshold: Optional[float] = None,
        element_type_filter: Optional[str] = None,
        max_total: int = 100,
        use_ai_rewrite: bool = False,
    ) -> dict:
        if link_depth <= 0 and not expand_paper:
            base_results = self.search(
                query, n_results,
                element_type_filter=element_type_filter,
                distance_threshold=distance_threshold,
                use_ai_rewrite=use_ai_rewrite,
            )
            for r in base_results["results"]:
                r["source"] = "direct"
                r["depth"] = 0
            base_results["graph_stats"] = {
                "direct_hits": len(base_results["results"]),
                "linked_notes": 0,
                "paper_expanded": 0,
            }
            return base_results

        base_results = self.search(
            query, n_results,
            element_type_filter=element_type_filter,
            distance_threshold=distance_threshold,
            use_ai_rewrite=use_ai_rewrite,
        )
        rewritten_queries = base_results.get("rewritten_queries", [])
        method = base_results["method"]

        from typing import Dict, List
        seen: Dict[str, dict] = {}
        output: List[dict] = []

        for r in base_results["results"]:
            note_id = r["note"]["id"]
            entry = {
                "note": r["note"],
                "distance": r["distance"],
                "source": "direct",
                "depth": 0,
                "linked_from": None,
                "link_reason": None,
            }
            seen[note_id] = entry
            output.append(entry)

        if link_depth > 0:
            frontier = [(r["note"]["id"], 0) for r in base_results["results"]]
            visited = set(seen.keys())

            for current_depth in range(1, link_depth + 1):
                if len(output) >= max_total:
                    break

                next_frontier = []
                for parent_id, _ in frontier:
                    if len(output) >= max_total:
                        break

                    linked_ids_with_reasons = self._get_linked_ids_with_reasons(parent_id)

                    for linked_id, reason in linked_ids_with_reasons:
                        if linked_id in visited or len(output) >= max_total:
                            continue
                        visited.add(linked_id)

                        linked_note = self.get(linked_id)
                        if not linked_note:
                            continue

                        entry = {
                            "note": linked_note.to_dict(),
                            "distance": None,
                            "source": "linked",
                            "depth": current_depth,
                            "linked_from": parent_id,
                            "link_reason": reason,
                        }
                        seen[linked_id] = entry
                        output.append(entry)
                        next_frontier.append((linked_id, current_depth))

                frontier = next_frontier

        paper_expanded_count = 0
        if expand_paper and len(output) < max_total:
            paper_titles = set()
            for r in base_results["results"]:
                sp = r["note"].get("source_paper", {})
                title = sp.get("title", "")
                if title and title != "Unknown Paper":
                    paper_titles.add(title)

            for title in paper_titles:
                if len(output) >= max_total:
                    break
                paper_notes = self.list_by_paper(title)
                for pn in paper_notes:
                    if pn.id in seen or len(output) >= max_total:
                        continue
                    entry = {
                        "note": pn.to_dict(),
                        "distance": None,
                        "source": "paper_expand",
                        "depth": 0,
                        "linked_from": None,
                        "link_reason": None,
                    }
                    seen[pn.id] = entry
                    output.append(entry)
                    paper_expanded_count += 1

        direct_count = sum(1 for r in output if r["source"] == "direct")
        linked_count = sum(1 for r in output if r["source"] == "linked")

        return {
            "results": output,
            "method": method,
            "rewritten_queries": rewritten_queries,
            "graph_stats": {
                "direct_hits": direct_count,
                "linked_notes": linked_count,
                "paper_expanded": paper_expanded_count,
            },
        }

    def _get_linked_ids_with_reasons(self, note_id: str) -> list[tuple]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT target_id, reason
                FROM note_links
                WHERE source_id = ?
            """, (note_id,))
            
            results = {}
            for row in cur.fetchall():
                target_id = row["target_id"]
                reason = row["reason"]
                if target_id not in results:
                    results[target_id] = (target_id, reason)
                else:
                    if reason and not results[target_id][1]:
                        results[target_id] = (target_id, reason)
                        
            return list(results.values())
