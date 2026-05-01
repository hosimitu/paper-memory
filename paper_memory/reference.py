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

論文解析時に抽出された重要な引用文献を管理する。
ノート（notes/）とは別レイヤーで、「今後読むべき文献」を追跡する。
"""

import json
import uuid
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Reference:
    """参考文献のデータモデル"""
    # 書誌情報
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""                            # 文献タイトル（原語）
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None                 # 出版年
    doi: str = ""                              # DOI（わかれば）
    journal: str = ""                          # ジャーナル/会議名

    # 参照元情報
    cited_by: str = ""                         # 引用元の論文タイトル
    cited_by_pdf: str = ""                     # 引用元のPDFパス

    # AIによる重要度評価
    relevance: str = "medium"                  # "high" | "medium"
    reason: str = ""                           # なぜ重要と判断したか（日本語）
    keywords: list[str] = field(default_factory=list)

    # 管理ステータス（シンプル2段階）
    status: str = "unread"                     # "unread" | "done"

    # タイムスタンプ
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Reference":
        """辞書からReferenceを生成"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "Reference":
        """JSON文字列からReferenceを生成"""
        return cls.from_dict(json.loads(json_str))


class ReferenceStore:
    """
    参考文献のストレージ管理クラス

    - JSONファイルベースの永続化（references/ ディレクトリ）
    - 完了した文献は _history.json に記録してファイル削除
    - ChromaDBには統合しない
    """

    HISTORY_FILENAME = "_history.json"

    def __init__(self, base_dir: str = "."):
        """
        Args:
            base_dir: プロジェクトルートディレクトリ
        """
        self.base_dir = Path(base_dir)
        self.refs_dir = self.base_dir / "references"
        self.refs_dir.mkdir(parents=True, exist_ok=True)

        # インメモリインデックス
        self._refs: dict[str, Reference] = {}

        # 起動時にJSONファイルを読み込み
        self._load_all_refs()

    # ========================================
    # CRUD操作
    # ========================================

    def add(self, ref: Reference) -> Reference:
        """参考文献を追加・保存"""
        self._refs[ref.id] = ref
        self._save_ref(ref)
        return ref

    def add_batch(self, refs: list[Reference]) -> list[Reference]:
        """複数の参考文献を一括追加"""
        for ref in refs:
            self._refs[ref.id] = ref
            self._save_ref(ref)
        return refs

    def get(self, ref_id: str) -> Optional[Reference]:
        """IDで参考文献を取得"""
        return self._refs.get(ref_id)

    def delete(self, ref_id: str) -> bool:
        """参考文献を削除"""
        if ref_id not in self._refs:
            return False
        del self._refs[ref_id]
        self._delete_ref_file(ref_id)
        return True

    def list_all(self) -> list[Reference]:
        """全参考文献を返す（unreadのみ）"""
        return list(self._refs.values())

    def list_by_status(self, status: str) -> list[Reference]:
        """ステータスでフィルタ"""
        return [r for r in self._refs.values() if r.status == status]

    def list_by_relevance(self, relevance: str) -> list[Reference]:
        """重要度でフィルタ"""
        return [r for r in self._refs.values() if r.relevance == relevance]

    def list_by_cited_by(self, cited_by: str) -> list[Reference]:
        """引用元論文タイトルでフィルタ"""
        return [
            r for r in self._refs.values()
            if cited_by.lower() in r.cited_by.lower()
        ]

    # ========================================
    # 重複チェック
    # ========================================

    def find_duplicate(self, title: str, doi: str = "") -> Optional[Reference]:
        """
        DOIまたはタイトルで既存の参考文献を検索（重複チェック）

        Returns:
            見つかった場合はReferenceオブジェクト、なければNone
        """
        for ref in self._refs.values():
            # DOIが両方あれば、DOIで比較（最も確実）
            if doi and ref.doi and doi.strip().lower() == ref.doi.strip().lower():
                return ref
            # タイトルの類似比較（小文字化して前方一致 or 完全一致）
            if title and ref.title:
                if title.strip().lower() == ref.title.strip().lower():
                    return ref
        return None

    def find_duplicate_in_history(self, title: str, doi: str = "") -> Optional[dict]:
        """
        完了済み履歴内で重複を検索

        Returns:
            見つかった場合は履歴エントリ（dict）、なければNone
        """
        history = self._load_history()
        for entry in history:
            if doi and entry.get("doi", ""):
                if doi.strip().lower() == entry["doi"].strip().lower():
                    return entry
            if title and entry.get("title", ""):
                if title.strip().lower() == entry["title"].strip().lower():
                    return entry
        return None

    # ========================================
    # ステータス更新と完了処理
    # ========================================

    def mark_done(self, ref_id: str, linked_notes: list[str] = None) -> bool:
        """
        参考文献を完了（done）にする

        1. _history.json に完了記録を追記
        2. references/ から個別JSONファイルを削除
        """
        ref = self._refs.get(ref_id)
        if not ref:
            return False

        # 履歴エントリを作成
        history_entry = {
            "title": ref.title,
            "authors": ref.authors,
            "year": ref.year,
            "doi": ref.doi,
            "journal": ref.journal,
            "cited_by": ref.cited_by,
            "relevance": ref.relevance,
            "completed_at": datetime.now().isoformat(),
            "linked_notes": linked_notes or [],
        }

        # 履歴に追記
        self._append_history(history_entry)

        # ファイルとインメモリから削除
        del self._refs[ref_id]
        self._delete_ref_file(ref_id)
        return True

    # ========================================
    # 統計情報
    # ========================================

    def get_stats(self) -> dict:
        """統計情報を取得"""
        status_counts: dict[str, int] = {}
        relevance_counts: dict[str, int] = {}
        cited_by_set: set[str] = set()

        for ref in self._refs.values():
            status_counts[ref.status] = status_counts.get(ref.status, 0) + 1
            relevance_counts[ref.relevance] = relevance_counts.get(ref.relevance, 0) + 1
            if ref.cited_by:
                cited_by_set.add(ref.cited_by)

        history = self._load_history()

        return {
            "total_unread": len(self._refs),
            "total_done": len(history),
            "by_status": status_counts,
            "by_relevance": relevance_counts,
            "cited_by_papers": len(cited_by_set),
        }

    # ========================================
    # 内部メソッド: JSON永続化
    # ========================================

    def _load_all_refs(self) -> None:
        """references/ ディレクトリ内の全JSONファイルを読み込み（_history.jsonは除外）"""
        for json_file in self.refs_dir.glob("*.json"):
            if json_file.name == self.HISTORY_FILENAME:
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ref = Reference.from_dict(data)
                self._refs[ref.id] = ref
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ 参考文献読み込みエラー ({json_file.name}): {e}", file=sys.stderr)

    def _save_ref(self, ref: Reference) -> None:
        """参考文献をJSONファイルに保存"""
        file_path = self.refs_dir / f"{ref.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(ref.to_json())

    def _delete_ref_file(self, ref_id: str) -> None:
        """参考文献のJSONファイルを削除"""
        file_path = self.refs_dir / f"{ref_id}.json"
        if file_path.exists():
            file_path.unlink()

    # ========================================
    # 内部メソッド: 履歴管理
    # ========================================

    def _load_history(self) -> list[dict]:
        """_history.json を読み込む"""
        history_path = self.refs_dir / self.HISTORY_FILENAME
        if not history_path.exists():
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️ 履歴ファイル読み込みエラー: {e}", file=sys.stderr)
            return []

    def _append_history(self, entry: dict) -> None:
        """_history.json に完了記録を追記"""
        history = self._load_history()
        history.append(entry)
        history_path = self.refs_dir / self.HISTORY_FILENAME
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_history(self) -> list[dict]:
        """完了済み履歴を取得（外部公開用）"""
        return self._load_history()
