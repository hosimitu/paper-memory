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
DOI Fetcher — CrossrefおよびOpenAlexを用いたDOIと書誌情報の自動取得
"""

import json
import urllib.request
import urllib.parse
import sys
import time
from difflib import SequenceMatcher
from typing import Optional


def _similar(a: str, b: str) -> float:
    """文字列の類似度を計算（0.0 ~ 1.0）"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _fetch_doi_crossref(title: str, authors: list[str] = None) -> Optional[str]:
    """Crossref APIを使用してDOIを取得"""
    query_params = {
        "query.title": title,
        "filter": "type:journal-article",
        "select": "DOI,title,author,issued",
        "rows": "3"
    }
    # 著者がいれば最初の著者名をクエリに追加して精度を上げる
    if authors and len(authors) > 0:
        query_params["query.author"] = authors[0]
        
    url = f"https://api.crossref.org/works?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "PaperMemory/1.0 (mailto:dummy@example.com)"
    })
    
    # APIへの負荷軽減のため1秒待機
    time.sleep(1.0)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("message", {}).get("items", [])
            for item in items:
                item_title = item.get("title", [""])[0]
                # タイトルの類似度が80%以上であれば採用
                if _similar(title, item_title) >= 0.80:
                    doi = item.get("DOI")
                    if doi:
                        return doi
    except Exception as e:
        # エラー時は握りつぶさずデバッグ用に小さく出力（運用に合わせて調整）
        pass
    return None


def _fetch_doi_openalex(title: str, authors: list[str] = None) -> Optional[str]:
    """OpenAlex APIを使用してDOIを取得"""
    search_query = title
    if authors and len(authors) > 0:
        search_query += f" {authors[0]}"
        
    query_params = {
        "search": search_query,
        "filter": "type:article",
        "select": "doi,title",
        "per-page": "3"
    }
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "PaperMemory/1.0 (mailto:dummy@example.com)"
    })
    
    # APIへの負荷軽減のため1秒待機
    time.sleep(1.0)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = data.get("results", [])
            for result in results:
                item_title = result.get("title", "")
                if item_title and _similar(title, item_title) >= 0.80:
                    doi_url = result.get("doi")
                    if doi_url:
                        # OpenAlexはDOIをURL形式(https://doi.org/...)で返すためプレフィックスを除去
                        return doi_url.replace("https://doi.org/", "")
    except Exception as e:
        pass
    return None


def fetch_doi_by_title_and_authors(title: str, authors: list[str] = None, year: int = None) -> Optional[str]:
    """
    タイトルと著者情報をもとにDOIを取得する
    Crossrefを優先し、取得できなければOpenAlexにフォールバックする
    """
    if not title:
        return None
        
    # 1. Crossref
    doi = _fetch_doi_crossref(title, authors)
    if doi:
        return doi
        
    # 2. OpenAlex (Fallback)
    doi = _fetch_doi_openalex(title, authors)
    return doi
