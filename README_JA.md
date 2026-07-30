# Paper Memory — 論文知識蓄積システム

[English Version](README.md)/日本語版

Zettelkasten原則 (原子性・リンキング・進化）に基づき、研究論文PDFから知識要素を抽出・蓄積・組織化するシステムです。
GraphRAGのような特定の枠組みによるグラフ化で関連性を検索するのではなく、ノート間でそもそも関連性を記述しておき、芋づる式に情報を取得するような思想で設計しています。

## 💻 動作環境

本システムは以下の環境で開発・動作確認を行っています。特にシェルコマンドの構文は**PowerShell**を前提としています。

- **OS**: Windows 10/11
- **Shell**: Windows PowerShell 5.1/PowerShell 7+
- **Python**: 3.10+


## ✨ 主な特徴とアーキテクチャ

本システムは、Gemini APIによる高度なテキスト解析と、Pythonバックエンドによる堅牢なデータ管理を組み合わせたアーキテクチャを採用しています。

- **Zettelkasten原則**: ノートの原子性を保ち、意味的な関連性に基づいたリンク構造を自動・手動で構築します。
- **SQLiteによる一元管理**: メタデータ、リンク関係、およびベクトル埋め込みをSQLiteデータベース (`paper_memory.db`) と `sqlite-vec` で一元管理します。
- **Webダッシュボード**: 蓄積された知識をブラウザ上で美しく視覚化し、直感的な探索が可能です。PDFのアップロードと自動解析も統合されています。
- **セマンティック検索**: Gemini Embedding (`models/gemini-embedding-2`) と `sqlite-vec` を用いた高性能なベクトル検索が可能です。
- **DOIの自動取得・検証**: 論文解析や参考文献登録時、タイトルと著者情報をもとにCrossref/OpenAlex APIを用いて正しいDOIを自動補完します。
- **ハイブリッド解析**: `docling`をデフォルトとし（表画像のLLM解析も対応）、必要に応じて`pypdf`や`marker-pdf`などのバックエンドを切り替え可能な柔軟で強力なPDF解析。

```text
[Web ダッシュボード (フロントエンド)]
  - 知識の視覚化・グラフ探索
  - PDFのアップロードとステータス管理
       ↓ REST API
[Python バックエンド]
  - Gemini API連携 (知識要素の抽出, 要約, リンク生成)
  - SQLite (paper_memory.db) + sqlite-vec による一元的なデータ管理・ベクトル検索
  - DOI自動補完・自動リンク管理 (autolink)
```

---

## 🚀 セットアップ（万全な環境の構築）

本システムの全機能（高精度な検索・AIによる自動リンク生成など）をフル活用するためには、以下のステップを実施して環境を構築してください。

### 1. Python環境の構築 (必須)

バックエンド処理を担うPython環境をセットアップします。

```powershell
# プロジェクトディレクトリへ移動
cd c:\github\paper-memory

# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化 (PowerShell)
.\.venv\Scripts\Activate.ps1

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 2. 高性能PDF解析機能の利用 (任意)

本システムは、論文の図表・スタイルを正確に抽出するために複数の解析バックエンドを提供しています。

- **標準（推奨）**: `docling`
  高速かつ高精度に本文や表、画像を抽出します。通常はこのバックエンドがデフォルトで使用されます。
- **高精度**: `marker-pdf` (`--use-marker`フラグ)
  複雑なLaTeX数式などをテキスト化したい場合に使用します（手動インストール `pip install marker-pdf` が必要です）。
- **軽量**: `pypdf` (`--use-pypdf`フラグ)
  プレーンテキストのみを高速に抽出したい場合のフォールバックです。

```powershell
# PDFをMarkdownに変換して抽出する例
python -m paper_memory extract "pdf/paper.pdf"
```

### 3. 環境変数の設定 (強く推奨)

プロジェクトルートに`.env`ファイルを作成し、Gemini APIキーを設定します。
下記のコードを実行するか`.env.example`をリネームして用いてください。

```powershell
# .envファイルの作成
New-Item .env -ItemType File
```

`.env`に以下を記述してください:
```env
GEMINI_API_KEY="あなたのAPIキー"
```
（言語設定や出力先を変更したい場合は`paper_memory/config.py`を直接編集してください。）

### 4. 動作確認

```powershell
# 統計情報の確認
python -m paper_memory stats
```

---

## 📖 使い方

### ステップ 1: 論文の解析と知識抽出

Webダッシュボードを起動し、ブラウザからPDFをアップロードして解析を行います。

```powershell
cd c:\github\paper-memory
python -m paper_memory serve
```
起動後、ブラウザで**`http://localhost:8080`**にアクセスし、UI上から対象のPDFをアップロードしてください。

**裏側で実行される処理:**
1. AIがPDFを読み込み、原子的な知識要素に分割します。
2. バックエンドがメイン論文の**DOIを自動補完**します。
3. ノートとベクトル埋め込みが **SQLite データベース** に保存されます。
4. 既存ノートを検索し、関連するリンクを**AIが自動生成**します。

### ステップ 2: 知識の検索と一覧

Webダッシュボードから検索・一覧表示を行うか、バックエンドCLIを使用します。

```powershell
# セマンティック検索
python -m paper_memory search --query "膜分離技術の性能評価"

# 閾値指定および論文単位の展開付き検索
python -m paper_memory search --query "膜分離" --threshold 0.45 --expand-paper

# ノートの一覧表示
python -m paper_memory list
python -m paper_memory list --type method
python -m paper_memory list --paper "論文タイトル"
```

### ステップ 3: 知識の進化 (Evolution)

既存ノートのリンクを再評価したり、タグやコンテキストを最新の状態に自動更新します。

```powershell
# AIによる自動リンク構築
python -m paper_memory autolink --paper-title "論文タイトル"
```

### ステップ 4: 知識の視覚化 (Web Dashboard)

蓄積された知識をブラウザ上でグラフィカルに閲覧・探索できます。

```powershell
python -m paper_memory serve
```
起動後、ブラウザで**`http://localhost:8080`**にアクセスしてください。ダークモードやグラフ表示に対応しています。

---

## 🛠️ バックエンドCLI (手動操作・データ管理)

```powershell
python -m paper_memory extract "pdf/paper.pdf" [--analyze-tables] # PDFからテキスト・画像を抽出
python -m paper_memory add --file scratch/notes.json [--cleanup]   # JSONファイルからノート追加
python -m paper_memory search --query "検索クエリ" [--n 10] [--threshold 0.45] [--expand-paper]
python -m paper_memory list [--paper "論文名"] [--type "タイプ"] # ノート一覧表示
python -m paper_memory get --note-id "ノートID"                    # ノート詳細取得
python -m paper_memory link --source "ID1" --target "ID2" --reason "理由" # 手動リンク追加
python -m paper_memory unlink --source "ID1" --target "ID2"     # リンク削除
python -m paper_memory neighbors --note-id "ノートID" [--n 5]     # 近傍ノート検索
python -m paper_memory autolink --note-id "ノートID"              # 自動リンク構築（単一ノート）
python -m paper_memory autolink --paper-title "論文名" [--yes]   # 自動リンク構築（論文全体）
python -m paper_memory serve [--port 8080]                      # ダッシュボード起動
python -m paper_memory stats                                    # 統計情報の表示
python -m paper_memory scan                                     # pdf/ フォルダのスキャン
python -m paper_memory reindex                                  # ベクトル検索インデックス再構築
python -m paper_memory delete --note-id "ノートID"               # ノート削除
python -m paper_memory delete-paper --paper-id 1                # 論文・全ノート・抽出データの削除
python -m paper_memory cleanup                                  # scratch/ の掃除
```

### 参考文献 (Reading List) の管理
```powershell
python -m paper_memory refs                               # 未読参考文献一覧
python -m paper_memory refs --relevance high             # 重要度でフィルタ
python -m paper_memory refs --cited-by "論文タイトル"     # 引用元論文でフィルタ
python -m paper_memory refs --history                    # 完了済み履歴を表示
python -m paper_memory refs-add --file refs.json --cleanup # 参考文献登録
python -m paper_memory refs-update --ref-id "ID" --status done  # ステータスを読了に更新
python -m paper_memory refs-stats                        # 参考文献の統計情報
```

---

## 📁 データ構造

```text
paper-memory/
├── GEMINI.md              # Gemini CLI コンテキスト定義
├── .gemini/               # Gemini CLI コマンド定義
├── paper_memory/          # Pythonバックエンドモジュール
│   ├── database.py        # SQLite スキーマ・接続・sqlite-vec ベクトル検索管理
│   ├── server.py          # REST API サーバー
│   ├── store.py           # ノートストア ビジネスロジック
│   ├── dashboard/         # Webダッシュボード静的ファイル
│   └── ...
├── paper_memory.db        # メインデータベースおよびベクトルストア (SQLite)
├── pdf/                   # 論文PDF格納用ディレクトリ
├── extracted/             # 解析済みMarkdown・画像 (自動生成)
├── logs/                  # 実行ログ (autolink等)
└── scratch/               # 一時作業領域
```

### データモデル (ノート)

各ノートは以下の構造で保存されます:

| フィールド          | 説明                                                 |
| ------------------- | ---------------------------------------------------- |
| `id`                | 一意なUUID                                           |
| `content`           | 知識要素の要約テキスト                               |
| `source_paper`      | 元論文情報（タイトル, 著者, 年, DOI等）              |
| `element_type`      | 要素の種類（background, method, result, insight 等） |
| `keywords`          | 検索用のキーワードリスト                             |
| `context`           | 知識が活きる文脈や前提条件                           |
| `tags`              | 分類用タグ                                           |
| `links`             | 他ノートとの関連付け (IDリスト)                      |
| `evolution_history` | ノートの更新・進化の履歴                             |

### 参考文献 (Reference)

| フィールド  | 説明                       |
| ----------- | -------------------------- |
| `id`        | 一意なUUID                 |
| `title`     | 文献タイトル               |
| `authors`   | 著者リスト                 |
| `year`      | 出版年                     |
| `doi`       | DOI                        |
| `journal`   | ジャーナル / 会議名        |
| `cited_by`  | 引用元の論文タイトル       |
| `relevance` | 重要度 (high / medium)     |
| `reason`    | 重要と判断された理由       |
| `status`    | ステータス (unread / done) |

※ `status`が`done`（読了）になると、データは`reference_history`テーブルに移動し、アクティブなリストからは非表示になります。

### データベースのリセット (初期化)

システムに蓄積されたすべての知識（ノート、リンク、参考文献など）を完全にリセットして初期状態に戻したい場合は、以下のファイルを削除してください。

- `paper_memory.db` (メタデータ、リンク関係、およびベクトルインデックスを管理するSQLiteデータベース)

*(必要に応じて、抽出済みのMarkdownファイルや画像もやり直したい場合は `extracted/` フォルダの中身も併せて削除してください。)*

---

## 📄 ライセンス

本プロジェクトはApache License 2.0のもとで公開されています。詳細は[LICENSE](LICENSE)ファイルを参照してください。
また、本プロジェクトはサードパーティ製ライブラリを使用しています。そのライセンスについては[THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md)を参照してください。
