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
PaperNote — 論文知識要素のデータモデル

A-MemのMemoryNoteを論文管理用に拡張したデータクラス。
1ノート = 1知識要素（原子性の原則）を保持する。
"""

import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Union


# 論文要素タイプの定義
ELEMENT_TYPES = [
    "background",   # 背景・先行研究
    "method",       # 手法・アプローチ
    "result",       # 結果・実験データ
    "discussion",   # 考察・解釈
    "conclusion",   # 結論
    "insight",      # 洞察・着想
    "limitation",   # 限界・課題
    "future_work",  # 今後の展望
    "definition",   # 用語定義
    "other",        # その他
]


@dataclass
class SourcePaper:
    """元論文の書誌情報"""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: str = ""
    journal: str = ""
    pdf_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SourcePaper":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PaperNote:
    """
    論文知識要素のデータモデル（A-MemのMemoryNote拡張版）

    Zettelkastenの原子性の原則に従い、1ノート = 1知識要素を保持する。
    """
    # コアデータ
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: Union[str, dict] = ""             # 知識要素のテキスト（多言語対応可）
    source_paper: SourcePaper = field(default_factory=SourcePaper)
    element_type: str = "other"                # 要素タイプ（ELEMENT_TYPES参照）

    # LLM生成メタデータ（Gemini CLIが生成）
    keywords: list[str] = field(default_factory=list)
    context: Union[str, dict] = ""             # この要素の文脈記述（多言語対応可）
    tags: list[str] = field(default_factory=list)

    # リンキング（Zettelkastenの原則）
    links: list[str] = field(default_factory=list)  # 関連ノートIDのリスト

    # タイムスタンプ
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())

    # 進化履歴（A-Memの進化原則）
    evolution_history: list[dict] = field(default_factory=list)
    retrieval_count: int = 0

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "PaperNote":
        """辞書からPaperNoteを生成"""
        # SourcePaperのネスト処理
        if "source_paper" in data and isinstance(data["source_paper"], dict):
            data["source_paper"] = SourcePaper.from_dict(data["source_paper"])
            
        # element_typeのバリデーションと正規化
        if "element_type" in data and isinstance(data["element_type"], str):
            val = data["element_type"].lower()
            if val not in ELEMENT_TYPES:
                val = "other"
            data["element_type"] = val
            
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "PaperNote":
        """JSON文字列からPaperNoteを生成"""
        return cls.from_dict(json.loads(json_str))

    def add_link(self, target_id: str, reason: str = "") -> None:
        """リンクを追加（A-Memのリンキング原則）"""
        if target_id not in self.links:
            self.links.append(target_id)
            self.evolution_history.append({
                "action": "link_added",
                "target_id": target_id,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            })

    def remove_link(self, note_id: str) -> None:
        """指定したノートIDへのリンクを削除する"""
        if note_id in self.links:
            self.links.remove(note_id)
            self.evolution_history.append({
                "action": "link_removed",
                "target_id": note_id,
                "timestamp": datetime.now().isoformat(),
            })

    def update_tags(self, new_tags: list[str], reason: str = "") -> None:
        """タグを更新（A-Memの進化原則）"""
        old_tags = self.tags.copy()
        # 重複排除しつつ追加
        for tag in new_tags:
            if tag not in self.tags:
                self.tags.append(tag)
        if self.tags != old_tags:
            self.evolution_history.append({
                "action": "tags_updated",
                "old_tags": old_tags,
                "new_tags": self.tags,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            })

    def update_context(self, new_context: Union[str, dict], reason: str = "") -> None:
        """コンテキストを更新（A-Memの進化原則）"""
        old_context = self.context
        self.context = new_context
        self.evolution_history.append({
            "action": "context_updated",
            "old_context": old_context,
            "new_context": new_context,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

    def record_access(self) -> None:
        """アクセスを記録"""
        self.retrieval_count += 1
        self.last_accessed = datetime.now().isoformat()

    def summary(self) -> str:
        """ノートの要約を返す（一覧表示用）"""
        source = self.source_paper.title or "不明な論文"
        return (
            f"[{self.element_type}] {self.content[:80]}..."
            f"\n  元論文: {source}"
            f"\n  タグ: {', '.join(str(t.get('local', t.get('en', list(t.values())[0]))) if isinstance(t, dict) else str(t) for t in self.tags[:5])}"
            f"\n  リンク数: {len(self.links)}"
        )
