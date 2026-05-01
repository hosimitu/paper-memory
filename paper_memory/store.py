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
ストレージ管理 — JSON永続化 + ChromaDBベクトル検索

ノートのCRUD操作、セマンティック検索、リンク管理を担当する。
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from .note import PaperNote, SourcePaper


class NoteStore:
    """
    論文ノートのストレージ管理クラス

    - JSONファイルベースの永続化（notes/ ディレクトリ）
    - ChromaDBへのベクトル登録・検索（オプション）
    """

    def __init__(self, base_dir: str = "."):
        """
        Args:
            base_dir: プロジェクトルートディレクトリ
        """
        self.base_dir = Path(base_dir)
        self.notes_dir = self.base_dir / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)

        # インメモリインデックス（JSONから読み込み）
        self._notes: dict[str, PaperNote] = {}

        # ChromaDBクライアント（遅延初期化）
        self._chroma_client = None
        self._chroma_collection = None

        # 起動時にJSONファイルを読み込み
        self._load_all_notes()

    # ========================================
    # CRUD操作
    # ========================================

    def add(self, note: PaperNote) -> PaperNote:
        """ノートを追加・保存"""
        self._notes[note.id] = note
        self._save_note(note)
        self._add_to_chroma(note)
        return note

    def add_batch(self, notes: list[PaperNote]) -> list[PaperNote]:
        """複数ノートを一括追加（ChromaDBへの登録はバッチで行う）"""
        ids = []
        documents = []
        metadatas = []
        
        for note in notes:
            self._notes[note.id] = note
            self._save_note(note)
            
            # ChromaDB用データの準備
            ids.append(note.id)
            documents.append(self._build_search_text(note))
            metadatas.append({
                "element_type": note.element_type,
                "paper_title": note.source_paper.title,
                "timestamp": note.timestamp,
            })
            
        # ChromaDBへ一括登録
        collection = self._get_chroma_collection()
        if collection:
            try:
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
            except Exception as e:
                print(f"⚠️ ChromaDBバッチ追加エラー: {e}", file=sys.stderr)
                
        return notes

    def get(self, note_id: str) -> Optional[PaperNote]:
        """IDでノートを取得"""
        note = self._notes.get(note_id)
        if note:
            note.record_access()
            self._save_note(note)
        return note

    def update(self, note: PaperNote) -> PaperNote:
        """ノートを更新"""
        self._notes[note.id] = note
        self._save_note(note)
        self._update_chroma(note)
        return note

    def delete(self, note_id: str) -> bool:
        """ノートを削除"""
        if note_id not in self._notes:
            return False
        del self._notes[note_id]
        self._delete_note_file(note_id)
        self._delete_from_chroma(note_id)
        return True

    def list_all(self) -> list[PaperNote]:
        """全ノートを返す"""
        return list(self._notes.values())

    def list_by_paper(self, paper_title: str) -> list[PaperNote]:
        """論文タイトルでフィルタ"""
        return [
            n for n in self._notes.values()
            if paper_title.lower() in n.source_paper.title.lower()
        ]

    def list_by_type(self, element_type: str) -> list[PaperNote]:
        """要素タイプでフィルタ"""
        return [
            n for n in self._notes.values()
            if n.element_type == element_type
        ]

    def get_stats(self) -> dict:
        """統計情報を取得"""
        papers = set()
        type_counts: dict[str, int] = {}
        total_links = 0
        for note in self._notes.values():
            papers.add(note.source_paper.title)
            type_counts[note.element_type] = type_counts.get(note.element_type, 0) + 1
            total_links += len(note.links)
        return {
            "total_notes": len(self._notes),
            "total_papers": len(papers),
            "total_links": total_links,
            "type_distribution": type_counts,
        }

    # ========================================
    # セマンティック検索（ChromaDB）
    # ========================================

    def search(self, query: str, n_results: int = 5, element_type_filter: Optional[str] = None) -> list[dict]:
        """
        セマンティック検索

        Args:
            query: 検索クエリ
            n_results: 返す結果数
            element_type_filter: 指定された場合、その要素タイプで検索結果をフィルタリングします。

        Returns:
            検索結果のリスト（ノート + 類似度スコア）
        """
        collection = self._get_chroma_collection()
        if collection is None:
            # ChromaDBが利用不可の場合、キーワードベースのフォールバック
            return self._keyword_search(query, n_results)

        try:
            query_params = {
                "query_texts": [query],
                "n_results": min(n_results, len(self._notes)),
            }
            if element_type_filter:
                # ChromaDBのwhere句を使用してメタデータでフィルタリング
                query_params["where"] = {"element_type": element_type_filter}
            
            results = collection.query(**query_params)
        except Exception as e:
            print(f"⚠️ ChromaDB検索エラー: {e}", file=sys.stderr)
            return self._keyword_search(query, n_results)

        output = []
        if results and results["ids"] and results["ids"][0]:
            for i, note_id in enumerate(results["ids"][0]):
                note = self._notes.get(note_id)
                if note:
                    note.record_access()
                    self._save_note(note)
                    distance = results["distances"][0][i] if results["distances"] else None
                    output.append({
                        "note": note.to_dict(),
                        "distance": distance,
                    })
        return output

    def find_neighbors(self, note_id: str, n_results: int = 5, element_type_filter: Optional[str] = None) -> list[dict]:
        """
        指定ノートの近傍ノートを検索（リンク候補の発見用）

        Args:
            note_id: 基準ノートID
            n_results: 返す結果数
            element_type_filter: 指定された場合、その要素タイプで検索結果をフィルタリングします。

        Returns:
            近傍ノートのリスト（ノート + 類似度スコア）
        """
        note = self._notes.get(note_id)
        if not note:
            return []

        # ノートのコンテンツ + メタデータで検索
        search_text = self._build_search_text(note)
        # element_type_filter を search メソッドに渡す
        results = self.search(search_text, n_results + 1, element_type_filter=element_type_filter)

        # 自分自身を除外
        return [r for r in results if r["note"]["id"] != note_id][:n_results]

    # ========================================
    # リンク管理
    # ========================================

    def add_link(self, source_id: str, target_id: str, reason: str = "") -> bool:
        """2つのノート間にリンクを追加（双方向）"""
        source = self._notes.get(source_id)
        target = self._notes.get(target_id)
        if not source or not target:
            return False

        source.add_link(target_id, reason)
        target.add_link(source_id, reason)
        self._save_note(source)
        self._save_note(target)
        return True

    def remove_link(self, source_id: str, target_id: str) -> bool:
        """2つのノート間のリンクを削除（双方向）"""
        source = self._notes.get(source_id)
        target = self._notes.get(target_id)
        if not source or not target:
            return False

        source.remove_link(target_id)
        target.remove_link(source_id)
        self._save_note(source)
        self._save_note(target)
        return True

    def get_linked_notes(self, note_id: str) -> list[PaperNote]:
        """リンクされたノートを取得"""
        note = self._notes.get(note_id)
        if not note:
            return []
        return [self._notes[lid] for lid in note.links if lid in self._notes]

    def list_pdfs(self) -> list[str]:
        """pdf/ ディレクトリ内のPDFファイル一覧を返す"""
        pdf_dir = self.base_dir / "pdf"
        if not pdf_dir.exists():
            return []
        return [f.name for f in pdf_dir.glob("*.pdf")]

    def reindex(self, batch_size: int = 50) -> int:
        """既存の全JSONノートからChromaDBインデックスを再構築する（バッチ処理でAPIレート制限を考慮）"""
        collection = self._get_chroma_collection()
        if collection is None:
            return 0
        
        import time
        notes_list = list(self._notes.values())
        total = len(notes_list)
        count = 0
        
        print(f"🔄 {total}件のノートを再インデックスします（バッチサイズ: {batch_size}）...")
        
        for i in range(0, total, batch_size):
            batch = notes_list[i:i + batch_size]
            
            ids = [n.id for n in batch]
            documents = [self._build_search_text(n) for n in batch]
            metadatas = [{
                "element_type": n.element_type,
                "paper_title": n.source_paper.title,
                "timestamp": n.timestamp,
            } for n in batch]
            
            try:
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                count += len(batch)
                print(f"✅ {count}/{total} 件完了...")
                
                # APIレート制限（RPM 100, TPM 30K, RPD 1K）を考慮して待機
                # 50件/バッチの場合、459件なら計10回程度のAPIコール。
                # 1バッチ平均200文字×50=10,000文字(約10K token)と想定すると、TPM 30Kに収めるには分間3バッチまで。
                # 安全のため各バッチ後に20秒待機（1分間に最大3バッチ）。
                if i + batch_size < total:
                    time.sleep(20) 
            except Exception as e:
                print(f"⚠️ バッチ処理中にエラーが発生しました（インデックス {i}）: {e}", file=sys.stderr)
                # エラー時は少し長く待機して再開を試みる
                time.sleep(30)
                
        return count

    # ========================================
    # 内部メソッド: JSON永続化
    # ========================================

    def _load_all_notes(self) -> None:
        """notes/ ディレクトリ内の全JSONファイルを読み込み"""
        for json_file in self.notes_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                note = PaperNote.from_dict(data)
                self._notes[note.id] = note
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ ノート読み込みエラー ({json_file.name}): {e}", file=sys.stderr)

    def _save_note(self, note: PaperNote) -> None:
        """ノートをJSONファイルに保存"""
        file_path = self.notes_dir / f"{note.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(note.to_json())

    def _delete_note_file(self, note_id: str) -> None:
        """ノートのJSONファイルを削除"""
        file_path = self.notes_dir / f"{note_id}.json"
        if file_path.exists():
            file_path.unlink()

    # ========================================
    # 内部メソッド: ChromaDB
    # ========================================

    def _get_chroma_collection(self):
        """ChromaDBコレクションを取得（遅延初期化）"""
        if self._chroma_collection is not None:
            return self._chroma_collection

        try:
            import chromadb
            import chromadb.utils.embedding_functions as embedding_functions
            
            # .envファイルから環境変数を読み込む
            try:
                from dotenv import load_dotenv
                load_dotenv(override=True)
            except ImportError:
                pass

            db_path = str(self.base_dir / ".chromadb")
            self._chroma_client = chromadb.PersistentClient(path=db_path)
            
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                # Gemini APIによる高性能な日本語対応Embedding (gemini-embedding-2を使用)
                gemini_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
                    api_key=api_key,
                    model_name="models/gemini-embedding-2"
                )
                self._chroma_collection = self._chroma_client.get_or_create_collection(
                    name="paper_notes_gemini2",
                    embedding_function=gemini_ef,
                    metadata={"hnsw:space": "cosine"},
                )
            else:
                # APIキーがない場合はデフォルトのローカルモデルにフォールバック
                self._chroma_collection = self._chroma_client.get_or_create_collection(
                    name="paper_notes",
                    metadata={"hnsw:space": "cosine"},
                )
            return self._chroma_collection
        except ImportError:
            print("⚠️ chromadbがインストールされていません。キーワード検索にフォールバックします。", file=sys.stderr)
            return None
        except Exception as e:
            print(f"⚠️ ChromaDB初期化エラー: {e}", file=sys.stderr)
            return None

    def _build_search_text(self, note: PaperNote) -> str:
        """検索用テキストを構築（コンテンツ + メタデータを結合）"""
        parts = [note.content]
        if note.keywords:
            parts.append("キーワード: " + ", ".join(note.keywords))
        if note.context:
            parts.append("文脈: " + note.context)
        if note.tags:
            parts.append("タグ: " + ", ".join(note.tags))
        return " ".join(parts)

    def _add_to_chroma(self, note: PaperNote) -> None:
        """ChromaDBにノートを追加"""
        collection = self._get_chroma_collection()
        if collection is None:
            return
        try:
            search_text = self._build_search_text(note)
            collection.upsert(
                ids=[note.id],
                documents=[search_text],
                metadatas=[{
                    "element_type": note.element_type,
                    "paper_title": note.source_paper.title,
                    "timestamp": note.timestamp,
                }],
            )
        except Exception as e:
            print(f"⚠️ ChromaDB追加エラー: {e}", file=sys.stderr)

    def _update_chroma(self, note: PaperNote) -> None:
        """ChromaDBのノートを更新"""
        self._add_to_chroma(note)  # upsertなので同じ

    def _delete_from_chroma(self, note_id: str) -> None:
        """ChromaDBからノートを削除"""
        collection = self._get_chroma_collection()
        if collection is None:
            return
        try:
            collection.delete(ids=[note_id])
        except Exception as e:
            print(f"⚠️ ChromaDB削除エラー: {e}", file=sys.stderr)

    # ========================================
    # フォールバック: キーワード検索
    # ========================================

    def _keyword_search(self, query: str, n_results: int = 5) -> list[dict]:
        """ChromaDB未使用時のキーワードベースのフォールバック検索"""
        query_lower = query.lower()
        scored = []
        for note in self._notes.values():
            score = 0
            text = self._build_search_text(note).lower()
            # クエリの各単語についてスコアリング
            for word in query_lower.split():
                if word in text:
                    score += text.count(word)
            if score > 0:
                scored.append((score, note))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, note in scored[:n_results]:
            note.record_access()
            self._save_note(note)
            results.append({
                "note": note.to_dict(),
                "distance": None,  # キーワード検索では距離なし
            })
        return results
