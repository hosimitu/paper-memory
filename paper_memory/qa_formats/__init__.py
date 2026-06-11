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
qa_formats — QA回答のMarkdown出力フォーマット管理モジュール

各フォーマットは以下のインターフェースを実装する:
    format_qa_to_markdown(query, answer, references, metadata) -> str

レジストリに登録されたフォーマットIDで選択可能。
将来的にはAIによる自動選択やUIのドロップダウンから選択できる。
"""

from .format_default import format_qa_to_markdown as _format_default

# フォーマットレジストリ
# キー: フォーマットID（文字列）, 値: (ラベル, 説明, 関数)
_REGISTRY = {
    "default": {
        "id": "default",
        "label": "標準形式",
        "description": "Q&A・日時・検索設定・参照ノート一覧を含む標準Markdown形式",
        "fn": _format_default,
    },
    # 将来追加予定:
    # "report": {
    #     "id": "report",
    #     "label": "レポート形式",
    #     "description": "章立て・要約付きのレポート風Markdown形式",
    #     "fn": _format_report,
    # },
    # "issues": {
    #     "id": "issues",
    #     "label": "課題列挙形式",
    #     "description": "論点・課題を箇条書きで列挙する形式",
    #     "fn": _format_issues,
    # },
}


def get_format(format_id: str):
    """
    フォーマットIDに対応する変換関数を返す。

    Args:
        format_id: フォーマットID（例: "default"）

    Returns:
        format_qa_to_markdown 関数。IDが未知の場合はデフォルトを返す。
    """
    entry = _REGISTRY.get(format_id) or _REGISTRY["default"]
    return entry["fn"]


def list_formats() -> list[dict]:
    """
    利用可能なフォーマットの一覧を返す（UIのセレクトボックス用）。

    Returns:
        list of dict: {"id": str, "label": str, "description": str}
    """
    return [
        {"id": v["id"], "label": v["label"], "description": v["description"]}
        for v in _REGISTRY.values()
    ]
