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

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from .note import PaperNote, SourcePaper
from .database import Database
from .ai_models import EMBEDDING_MODEL


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
            content=row["content"],
            source_paper=sp,
            element_type=row["element_type"],
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            context=row["context"] or "",
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
                note.content,
                paper_id,
                note.element_type,
                json.dumps(note.keywords, ensure_ascii=False),
                note.context,
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
        self._add_to_chroma(note)
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
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            except Exception as e:
                print(f"⚠️ ChromaDBバッチ追加エラー: {e}", file=sys.stderr)
                
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

    def add_qa_history(self, query: str, answer: str, references: list, threshold: float) -> None:
        """QAのやり取りを履歴に保存し、10件を超えたら古いものを削除する"""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO qa_history (query, answer, references_json, threshold, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """, (
                query,
                answer,
                json.dumps(references, ensure_ascii=False),
                threshold,
                datetime.now().isoformat()
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
                history.append({
                    "id": row["id"],
                    "query": row["query"],
                    "answer": row["answer"],
                    "references": json.loads(row["references_json"]) if row["references_json"] else [],
                    "threshold": row["threshold"],
                    "timestamp": row["timestamp"]
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

    def search(self, query: str, n_results: int = 10, element_type_filter: Optional[str] = None, distance_threshold: Optional[float] = None) -> list[dict]:
        """
        セマンティック検索
        
        Args:
            query: 検索クエリ
            n_results: 最大取得件数（デフォルト: 10）
            element_type_filter: 要素タイプによるフィルタ
            distance_threshold: 距離の閾値（指定された場合、閾値以下のものを最大 n_results 件返します）
        """
        collection = self._get_chroma_collection()
        if collection is None:
            return self._keyword_search(query, n_results)

        try:
            query_params = {
                "query_texts": [query],
                "n_results": min(n_results, self.get_stats()["total_notes"] or 1),
            }
            if element_type_filter:
                query_params["where"] = {"element_type": element_type_filter}
            
            results = collection.query(**query_params)
        except Exception as e:
            print(f"⚠️ ChromaDB検索エラー: {e}", file=sys.stderr)
            return self._keyword_search(query, n_results)

        output = []
        if results and results["ids"] and results["ids"][0]:
            for i, note_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else None
                
                # 閾値チェック
                if distance_threshold is not None and distance is not None:
                    if distance > distance_threshold:
                        continue
                
                note = self.get(note_id)
                if note:
                    output.append({
                        "note": note.to_dict(),
                        "distance": distance,
                    })
        
        return output


    def find_neighbors(self, note_id: str, n_results: int = 10, element_type_filter: Optional[str] = None) -> list[dict]:
        """指定ノートの近傍ノートを検索"""
        note = self.get(note_id)
        if not note:
            return []
        search_text = self._build_search_text(note)
        results = self.search(search_text, n_results + 1, element_type_filter=element_type_filter)
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
            return 0
        
        import time
        notes_list = self.list_all()
        total = len(notes_list)
        count = 0
        
        print(f"🔄 {total}件のノートを再インデックスします（バッチサイズ: {batch_size}）...")
        
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
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                count += len(batch)
                print(f"✅ {count}/{total} 件完了...")
                
                if i + batch_size < total:
                    time.sleep(20) 
            except Exception as e:
                print(f"⚠️ バッチ処理中にエラーが発生しました（インデックス {i}）: {e}", file=sys.stderr)
                time.sleep(30)
                
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
                from dotenv import load_dotenv
                load_dotenv(override=True)
            except ImportError:
                pass

            db_path = str(self.base_dir / ".chromadb")
            self._chroma_client = chromadb.PersistentClient(path=db_path)
            
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                gemini_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
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
        parts = [note.content]
        if note.keywords:
            parts.append("Keywords: " + ", ".join(note.keywords))
        if note.context:
            parts.append("Context: " + note.context)
        if note.tags:
            parts.append("Tags: " + ", ".join(note.tags))
        return " ".join(parts)

    def _add_to_chroma(self, note: PaperNote) -> None:
        collection = self._get_chroma_collection()
        if collection is None:
            return
        try:
            search_text = self._build_search_text(note)
            collection.upsert(
                ids=[note.id],
                documents=[search_text],
                metadatas=[{
                    "element_type": note.element_type,
                    "paper_title": note.source_paper.title,
                    "timestamp": note.timestamp,
                }],
            )
        except Exception as e:
            print(f"⚠️ ChromaDB追加エラー: {e}", file=sys.stderr)

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
