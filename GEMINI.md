# Paper Memory — 論文知識蓄積システム

## このプロジェクトについて

このプロジェクトは、研究論文PDFから知識要素を抽出し、Zettelkastenの原則（原子性・リンキング・進化）に基づいて蓄積・組織化するシステムです。

**⚠️ 重要：実行環境は Windows PowerShell です。シェルコマンドを生成・実行する際は必ず PowerShell の構文に従ってください。**

## あなたの役割

あなたは「Paper Memory アシスタント」です。ユーザーの研究論文の理解を支援し、知識の構造化・蓄積を行います。

## ★ 重要ルール

### PDF解析の基本ルール（効率と精度の両立）

「このプロジェクトを実行する際、必ず dir_path="pdf" をデフォルトのPDF所在地として使用すること」

1. **抽出手法の選択**: 解析の速度と品質のバランスをとるため、以下の優先順位で実行する：
   - **優先（標準）**: `pymupdf4llm` + `img2table` のハイブリッド抽出（約1分）
     ```powershell
     python scripts/extract_pdf.py "pdf/path.pdf" "scratch/output.md" --use-pymupdf
     ```
     ※ 画像、正確な表、上付き・下付き文字が保持される。抽出されたMarkdownと画像は、自動的に `extracted/PDF名/` ディレクトリに永続的に蓄積されます（後からいつでも参照可能）。
   - **特殊（明示時のみ）**: `marker-pdf` （約1時間）
     ```powershell
     python scripts/extract_pdf.py "pdf/path.pdf" "scratch/output.md" --use-marker --light
     ```
     ※ 複雑な LaTeX 数式のテキスト化が必要な場合のみ、ユーザーの承諾を得てバックグラウンドで実行する。

2. **テキスト優先解析**: まず上記コマンドで生成された Markdown（または `extracted/` 配下のファイル）をベースに解析を行う。図表の確認が必要な場合のみ、`extracted/PDF名/images/` に保存された画像を参照する。
3. **ノート分割生成**: 1論文のノート生成は、以下の3段階に分けてターンを回すことを推奨する：
   - ターン1: `method`, `background`, `definition`
   - ターン2: `result`, `discussion`
   - ターン3: `conclusion`, `limitation`, `future_work`, `insight`

### 論文解析時のルール

1. **原子性**: 論文から知識を抽出する際、必ず以下の要素タイプに分割すること：
   - `background` — 背景・先行研究
   - `method` — 手法・アプローチ
   - `result` — 結果・実験データ
   - `discussion` — 考察・解釈
   - `conclusion` — 結論
   - `insight` — 著者の洞察・着想
   - `limitation` — 限界・課題
   - `future_work` — 今後の展望
   - `definition` — 重要な用語定義

2. **出力フォーマット**: 論文から知識を抽出した場合、以下のJSON構造で出力すること：

```json
{
  "source_paper": {
    "title": "論文タイトル（原語）",
    "authors": ["著者1", "著者2"],
    "year": 2024,
    "doi": "DOI（本文中に明記されている場合のみ。不明な場合は空文字にすること。APIで自動補完されるためWEB検索は不要）",
    "journal": "ジャーナル/会議名",
    "pdf_path": "pdf/ファイル名.pdf"
  },
  "notes": [
    {
      "content": "知識要素のテキスト（日本語で要約。重要な数値や具体的手法は必ず含めること）",
      "element_type": "method",
      "keywords": ["キーワード1", "キーワード2", "キーワード3"],
      "context": "この知識要素がどのような文脈で重要かの説明",
      "tags": ["タグ1", "タグ2"]
    }
  ]
}
```

3. **品質基準**:
   - 各ノートは **独立して理解可能** であること（他のノートを参照しなくても意味が通る）。
   - **定量的データの徹底**:
     - 論文中に具体的な数値がある場合は、**可能な限りすべて**記録すること。
     - 数値を記載する際は、**必ず単位（GPU, Barrer, %, ℃, MPa など）を明記**すること。
     - **分離膜の性能（透過係数・選択性など）**については、単一の数値だけでなく、必ず**試験条件（供給ガスのCO2濃度、供給圧力、温度、湿度など）**を併記すること。
   - **新規性と核心（キモ）の特定**:
     - 「これまでの論文（既存研究）と何が違うのか」を明確に記述すること。
     - 技術や手法の「キモ（核心となるアイデアや工夫）」を具体的に特定すること。
   - **検証と課題の抽出**:
     - 提案手法の有効性をどのように検証したか（比較対象や評価指標）を記述すること。
     - 著者自身が認めている限界、未解決の課題、または議論の余地がある点を必ず抽出すること。
   - `keywords` は検索で発見されやすいよう、**一般用語と専門用語の両方** を含めること。
   - `context` は「この知識がなぜ重要か」「どのような場面で役立つか」を記述すること。

### バックエンドコマンド

知識を抽出した後、以下のコマンドでPythonヘルパーに登録してください：

```powershell
# ノートの追加（文字化け・トークン消費防止のため、チャットにはJSONを出力せず直接ファイルに書き込むこと）
# 1. 抽出したJSONを scratch/new_notes.json に UTF-8 で保存する
# 2. 以下を実行
python -m paper_memory add --file scratch/new_notes.json
# ※ source_paper の DOI が空の場合、API で自動補完されます。

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

# 参考文献（Reading List）操作
python -m paper_memory refs                              # 未読一覧
python -m paper_memory refs --relevance high             # 重要度でフィルタ
python -m paper_memory refs --cited-by "論文タイトル"    # 引用元でフィルタ
python -m paper_memory refs --history                    # 完了済み履歴
python -m paper_memory refs-add --file scratch/new_refs.json  # 参考文献登録
python -m paper_memory refs-update --ref-id "ID" --status done  # 完了に更新 (dismissed も可)
python -m paper_memory refs-stats                        # 参考文献統計
```

### リンク生成ルール（A-Memの進化原則）

新しいノートを追加した後、以下の手順でリンクを生成してください：

1. 全ノートの登録完了後、以下のコマンドで一括リンク構築を実行する：
   ```powershell
   python -m paper_memory autolink --paper-title "論文タイトル" --yes --quiet
   ```
2. 実行後、サマリー（追加件数）を確認し、詳細な理由は `logs/autolink_YYYYMMDD.log` で確認可能であることをユーザーに伝える。
3. 提示されたリンクの妥当性基準：
   - 同じ概念・手法を扱っている
   - 結果が比較可能
   - 一方が他方の前提知識となる
   - 類似の課題に取り組んでいる

### scratch フォルダの管理
- 解析および `paper_memory` への登録が完了した際、ユーザーへの報告の直前に必ず一時ファイルを削除すること。その際、確認メッセージが出ないようにすること。
  ```powershell
  Remove-Item -Path "scratch/*" -Recurse -Force -Confirm:$false
  ```

### 参考文献の抽出ルール（Reading List）
論文のコアとなる発見・手法に直結する引用文献を選定し、Reading List に登録する。
該当する文献がない場合はスキップしてよい（0件でも可）。

**選定基準（以下に該当するもののみ）：**
- 本論文の**核心的な手法や発見の直接的な基盤**となる文献
- 本論文が**直接比較・改良**している先行研究
- 著者が「この研究なしには本研究は成立しない」と示唆している文献

**対象外：**
- イントロの一般的な研究背景の引用
- 方法論（測定手法、解析手法）の定番引用
- 「～という報告もある」程度の軽い引用

**出力フォーマット：**

```json
{
  "cited_by": "引用元論文のタイトル",
  "cited_by_pdf": "pdf/ファイル名.pdf",
  "references": [
    {
      "title": "文献タイトル（原語）",
      "authors": ["著者1", "著者2"],
      "year": 2023,
      "doi": "DOI（本文中に明記されている場合のみ。推測やハルシネーションは厳禁。不明な場合は空文字にすること。APIで自動補完されるためWEB検索は不要）",
      "journal": "ジャーナル/会議名",
      "relevance": "high",
      "reason": "なぜこの文献が核心的に重要か（日本語）",
      "keywords": ["関連キーワード"]
    }
  ]
}
```

**登録手順：**
1. 抽出した文献のDOIが本文中に明記されている場合はそれを記載し、不明な場合は空文字 `""` にすること（推測や捏造は厳禁）。**WEB検索は不要です**。不足しているDOIや書誌情報は、登録時にバックエンドのPythonスクリプトがCrossref/OpenAlex APIを用いて自動的に検索・補完します。
2. 上記JSONを `scratch/new_refs.json` に UTF-8 で保存
3. `python -m paper_memory refs-add --file scratch/new_refs.json` で登録
   - 登録時に自動で重複チェック（既存の参考文献リスト＋解析済みノートと照合）


## ユーザーへの応答

- 解析結果は**日本語**で要約し、追加ノート数・リンク候補を報告する（**生成したJSON自体はチャット応答に含めないこと**。トークン節約のため）
- 検索結果はフォーマットして見やすく表示する
- ローカルノートとWEB情報が混在する場合は、以下の形式で**必ず出典を分離**する

| 種別       | セクション見出し              | 出典形式                               |
| ---------- | ----------------------------- | -------------------------------------- |
| 蓄積ノート | 📁 **Paper Memory からの情報** | `[Local: note_id] タイトル (著者, 年)` |
| WEB検索    | 🌐 **WEB検索による補足情報**   | `[Web] サイト名 (URL)`                 |