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
Server — ダッシュボード用 REST API サーバー
"""

import http.server
import json
import urllib.parse
import os
import mimetypes
import hashlib
from pathlib import Path
from .store import NoteStore
from .reference import ReferenceStore
from .ai_models import QA_MODEL
from .config import DEFAULT_LANGUAGE
import datetime

# レート制限管理 (RPM)
API_USAGE_LOG = []
API_LIMIT_RPM = 15

def update_api_usage():
    global API_USAGE_LOG
    now = datetime.datetime.now()
    one_minute_ago = now - datetime.timedelta(minutes=1)
    # 1分より前のログを削除
    API_USAGE_LOG = [t for t in API_USAGE_LOG if t > one_minute_ago]
    return len(API_USAGE_LOG)

class PaperMemoryHandler(http.server.BaseHTTPRequestHandler):
    """
    Paper Memory ダッシュボード用の HTTP ハンドラ
    """

    def do_GET(self):
        """GET リクエストのルーティング"""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # API エンドポイント
        if path.startswith("/api/"):
            self.handle_api(path, query)
        else:
            # 静的ファイル配信
            self.handle_static(path)

    def handle_api(self, path, query):
        """API リクエストの処理"""
        store = NoteStore()
        ref_store = ReferenceStore()
        
        data = None
        status = 200

        try:
            # --- ノート関連 ---
            if path == "/api/notes":
                element_type = query.get("type", [None])[0]
                if element_type:
                    data = [n.to_dict() for n in store.list_by_type(element_type)]
                else:
                    data = [n.to_dict() for n in store.list_all()]
            elif path.startswith("/api/notes/"):
                parts = path.strip("/").split("/")
                if len(parts) >= 3:
                    note_id = parts[2]
                    if len(parts) == 4 and parts[3] == "links":
                        data = [n.to_dict() for n in store.get_linked_notes(note_id)]
                    else:
                        note = store.get(note_id)
                        if note:
                            res_data = note.to_dict()
                            linked_notes = []
                            for l_id in note.links:
                                l_note = store.get(l_id)
                                if l_note:
                                    # リンク理由の取得
                                    link_reason = ""
                                    for h in reversed(note.evolution_history):
                                        if h.get("action") == "link_added" and h.get("target_id") == l_id:
                                            link_reason = h.get("reason", "")
                                            break
                                    
                                    linked_notes.append({
                                        "id": l_note.id,
                                        "content": l_note.content[:100] + "...",
                                        "element_type": l_note.element_type,
                                        "reason": link_reason
                                    })
                            res_data["linked_notes_info"] = linked_notes
                            data = res_data
                        else:
                            status = 404
                            data = {"error": "Note not found"}
                else:
                    status = 400

            # --- 論文関連 ---
            elif path == "/api/papers":
                with store.db.get_connection() as conn:
                    cur = conn.execute("SELECT * FROM papers ORDER BY year DESC, title ASC")
                    data = [dict(r) for r in cur.fetchall()]
            elif path.startswith("/api/papers/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[3] == "notes":
                    paper_id = parts[2]
                    data = [n.to_dict() for n in store.list_by_paper_id(paper_id)]
                else:
                    status = 404

            # --- 参考文献関連 ---
            elif path == "/api/references":
                data = [r.to_dict() for r in ref_store.list_all()]
            elif path.startswith("/api/references/history"):
                data = ref_store.get_history()

            # --- 検索・統計 ---
            elif path == "/api/search":
                q = query.get("q", [""])[0]
                threshold = query.get("threshold", [None])[0]
                if threshold is not None:
                    try:
                        threshold = float(threshold)
                    except ValueError:
                        threshold = None
                
                # 閾値が指定されている場合は n_results を大きめにする
                n = int(query.get("n", [10])[0])
                search_data = store.search(q, n_results=n, distance_threshold=threshold)
                data = {
                    "results": search_data["results"],
                    "search_method": search_data["method"],
                    "query": q,
                    "threshold": threshold,
                    "n": n
                }
            elif path == "/api/qa/history":
                limit = int(query.get("limit", [10])[0])
                offset = int(query.get("offset", [0])[0])
                data = store.get_qa_history(limit=limit, offset=offset)
            elif path == "/api/stats":
                data = {
                    "notes": store.get_stats(),
                    "references": ref_store.get_stats(),
                    "api_usage": {
                        "used": update_api_usage(),
                        "limit": API_LIMIT_RPM
                    }
                }
            elif path == "/api/config":
                data = {
                    "language": DEFAULT_LANGUAGE
                }
            else:
                status = 404
                data = {"error": "Endpoint not found"}

        except Exception as e:
            status = 500
            data = {"error": str(e)}

        # レスポンス送信
        json_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        etag = f'"{hashlib.md5(json_data).hexdigest()}"'

        # ETag チェック
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.end_headers()
            return

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache") 
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        if json_data:
            self.wfile.write(json_data)

    def handle_static(self, path):
        """静的ファイルの配信 (dashboard/ ディレクトリ)"""
        if path == "/" or path == "":
            path = "/index.html"
        
        module_dir = Path(__file__).parent
        static_dir = module_dir / "dashboard"
        file_path = (static_dir / path.lstrip("/")).resolve()

        if not str(file_path).startswith(str(static_dir)):
            self.send_response(403)
            self.end_headers()
            return

        if file_path.exists() and file_path.is_file():
            self.send_response(200)
            content_type, _ = mimetypes.guess_type(str(file_path))
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """POST リクエストのルーティング"""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/"):
            # リクエストボディの読み込み
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                post_data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                post_data = {}

            self.handle_api_post(path, post_data)
        else:
            self.send_response(405)
            self.end_headers()

    def handle_api_post(self, path, post_data):
        """API POST リクエストの処理"""
        ref_store = ReferenceStore()
        store = NoteStore()
        data = {"status": "success"}
        status_code = 200

        try:
            if path == "/api/qa":
                query_text = post_data.get("query", "")
                if not query_text:
                    status_code = 400
                    data = {"error": "Query is required"}
                else:
                    # 1. 検索実行（閾値ベースで関連性の高いもののみ抽出）
                    threshold = post_data.get("threshold", 0.45)
                    n_results = post_data.get("n", 15)
                    search_data = store.search(query_text, n_results=n_results, distance_threshold=threshold)
                    search_results = search_data["results"]
                    search_method = search_data["method"]
                    
                    if not search_results:
                        # 関連ノートが見つからない場合は、AIへのプロンプト送信を中断してユーザーに通知する
                        data = {
                            "answer": f"指定された閾値（{threshold}）では関連する知識ノートが見つかりませんでした。閾値を上げて再試行するか、質問内容を変えてみてください。",
                            "references": [],
                            "status": "no_context"
                        }
                        # ここで処理を終了し、下の共通レスポンス送信へ進む
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
                        return
                    
                    # 2. プロンプト構築
                    context_lines = []
                    references = []
                    for i, res in enumerate(search_results):
                        note = res["note"]
                        title = note["source_paper"]["title"]
                        content = note["content"]
                        note_id = note["id"]
                        ref_num = i + 1
                        context_lines.append(f"[{ref_num}] Paper: {title}\nNote content: {content}\n")
                        references.append({"id": ref_num, "title": title, "note_id": note_id})
                        
                    context_str = "\n".join(context_lines)
                    
                    from .prompts import get_qa_assistant_prompt
                    lang = post_data.get("lang", DEFAULT_LANGUAGE)
                    prompt = get_qa_assistant_prompt(context_str, query_text, lang)

                    
                    # 3. LLM呼び出し
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=FutureWarning)
                        import google.generativeai as genai
                    api_key = os.environ.get("GEMINI_API_KEY")
                    if not api_key:
                        raise ValueError("GEMINI_API_KEY is not set.")
                    
                    genai.configure(api_key=api_key)
                    # ユーザー指定のモデルを使用
                    model = genai.GenerativeModel(QA_MODEL)
                    
                    # リクエスト履歴を記録
                    global API_USAGE_LOG
                    API_USAGE_LOG.append(datetime.datetime.now())
                    
                    response = model.generate_content(prompt)
                    
                    # 4. 後処理（思考プロセスのカット）
                    answer_text = response.text
                    if "===回答開始===" in answer_text:
                        answer_text = answer_text.split("===回答開始===")[-1].strip()
                    elif "===Answer Start===" in answer_text:
                        answer_text = answer_text.split("===Answer Start===")[-1].strip()
                    elif "提供された情報に" in answer_text:
                        # マーカーがない場合のフォールバック（最初の日本語らしい文から）
                        parts = answer_text.split("提供された情報に", 1)
                        if len(parts) > 1:
                            answer_text = "提供された情報に" + parts[1]
                    elif "Based on the provided information" in answer_text:
                        parts = answer_text.split("Based on the provided information", 1)
                        if len(parts) > 1:
                            answer_text = "Based on the provided information" + parts[1]
                    
                    # 引用文献リストの強制カット
                    if "📚 引用文献" in answer_text:
                        answer_text = answer_text.split("📚 引用文献")[0].strip()
                    elif "引用文献" in answer_text:
                        answer_text = answer_text.split("引用文献")[0].strip()
                        
                    data = {
                        "answer": answer_text,
                        "references": references,
                        "search_method": search_method,
                        "api_usage": {
                            "used": update_api_usage(),
                            "limit": API_LIMIT_RPM
                        }
                    }
                    
                    # 履歴に保存
                    store.add_qa_history(query_text, answer_text, references, threshold, search_method=search_method)

            elif path.startswith("/api/references/") and path.endswith("/status"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    ref_id = parts[2]
                    new_status = post_data.get("status")
                    success = False
                    
                    if new_status == "done":
                        linked_notes = post_data.get("linked_notes", [])
                        success = ref_store.mark_done(ref_id, linked_notes)
                    elif new_status in ["unread", "dismissed"]:
                        ref = ref_store.get(ref_id)
                        if ref:
                            ref.status = new_status
                            ref.updated_at = __import__('datetime').datetime.now().isoformat()
                            ref_store.add(ref)
                            success = True
                        else:
                            success = False
                    else:
                        status_code = 400
                        data = {"error": "Invalid status"}

                    if not success and status_code == 200:
                        status_code = 404
                        data = {"error": "Reference not found"}
                else:
                    status_code = 400
                    data = {"error": "Invalid path"}
            
            elif path.startswith("/api/qa/history/") and path.endswith("/delete"):
                parts = path.strip("/").split("/")
                if len(parts) == 5:
                    try:
                        history_id = int(parts[3])
                        success = store.delete_qa_history_item(history_id)
                        data = {"status": "success" if success else "not_found"}
                    except ValueError:
                        status_code = 400
                        data = {"error": "Invalid history ID"}
                else:
                    status_code = 400
                    data = {"error": "Invalid path"}

            elif path == "/api/qa/history/clear":
                store.clear_qa_history()
                data = {"status": "success"}
            else:
                status_code = 404
                data = {"error": "Endpoint not found"}

        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # 429 Too Many Requests の判定
            try:
                from google.api_core import exceptions as google_exceptions
                if isinstance(e, google_exceptions.ResourceExhausted):
                    status_code = 429
                    data = {"error": "AIへのリクエスト制限（Rate Limit）に達しました。しばらく待ってから再度お試しください。"}
                else:
                    status_code = 500
                    data = {"error": f"{type(e).__name__}: {str(e)}"}
            except ImportError:
                status_code = 500
                data = {"error": f"{type(e).__name__}: {str(e)}"}

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

def run_server(port=8080):
    """サーバーの起動"""
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, PaperMemoryHandler)
    print(f"🚀 Paper Memory Server started at http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopping...")
        httpd.server_close()
