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

try:
    import google.generativeai as genai
    from dotenv import load_dotenv
except ImportError:
    genai = None

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

    # 環境変数の読み込み (.env)
    load_dotenv(override=True)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY 環境変数が設定されていません。自動リンク評価をスキップします。", file=sys.stderr)
        return []

    genai.configure(api_key=api_key)
    # 評価には高速かつ安価なモデルを使用
    model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

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

    prompt = f"""
あなたは学術論文の知識データベースにおける「Zettelkasten」のリンク構築アシスタントです。
以下の「ターゲットノート」と、関連する可能性のある「候補ノート」のリストを読み、
意味的・論理的な繋がり（補完、対立、前提、応用など）がある候補ノートを特定してください。
単なるキーワードの一致ではなく、「この2つを繋ぐことで新たな知見や文脈が生まれるか」を重視してください。

出力は以下のJSONスキーマに従う配列（リスト）のみを出力してください（Markdownの```jsonなどの修飾は不要です）。
[
  {{
    "target_id": "候補ノートのID",
    "is_linked": true,
    "reason": "関連する理由（日本語で、簡潔に1〜2文で）"
  }}
]
関連がない場合は is_linked を false にしてください。必ず候補ノートの数と同じ要素数の配列を返してください。

---
ターゲットノート:
{target_json}

候補ノートリスト:
{candidates_json}
"""
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        result_text = response.text.strip()
        
        # Markdownのコードブロック記法が含まれている場合は除去
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        elif result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        try:
            # JSONとしてパース
            results = json.loads(result_text)
            if not isinstance(results, list):
                results = [results]
            return results
        except json.JSONDecodeError as e:
            # 配列ではなく連続したJSONオブジェクト（{} {}...）が返された場合の救済処理
            import re
            fixed_text = re.sub(r'\}\s*\{', '},{', result_text)
            if not fixed_text.startswith('['):
                fixed_text = '[' + fixed_text + ']'
            try:
                results = json.loads(fixed_text)
                return results
            except json.JSONDecodeError:
                raise e
    except Exception as e:
        print(f"⚠️ LLMリンク評価中にエラーが発生しました: {e}", file=sys.stderr)
        return []
