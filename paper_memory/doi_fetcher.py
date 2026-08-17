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
DOI Fetcher — CrossrefおよびOpenAlexを用いたDOIと書誌情報の自動取得・検証
"""

import json
import re
import urllib.request
import urllib.parse
import sys
import time
from difflib import SequenceMatcher
from typing import Optional, Union, Dict, Any


def normalize_doi(doi: Optional[str]) -> str:
    """DOI文字列を正規化（大文字小文字・URLプレフィックスの統一）"""
    if not doi:
        return ""
    doi_str = str(doi).strip().lower()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
        if doi_str.startswith(prefix):
            doi_str = doi_str[len(prefix):]
    return doi_str.strip().strip("/")


def is_doi_match(doi1: Optional[str], doi2: Optional[str]) -> bool:
    """2つのDOIが実質的に一致しているかを判定"""
    norm1 = normalize_doi(doi1)
    norm2 = normalize_doi(doi2)
    if not norm1 or not norm2:
        return False
    return norm1 == norm2


def _normalize_title(title: Optional[str]) -> str:
    """タイトルの正規化（HTMLタグ除去、記号・句読点除去、空白統一、小文字化）"""
    if not title:
        return ""
    # HTMLタグ（<i>, <b>, <sub>, <sup> 等）を除去
    text = re.sub(r"<[^>]+>", " ", str(title))
    # LaTeX等の数式記号や特殊記号・句読点を空白に置換
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    # 連続空白を単一空白に統一しトリムして小文字化
    return " ".join(text.split()).lower()


def _similar(a: str, b: str) -> float:
    """正規化されたタイトルの類似度を計算（0.0 ~ 1.0）"""
    norm_a = _normalize_title(a)
    norm_b = _normalize_title(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _extract_year_from_crossref(item: Dict[str, Any]) -> Optional[int]:
    """Crossrefのアイテムから出版年（西暦）を抽出"""
    for date_field in ["issued", "published-print", "published-online", "created"]:
        val = item.get(date_field)
        if isinstance(val, dict):
            date_parts = val.get("date-parts")
            if isinstance(date_parts, list) and len(date_parts) > 0 and len(date_parts[0]) > 0:
                try:
                    return int(date_parts[0][0])
                except (ValueError, TypeError):
                    pass
    return None


def _extract_year_from_openalex(item: Dict[str, Any]) -> Optional[int]:
    """OpenAlexのアイテムから出版年（西暦）を抽出"""
    py = item.get("publication_year")
    if py is not None:
        try:
            return int(py)
        except (ValueError, TypeError):
            pass
    return None


def _calculate_score(query_title: str, item_title: str, query_year: Optional[int], item_year: Optional[int]) -> tuple[float, float]:
    """
    タイトル類似度と出版年をもとにスコアを算出する。
    Returns: (total_score, title_similarity)
    """
    title_sim = _similar(query_title, item_title)
    if title_sim < 0.80:
        return 0.0, title_sim

    score = title_sim

    # 出版年の照合（指定されている場合）
    if query_year is not None and item_year is not None:
        try:
            q_y = int(query_year)
            i_y = int(item_year)
            diff = abs(q_y - i_y)
            if diff == 0:
                score += 0.05
            elif diff == 1:
                score += 0.02
            elif diff >= 2:
                score -= 0.10
        except (ValueError, TypeError):
            pass

    return score, title_sim


def _fetch_candidates_crossref(title: str, authors: list[str] = None, year: int = None) -> list[Dict[str, Any]]:
    """Crossref APIから候補一覧を取得してスコアリング"""
    query_params = {
        "query.title": title,
        "filter": "type:journal-article",
        "select": "DOI,title,author,issued,published-print,published-online,created",
        "rows": "5"
    }
    if authors and len(authors) > 0:
        query_params["query.author"] = authors[0]

    url = f"https://api.crossref.org/works?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "PaperMemory/1.0 (mailto:dummy@example.com)"
    })

    time.sleep(1.0)

    candidates = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("message", {}).get("items", [])
            for item in items:
                doi = item.get("DOI")
                if not doi:
                    continue
                titles = item.get("title", [])
                item_title = titles[0] if titles else ""
                item_year = _extract_year_from_crossref(item)
                score, title_sim = _calculate_score(title, item_title, year, item_year)
                if title_sim >= 0.80:
                    candidates.append({
                        "doi": doi,
                        "title": item_title,
                        "year": item_year,
                        "score": score,
                        "title_similarity": title_sim,
                        "source": "crossref"
                    })
    except Exception:
        pass
    return candidates


def _fetch_candidates_openalex(title: str, authors: list[str] = None, year: int = None) -> list[Dict[str, Any]]:
    """OpenAlex APIから候補一覧を取得してスコアリング"""
    search_query = title
    if authors and len(authors) > 0:
        search_query += f" {authors[0]}"

    query_params = {
        "search": search_query,
        "filter": "type:article",
        "select": "doi,title,publication_year",
        "per-page": "5"
    }
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "PaperMemory/1.0 (mailto:dummy@example.com)"
    })

    time.sleep(1.0)

    candidates = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = data.get("results", [])
            for result in results:
                doi_url = result.get("doi")
                if not doi_url:
                    continue
                doi = doi_url.replace("https://doi.org/", "").strip()
                item_title = result.get("title", "")
                item_year = _extract_year_from_openalex(result)
                score, title_sim = _calculate_score(title, item_title, year, item_year)
                if title_sim >= 0.80:
                    candidates.append({
                        "doi": doi,
                        "title": item_title,
                        "year": item_year,
                        "score": score,
                        "title_similarity": title_sim,
                        "source": "openalex"
                    })
    except Exception:
        pass
    return candidates


def fetch_doi_details(title: str, authors: list[str] = None, year: int = None) -> Optional[Dict[str, Any]]:
    """
    タイトルと著者・出版年情報をもとにベストマッチするDOI詳細情報を取得する。
    Crossref優先、取得できなければOpenAlexにフォールバック。
    """
    if not title:
        return None

    # 1. Crossref
    cr_candidates = _fetch_candidates_crossref(title, authors, year)
    if cr_candidates:
        cr_candidates.sort(key=lambda c: c["score"], reverse=True)
        return cr_candidates[0]

    # 2. OpenAlex (Fallback)
    oa_candidates = _fetch_candidates_openalex(title, authors, year)
    if oa_candidates:
        oa_candidates.sort(key=lambda c: c["score"], reverse=True)
        return oa_candidates[0]

    return None


def fetch_doi_by_title_and_authors(title: str, authors: list[str] = None, year: int = None) -> Optional[str]:
    """
    タイトルと著者・出版年情報をもとにベストマッチするDOI文字列を取得する。
    """
    details = fetch_doi_details(title, authors, year)
    return details["doi"] if details else None


def verify_doi_match(existing_doi: str, title: str, authors: list[str] = None, year: int = None) -> Dict[str, Any]:
    """
    既存のDOIと、タイトル等からAPI検索したDOIを検証・比較する。
    """
    details = fetch_doi_details(title, authors, year)
    if not details or not details.get("doi"):
        return {
            "is_match": True,  # APIで検出できない場合は既存DOIを妥当とみなす
            "status": "not_found",
            "existing_doi": existing_doi,
            "fetched_doi": None,
            "details": None,
        }

    fetched_doi = details["doi"]
    matched = is_doi_match(existing_doi, fetched_doi)
    return {
        "is_match": matched,
        "status": "match" if matched else "mismatch",
        "existing_doi": existing_doi,
        "fetched_doi": fetched_doi,
        "details": details,
    }
