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
format_default — QA回答のデフォルトMarkdown出力フォーマット

Q&A・日時・検索設定・参照ノート一覧を含む標準的な形式で出力する。
"""

from datetime import datetime


def format_qa_to_markdown(
    query: str,
    answer: str,
    references: list[dict],
    metadata: dict,
) -> str:
    """
    QA回答を標準Markdown形式に変換する。

    Args:
        query: ユーザーの質問文
        answer: AIの回答テキスト
        references: 参照ノートのリスト
            [{"id": int, "title": str, "note_id": str, "source": str, "depth": int}, ...]
        metadata: 検索設定等のメタデータ
            {
                "timestamp": str,          # ISO形式のタイムスタンプ
                "threshold": float,        # 類似度閾値
                "search_method": str,      # 検索方法
                "link_depth": int,         # リンク深度
                "expand_paper": bool,      # 論文展開フラグ
                "n": int,                  # 取得件数
                "rewritten_queries": list  # AI補正クエリ一覧
            }

    Returns:
        Markdown形式の文字列
    """
    # タイムスタンプを整形
    timestamp_str = metadata.get("timestamp", datetime.now().isoformat())
    try:
        dt = datetime.fromisoformat(timestamp_str)
        formatted_time = dt.strftime("%Y年%m月%d日 %H:%M:%S")
    except (ValueError, TypeError):
        formatted_time = timestamp_str

    # 検索設定の整形
    search_method = metadata.get("search_method", "vector")
    threshold = metadata.get("threshold", 0.45)
    link_depth = metadata.get("link_depth", 1)
    expand_paper = metadata.get("expand_paper", False)
    n_results = metadata.get("n", 15)
    rewritten_queries = metadata.get("rewritten_queries", [])

    method_label = {
        "vector": "ベクトル検索",
        "hybrid": "ハイブリッド検索",
        "keyword": "キーワード検索",
    }.get(search_method, search_method)

    expand_label = "あり" if expand_paper else "なし"

    # 補正クエリの整形
    rewritten_section = ""
    if rewritten_queries:
        rewritten_list = "\n".join(f"- {q}" for q in rewritten_queries)
        rewritten_section = f"\n### 🔄 AI補正クエリ\n\n{rewritten_list}\n"

    # 参照ノートセクションの整形
    references_section = ""
    if references:
        ref_lines = []
        for ref in references:
            depth_info = f"（深度: {ref.get('depth', 0)}）" if ref.get("depth", 0) > 0 else ""
            source_info = f"（{ref.get('source', 'direct')}）" if ref.get("source") != "direct" else ""
            ref_lines.append(
                f"- **[{ref.get('id', '?')}]** {ref.get('title', 'Unknown Paper')}{depth_info}{source_info}"
            )
        references_section = "\n---\n\n## 📚 参照ノート\n\n" + "\n".join(ref_lines) + "\n"

    # Markdownの組み立て
    md = f"""# QA回答記録

> **質問:** {query}

**記録日時:** {formatted_time}

---

## 💬 回答

{answer}
{rewritten_section}
---

## ⚙️ 検索設定

| 項目 | 値 |
|---|---|
| 検索方式 | {method_label} |
| 類似度閾値 | {threshold} |
| リンク深度 | {link_depth} |
| 論文内展開 | {expand_label} |
| 取得件数 | {n_results} |
{references_section}"""

    return md.strip()
