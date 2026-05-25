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

        # ChromaDBクライアント（遅延初期化）
        self._chroma_client = None
        self._chroma_collection = None

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

    # ========================================
    # CRUD操作
    # ========================================

    def add(self, note: PaperNote) -> PaperNote:
        """ノートを追加・保存"""
        self._save_note(note)
        try:
            self._add_to_chroma(note)
        except Exception as e:
            # SQLite には保存されているがインデックスに失敗したことを警告
            print(f"⚠️ Note saved to DB, but indexing failed: {e}", file=sys.stderr)
        return note

    def add_batch(self, notes: list[PaperNote]) -> list[PaperNote]:
        """複数ノートを一括追加"""
        ids = []
        documents = []
        metadatas = []
        
        for note in notes:
            self._save_note(note)
            ids.append(note.id)
            documents.append(self._build_search_text(note))
            metadatas.append({
                "element_type": note.element_type,
                "paper_title": note.source_paper.title,
                "timestamp": note.timestamp,
            })
            
        collection = self._get_chroma_collection()
        if collection:
            try:
                self._upsert_with_retry(
                    collection,
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
            except Exception as e:
                print(f"⚠️ Batch saved to DB, but indexing failed: {e}", file=sys.stderr)
        else:
            print("⚠️ ChromaDB collection is not available for indexing. Vector search will be disabled.", file=sys.stderr)
                
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
        self._update_chroma(note)
        return note

    def delete(self, note_id: str) -> bool:
        """ノートを削除"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            if cur.rowcount == 0:
                return False
            conn.commit()
            
        self._delete_from_chroma(note_id)
        return True

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

    def add_qa_history(self, query: str, answer: str, references: list, threshold: float, search_method: str = "vector", link_depth: int = 1, expand_paper: bool = False, n: int = 15, rewritten_queries: Optional[list[str]] = None) -> None:
        """QAのやり取りを履歴に保存し、10件を超えたら古いものを削除する"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO qa_history (query, answer, references_json, threshold, timestamp, search_method, link_depth, expand_paper, n, rewritten_query)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                import google.generativeai as genai

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return []

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(SEARCH_REWRITE_MODEL)
            response = model.generate_content(get_search_rewrite_prompt(query))
            raw_text = response.text.strip()
            return self._parse_rewrite_candidates(raw_text)
        except Exception as e:
            print(f"⚠️ クエリ補正に失敗しました: {e}", file=sys.stderr)
            return []

    def _collect_vector_results(self, collection, query_texts, n_results, element_type_filter, distance_threshold):
        collected = []
        seen_ids = set()

        for query_text in query_texts:
            query_params = {
                "query_texts": [query_text],
                "n_results": min(n_results, self.get_stats()["total_notes"] or 1),
            }
            if element_type_filter:
                query_params["where"] = {"element_type": element_type_filter}

            results = collection.query(**query_params)
            if not results or not results.get("ids") or not results["ids"][0]:
                continue

            for i, note_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results.get("distances") else None
                if distance_threshold is not None and distance is not None and distance > distance_threshold:
                    continue
                if note_id in seen_ids:
                    continue
                seen_ids.add(note_id)
                note = self.get(note_id)
                if note:
                    collected.append({
                        "note": note.to_dict(),
                        "distance": distance,
                    })

        collected.sort(key=lambda item: item["distance"] if item["distance"] is not None else 1.0)
        return collected[:n_results]

    def search(
        self,
        query: str,
        n_results: int = 10,
        element_type_filter: Optional[str] = None,
        distance_threshold: Optional[float] = None,
        rewritten_queries: Optional[list[str]] = None,
        use_ai_rewrite: bool = True,
    ) -> dict:
        """
        セマンティック検索
        
        Args:
            query: 検索クエリ
            n_results: 最大取得件数（デフォルト: 10）
            element_type_filter: 要素タイプによるフィルタ
            distance_threshold: 距離の閾値（指定された場合、閾値以下のものを最大 n_results 件返します）
            use_ai_rewrite: AIによるクエリ変換を利用するか
        
        Returns:
            dict: {"results": list[dict], "method": "vector" | "keyword", "rewritten_queries": list[str]}
        """
        collection = self._get_chroma_collection()
        if rewritten_queries is None:
            rewritten_queries = self._rewrite_ambiguous_query(query) if use_ai_rewrite else []
        elif not use_ai_rewrite:
            rewritten_queries = []

        if collection is None:
            return {"results": self._keyword_search(query, n_results), "method": "keyword", "rewritten_queries": rewritten_queries}

        query_candidates = [query]
        if rewritten_queries:
            query_candidates = list(dict.fromkeys([query, *rewritten_queries]))

        try:
            output = self._collect_vector_results(
                collection,
                query_candidates,
                n_results,
                element_type_filter,
                distance_threshold,
            )
        except Exception as e:
            print(f"⚠️ ChromaDB検索エラー: {e}", file=sys.stderr)
            return {"results": self._keyword_search(query, n_results), "method": "keyword", "rewritten_queries": rewritten_queries}

        if not output:
            print(f"ℹ️ セマンティック検索でヒットしなかったため、キーワード検索に切り替えます: {query}", file=sys.stderr)
            return {"results": self._keyword_search(query, n_results), "method": "keyword", "rewritten_queries": rewritten_queries}

        return {"results": output, "method": "vector", "rewritten_queries": rewritten_queries}

    def search_with_graph(
        self,
        query: str,
        n_results: int = 10,
        link_depth: int = 1,
        expand_paper: bool = False,
        distance_threshold: Optional[float] = None,
        element_type_filter: Optional[str] = None,
        max_total: int = 100,
        use_ai_rewrite: bool = True,
    ) -> dict:
        """
        グラフ探索付きセマンティック検索

        ベクトル検索の結果を起点に、ノート間リンクを BFS で辿り、
        オプションで同一論文の他ノートも展開して返す。

        Args:
            query: 検索クエリ
            n_results: ベクトル検索の初期取得件数（デフォルト: 10）
            link_depth: リンクを遡るホップ数（デフォルト: 1, 0 で従来検索）
            expand_paper: 同一論文の他ノートを展開するか（デフォルト: False）
            distance_threshold: 距離の閾値
            element_type_filter: 要素タイプによるフィルタ（ベクトル検索のみ）
            max_total: 最大結果数の上限（デフォルト: 100）

        Returns:
            dict: {
                "results": list[dict],  # 各要素に source, depth, linked_from, link_reason を含む
                "method": "vector" | "keyword",
                "graph_stats": {"direct_hits": int, "linked_notes": int, "paper_expanded": int}
            }
        """
        # link_depth=0 かつ expand_paper=False の場合は従来の search() にフォールバック
        if link_depth <= 0 and not expand_paper:
            base_results = self.search(
                query, n_results,
                element_type_filter=element_type_filter,
                distance_threshold=distance_threshold,
                use_ai_rewrite=use_ai_rewrite,
            )
            # 従来の結果に source/depth フィールドを付与して統一フォーマットに
            for r in base_results["results"]:
                r["source"] = "direct"
                r["depth"] = 0
            base_results["graph_stats"] = {
                "direct_hits": len(base_results["results"]),
                "linked_notes": 0,
                "paper_expanded": 0,
            }
            return base_results

        # 1. ベクトル検索で初期ヒットを取得
        base_results = self.search(
            query, n_results,
            element_type_filter=element_type_filter,
            distance_threshold=distance_threshold,
            use_ai_rewrite=use_ai_rewrite,
        )
        rewritten_queries = base_results.get("rewritten_queries", [])
        method = base_results["method"]

        # 統合結果: note_id -> result_dict のマッピング（重複排除用）
        seen: Dict[str, dict] = {}
        output: List[dict] = []

        # 直接ヒットを登録
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

        # 2. BFS でリンクを link_depth ホップまで辿る
        if link_depth > 0:
            # BFS のフロンティア: (note_id, depth, linked_from_id)
            frontier = [(r["note"]["id"], 0) for r in base_results["results"]]
            visited = set(seen.keys())

            for current_depth in range(1, link_depth + 1):
                if len(output) >= max_total:
                    break

                next_frontier = []
                for parent_id, _ in frontier:
                    if len(output) >= max_total:
                        break

                    # リンク先を取得（DB から直接取得して効率化）
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

        # 3. 同一論文の他ノートを展開
        paper_expanded_count = 0
        if expand_paper and len(output) < max_total:
            # 直接ヒットした論文タイトルを収集
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

        # 統計情報の集計
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

    def _get_linked_ids_with_reasons(self, note_id: str) -> List[tuple]:
        """
        指定ノートのリンク先IDとリンク理由を取得する（双方向）

        Returns:
            list[tuple]: [(linked_id, reason), ...]
        """
        results = []
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # source_id → target_id 方向
            cur.execute(
                "SELECT target_id, reason FROM note_links WHERE source_id = ?",
                (note_id,)
            )
            for row in cur.fetchall():
                reason = self._parse_maybe_json(row["reason"])
                results.append((row["target_id"], reason))

            # target_id → source_id 方向（双方向リンク対応）
            cur.execute(
                "SELECT source_id, reason FROM note_links WHERE target_id = ?",
                (note_id,)
            )
            seen_ids = {r[0] for r in results}
            for row in cur.fetchall():
                if row["source_id"] not in seen_ids:
                    reason = self._parse_maybe_json(row["reason"])
                    results.append((row["source_id"], reason))

        return results

    def find_neighbors(self, note_id: str, n_results: int = 10, element_type_filter: Optional[str] = None) -> list[dict]:
        """指定ノートの近傍ノートを検索"""
        note = self.get(note_id)
        if not note:
            return []
        search_text = self._build_search_text(note)
        search_data = self.search(search_text, n_results + 1, element_type_filter=element_type_filter)
        results = search_data["results"]
        return [r for r in results if r["note"]["id"] != note_id][:n_results]

    # ========================================
    # リンク管理
    # ========================================

    def add_link(self, source_id: str, target_id: str, reason: str = "") -> bool:
        """2つのノート間にリンクを追加（双方向）"""
        source = self.get(source_id)
        target = self.get(target_id)
        if not source or not target:
            return False

        source.add_link(target_id, reason)
        target.add_link(source_id, reason)
        self._save_note(source)
        self._save_note(target)
        return True

    def remove_link(self, source_id: str, target_id: str) -> bool:
        """2つのノート間のリンクを削除（双方向）"""
        source = self.get(source_id)
        target = self.get(target_id)
        if not source or not target:
            return False

        source.remove_link(target_id)
        target.remove_link(source_id)
        self._save_note(source)
        self._save_note(target)
        return True

    def get_linked_notes(self, note_id: str) -> list[PaperNote]:
        """リンクされたノートを取得"""
        note = self.get(note_id)
        if not note:
            return []
        return [n for lid in note.links if (n := self.get(lid)) is not None]

    def list_pdfs(self) -> list[str]:
        """pdf/ ディレクトリ内のPDFファイル一覧を返す"""
        pdf_dir = self.base_dir / "pdf"
        if not pdf_dir.exists():
            return []
        return [f.name for f in pdf_dir.glob("*.pdf")]

    def reindex(self, batch_size: int = 50) -> int:
        """既存の全ノートからChromaDBインデックスを再構築する"""
        collection = self._get_chroma_collection()
        if collection is None:
            raise RuntimeError("ChromaDB collection is not available.")
        
        notes_list = self.list_all()
        total = len(notes_list)
        count = 0
        
        print(f"🔄 {total}件のノートを再インデックスします（バッチサイズ: {batch_size}）...", file=sys.stderr)
        
        for i in range(0, total, batch_size):
            batch = notes_list[i:i + batch_size]
            
            ids = [n.id for n in batch]
            documents = [self._build_search_text(n) for n in batch]
            metadatas = [{
                "element_type": n.element_type,
                "paper_title": n.source_paper.title,
                "timestamp": n.timestamp,
            } for n in batch]
            
            try:
                self._upsert_with_retry(
                    collection,
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                count += len(batch)
                print(f"✅ {count}/{total} 件完了...", file=sys.stderr)
                
                if i + batch_size < total:
                    # レート制限を考慮して少し待機
                    time.sleep(2) 
            except Exception as e:
                print(f"❌ バッチ処理中に致命的なエラーが発生しました（インデックス {i}）: {e}", file=sys.stderr)
                # 再インデックス時は一部失敗しても続行せず、問題を報告する
                raise e
                
        return count

    # ========================================
    # 内部メソッド: ChromaDB
    # ========================================

    def _get_chroma_collection(self):
        if self._chroma_collection is not None:
            return self._chroma_collection

        try:
            import chromadb
            import chromadb.utils.embedding_functions as embedding_functions
            
            try:
                pass
            except ImportError:
                pass

            db_path = str(self.base_dir / ".chromadb")
            self._chroma_client = chromadb.PersistentClient(path=db_path)
            class GeminiEmbeddingFunction(embedding_functions.EmbeddingFunction):
                def __init__(self, api_key: str, model_name: str):
                    self.api_key = api_key
                    self.model_name = model_name if model_name.startswith('models/') else f'models/{model_name}'
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=FutureWarning)
                        import google.generativeai as genai
                        genai.configure(api_key=self.api_key)
                def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
                    import google.generativeai as genai
                    import warnings
                    import time
                    import sys
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore", category=FutureWarning)
                                result = genai.embed_content(
                                    model=self.model_name,
                                    content=input,
                                    task_type="RETRIEVAL_DOCUMENT"
                                )
                            return result['embedding']
                        except Exception as e:
                            if ("429" in str(e) or "quota" in str(e).lower()) and attempt < max_retries - 1:
                                wait_time = (attempt + 1) * 10
                                print(f"⚠️ Embedding: レート制限に達しました。{wait_time}秒後にリトライします ({attempt + 1}/{max_retries})...", file=sys.stderr)
                                time.sleep(wait_time)
                                continue
                            raise e
            
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                gemini_ef = GeminiEmbeddingFunction(
                    api_key=api_key,
                    model_name=EMBEDDING_MODEL
                )
                self._chroma_collection = self._chroma_client.get_or_create_collection(
                    name="paper_notes_gemini2",
                    embedding_function=gemini_ef,
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                self._chroma_collection = self._chroma_client.get_or_create_collection(
                    name="paper_notes",
                    metadata={"hnsw:space": "cosine"},
                )
            return self._chroma_collection
        except ImportError:
            print("⚠️ chromadbがインストールされていません。キーワード検索にフォールバックします。", file=sys.stderr)
            return None
        except Exception as e:
            print(f"⚠️ ChromaDB初期化エラー: {e}", file=sys.stderr)
            return None

    def _build_search_text(self, note: PaperNote) -> str:
        parts = []
        if isinstance(note.content, dict):
            parts.extend(str(v) for v in note.content.values() if v)
        elif note.content:
            parts.append(str(note.content))
            
        if note.keywords:
            keyword_list = []
            for kw in note.keywords:
                if isinstance(kw, dict):
                    keyword_list.extend(str(v) for v in kw.values() if v)
                else:
                    keyword_list.append(str(kw))
            parts.append("Keywords: " + ", ".join(keyword_list))
            
        if isinstance(note.context, dict):
            parts.extend("Context: " + str(v) for v in note.context.values() if v)
        elif note.context:
            parts.append("Context: " + str(note.context))
            
        if note.tags:
            tag_list = []
            for tag in note.tags:
                if isinstance(tag, dict):
                    tag_list.extend(str(v) for v in tag.values() if v)
                else:
                    tag_list.append(str(tag))
            parts.append("Tags: " + ", ".join(tag_list))
        return " ".join(parts)

    def _add_to_chroma(self, note: PaperNote) -> None:
        collection = self._get_chroma_collection()
        if collection is None:
            raise RuntimeError("ChromaDB is not initialized.")
        
        search_text = self._build_search_text(note)
        self._upsert_with_retry(
            collection,
            ids=[note.id],
            documents=[search_text],
            metadatas=[{
                "element_type": note.element_type,
                "paper_title": note.source_paper.title,
                "timestamp": note.timestamp,
            }],
        )

    def _upsert_with_retry(self, collection, ids, documents, metadatas, max_retries=3):
        """リトライ機能付きの upsert"""
        last_exception = None
        for attempt in range(max_retries):
            try:
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                return
            except Exception as e:
                last_exception = e
                # 429 (Rate Limit) の場合は待機してリトライ
                if "429" in str(e) or "quota" in str(e).lower():
                    wait_time = (attempt + 1) * 10
                    print(f"⚠️ レート制限に達しました。{wait_time}秒後にリトライします ({attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    # その他のエラーは即時レイズ
                    raise e
        
        raise last_exception

    def _update_chroma(self, note: PaperNote) -> None:
        self._add_to_chroma(note)

    def _delete_from_chroma(self, note_id: str) -> None:
        collection = self._get_chroma_collection()
        if collection is None:
            return
        try:
            collection.delete(ids=[note_id])
        except Exception as e:
            print(f"⚠️ ChromaDB削除エラー: {e}", file=sys.stderr)

    # ========================================
    # フォールバック: キーワード検索
    # ========================================

    def _keyword_search(self, query: str, n_results: int = 5) -> list[dict]:
        query_lower = query.lower()
        scored = []
        for note in self.list_all():
            score = 0
            text = self._build_search_text(note).lower()
            for word in query_lower.split():
                if word in text:
                    score += text.count(word)
            if score > 0:
                scored.append((score, note))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, note in scored[:n_results]:
            note.record_access()
            self._save_note(note)
            results.append({
                "note": note.to_dict(),
                "distance": None,
            })
        return results
