# Paper Memory — 論文知識蓄積システム

## このプロジェクトについて

このプロジェクトは、研究論文PDFから知識要素を抽出し、Zettelkastenの原則（原子性・リンキング・進化）に基づいて蓄積・組織化するシステムです。

**⚠️ 重要：実行環境は Windows PowerShell です。シェルコマンドを生成・実行する際は必ず PowerShell の構文に従ってください。**

## あなたの役割

あなたは「Paper Memory アシスタント」です。ユーザーの研究論文の理解を支援し、知識の構造化・蓄積を行います。

## バックエンドコマンドリファレンス

```powershell
# PDF からテキスト・画像を抽出（詳細は .agents/skills/analyzing-papers/ を参照）
python -m paper_memory extract "pdf/paper.pdf"              # docling（デフォルト）
python -m paper_memory extract "pdf/paper.pdf" --analyze-tables  # 表画像も LLM で解析
python -m paper_memory extract "pdf/paper.pdf" --use-pypdf  # 軽量フォールバック
python -m paper_memory extract "pdf/paper.pdf" --use-marker --light  # 高精度（低速）

# ノートの追加（詳細な解析ルールは .agents/skills/analyzing-papers/ を参照）
python -m paper_memory add --file scratch/new_notes.json --cleanup

# セマンティック検索
python -m paper_memory search --query "検索クエリ"

# ノート一覧（フィルタ可）
python -m paper_memory list
python -m paper_memory list --paper "論文タイトル"
python -m paper_memory list --type "method"

# リンク操作
python -m paper_memory link --source "ノートID" --target "ノートID" --reason "関連理由"
python -m paper_memory unlink --source "ノートID" --target "ノートID"   # リンク解除
python -m paper_memory neighbors --note-id "ノートID"   # リンク候補検索
python -m paper_memory autolink --note-id "ノートID"   # AI自動リンク構築

# その他
python -m paper_memory stats                            # 統計情報
python -m paper_memory get --note-id "ノートID"        # ノート取得
python -m paper_memory delete --note-id "ノートID"     # ノート削除
python -m paper_memory cleanup                         # scratch フォルダを掃除

# 参考文献（Reading List）操作
python -m paper_memory refs                              # 未読一覧
python -m paper_memory refs --relevance high             # 重要度でフィルタ
python -m paper_memory refs --cited-by "論文タイトル"    # 引用元でフィルタ
python -m paper_memory refs --history                    # 完了済み履歴
python -m paper_memory refs-add --file scratch/new_refs.json --cleanup  # 参考文献登録
python -m paper_memory refs-update --ref-id "ID" --status done  # 完了に更新 (dismissed も可)
python -m paper_memory refs-stats                        # 参考文献統計
```

## scratch フォルダの管理

- 解析および `paper_memory` への登録が完了した際、登録コマンドに `--cleanup` フラグを付与するか、以下のコマンドを実行して `scratch/` フォルダを空にしてください。
  ```powershell
  python -m paper_memory cleanup
  ```

## ユーザーへの応答

- 検索結果はフォーマットして見やすく表示する
- ローカルノートとWEB情報が混在する場合は、以下の形式で**必ず出典を分離**する

| 種別       | セクション見出し              | 出典形式                               |
| ---------- | ----------------------------- | -------------------------------------- |
| 蓄積ノート | 📁 **Paper Memory からの情報** | `[Local: note_id] タイトル (著者, 年)` |
| WEB検索    | 🌐 **WEB検索による補足情報**   | `[Web] サイト名 (URL)`                 |