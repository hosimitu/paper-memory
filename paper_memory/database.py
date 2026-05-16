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
Database — SQLite ストレージの管理モジュール

SQLite のスキーマ定義・接続管理・既存 JSON からのマイグレーションを担当する。
"""

import sqlite3
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class Database:
    def __init__(self, db_path: str = "paper_memory.db"):
        self.db_path = Path(db_path)

    def get_connection(self) -> sqlite3.Connection:
        """SQLite 接続を取得（Dictのようにアクセスできる row_factory を設定）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # 外部キー制約を有効化
        conn.execute("PRAGMA foreign_keys = ON")
        # WALモードでパフォーマンスと同時アクセス耐性を向上
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        """データベースのテーブルを作成（存在しない場合のみ）"""
        with self.get_connection() as conn:
            # 論文情報（正規化）
            conn.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                authors TEXT,
                year INTEGER,
                doi TEXT,
                journal TEXT,
                pdf_path TEXT
            )
            """)

            # ノート本体
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                paper_id INTEGER REFERENCES papers(id),
                element_type TEXT NOT NULL DEFAULT 'other',
                keywords TEXT,
                context TEXT,
                tags TEXT,
                timestamp TEXT NOT NULL,
                last_accessed TEXT,
                retrieval_count INTEGER DEFAULT 0,
                evolution_history TEXT
            )
            """)

            # ノート間リンク
            conn.execute("""
            CREATE TABLE IF NOT EXISTS note_links (
                source_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                reason TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id)
            )
            """)

            # 参考文献 (Reading List)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS references_table (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                year INTEGER,
                doi TEXT,
                journal TEXT,
                cited_by TEXT,
                cited_by_pdf TEXT,
                relevance TEXT DEFAULT 'medium',
                reason TEXT,
                keywords TEXT,
                status TEXT DEFAULT 'unread',
                created_at TEXT,
                updated_at TEXT
            )
            """)

            # 参考文献履歴
            conn.execute("""
            CREATE TABLE IF NOT EXISTS reference_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                authors TEXT,
                year INTEGER,
                doi TEXT,
                journal TEXT,
                cited_by TEXT,
                relevance TEXT,
                completed_at TEXT,
                linked_notes TEXT
            )
            """)

            # QA履歴
            conn.execute("""
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                answer TEXT NOT NULL,
                references_json TEXT,
                threshold REAL,
                timestamp TEXT NOT NULL,
                search_method TEXT DEFAULT 'vector'
            )
            """)

            # 既存のテーブルにカラムがない場合は追加 (Migration)
            cursor = conn.execute("PRAGMA table_info(qa_history)")
            columns = [column['name'] for column in cursor.fetchall()]
            if 'search_method' not in columns:
                conn.execute("ALTER TABLE qa_history ADD COLUMN search_method TEXT DEFAULT 'vector'")

            conn.commit()

    def migrate_notes(self, notes_dir: Path, backup_dir: Path) -> int:
        """
        JSON ファイルから SQLite への移行（Notes用）
        - 冪等性を担保（ON CONFLICT DO UPDATE）
        - リンク理由の抽出
        - 完了後、_backup ディレクトリに移動
        """
        self.initialize()
        
        if not notes_dir.exists():
            print(f"⚠️ ディレクトリが見つかりません: {notes_dir}", file=sys.stderr)
            return 0

        backup_dir.mkdir(parents=True, exist_ok=True)
        notes_to_migrate = []
        json_files = list(notes_dir.glob("*.json"))

        if not json_files:
            return 0

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    notes_to_migrate.append((json_file, json.load(f)))
            except Exception as e:
                print(f"⚠️ ファイル読み込みエラー ({json_file.name}): {e}", file=sys.stderr)

        migrated_count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 論文（papers）とノート（notes）の登録
            for file_path, note_data in notes_to_migrate:
                sp = note_data.get("source_paper", {})
                title = sp.get("title", "")
                if not title:
                    title = "Unknown Paper"

                # 論文データのUPSERT
                cursor.execute("""
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
                    json.dumps(sp.get("authors", []), ensure_ascii=False),
                    sp.get("year"),
                    sp.get("doi"),
                    sp.get("journal"),
                    sp.get("pdf_path")
                ))

                cursor.execute("SELECT id FROM papers WHERE title = ?", (title,))
                paper_id = cursor.fetchone()["id"]

                # ノートデータのUPSERT
                cursor.execute("""
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
                    note_data["id"],
                    note_data.get("content", ""),
                    paper_id,
                    note_data.get("element_type", "other"),
                    json.dumps(note_data.get("keywords", []), ensure_ascii=False),
                    note_data.get("context", ""),
                    json.dumps(note_data.get("tags", []), ensure_ascii=False),
                    note_data.get("timestamp", datetime.now().isoformat()),
                    note_data.get("last_accessed", datetime.now().isoformat()),
                    note_data.get("retrieval_count", 0),
                    json.dumps(note_data.get("evolution_history", []), ensure_ascii=False)
                ))

            # 2. リンク（note_links）の登録（2パス目）
            for file_path, note_data in notes_to_migrate:
                source_id = note_data["id"]
                links = note_data.get("links", [])
                history = note_data.get("evolution_history", [])

                for target_id in links:
                    # 最新の link_added エントリから reason を抽出
                    reason = ""
                    created_at = datetime.now().isoformat()
                    
                    for event in reversed(history):
                        if event.get("action") == "link_added" and event.get("target_id") == target_id:
                            reason = event.get("reason", "")
                            created_at = event.get("timestamp", created_at)
                            break

                    try:
                        cursor.execute("""
                        INSERT INTO note_links (source_id, target_id, reason, created_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(source_id, target_id) DO UPDATE SET
                            reason=excluded.reason,
                            created_at=excluded.created_at
                        """, (source_id, target_id, reason, created_at))
                    except sqlite3.IntegrityError:
                        print(f"⚠️ リンク先ノート ({target_id}) が存在しないためリンクをスキップしました。", file=sys.stderr)
                
                migrated_count += 1
                
            conn.commit()

            # 3. マイグレーション完了後（コミット成功後）にファイルをバックアップに移動
            for file_path, _ in notes_to_migrate:
                try:
                    shutil.move(str(file_path), str(backup_dir / file_path.name))
                except Exception as e:
                    print(f"⚠️ バックアップ移動エラー ({file_path.name}): {e}", file=sys.stderr)

        return migrated_count

    def migrate_references(self, refs_dir: Path, backup_dir: Path) -> int:
        """JSON ファイルから SQLite への移行（References用）"""
        self.initialize()
        
        if not refs_dir.exists():
            print(f"⚠️ ディレクトリが見つかりません: {refs_dir}", file=sys.stderr)
            return 0

        backup_dir.mkdir(parents=True, exist_ok=True)
        migrated_count = 0
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 履歴 (_history.json) の移行
            history_path = refs_dir / "_history.json"
            if history_path.exists():
                try:
                    with open(history_path, "r", encoding="utf-8") as f:
                        history_data = json.load(f)
                        
                    for entry in history_data:
                        cursor.execute("""
                        INSERT INTO reference_history (title, authors, year, doi, journal, cited_by, relevance, completed_at, linked_notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            entry.get("title", ""),
                            json.dumps(entry.get("authors", []), ensure_ascii=False),
                            entry.get("year"),
                            entry.get("doi"),
                            entry.get("journal"),
                            entry.get("cited_by"),
                            entry.get("relevance", "medium"),
                            entry.get("completed_at"),
                            json.dumps(entry.get("linked_notes", []), ensure_ascii=False)
                        ))
                    
                    try:
                        shutil.move(str(history_path), str(backup_dir / "_history.json"))
                    except Exception as e:
                        print(f"⚠️ バックアップ移動エラー ({history_path.name}): {e}", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️ 履歴読み込みエラー: {e}", file=sys.stderr)

            # 2. 個別 JSON (unread等) の移行
            for json_file in refs_dir.glob("*.json"):
                if json_file.name == "_history.json":
                    continue
                    
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        ref_data = json.load(f)
                        
                    cursor.execute("""
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
                        ref_data["id"],
                        ref_data.get("title", ""),
                        json.dumps(ref_data.get("authors", []), ensure_ascii=False),
                        ref_data.get("year"),
                        ref_data.get("doi"),
                        ref_data.get("journal"),
                        ref_data.get("cited_by"),
                        ref_data.get("cited_by_pdf"),
                        ref_data.get("relevance", "medium"),
                        ref_data.get("reason"),
                        json.dumps(ref_data.get("keywords", []), ensure_ascii=False),
                        ref_data.get("status", "unread"),
                        ref_data.get("created_at"),
                        ref_data.get("updated_at")
                    ))
                    
                    migrated_count += 1
                    
                    try:
                        shutil.move(str(json_file), str(backup_dir / json_file.name))
                    except Exception as e:
                        print(f"⚠️ バックアップ移動エラー ({json_file.name}): {e}", file=sys.stderr)

                except Exception as e:
                    print(f"⚠️ 参考文献読み込みエラー ({json_file.name}): {e}", file=sys.stderr)

            conn.commit()
            
        return migrated_count
