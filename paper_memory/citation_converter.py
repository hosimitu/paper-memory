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
CitationConverter — 論文Markdownの引用番号を脚注記法（[^1]）に変換するモジュール

機能:
  1. 本文中の角括弧引用（例: [1], [2,3], [1-5], [6 -8]）を検出し、脚注記法 [^1][^2]... に変換
  2. Table/Figure/Equation の参照（例: Fig. [1], Table [1], Eq. [1]）やキャプションの誤判定を防止
  3. DoclingDocument のメタデータ（DocItemLabel.REFERENCE 等）または Markdown 本文から参考文献リストを抽出
  4. 文書末尾に [^1]: 参考文献定義 を付与
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReferenceEntry:
    """参考文献エントリ"""
    key: str  # 参照キー（例: "1", "2"）
    text: str  # 参考文献の本文テキスト


class CitationConverter:
    """角括弧形式の引用参照をMarkdown脚注に変換するクラス"""

    # 保護対象のプレフィックス（図・表・式など直後の [N] を引用とみなさないためのキーワード）
    PROTECTED_PREFIX_PATTERN = re.compile(
        r"(?:Fig(?:\.|ure)?s?|Tables?|Eq(?:n|s|\.)?|Equations?|Schemes?|Box|Section|Chapter|Step|Algorithm)\s*!*$",
        re.IGNORECASE,
    )

    # 引用とみなす角括弧パターン（例: [1], [1, 2], [1-3], [1 - 3], [1,3-5]）
    BRACKET_CITATION_PATTERN = re.compile(
        r"\[\s*(\d+(?:\s*(?:[,;]|-|–)\s*\d+)*)\s*\]"
    )

    def __init__(self, doc: Optional[Any] = None) -> None:
        """
        Args:
            doc: DoclingDocument オブジェクト（オプション）。渡された場合は構造情報を利用して精度を高める。
        """
        self.doc = doc

    def extract_references_from_docling(self) -> dict[str, str]:
        """DoclingDocument の DocItemLabel.REFERENCE から参考文献を抽出する"""
        if not self.doc:
            return {}

        refs: dict[str, str] = {}
        try:
            from docling_core.types.doc import DocItemLabel

            ref_index = 1
            for item, _ in self.doc.iterate_items():
                if getattr(item, "label", None) == DocItemLabel.REFERENCE:
                    text = item.text.strip()
                    if not text:
                        continue
                    # [1] や 1. や (1) などの番号プレフィックスを検出
                    m = re.match(r"^(?:\[(\d+)\]|\((\d+)\)|(\d+)[\.\s])\s*(.*)$", text)
                    if m:
                        num = m.group(1) or m.group(2) or m.group(3)
                        content = m.group(4).strip()
                        refs[num] = content or text
                    else:
                        refs[str(ref_index)] = text
                        ref_index += 1
        except Exception:
            pass

        return refs

    def extract_references_from_markdown(self, md_text: str) -> tuple[str, dict[str, str]]:
        """
        Markdown 本文の References セクションから参考文献を抽出し、
        (Referencesセクション前までの本文, 参考文献辞書) を返す。
        """
        refs: dict[str, str] = {}

        # References / REFERENCES / 参考文献 セクションの開始位置を探す
        ref_header_pattern = re.compile(
            r"(?:\n|^)(#{1,4}\s*(?:References?|REFERENCES?|Bibliography|REFERENCES\s*AND\s*NOTES|参考文献)[^\n]*\n)",
            re.IGNORECASE,
        )
        match = ref_header_pattern.search(md_text)
        if not match:
            return md_text, refs

        body = md_text[: match.start()].rstrip()
        ref_section = md_text[match.end() :]

        # 参考文献エントリのパース
        lines = ref_section.split("\n")
        current_num: Optional[str] = None
        current_text: list[str] = []
        auto_index = 1

        def save_current():
            nonlocal current_num, current_text
            if current_num and current_text:
                refs[current_num] = " ".join(current_text).strip()
            current_num = None
            current_text = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # - [1] Author... または - (1) Author... または 1. Author... または 1 Author...
            m = re.match(
                r"^(?:-\s*)?(?:\[(\d+)\]|\((\d+)\)|(\d+)\.|\b(\d+)\b)\s*(.*)$",
                line_str,
            )
            # Markdown リンク形式: - [Author, 2020...](url) は番号ではないので判定
            link_match = re.match(r"^-\s*\[([^\]]+)\]\(([^)]+)\)$", line_str)

            if m and (m.group(1) or m.group(2) or m.group(3) or (m.group(4) and not link_match)):
                save_current()
                current_num = m.group(1) or m.group(2) or m.group(3) or m.group(4)
                content = m.group(5).strip()
                current_text.append(content)
            elif link_match:
                save_current()
                current_num = str(auto_index)
                auto_index += 1
                current_text.append(line_str.lstrip("- ").strip())
            else:
                if current_num:
                    current_text.append(line_str.lstrip("- ").strip())

        save_current()
        return body, refs

    def parse_citation_numbers(self, cit_str: str) -> list[int]:
        """
        '1, 2, 5-7, 10' のような文字列を展開して整数のリスト [1, 2, 5, 6, 7, 10] に変換する
        """
        numbers: list[int] = []
        # 区切り文字（カンマ、セミコロン）で分割
        parts = re.split(r"[,;]", cit_str)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # ハイフンやダッシュでの範囲指定
            range_match = re.match(r"^(\d+)\s*(?:-|–)\s*(\d+)$", part)
            if range_match:
                start_n = int(range_match.group(1))
                end_n = int(range_match.group(2))
                if start_n <= end_n and (end_n - start_n) <= 50:  # 異常に大きな範囲を防止
                    numbers.extend(range(start_n, end_n + 1))
                else:
                    numbers.append(start_n)
                    numbers.append(end_n)
            elif part.isdigit():
                numbers.append(int(part))
        return sorted(list(dict.fromkeys(numbers)))

    def convert_in_text_citations(
        self, text: str, valid_keys: Optional[set[str]] = None
    ) -> str:
        """
        本文中の [1], [2,3], [1-5] を [^1], [^2][^3] に変換する。
        Table/Figure/Equation の直後にあるものは除外する。
        """
        result_parts: list[str] = []
        last_end = 0

        for m in self.BRACKET_CITATION_PATTERN.finditer(text):
            start, end = m.span()
            inner_str = m.group(1)

            # 直前の文字列を取得して、保護対象プレフィックス（Fig., Table, Eq. など）か判定
            prefix = text[max(0, start - 30) : start]
            if self.PROTECTED_PREFIX_PATTERN.search(prefix):
                # 保護対象なので置換せずそのまま残す
                result_parts.append(text[last_end:end])
                last_end = end
                continue

            nums = self.parse_citation_numbers(inner_str)
            if not nums:
                result_parts.append(text[last_end:end])
                last_end = end
                continue

            # valid_keys（検出された参考文献の番号集合）が存在する場合の検証
            if valid_keys:
                # 検出された番号が参考文献に1つも該当しない場合は置換しない
                str_nums = [str(n) for n in nums]
                if not any(n in valid_keys for n in str_nums):
                    result_parts.append(text[last_end:end])
                    last_end = end
                    continue

            # 脚注記法 [^1][^2] に変換
            replacement = "".join(f"[^{n}]" for n in nums)
            result_parts.append(text[last_end:start])
            result_parts.append(replacement)
            last_end = end

        result_parts.append(text[last_end:])
        return "".join(result_parts)

    def convert(self, md_text: str) -> str:
        """
        Markdown テキストを受け取り、引用文献を脚注記法に変換した Markdown を返す。
        """
        # 1. 参考文献リストの取得
        refs = self.extract_references_from_docling()
        body_text = md_text

        if not refs:
            # docling から取れなかった場合は Markdown から抽出
            body_text, refs = self.extract_references_from_markdown(md_text)
        else:
            # docling から取れた場合でも References セクションを本文から切り離す
            body_text, _ = self.extract_references_from_markdown(md_text)

        valid_keys = set(refs.keys()) if refs else None

        # 2. 本文中の引用番号を置換
        converted_body = self.convert_in_text_citations(body_text, valid_keys=valid_keys)

        # 3. 脚注定義の構築
        if not refs:
            return converted_body

        footnote_lines = ["\n\n## References / Footnotes\n"]
        # キーを数値順にソート（数値でないものは末尾）
        def sort_key(k: str) -> tuple[int, int, str]:
            if k.isdigit():
                return (0, int(k), "")
            return (1, 0, k)

        for k in sorted(refs.keys(), key=sort_key):
            ref_content = refs[k]
            footnote_lines.append(f"[^{k}]: {ref_content}")

        return converted_body + "\n".join(footnote_lines) + "\n"
