# Paper Memory — 論文知識蓄積システム

A-Memの設計思想（Zettelkasten原則：原子性・リンキング・進化）に基づき、研究論文PDFから知識要素を抽出・蓄積・組織化するシステムです。

## ✨ 主な特徴とアーキテクチャ

本システムは、LLM（Gemini CLI）による高度なテキスト解析と、Pythonバックエンドによる堅牢なデータ管理を組み合わせたハイブリッド・アーキテクチャを採用しています。

- **Zettelkasten原則**: ノートの原子性を保ち、意味的な関連性に基づいたリンク構造を自動・手動で構築します。
- **セマンティック検索**: Gemini Embedding を用いた高性能な日本語のベクトル検索が可能です。
- **DOIの自動取得・検証**: 論文解析や参考文献登録時、タイトルと著者情報をもとに Crossref / OpenAlex API を用いて正しい DOI を自動補完します。

```text
[Gemini CLI (フロントエンド)]
  - PDFの読み込み・要約
  - 知識要素（背景, 手法, 結果等）への分割
  - リンク生成の判断
       ↓ シェルコマンド連携
[Pythonヘルパー (バックエンド)]
  - ChromaDBを用いたセマンティック検索
  - JSONによる確実なデータ永続化
  - DOI自動補完・リンク管理
```

---

## 🚀 セットアップ（万全な環境の構築）

本システムの全機能（高精度な検索・AIによる自動リンク生成など）をフル活用するためには、以下の3ステップをすべて実施して「万全な環境」を構築してください。

### 1. Python環境の構築 (必須)
バックエンド処理を担うPython環境をセットアップします。

```bash
cd c:\github\paper-memory
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 環境変数の設定 (強く推奨)
プロジェクトルートに `.env` ファイルを作成し、Gemini APIキーを設定します。
※ **注意**: これを設定しなくても最低限の機能（ローカルでの簡易検索やDOI取得）は動きますが、**高精度な日本語セマンティック検索や自動リンク生成機能（autolink）を利用して「万全な状態」で運用するためには必須**となります。

```bash
# PowerShellの場合
New-Item .env -ItemType File
```

`.env` に以下を記述してください:
```env
GEMINI_API_KEY="あなたのAPIキー"
```
*(APIキーは [Google AI Studio](https://aistudio.google.com/app/apikey) から無料で取得可能です)*

### 3. Gemini CLIのインストール (必須)
論文の読み込みや解析のフロントエンドとして使用します。

```bash
npm install -g @google/gemini-cli
```

### 4. 動作確認
```bash
# バックエンドの確認
python -m paper_memory stats

# フロントエンドの確認
gemini
```

---

## 📖 基本的な使い方（知識のライフサイクル）

### Step 1: 論文の解析と知識の抽出
解析したいPDFを `pdf/` フォルダに配置し、Gemini CLI経由で解析を指示します。

```bash
cd c:\github\paper-memory
gemini
```
プロンプトで以下を入力します:
```text
/paper:add pdf/your_paper_filename.pdf
```
*(自然言語で「filename.pdfを解析して」と入力しても実行可能です)*

**裏側で行われること:**
1. AIがPDFを読み込み、知識要素に分割します。
2. バックエンドがメイン論文の **DOIを自動補完** します。
3. ChromaDBとJSONにノートが保存されます。
4. AIが既存のノート群から近傍ノートを検索し、**関連リンクを自動生成** します。

### Step 2: 知識の検索と一覧
蓄積された知識はいつでも検索・閲覧できます。

```text
# セマンティック検索
/paper:search 膜分離技術の性能評価

# ノートの一覧表示
/paper:list
/paper:list method
/paper:list 論文タイトル
```

### Step 3: 知識の進化
既存ノートのリンクを再評価し、タグや文脈を自動で更新させます。

```text
/paper:evolve
```

---

## 🛠️ バックエンドCLI（手動操作・管理用）

Pythonヘルパーを直接呼び出すことで、より詳細なデータ管理や手動での操作が可能です。

### 知識ノートの管理
```bash
python -m paper_memory add --json '[{...}]'               # JSONから直接ノート追加
python -m paper_memory search --query "検索クエリ"         # 検索
python -m paper_memory list [--paper "論文名"] [--type "method"] # 一覧
python -m paper_memory link --source "id1" --target "id2" --reason "理由" # リンク手動追加
python -m paper_memory neighbors --note-id "xxx"          # 近傍ノート検索
python -m paper_memory stats                              # 統計情報の表示
python -m paper_memory get --note-id "xxx"                # ノート詳細取得
python -m paper_memory delete --note-id "xxx"             # ノート削除
```

### 参考文献 (Reading List) の管理
論文内で言及された「今後読むべき重要な文献」を追跡・管理します。（DOI自動補完対応）

```bash
python -m paper_memory refs                              # 未読一覧
python -m paper_memory refs --relevance high             # 重要度でフィルタ
python -m paper_memory refs --cited-by "論文名"          # 引用元論文でフィルタ
python -m paper_memory refs --history                    # 読了済み履歴の確認
python -m paper_memory refs-add --file refs.json         # 新規文献の登録 (JSON)
python -m paper_memory refs-update --ref-id "id" --status done  # 読了ステータスへ更新
python -m paper_memory refs-stats                        # 統計情報の表示
```

---

## 📁 データ構造

### ディレクトリ構成
```text
paper-memory/
├── GEMINI.md              # Gemini CLI用コンテキスト（システムプロンプト・ルール）
├── .gemini/               # Gemini CLI コマンド定義
├── paper_memory/          # Pythonバックエンドモジュール
│   ├── note.py            # ノートデータモデル
│   ├── reference.py       # 参考文献データモデル
│   ├── autolinker.py      # AI自動リンク構築ロジック
│   ├── doi_fetcher.py     # APIを利用したDOI自動補完ロジック
│   └── store.py           # ストレージ (JSON + ChromaDB) 管理
├── notes/                 # ノートの永続化先 (JSON)
├── references/            # 未読参考文献リスト (JSON)
│   └── _history.json      # 読了済み参考文献履歴
├── .chromadb/             # ベクトル検索インデックス (自動生成)
└── pdf/                   # 解析対象の論文PDF置き場
```

### データモデル
各ノートは以下の構造で保存されます:

| フィールド | 説明 |
|-----------|------|
| `id` | 一意なUUID |
| `content` | 知識要素の要約テキスト |
| `source_paper` | 元論文情報（タイトル, 著者, 年, DOI等） |
| `element_type` | 要素の種類（background, method, result, insight 等） |
| `keywords` | 検索用のキーワードリスト |
| `context` | 知識が活きる文脈や前提条件 |
| `tags` | 分類用タグ |
| `links` | 他ノートとの関連付け (IDリスト) |
| `evolution_history`| ノートの更新・進化の履歴 |

### 参考文献 (Reference)
| フィールド | 説明 |
|-----------|------|
| `id` | 一意なUUID |
| `title` | 文献タイトル |
| `authors` | 著者リスト |
| `year` | 出版年 |
| `doi` | DOI |
| `journal` | ジャーナル / 会議名 |
| `cited_by` | 引用元の論文タイトル |
| `relevance` | 重要度 (high / medium) |
| `reason` | 重要と判断された理由 |
| `status` | ステータス (unread / done) |

※ `status` が `done`（読了）になると、ファイルは削除され `_history.json` に履歴として移行します。
