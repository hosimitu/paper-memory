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
import json
import os
import sys

import warnings
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        import google.generativeai as genai
except ImportError:
    genai = None

from .ai_models import AUTOLINK_MODEL

def evaluate_links(target_note: dict, candidate_notes: list[dict]) -> list[dict]:
    """
    ターゲットノートと候補ノートのリストを受け取り、意味的な繋がりをLLMで評価する。
    
    Returns:
        [
            {
                "target_id": "...",
                "is_linked": True,
                "reason": "..."
            },
            ...
        ]
    """
    if genai is None:
        print("⚠️ google-generativeai がインストールされていません。", file=sys.stderr)
        return []

    # 環境変数の読み込み (config.py経由でロード済み)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY 環境変数が設定されていません。自動リンク評価をスキップします。", file=sys.stderr)
        return []

    genai.configure(api_key=api_key)
    # 評価には高速かつ安価なモデルを使用
    model = genai.GenerativeModel(AUTOLINK_MODEL)

    # ノート情報をLLMに渡すために整形
    target_json = json.dumps(target_note, ensure_ascii=False, indent=2)
    
    candidates_simplified = []
    for c in candidate_notes:
        note_data = c.get("note", {})
        candidates_simplified.append({
            "id": note_data.get("id"),
            "content": note_data.get("content"),
            "element_type": note_data.get("element_type"),
            "keywords": note_data.get("keywords", []),
            "context": note_data.get("context", "")
        })
    candidates_json = json.dumps(candidates_simplified, ensure_ascii=False, indent=2)

    from .prompts import get_autolink_prompt
    prompt = get_autolink_prompt(target_json, candidates_json)

    import time
    try:
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                break
            except Exception as e:
                if ("429" in str(e) or "quota" in str(e).lower()) and attempt < max_retries - 1:
                    wait_sec = 10 * (attempt + 1)
                    print(f"⚠️ LLMリンク評価: レート制限発生。{wait_sec}秒待機してリトライします (試行 {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_sec)
                    continue
                raise e
        result_text = response.text.strip()
        
        # Robust JSON extraction
        import json
        decoder = json.JSONDecoder()
        results = []
        text = result_text.lstrip()
        
        while text:
            try:
                obj, index = decoder.raw_decode(text)
                if isinstance(obj, list):
                    results.extend(obj)
                else:
                    results.append(obj)
                text = text[index:].lstrip()
            except json.JSONDecodeError as e:
                # If we haven't parsed anything and it fails, try to find the first '[' or '{'
                import re
                match = re.search(r'[[{]', text)
                if match and match.start() > 0:
                    text = text[match.start():]
                    continue
                else:
                    # If we already have some results, ignore the rest of the unparseable text
                    if results:
                        break
                    print(f"⚠️ JSON Decode Error. Raw text:\n{result_text[:500]}...", file=sys.stderr)
                    raise e
                    
        return results
    except Exception as e:
        print(f"⚠️ LLMリンク評価中にエラーが発生しました: {e}", file=sys.stderr)
        return []
