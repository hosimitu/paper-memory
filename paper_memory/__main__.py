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
Paper Memory CLI — Gemini CLIから呼び出されるバックエンドCLI

使用例:
    python -m paper_memory add --json '{ ... }'
    python -m paper_memory search --query "膜分離技術"
    python -m paper_memory list [--paper "論文タイトル"] [--type "method"]
    python -m paper_memory link --source "id1" --target "id2" [--reason "関連理由"]
    python -m paper_memory neighbors --note-id "xxx"
    python -m paper_memory stats
    python -m paper_memory get --note-id "xxx"
    python -m paper_memory delete --note-id "xxx"
"""

import argparse
import json
import sys
import os
from pathlib import Path

from .store import NoteStore
from .note import PaperNote
from .reference import Reference, ReferenceStore


def get_project_root() -> str:
    """プロジェクトルートを取得（PAPER_MEMORY_ROOT環境変数 or カレントディレクトリ）"""
    return os.environ.get("PAPER_MEMORY_ROOT", ".")


def create_parser() -> argparse.ArgumentParser:
    """コマンドラインパーサーを作成"""
    parser = argparse.ArgumentParser(
        prog="paper_memory",
        description="Paper Memory — 論文要素蓄積システム（バックエンドCLI）",
    )
    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")

    # --- add コマンド ---
    add_parser = subparsers.add_parser("add", help="ノートを追加")
    add_parser.add_argument(
        "--json", help="追加するノートのJSON（単一オブジェクトまたは配列）",
    )
    add_parser.add_argument(
        "--stdin", action="store_true", help="標準入力からJSONを読み込む",
    )
    add_parser.add_argument(
        "--base64", help="Base64エンコードされたJSONを入力",
    )
    add_parser.add_argument(
        "--file", help="JSONファイルから読み込んで登録",
    )
    add_parser.add_argument(
        "--cleanup", action="store_true", help="登録完了後に scratch フォルダを空にする",
    )

    # --- search コマンド ---
    search_parser = subparsers.add_parser("search", help="セマンティック検索")
    search_parser.add_argument("--query", required=True, help="検索クエリ")
    search_parser.add_argument("--n", type=int, default=10, help="結果数（デフォルト: 10）")
    search_parser.add_argument("--threshold", type=float, default=None, help="距離の閾値（例: 0.45。指定すると閾値以下の結果をすべて返します）")

    # --- list コマンド ---
    list_parser = subparsers.add_parser("list", help="ノート一覧")
    list_parser.add_argument("--paper", default=None, help="論文タイトルでフィルタ")
    list_parser.add_argument("--type", default=None, help="要素タイプでフィルタ")

    # --- link コマンド ---
    link_parser = subparsers.add_parser("link", help="ノート間にリンクを追加")
    link_parser.add_argument("--source", required=True, help="リンク元ノートID")
    link_parser.add_argument("--target", required=True, help="リンク先ノートID")
    link_parser.add_argument("--reason", default="", help="リンクの理由")

    # --- unlink コマンド ---
    unlink_parser = subparsers.add_parser("unlink", help="ノート間のリンクを削除")
    unlink_parser.add_argument("--source", required=True, help="リンク元ノートID")
    unlink_parser.add_argument("--target", required=True, help="リンク先ノートID")
    unlink_parser.add_argument("--yes", action="store_true", help="確認プロンプトをスキップして削除する")

    # --- neighbors コマンド ---
    neighbors_parser = subparsers.add_parser("neighbors", help="近傍ノートを検索")
    neighbors_parser.add_argument("--note-id", required=True, help="基準ノートID")
    neighbors_parser.add_argument("--n", type=int, default=5, help="結果数（デフォルト: 5）")
    neighbors_parser.add_argument("--filter-type", default=None, help="要素タイプでフィルタリング（例: method, result）")

    # --- autolink コマンド ---
    autolink_parser = subparsers.add_parser("autolink", help="LLMによる自動リンク構築")
    autolink_parser.add_argument("--note-id", default=None, help="基準ノートID")
    autolink_parser.add_argument("--paper-title", default=None, help="論文タイトルを指定して全ノートを一括autolinkする")
    autolink_parser.add_argument("--n", type=int, default=5, help="結果数（デフォルト: 5）")
    autolink_parser.add_argument("--yes", action="store_true", help="確認プロンプトをスキップしてすべて承認する")
    autolink_parser.add_argument("--quiet", action="store_true", help="詳細を表示せず、サマリーのみ出力する（ログにはすべて記録）")
    # --- scan コマンド ---
    subparsers.add_parser("scan", help="pdf/ フォルダ内のファイルをスキャン")

    # --- stats コマンド ---
    subparsers.add_parser("stats", help="統計情報を表示")

    # --- reindex コマンド ---
    subparsers.add_parser("reindex", help="検索インデックスを再構築")

    # --- migrate コマンド ---
    migrate_parser = subparsers.add_parser("migrate", help="JSONファイルをSQLiteに移行")
    migrate_parser.add_argument("--type", required=True, choices=["notes", "refs"], help="移行する対象")

    # --- serve コマンド ---
    serve_parser = subparsers.add_parser("serve", help="Webダッシュボード用APIサーバーを起動")
    serve_parser.add_argument("--port", type=int, default=8080, help="ポート番号 (デフォルト: 8080)")

    # --- get コマンド ---
    get_parser = subparsers.add_parser("get", help="ノートを取得")
    get_parser.add_argument("--note-id", required=True, help="ノートID")

    # --- delete コマンド ---
    delete_parser = subparsers.add_parser("delete", help="ノートを削除")
    delete_parser.add_argument("--note-id", required=True, help="ノートID")

    # ========================================
    # 参考文献管理コマンド
    # ========================================

    # --- refs コマンド ---
    refs_parser = subparsers.add_parser("refs", help="参考文献一覧")
    refs_parser.add_argument("--status", default=None, help="ステータスでフィルタ（unread / done）")
    refs_parser.add_argument("--relevance", default=None, help="重要度でフィルタ（high / medium）")
    refs_parser.add_argument("--cited-by", default=None, help="引用元論文タイトルでフィルタ")
    refs_parser.add_argument("--history", action="store_true", help="完了済み履歴を表示")

    # --- refs-add コマンド ---
    refs_add_parser = subparsers.add_parser("refs-add", help="参考文献を登録")
    refs_add_parser.add_argument("--file", required=True, help="JSONファイルから読み込んで登録")
    refs_add_parser.add_argument(
        "--cleanup", action="store_true", help="登録完了後に scratch フォルダを空にする",
    )

    # --- refs-update コマンド ---
    refs_update_parser = subparsers.add_parser("refs-update", help="参考文献のステータスを更新")
    refs_update_parser.add_argument("--ref-id", required=True, help="参考文献ID")
    refs_update_parser.add_argument("--status", required=True, choices=["unread", "done", "dismissed"], help="新しいステータス")
    refs_update_parser.add_argument("--link-notes", default="", help="紐付けるノートID（カンマ区切り）")

    # --- refs-stats コマンド ---
    subparsers.add_parser("refs-stats", help="参考文献の統計情報")

    # --- cleanup コマンド ---
    subparsers.add_parser("cleanup", help="scratch フォルダの中身を削除")

    return parser


def output_json(data, indent: int = 2) -> None:
    """JSON形式で標準出力に出力"""
    print(json.dumps(data, ensure_ascii=False, indent=indent))


def cmd_add(args, store: NoteStore, ref_store: ReferenceStore) -> None:
    """ノート追加コマンド"""
    json_str = ""
    if args.base64:
        import base64
        try:
            json_str = base64.b64decode(args.base64).decode('utf-8')
        except Exception as e:
            print(f"❌ Base64デコードエラー: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                json_str = f.read()
        except Exception as e:
            print(f"❌ ファイル読み込みエラー: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.stdin:
        # 標準入力から読み込み（エンコーディングをUTF-8に強制）
        import io
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
        json_str = sys.stdin.read()
    elif args.json:
        json_str = args.json
    else:
        print("❌ エラー: --json, --file, --stdin, --base64 のいずれかが必要です", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析エラー: {e}", file=sys.stderr)
        print(f"受け取った内容の一部: {json_str[:100]}...", file=sys.stderr)
        sys.exit(1)

    # 配列なら一括追加、オブジェクトなら単一追加、または最適化フォーマット
    from .doi_fetcher import fetch_doi_by_title_and_authors
    
    if isinstance(data, list):
        # 個別のノートリストの場合（通常はsource_paperが含まれるはずだが）
        for d in data:
            sp = d.get("source_paper", {})
            if sp and sp.get("title") and not sp.get("doi"):
                print(f"🔍 メイン論文のDOIを検索中: {sp['title']}", file=sys.stderr)
                doi = fetch_doi_by_title_and_authors(sp["title"], sp.get("authors"), sp.get("year"))
                if doi:
                    sp["doi"] = doi
                    print(f"✅ DOIを取得しました: {doi}", file=sys.stderr)
        
        notes = [PaperNote.from_dict(d) for d in data]
        added = store.add_batch(notes)
        
        # 参考文献リストから自動削除
        cleaned_total = 0
        paper_titles = set()
        for d in data:
            sp = d.get("source_paper", {})
            if sp and sp.get("title"):
                paper_titles.add((sp["title"], sp.get("doi", "")))
        for title, doi in paper_titles:
            cleaned_total += ref_store.mark_done_by_title(title, doi)
        if cleaned_total > 0:
            print(f"✅ 参考文献リストから {cleaned_total} 件を完了に移動しました。", file=sys.stderr)

        output_json({
            "status": "success",
            "message": f"{len(added)}件のノートを追加しました",
            "note_ids": [n.id for n in added],
        })
    elif isinstance(data, dict):
        if "notes" in data and isinstance(data["notes"], list) and "source_paper" in data:
            # トークン節約のための最適化フォーマット
            source_paper = data["source_paper"]
            
            # DOI補完
            if source_paper.get("title") and not source_paper.get("doi"):
                print(f"🔍 メイン論文のDOIを検索中: {source_paper['title']}", file=sys.stderr)
                doi = fetch_doi_by_title_and_authors(source_paper["title"], source_paper.get("authors"), source_paper.get("year"))
                if doi:
                    source_paper["doi"] = doi
                    print(f"✅ DOIを取得しました: {doi}", file=sys.stderr)
            
            notes = []
            for d in data["notes"]:
                d["source_paper"] = source_paper
                notes.append(PaperNote.from_dict(d))
            added = store.add_batch(notes)
            
            # 参考文献リストから自動削除（タイトルまたはDOI一致）
            if source_paper.get("title"):
                count = ref_store.mark_done_by_title(source_paper["title"], source_paper.get("doi", ""))
                if count > 0:
                    print(f"✅ 参考文献リストから {count} 件を完了に移動しました。", file=sys.stderr)

            output_json({
                "status": "success",
                "message": f"{len(added)}件のノートを追加しました",
                "note_ids": [n.id for n in added],
            })
        else:
            # 単一のノートオブジェクトの場合
            sp = data.get("source_paper", {})
            if sp and sp.get("title") and not sp.get("doi"):
                print(f"🔍 メイン論文のDOIを検索中: {sp['title']}", file=sys.stderr)
                doi = fetch_doi_by_title_and_authors(sp["title"], sp.get("authors"), sp.get("year"))
                if doi:
                    sp["doi"] = doi
                    print(f"✅ DOIを取得しました: {doi}", file=sys.stderr)

            note = PaperNote.from_dict(data)
            added = store.add(note)
            
            # 参考文献リストから自動削除
            if sp and sp.get("title"):
                count = ref_store.mark_done_by_title(sp["title"], sp.get("doi", ""))
                if count > 0:
                    print(f"✅ 参考文献リストから {count} 件を完了に移動しました。", file=sys.stderr)

            output_json({
                "status": "success",
                "message": "ノートを追加しました",
                "note_id": added.id,
            })

    # scratchフォルダの掃除
    if hasattr(args, "cleanup") and args.cleanup:
        cmd_cleanup(args, store)


def cmd_search(args, store: NoteStore) -> None:
    """セマンティック検索コマンド"""
    results = store.search(args.query, args.n, distance_threshold=args.threshold)
    output_json({
        "status": "success",
        "query": args.query,
        "result_count": len(results),
        "results": results,
    })


def cmd_list(args, store: NoteStore) -> None:
    """ノート一覧コマンド"""
    if args.paper:
        notes = store.list_by_paper(args.paper)
    elif args.type:
        notes = store.list_by_type(args.type)
    else:
        notes = store.list_all()

    output_json({
        "status": "success",
        "count": len(notes),
        "notes": [n.to_dict() for n in notes],
    })


def cmd_link(args, store: NoteStore) -> None:
    """リンク追加コマンド"""
    success = store.add_link(args.source, args.target, args.reason)
    if success:
        output_json({
            "status": "success",
            "message": f"リンクを追加しました: {args.source} <-> {args.target}",
        })
    else:
        output_json({
            "status": "error",
            "message": "ノートが見つかりません",
        })
        sys.exit(1)


def cmd_unlink(args, store: NoteStore) -> None:
    """リンク削除コマンド（確認プロンプト付き）"""
    source = store.get(args.source)
    target = store.get(args.target)
    
    if not source or not target:
        print("❌ 指定されたノートが見つかりません。", file=sys.stderr)
        sys.exit(1)
        
    if args.target not in source.links:
        print("ℹ️ この2つのノートはリンクされていません。", file=sys.stderr)
        sys.exit(0)
        
    # evolution_history からリンク時の理由を取得
    link_reason = "不明"
    for h in reversed(source.evolution_history):
        if h.get("action") == "link_added" and h.get("target_id") == args.target:
            link_reason = h.get("reason", "不明")
            break

    # 削除対象の情報をユーザーに提示
    print("\n" + "="*50)
    print(f"⚠️ 以下のリンクを削除しようとしています。")
    print(f"【リンク元】[{source.element_type}] {source.source_paper.title}")
    print(f"  内容: {source.content[:50]}...")
    print(f"【リンク先】[{target.element_type}] {target.source_paper.title}")
    print(f"  内容: {target.content[:50]}...")
    print(f"【リンクされた理由】\n  {link_reason}")
    print("="*50)
    
    if args.yes:
        ans = "y"
    else:
        ans = input("本当にこのリンクを削除しますか？ [y/N]: ").strip().lower()
        
    if ans == "y":
        success = store.remove_link(args.source, args.target)
        if success:
            print("✅ リンクを削除しました。")
        else:
            print("❌ リンク削除に失敗しました。")
    else:
        print("⏭️ 削除をキャンセルしました。")


def cmd_neighbors(args, store: NoteStore) -> None:
    """近傍ノート検索コマンド"""
    # element_type_filter を find_neighbors に渡す
    results = store.find_neighbors(args.note_id, args.n, element_type_filter=args.filter_type)
    output_json({
        "status": "success",
        "base_note_id": args.note_id,
        "result_count": len(results),
        "results": results,
    })


def cmd_autolink(args, store: NoteStore) -> None:
    """自動リンク構築コマンド（一括処理・静音化対応）"""
    from .autolinker import evaluate_links
    from datetime import datetime

    if not args.note_id and not args.paper_title:
        print("❌ エラー: --note-id または --paper-title のいずれかが必要です", file=sys.stderr)
        sys.exit(1)

    target_note_ids = []
    if args.paper_title:
        notes = store.list_by_paper(args.paper_title)
        target_note_ids = [n.id for n in notes]
        if not target_note_ids:
            print(f"ℹ️ 論文 '{args.paper_title}' に紐づくノートが見つかりませんでした。", file=sys.stderr)
            return
        if not args.quiet:
            print(f"📦 論文 '{args.paper_title}' の全{len(target_note_ids)}件のノートを処理します...", file=sys.stderr)
    else:
        target_note_ids = [args.note_id]

    # ログファイルの準備
    log_file_path = f"logs/autolink_{datetime.now().strftime('%Y%m%d')}.log"
    
    # セッション開始をログに記録
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"🚀 Autolink Session: {datetime.now().isoformat()}\n")
        if args.paper_title:
            f.write(f"Target Paper: {args.paper_title}\n")
        elif args.note_id:
            n = store.get(args.note_id)
            if n:
                f.write(f"Target Note: {args.note_id} (Paper: {n.source_paper.title})\n")
        f.write(f"{'='*80}\n")

    total_added = 0
    total_evaluated = 0

    for note_id in target_note_ids:
        target_note = store.get(note_id)
        if not target_note:
            print(f"⚠️ ノートが見つかりません: {note_id}", file=sys.stderr)
            continue
            
        initial_n = args.n
        if not args.quiet:
            print(f"🔍 ノート '{note_id}' の近傍候補を検索中...", file=sys.stderr)
        
        candidates = store.find_neighbors(note_id, initial_n)
        
        # 適応型探索（ロジックは維持、出力のみ制御）
        needs_expansion = False
        if candidates:
            paper_titles = {c["note"]["source_paper"]["title"] for c in candidates}
            if len(paper_titles) <= 1 and len(candidates) >= 1:
                needs_expansion = True
            if target_note.element_type in ["definition", "insight", "background"]:
                needs_expansion = True
            distances = [c["distance"] for c in candidates if c["distance"] is not None]
            if distances:
                min_dist = min(distances)
                if min_dist > 0.4:
                    needs_expansion = True
        else:
            needs_expansion = True

        if needs_expansion and initial_n < 15:
            expanded_n = max(15, initial_n * 3)
            if not args.quiet:
                print(f"📡 探索範囲を拡大中: n={expanded_n}", file=sys.stderr)
            candidates = store.find_neighbors(note_id, expanded_n)
        
        if not candidates:
            continue
            
        if not args.quiet:
            print(f"🧠 {len(candidates)}件の候補をLLMで評価中...", file=sys.stderr)
        
        evaluations = evaluate_links(target_note.to_dict(), candidates)
        total_evaluated += len(candidates)
        
        if not evaluations:
            continue
            
        for eval_item in evaluations:
            if not eval_item.get("is_linked"):
                continue
                
            candidate_id = eval_item.get("target_id")
            reason = eval_item.get("reason", "")
            
            # 候補ノートのタイトルを取得（ログ用）
            candidate_dict = next((c for c in candidates if c["note"]["id"] == candidate_id), None)
            candidate_title = candidate_dict["note"]["source_paper"]["title"] if candidate_dict else "不明"

            # 既にリンク済みかチェック（既存リンクの取得メソッドがない場合は store.add_link の戻り値で判断）
            if not args.quiet:
                print("\n" + "="*50)
                print(f"✨ リンク候補を発見: {note_id} <-> {candidate_id}")
                print(f"📝 理由: {reason}")
                print("="*50)
            
            # ログ記録
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] ")
                f.write(f"[{target_note.source_paper.title}] {note_id} <-> ")
                f.write(f"[{candidate_title}] {candidate_id} | Reason: {reason}\n")
            
            if args.yes:
                ans = "y"
            else:
                ans = input(f"このリンクを追加しますか？ ({note_id} <-> {candidate_id}) [y/N]: ").strip().lower()
                
            if ans == "y":
                success = store.add_link(note_id, candidate_id, reason)
                if success:
                    if not args.quiet:
                        print("✅ リンクを追加しました。")
                    total_added += 1
                else:
                    if not args.quiet:
                        print("❌ リンクの追加に失敗しました。")
            else:
                if not args.quiet:
                    print("⏭️ スキップしました。")
            
    print(f"\n🎉 自動リンク構築完了: {total_added}件のリンクを追加しました（計{total_evaluated}件評価）。")
    print(f"📂 詳細ログ: {log_file_path}")


def cmd_scan(args, store: NoteStore) -> None:
    """PDFスキャンコマンド"""
    pdfs = store.list_pdfs()
    notes = store.list_all()
    
    # 登録済みのPDFパスを収集
    registered_paths = {n.source_paper.pdf_path for n in notes if n.source_paper.pdf_path}
    
    new_pdfs = [f for f in pdfs if f"pdf/{f}" not in registered_paths and f not in registered_paths]
    already_registered = [f for f in pdfs if f"pdf/{f}" in registered_paths or f in registered_paths]
    
    output_json({
        "status": "success",
        "new_pdf_count": len(new_pdfs),
        "new_pdfs": new_pdfs,
        "registered_pdf_count": len(already_registered),
        "registered_pdfs": already_registered,
        "message": f"{len(new_pdfs)}件の未登録ファイルが見つかりました。" if new_pdfs else "すべてのファイルは登録済みです。",
    })


def cmd_stats(args, store: NoteStore) -> None:
    """統計情報表示コマンド"""
    stats = store.get_stats()
    output_json({
        "status": "success",
        **stats,
    })


def cmd_cleanup(args, store: NoteStore) -> None:
    """scratch フォルダを空にする"""
    import shutil
    root = get_project_root()
    scratch_dir = Path(root) / "scratch"
    if scratch_dir.exists():
        print(f"🧹 scratch/ フォルダを掃除しています...", file=sys.stderr)
        for item in scratch_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"⚠️ 削除失敗: {item} - {e}", file=sys.stderr)
        print("✅ scratch/ フォルダを空にしました。", file=sys.stderr)
    else:
        print("ℹ️ scratch/ フォルダが存在しません。", file=sys.stderr)


def cmd_reindex(args, store: NoteStore) -> None:
    """リインデックスコマンド"""
    count = store.reindex()
    output_json({
        "status": "success",
        "message": f"{count}件のノートを再インデックスしました",
    })


def cmd_migrate(args, store: NoteStore, ref_store: ReferenceStore) -> None:
    """マイグレーションコマンド"""
    from pathlib import Path
    root = Path(get_project_root())
    backup_dir = root / "_backup"
    
    if args.type == "notes":
        notes_dir = root / "notes"
        print(f"🔄 notes/ ディレクトリのJSONをSQLiteに移行します...", file=sys.stderr)
        count = store.db.migrate_notes(notes_dir, backup_dir / "notes")
        
        # 移行した論文について参考文献リストをクリーンアップ
        if count > 0:
            all_papers = store.list_all()
            paper_info = {} # title -> doi
            for n in all_papers:
                paper_info[n.source_paper.title] = n.source_paper.doi
            
            cleaned = 0
            for title, doi in paper_info.items():
                cleaned += ref_store.mark_done_by_title(title, doi)
            if cleaned > 0:
                print(f"✅ 参考文献リストから {cleaned} 件を完了に移動しました。", file=sys.stderr)

        output_json({
            "status": "success",
            "message": f"{count}件のノートをデータベースに移行し、JSONファイルをバックアップに退避しました"
        })
    elif args.type == "refs":
        refs_dir = root / "references"
        print(f"🔄 references/ ディレクトリのJSONをSQLiteに移行します...", file=sys.stderr)
        count = store.db.migrate_references(refs_dir, backup_dir / "references")
        output_json({
            "status": "success",
            "message": f"{count}件の参考文献と履歴をデータベースに移行し、JSONファイルをバックアップに退避しました"
        })
    else:
        output_json({
            "status": "error",
            "message": "未知の移行対象です"
        })


def cmd_serve(args, store: NoteStore) -> None:
    """サーバー起動コマンド"""
    from .server import run_server
    run_server(port=args.port)


def cmd_get(args, store: NoteStore) -> None:
    """ノート取得コマンド"""
    note = store.get(args.note_id)
    if note:
        output_json({
            "status": "success",
            "note": note.to_dict(),
        })
    else:
        output_json({
            "status": "error",
            "message": f"ノートが見つかりません: {args.note_id}",
        })
        sys.exit(1)


def cmd_delete(args, store: NoteStore) -> None:
    """ノート削除コマンド"""
    success = store.delete(args.note_id)
    if success:
        output_json({
            "status": "success",
            "message": f"ノートを削除しました: {args.note_id}",
        })
    else:
        output_json({
            "status": "error",
            "message": f"ノートが見つかりません: {args.note_id}",
        })
        sys.exit(1)


# ========================================
# 参考文献管理コマンド
# ========================================

def cmd_refs(args, ref_store: ReferenceStore) -> None:
    """参考文献一覧コマンド"""
    # 完了済み履歴を表示
    if args.history:
        history = ref_store.get_history()
        output_json({
            "status": "success",
            "count": len(history),
            "history": history,
        })
        return

    # フィルタ適用
    if args.status:
        refs = ref_store.list_by_status(args.status)
    elif args.relevance:
        refs = ref_store.list_by_relevance(args.relevance)
    elif args.cited_by:
        refs = ref_store.list_by_cited_by(args.cited_by)
    else:
        refs = ref_store.list_all()

    output_json({
        "status": "success",
        "count": len(refs),
        "references": [r.to_dict() for r in refs],
    })


def cmd_refs_add(args, ref_store: ReferenceStore, note_store: NoteStore) -> None:
    """参考文献登録コマンド（重複チェック付き）"""
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            json_str = f.read()
    except Exception as e:
        print(f"❌ ファイル読み込みエラー: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        if "references" in data and isinstance(data["references"], list) and "cited_by" in data:
            # トークン節約のための最適化フォーマット
            refs = data["references"]
            for r in refs:
                r["cited_by"] = data["cited_by"]
                r["cited_by_pdf"] = data.get("cited_by_pdf", "")
            data = refs
        else:
            data = [data]

    added = []
    skipped_dup_ref = []    # 参考文献リストに既に登録済み
    skipped_dup_note = []   # 解析済みノートが既に存在

    from .doi_fetcher import fetch_doi_by_title_and_authors

    for item in data:
        title = item.get("title", "")
        doi = item.get("doi", "")
        authors = item.get("authors", [])
        year = item.get("year", None)

        if title and not doi:
            print(f"🔍 APIからDOIを検索中: {title}", file=sys.stderr)
            fetched_doi = fetch_doi_by_title_and_authors(title, authors, year)
            if fetched_doi:
                item["doi"] = fetched_doi
                doi = fetched_doi
                print(f"✅ DOIを取得しました: {doi}", file=sys.stderr)
            else:
                print(f"⚠️ DOIを取得できませんでした", file=sys.stderr)

        # 1. references/ 内で重複チェック
        existing_ref = ref_store.find_duplicate(title, doi)
        if existing_ref:
            # 除外済み(dismissed)の場合、別の論文から引用されていれば再有効化する
            if existing_ref.status == "dismissed" and existing_ref.cited_by != item.get("cited_by"):
                print(f"🔄 除外済みの参考文献を再有効化: '{title}' （新しい引用元: {item.get('cited_by')}）", file=sys.stderr)
                existing_ref.status = "unread"
                existing_ref.cited_by = item.get("cited_by")
                existing_ref.cited_by_pdf = item.get("cited_by_pdf", "")
                existing_ref.reason = item.get("reason", existing_ref.reason)
                existing_ref.updated_at = datetime.now().isoformat()
                ref_store.add(existing_ref) # 上書き保存
                added.append(existing_ref)
                continue

            print(f"⚠️ Reading Listに登録済み: '{title}' （引用元: {existing_ref.cited_by}）", file=sys.stderr)
            skipped_dup_ref.append(title)
            continue

        # 2. _history.json 内で重複チェック
        existing_history = ref_store.find_duplicate_in_history(title, doi)
        if existing_history:
            print(f"✅ 解析完了済み: '{title}'（完了日: {existing_history.get('completed_at', '不明')}）", file=sys.stderr)
            skipped_dup_ref.append(title)
            continue

        # 3. notes/ 内の source_paper で重複チェック（解析済みか確認）
        notes = note_store.list_all()
        is_analyzed = False
        for note in notes:
            sp = note.source_paper
            if doi and sp.doi and doi.strip().lower() == sp.doi.strip().lower():
                is_analyzed = True
                break
            if title and sp.title and title.strip().lower() == sp.title.strip().lower():
                is_analyzed = True
                break
        if is_analyzed:
            print(f"✅ 解析済み（ノート登録あり）: '{title}'", file=sys.stderr)
            skipped_dup_note.append(title)
            continue

        # 重複なし → 登録
        ref = Reference.from_dict(item)
        ref_store.add(ref)
        added.append(ref)

    output_json({
        "status": "success",
        "message": f"{len(added)}件の参考文献を登録しました",
        "added_count": len(added),
        "added_ids": [r.id for r in added],
        "skipped_duplicate_refs": skipped_dup_ref,
        "skipped_already_analyzed": skipped_dup_note,
    })

    # scratchフォルダの掃除
    if hasattr(args, "cleanup") and args.cleanup:
        cmd_cleanup(args, note_store)


def cmd_refs_update(args, ref_store: ReferenceStore) -> None:
    """参考文献ステータス更新コマンド"""
    if args.status == "done":
        # done → 履歴に記録してファイル削除
        linked_notes = [n.strip() for n in args.link_notes.split(",") if n.strip()] if args.link_notes else []
        success = ref_store.mark_done(args.ref_id, linked_notes)
        if success:
            output_json({
                "status": "success",
                "message": f"参考文献を完了にしました: {args.ref_id}",
            })
        else:
            output_json({
                "status": "error",
                "message": f"参考文献が見つかりません: {args.ref_id}",
            })
            sys.exit(1)
    else:
        # その他のステータス更新（unreadへの巻き戻しなど）
        ref = ref_store.get(args.ref_id)
        if ref:
            ref.status = args.status
            ref.updated_at = __import__('datetime').datetime.now().isoformat()
            ref_store.add(ref)  # 上書き保存
            output_json({
                "status": "success",
                "message": f"ステータスを更新しました: {args.ref_id} → {args.status}",
            })
        else:
            output_json({
                "status": "error",
                "message": f"参考文献が見つかりません: {args.ref_id}",
            })
            sys.exit(1)


def cmd_refs_stats(args, ref_store: ReferenceStore) -> None:
    """参考文献統計情報コマンド"""
    stats = ref_store.get_stats()
    output_json({
        "status": "success",
        **stats,
    })


def main() -> None:
    """メインエントリーポイント"""
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding.lower() != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # ストア初期化
    root = get_project_root()
    store = NoteStore(base_dir=root)
    ref_store = ReferenceStore(base_dir=root)

    # NoteStoreのみで動作するコマンド
    note_commands = {
        "add": cmd_add,
        "search": cmd_search,
        "list": cmd_list,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "autolink": cmd_autolink,
        "neighbors": cmd_neighbors,
        "scan": cmd_scan,
        "stats": cmd_stats,
        "reindex": cmd_reindex,
        "migrate": cmd_migrate,
        "serve": cmd_serve,
        "get": cmd_get,
        "delete": cmd_delete,
        "cleanup": cmd_cleanup,
    }

    # コマンドディスパッチ
    if args.command in note_commands:
        if args.command in ["add", "migrate"]:
            note_commands[args.command](args, store, ref_store)
        else:
            note_commands[args.command](args, store)
    elif args.command == "refs":
        cmd_refs(args, ref_store)
    elif args.command == "refs-add":
        cmd_refs_add(args, ref_store, store)
    elif args.command == "refs-update":
        cmd_refs_update(args, ref_store)
    elif args.command == "refs-stats":
        cmd_refs_stats(args, ref_store)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
