# Paper Memory — 論文知識蓄積システム

[English Version](README_EN.md) / 日本語版

A-Memの設計思想（Zettelkasten原則：原子性・リンキング・進化）に基づき、研究論文PDFから知識要素を抽出・蓄積・組織化するシステムです。

## 💻 動作環境

本システムは以下の環境で開発・動作確認を行っています。特にシェルコマンドの構文は **PowerShell** を前提としています。

- **OS**: Windows 10/11
- **Shell**: Windows PowerShell 5.1 / PowerShell 7+
- **Python**: 3.10+
- **Node.js**: 18+ (Gemini CLI用)


## ✨ 主な特徴とアーキテクチャ

本システムは、LLM（Gemini CLI）による高度なテキスト解析と、Pythonバックエンドによる堅牢なデータ管理を組み合わせたハイブリッド・アーキテクチャを採用しています。

- **Zettelkasten原則**: ノートの原子性を保ち、意味的な関連性に基づいたリンク構造を自動・手動で構築します。
- **SQLiteによる一元管理**: メタデータとリンク関係を SQLite データベースで高速かつ堅牢に管理します。
- **Webダッシュボード**: 蓄積された知識をブラウザ上で美しく視覚化し、直感的な探索が可能です。
- **セマンティック検索**: Gemini Embedding を用いた高性能な日本語のベクトル検索が可能です。
- **DOIの自動取得・検証**: 論文解析や参考文献登録時、タイトルと著者情報をもとに Crossref / OpenAlex API を用いて正しい DOI を自動補完します。

```text
[Gemini CLI (フロントエンド)]
  - PDFの読み込み・要約
  - 知識要素（背景, 手法, 結果等）への分割
  - リンク生成の判断
       ↓ シェルコマンド連携
[Pythonヘルパー (バックエンド)]
  - SQLite による一元的なデータ管理
  - ChromaDB を用いたセマンティック検索
  - DOI自動補完・リンク管理
       ↓ API提供
[Web ダッシュボード (閲覧用)]
  - 知識の視覚化・グラフ探索
  - ダーク/ライトモード対応
```

---

## 🚀 セットアップ（万全な環境の構築）

本システムの全機能（高精度な検索・AIによる自動リンク生成など）をフル活用するためには、以下の3ステップをすべて実施して「万全な環境」を構築してください。

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

### 2. 高性能PDF解析機能の有効化
本システムは、論文の図表・スタイルを正確に抽出するためにハイブリッド解析パイプラインを採用しています。

- **標準（推奨）**: `pymupdf4llm` + `img2table`
  本文・画像抽出に加え、画像処理ベースで表を正確に認識します。上付き・下付き文字も復元されます。
- **高精度**: `marker-pdf`
  複雑な LaTeX 数式をテキスト化したい場合に使用します（実行に時間がかかります）。

```powershell
# PDFをMarkdownに変換する例
python scripts/extract_pdf.py "pdf/paper.pdf" "scratch/output.md" --use-pymupdf
```

### 3. データのマイグレーション (既存ユーザーのみ)
既存の JSON データがある場合は、以下のコマンドで SQLite へ移行します。

```powershell
python -m paper_memory migrate --type notes
python -m paper_memory migrate --type refs
```

### 3. 環境変数の設定 (強く推奨)
プロジェクトルートに `.env` ファイルを作成し、Gemini APIキーを設定します。

```powershell
# .envファイルの作成
New-Item .env -ItemType File
```

`.env` に以下を記述してください:
```env
GEMINI_API_KEY="あなたのAPIキー"
```

---

## 📖 使い方

### 1. 知識を蓄積する (Gemini CLI)
解析したいPDFを `pdf/` フォルダに配置し、Gemini CLI経由で解析を指示します。

```powershell
gemini
# プロンプトで以下を入力
/paper:add pdf/your_paper_filename.pdf
```

### 2. 知識をブラウズする (Web Dashboard)
蓄積された知識を視覚的にブラウズするには、ダッシュボードを起動します。

```powershell
# サーバーの起動
python -m paper_memory serve
```
起動後、ブラウザで **`http://localhost:8080`** にアクセスしてください。

### 3. 知識を検索・管理する (CLI)
Gemini CLI または直接のコマンドから検索が可能です。

```text
# セマンティック検索
/paper:search 膜分離技術の性能評価
```

---

## 🛠️ バックエンドCLI

```powershell
python -m paper_memory stats                              # 統計情報の表示
python -m paper_memory list [--paper "論文名"]             # 一覧
python -m paper_memory search --query "検索クエリ"         # 検索
python -m paper_memory serve [--port 8080]                # ダッシュボード起動
python -m paper_memory migrate --type [notes|refs]        # JSONからDBへの移行
```

---

## 📁 データ構造

```text
paper-memory/
├── paper_memory/          # Pythonバックエンドモジュール
│   ├── database.py        # SQLite スキーマ・接続管理 (NEW)
│   ├── server.py          # REST API サーバー (NEW)
│   ├── dashboard/         # Webダッシュボード静的ファイル (NEW)
│   └── ...
├── paper_memory.db        # メインデータベース (SQLite)
├── .chromadb/             # ベクトル検索インデックス
├── pdf/                   # 論文PDF
└── _backup/               # 移行済みJSONの退避先
```


### データモデル
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

※ `status` が `done`（読了）になると、ファイルは削除され `_history.json` に履歴として移行します。

---

## 📄 ライセンス

本プロジェクトは Apache License 2.0 のもとで公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。
また、本プロジェクトはサードパーティ製ライブラリを使用しています。そのライセンスについては [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) を参照してください。
