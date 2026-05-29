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
import re
from PIL import Image
import base64

def get_markdown_path(pdf_path_str: str, title: str = "", base_dir: str = "extracted") -> Path:
    project_root = Path(__file__).parent.parent
    extracted_dir = project_root / base_dir
    
    if pdf_path_str:
        pdf_path = Path(pdf_path_str)
        stem = pdf_path.stem
        safe_stem = stem.encode('ascii', 'ignore').decode('ascii')
        if not safe_stem.strip():
            safe_stem = "paper"
        clean_name = re.sub(r'[^a-zA-Z0-9\s_-]', '', safe_stem).strip().replace(' ', '_')
        if len(clean_name) > 80:
            clean_name = clean_name[:80].rstrip('_')
        
        exact_path = extracted_dir / clean_name / f"{clean_name}.md"
        if exact_path.exists():
            return exact_path.resolve()

    if title and extracted_dir.exists():
        alphanum_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
        if alphanum_title:
            search_term = alphanum_title[:30]
            for d in extracted_dir.iterdir():
                if d.is_dir():
                    alphanum_dir = re.sub(r'[^a-zA-Z0-9]', '', d.name).lower()
                    if search_term in alphanum_dir:
                        md_files = list(d.glob("*.md"))
                        if md_files:
                            return md_files[0].resolve()
                        
    return None

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


def _flatten_link_reason(link_reason):
    if isinstance(link_reason, dict):
        return link_reason.get("en") or link_reason.get("local") or next(iter(link_reason.values()), "")
    if link_reason is None:
        return ""
    return str(link_reason)


def _format_qa_note_value(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_qa_context_payload(search_results, query_text, search_method, link_depth, expand_paper):
    citation_map = {}
    paper_to_citations = {}

    for idx, res in enumerate(search_results):
        note = res["note"]
        citation_id = idx + 1
        citation_map[note["id"]] = citation_id
        paper_title = note["source_paper"].get("title", "Unknown Paper")
        paper_to_citations.setdefault(paper_title, []).append(citation_id)

    nodes = []
    edges = []

    for idx, res in enumerate(search_results):
        note = res["note"]
        citation_id = idx + 1
        source_type = res.get("source", "direct")
        depth = res.get("depth", 0)
        linked_from_citation = None
        link_reason = _flatten_link_reason(res.get("link_reason"))

        if source_type == "linked":
            linked_from_citation = citation_map.get(res.get("linked_from"))

        same_paper_sources = []
        paper_title = note["source_paper"].get("title", "Unknown Paper")
        if source_type == "paper_expand":
            same_paper_sources = [cid for cid in paper_to_citations.get(paper_title, []) if cid != citation_id]

        nodes.append(
            {
                "citation_id": citation_id,
                "paper_title": paper_title,
                "note_type": note.get("element_type", "other"),
                "source_type": source_type,
                "depth": depth,
                "linked_from_citation_id": linked_from_citation,
                "link_reason": link_reason,
                "same_paper_sources": same_paper_sources,
                "content": _format_qa_note_value(note.get("content", "")),
                "context": _format_qa_note_value(note.get("context", "")),
            }
        )

        if source_type == "linked" and linked_from_citation is not None:
            edges.append(
                {
                    "from": linked_from_citation,
                    "to": citation_id,
                    "relation_type": "linked",
                    "depth": depth,
                    "reason": link_reason,
                }
            )

        if source_type == "paper_expand":
            for source_citation in same_paper_sources:
                edges.append(
                    {
                        "from": source_citation,
                        "to": citation_id,
                        "relation_type": "same_paper",
                        "depth": 0,
                        "reason": "Same paper context expansion",
                    }
                )

    return {
        "metadata": {
            "query": query_text,
            "search_method": search_method,
            "link_depth": link_depth,
            "expand_paper": expand_paper,
        },
        "nodes": nodes,
        "edges": edges,
    }


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
        elif path.startswith("/extracted/"):
            # extracted/ フォルダのMarkdownをプレーンテキストとして配信
            self.handle_extracted(path)
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
                            
                            md_path = get_markdown_path(note.source_paper.pdf_path, note.source_paper.title) if note.source_paper else None
                            res_data["has_markdown"] = bool(md_path and md_path.exists())
                            res_data["markdown_url"] = f"/extracted/{md_path.parent.name}/{md_path.name}" if md_path and md_path.exists() else None
                            res_data["paper_id"] = note.source_paper.id if hasattr(note.source_paper, 'id') else None

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
                                    
                                    # content が dict（多言語形式）の場合にも対応
                                    if isinstance(l_note.content, dict):
                                        _content_val = {}
                                        for k, v in l_note.content.items():
                                            vs = str(v or "")
                                            _content_val[k] = vs[:100] + ("..." if len(vs) > 100 else "")
                                    else:
                                        vs = str(l_note.content or "")
                                        _content_val = vs[:100] + ("..." if len(vs) > 100 else "")
                                        
                                    linked_notes.append({
                                        "id": l_note.id,
                                        "content": _content_val,
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
                    papers = []
                    for r in cur.fetchall():
                        p = dict(r)
                        md_path = get_markdown_path(p.get("pdf_path"), p.get("title"))
                        p["has_markdown"] = bool(md_path and md_path.exists())
                        p["markdown_url"] = f"/extracted/{md_path.parent.name}/{md_path.name}" if md_path and md_path.exists() else None

                        # サムネイル画像の検出
                        # ★ 改修点1: SVGデータを文字列として定義
                        default_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="176" height="221" viewBox="0 0 176 221">
                        <rect width="176" height="221" fill="#f5f5f5"/>
                        <rect x="18" y="20" width="140" height="180" rx="8" fill="none" stroke="#999999" stroke-width="3"/>
                        <line x1="50" y1="70" x2="126" y2="70" stroke="#bbbbbb" stroke-width="2"/>
                        <line x1="50" y1="90" x2="126" y2="90" stroke="#bbbbbb" stroke-width="2"/>
                        <line x1="50" y1="110" x2="100" y2="110" stroke="#bbbbbb" stroke-width="2"/>
                        <text x="88" y="160" text-anchor="middle" fill="#777777" font-size="20" font-family="Arial, sans-serif">NO COVER</text>
                        </svg>"""

                        # ★ 改修点2: SVG文字列をBase64に変換し、Data URI形式のURLを作成する
                        encoded_svg = base64.b64encode(default_svg.encode('utf-8')).decode('utf-8')
                        thumbnail_url = f"data:image/svg+xml;base64,{encoded_svg}"
                        if md_path and md_path.exists():
                            images_dir = md_path.parent / "images"
                            if images_dir.exists() and images_dir.is_dir():
                                image_files = [
                                    f for f in images_dir.iterdir() 
                                    if f.is_file() 
                                    and f.name.lower().startswith('picture-')
                                    and f.suffix.lower() in ('.png', '.jpg', '.jpeg')
                                ]
                                
                                best_image = None
                                TARGET_SIZE = 40 * 1024  # 目標サイズ（40kB）
                                MAX_SIZE = 60 * 1024     # ★ 上限サイズ（60kB未満）
                                MIN_SIZE = 28 * 1024     # ★ 下限サイズ（28kB以上）※あまりに小さいと表紙として不適切な可能性があるため
                                
                                min_size_difference = float('inf')
                                
                                for f in image_files:
                                    try:
                                        with Image.open(f) as img:
                                            width, height = img.size
                                            aspect_ratio = height / width
                                            
                                            # 条件1: 縦横比が表紙の範囲（1.2 〜 1.5）
                                            if 1.2 <= aspect_ratio <= 1.5:
                                                
                                                file_size = f.stat().st_size
                                                
                                                # ★ 条件2: ファイルサイズが「60kB未満」であること
                                                if MIN_SIZE < file_size < MAX_SIZE:
                                                    
                                                    # 40kBに一番近いものを選ぶ
                                                    size_difference = abs(file_size - TARGET_SIZE)
                                                    if size_difference < min_size_difference:
                                                        min_size_difference = size_difference
                                                        best_image = f
                                    except Exception:
                                        continue
                                 
                                if best_image:
                                    thumbnail_url = f"/extracted/{md_path.parent.name}/images/{best_image.name}"

                        p["thumbnail_url"] = thumbnail_url
                        
                        papers.append(p)
                    data = papers
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
                
                n = int(query.get("n", [10])[0])
                link_depth = int(query.get("link_depth", [1])[0])
                expand_paper = query.get("expand_paper", ["false"])[0].lower() == "true"
                
                search_data = store.search_with_graph(
                    q,
                    n_results=n,
                    link_depth=link_depth,
                    expand_paper=expand_paper,
                    distance_threshold=threshold,
                )
                data = {
                    "results": search_data["results"],
                    "search_method": search_data["method"],
                    "graph_stats": search_data.get("graph_stats"),
                    "query": q,
                    "threshold": threshold,
                    "n": n,
                    "link_depth": link_depth,
                    "expand_paper": expand_paper,
                    "rewritten_queries": search_data.get("rewritten_queries", []),
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

    def handle_extracted(self, path):
        """extracted/ ディレクトリのMarkdownをプレーンテキストとして配信"""
        project_root = Path(__file__).parent.parent
        extracted_dir = (project_root / "extracted").resolve()
        # URLデコード（日本語ファイル名などに対応）
        decoded_path = urllib.parse.unquote(path)
        file_path = (project_root / decoded_path.lstrip("/")).resolve()

        # ディレクトリトラバーサル防止
        if not str(file_path).startswith(str(extracted_dir)):
            self.send_response(403)
            self.end_headers()
            return

        if file_path.exists() and file_path.is_file():
            self.send_response(200)
            # Markdownはテキストとして配信することでブラウザが別タブでテキスト表示する
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
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
                    # 1. グラフ探索付き検索を実行
                    threshold = post_data.get("threshold", 0.45)
                    n_results = post_data.get("n", 15)
                    link_depth = post_data.get("link_depth", 1)
                    expand_paper = post_data.get("expand_paper", False)
                    use_ai_rewrite = post_data.get("use_ai_rewrite", True)
                    if isinstance(use_ai_rewrite, str):
                        use_ai_rewrite = use_ai_rewrite.lower() == "true"
                    else:
                        use_ai_rewrite = bool(use_ai_rewrite)
                    
                    search_data = store.search_with_graph(
                        query_text,
                        n_results=n_results,
                        link_depth=link_depth,
                        expand_paper=expand_paper,
                        distance_threshold=threshold,
                        use_ai_rewrite=use_ai_rewrite,
                    )
                    search_results = search_data["results"]
                    search_method = search_data["method"]
                    graph_stats = search_data.get("graph_stats", {})
                    
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
                    
                    # 2. プロンプト構築（リンク経由ノートの理由を注入）
                    references = []
                    for i, res in enumerate(search_results):
                        note = res["note"]
                        title = note["source_paper"]["title"]
                        note_id = note["id"]
                        ref_num = i + 1
                        source = res.get("source", "direct")

                        references.append({
                            "id": ref_num,
                            "title": title,
                            "note_id": note_id,
                            "source": source,
                            "depth": res.get("depth", 0),
                        })

                    qa_context = build_qa_context_payload(
                        search_results,
                        query_text,
                        search_method,
                        link_depth,
                        expand_paper,
                    )

                    from .prompts import get_qa_assistant_prompt
                    lang = post_data.get("lang", DEFAULT_LANGUAGE)
                    prompt = get_qa_assistant_prompt(qa_context, query_text, lang)

                    # 3. LLM呼び出し
                    from .gemini_client import generate_content_with_retry
                    
                    api_key = os.environ.get("GEMINI_API_KEY")
                    if not api_key:
                        raise ValueError("GEMINI_API_KEY is not set.")
                    
                    # リクエスト履歴を記録
                    global API_USAGE_LOG
                    API_USAGE_LOG.append(datetime.datetime.now())
                    
                    response = generate_content_with_retry(model=QA_MODEL, contents=prompt, max_retries=1)
                    
                    # 4. 後処理（思考プロセスのカット）
                    answer_text = response.text
                    if "===Answer Start===" in answer_text:
                        answer_text = answer_text.split("===Answer Start===")[-1].strip()
                    elif "===回答開始===" in answer_text:
                        # 互換性のため残す
                        answer_text = answer_text.split("===回答開始===")[-1].strip()
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
                        "graph_stats": graph_stats,
                        "rewritten_queries": search_data.get("rewritten_queries", []),
                        "api_usage": {
                            "used": update_api_usage(),
                            "limit": API_LIMIT_RPM
                        }
                    }
                    
                    # 履歴に保存
                    store.add_qa_history(
                        query_text,
                        answer_text,
                        references,
                        threshold,
                        search_method=search_method,
                        link_depth=link_depth,
                        expand_paper=expand_paper,
                        n=n_results,
                        rewritten_queries=search_data.get("rewritten_queries", []),
                    )

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
            
            elif path.startswith("/api/notes/") and path.endswith("/open-markdown"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    note_id = parts[2]
                    note = store.get(note_id)
                    if note and getattr(note, 'source_paper', None):
                        md_path = get_markdown_path(note.source_paper.pdf_path, getattr(note.source_paper, "title", ""))
                        if md_path and md_path.exists():
                            try:
                                if os.name == 'nt':
                                    os.startfile(md_path)
                                else:
                                    import subprocess
                                    import sys
                                    opener = "open" if sys.platform == "darwin" else "xdg-open"
                                    subprocess.call([opener, str(md_path)])
                                data = {"status": "success"}
                            except Exception as e:
                                status_code = 500
                                data = {"error": f"Failed to open: {e}"}
                        else:
                            status_code = 404
                            data = {"error": "Markdown file not found"}
                    else:
                        status_code = 404
                        data = {"error": "Note or PDF path not found"}
                else:
                    status_code = 400
                    data = {"error": "Invalid path"}

            elif path.startswith("/api/papers/") and path.endswith("/open-markdown"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    paper_id = parts[2]
                    with store.db.get_connection() as conn:
                        cur = conn.execute("SELECT pdf_path, title FROM papers WHERE id = ?", (paper_id,))
                        row = cur.fetchone()
                        if row:
                            md_path = get_markdown_path(row["pdf_path"], row["title"])
                            if md_path and md_path.exists():
                                try:
                                    if os.name == 'nt':
                                        os.startfile(md_path)
                                    else:
                                        import subprocess
                                        import sys
                                        opener = "open" if sys.platform == "darwin" else "xdg-open"
                                        subprocess.call([opener, str(md_path)])
                                    data = {"status": "success"}
                                except Exception as e:
                                    status_code = 500
                                    data = {"error": f"Failed to open: {e}"}
                            else:
                                status_code = 404
                                data = {"error": "Markdown file not found"}
                        else:
                            status_code = 404
                            data = {"error": "Paper or PDF path not found"}
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
                from google.genai import errors as genai_errors
                if isinstance(e, genai_errors.APIError) and getattr(e, "code", None) == 429:
                    status_code = 429
                    data = {"error": "AIへのリクエスト制限（Rate Limit）に達しました。しばらく待ってから再度お試しください。"}
                elif "429" in str(e) or "quota" in str(e).lower():
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
