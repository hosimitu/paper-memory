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
Reference — 参考文献（Reading List）のデータモデルとストレージ

論文解析時に抽出された重要な引用文献を管理する（SQLiteバックエンド）。
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .database import Database


@dataclass
class Reference:
    """参考文献のデータモデル"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: str = ""
    journal: str = ""
    cited_by: str = ""
    cited_by_pdf: str = ""
    relevance: str = "medium"
    reason: str = ""
    keywords: list[str] = field(default_factory=list)
    status: str = "unread"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Reference":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "Reference":
        return cls.from_dict(json.loads(json_str))


class ReferenceStore:
    """参考文献のストレージ管理クラス（SQLite版）"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.db = Database(str(self.base_dir / "paper_memory.db"))
        self.db.initialize()

    def _row_to_ref(self, row) -> Reference:
        return Reference(
            id=row["id"],
            title=row["title"],
            authors=json.loads(row["authors"]) if row["authors"] else [],
            year=row["year"],
            doi=row["doi"] or "",
            journal=row["journal"] or "",
            cited_by=row["cited_by"] or "",
            cited_by_pdf=row["cited_by_pdf"] or "",
            relevance=row["relevance"],
            reason=row["reason"] or "",
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def _save_ref(self, ref: Reference) -> None:
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO references_table (id, title, authors, year, doi, journal, cited_by, cited_by_pdf, relevance, reason, keywords, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                authors=excluded.authors,
                year=excluded.year,
                doi=excluded.doi,
                journal=excluded.journal,
                cited_by=excluded.cited_by,
                cited_by_pdf=excluded.cited_by_pdf,
                relevance=excluded.relevance,
                reason=excluded.reason,
                keywords=excluded.keywords,
                status=excluded.status,
                updated_at=excluded.updated_at
            """, (
                ref.id, ref.title, json.dumps(ref.authors, ensure_ascii=False),
                ref.year, ref.doi, ref.journal, ref.cited_by, ref.cited_by_pdf,
                ref.relevance, ref.reason, json.dumps(ref.keywords, ensure_ascii=False),
                ref.status, ref.created_at, ref.updated_at
            ))
            conn.commit()

    def add(self, ref: Reference) -> Reference:
        self._save_ref(ref)
        return ref

    def add_batch(self, refs: list[Reference]) -> list[Reference]:
        for ref in refs:
            self._save_ref(ref)
        return refs

    def get(self, ref_id: str) -> Optional[Reference]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM references_table WHERE id = ?", (ref_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_ref(row)
        return None

    def delete(self, ref_id: str) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.execute("DELETE FROM references_table WHERE id = ?", (ref_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_all(self) -> list[Reference]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM references_table")
            return [self._row_to_ref(r) for r in cur.fetchall()]

    def list_by_status(self, status: str) -> list[Reference]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM references_table WHERE status = ?", (status,))
            return [self._row_to_ref(r) for r in cur.fetchall()]

    def list_by_relevance(self, relevance: str) -> list[Reference]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM references_table WHERE relevance = ?", (relevance,))
            return [self._row_to_ref(r) for r in cur.fetchall()]

    def list_by_cited_by(self, cited_by: str) -> list[Reference]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM references_table WHERE LOWER(cited_by) LIKE ?", (f"%{cited_by.lower()}%",))
            return [self._row_to_ref(r) for r in cur.fetchall()]

    def find_duplicate(self, title: str, doi: str = "") -> Optional[Reference]:
        with self.db.get_connection() as conn:
            if doi:
                cur = conn.execute("SELECT * FROM references_table WHERE LOWER(doi) = ?", (doi.strip().lower(),))
                row = cur.fetchone()
                if row: return self._row_to_ref(row)
            
            if title:
                cur = conn.execute("SELECT * FROM references_table WHERE LOWER(title) = ?", (title.strip().lower(),))
                row = cur.fetchone()
                if row: return self._row_to_ref(row)
        return None

    def find_duplicate_in_history(self, title: str, doi: str = "") -> Optional[dict]:
        with self.db.get_connection() as conn:
            if doi:
                cur = conn.execute("SELECT * FROM reference_history WHERE LOWER(doi) = ?", (doi.strip().lower(),))
                row = cur.fetchone()
                if row: return dict(row)
            
            if title:
                cur = conn.execute("SELECT * FROM reference_history WHERE LOWER(title) = ?", (title.strip().lower(),))
                row = cur.fetchone()
                if row: return dict(row)
        return None

    def mark_done(self, ref_id: str, linked_notes: list[str] = None) -> bool:
        ref = self.get(ref_id)
        if not ref:
            return False

        with self.db.get_connection() as conn:
            # 履歴に移動
            conn.execute("""
            INSERT INTO reference_history (title, authors, year, doi, journal, cited_by, relevance, completed_at, linked_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ref.title, json.dumps(ref.authors, ensure_ascii=False), ref.year, ref.doi,
                ref.journal, ref.cited_by, ref.relevance, datetime.now().isoformat(),
                json.dumps(linked_notes or [], ensure_ascii=False)
            ))
            # アクティブテーブルから削除
            conn.execute("DELETE FROM references_table WHERE id = ?", (ref_id,))
            conn.commit()
        return True

    def mark_done_by_title(self, title: str, doi: str = "") -> int:
        """タイトルまたはDOIに一致する参考文献をすべて『完了』にする"""
        with self.db.get_connection() as conn:
            # 一致するIDを特定
            ref_ids = []
            if doi:
                cur = conn.execute("SELECT id FROM references_table WHERE LOWER(doi) = ?", (doi.strip().lower(),))
                ref_ids.extend([r["id"] for r in cur.fetchall()])
            
            if title:
                cur = conn.execute("SELECT id FROM references_table WHERE LOWER(title) = ?", (title.strip().lower(),))
                ref_ids.extend([r["id"] for r in cur.fetchall()])
            
            # 重複排除
            ref_ids = list(set(ref_ids))
            
            count = 0
            for rid in ref_ids:
                if self.mark_done(rid):
                    count += 1
            return count

    def get_stats(self) -> dict:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT status, COUNT(*) as c FROM references_table GROUP BY status")
            by_status = {r["status"]: r["c"] for r in cur.fetchall()}
            
            cur = conn.execute("SELECT relevance, COUNT(*) as c FROM references_table GROUP BY relevance")
            by_relevance = {r["relevance"]: r["c"] for r in cur.fetchall()}
            
            cur = conn.execute("SELECT COUNT(DISTINCT cited_by) as c FROM references_table WHERE cited_by != ''")
            cited_by_count = cur.fetchone()["c"]
            
            cur = conn.execute("SELECT COUNT(*) as c FROM references_table WHERE status = 'unread'")
            total_unread = cur.fetchone()["c"]
            
            cur = conn.execute("SELECT COUNT(*) as c FROM reference_history")
            total_done = cur.fetchone()["c"]

        return {
            "total_unread": total_unread,
            "total_done": total_done,
            "by_status": by_status,
            "by_relevance": by_relevance,
            "cited_by_papers": cited_by_count,
        }

    def get_history(self) -> list[dict]:
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM reference_history ORDER BY completed_at DESC")
            return [dict(r) for r in cur.fetchall()]
