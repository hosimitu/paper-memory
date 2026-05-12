import sys
import os
import re
import math
import argparse
import traceback
import shutil
from pathlib import Path
from dotenv import load_dotenv


def extract_with_pypdf(pdf_path, output_path):
    """Extract text using pypdf (standard fallback)"""
    print(f"Extracting text using pypdf: {pdf_path}")
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            meta = reader.metadata
            if meta:
                f.write(f"Title: {meta.get('/Title', 'Unknown')}\n")
                f.write(f"Author: {meta.get('/Author', 'Unknown')}\n")
                f.write("-" * 20 + "\n")

            for i, page in enumerate(reader.pages):
                f.write(f"\n--- Page {i+1} ---\n")
                text = page.extract_text()
                if text:
                    f.write(text)
                else:
                    f.write("(No text extracted)")
                f.write("\n\n")
        return True
    except Exception as e:
        print(f"pypdf extraction failed: {e}")
        return False


def extract_with_marker(pdf_path, output_path, light_mode=False):
    """Extract markdown using marker-pdf (high accuracy, slow)"""
    print(f"Attempting extraction using marker-pdf: {pdf_path} (Light mode: {light_mode})")
    try:
        import subprocess
        temp_dir = Path("scratch/marker_temp")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        pdf_name = Path(pdf_path).stem

        env = os.environ.copy()
        if light_mode:
            env["TORCH_DEVICE"] = "cpu"
            env["OCR_ENGINE"] = "None"
            env["EXTRACT_IMAGES"] = "True"

        cmd = ["marker_single", str(pdf_path), "--output_dir", str(temp_dir), "--output_format", "markdown"]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", env=env)

        if result.returncode != 0:
            print(f"marker-pdf failed with exit code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            return False

        generated_md = temp_dir / pdf_name / f"{pdf_name}.md"

        if generated_md.exists():
            shutil.copy2(generated_md, output_path)
            print(f"Successfully extracted with marker-pdf to: {output_path}")
            return True
        else:
            print(f"Expected output file not found: {generated_md}")
            return False

    except Exception as e:
        print(f"marker-pdf extraction failed: {e}")
        return False


def _get_styled_text_from_bbox(page, bbox, scale_factor):
    """
    指定されたbbox内のテキストを、上付き・下付き文字を考慮して抽出する。
    """
    try:
        # 座標変換 (pixel -> point)
        fitz_bbox = [b * scale_factor for b in bbox]
        
        # 辞書形式でテキスト情報を取得
        blocks = page.get_text("dict", clip=fitz_bbox)["blocks"]
        
        text_parts = []
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                spans = line["spans"]
                if not spans: continue
                
                # ライン内の平均サイズとベースラインを取得
                avg_y = sum(s["origin"][1] for s in spans) / len(spans)
                avg_size = sum(s["size"] for s in spans) / len(spans)
                
                line_text = ""
                for s in spans:
                    stext = s["text"]
                    sy = s["origin"][1]
                    ssize = s["size"]
                    
                    # 上付き・下付き判定: フォントサイズが周囲より小さく、位置が上下にズレている場合
                    is_sup = sy < (avg_y - avg_size * 0.1) and ssize < (avg_size * 0.95)
                    is_sub = sy > (avg_y + avg_size * 0.1) and ssize < (avg_size * 0.95)
                    
                    if is_sup and len(stext.strip()) > 0:
                        stext = f"<sup>{stext.strip()}</sup>"
                    elif is_sub and len(stext.strip()) > 0:
                        stext = f"<sub>{stext.strip()}</sub>"
                    
                    line_text += stext
                text_parts.append(line_text)
        
        final_text = " ".join(text_parts).strip()
        
        # 共通の科学式と脚注の補正
        if final_text:
            # 既にタグがついている場合は重複させない
            if "<sub>" not in final_text:
                final_text = final_text.replace("CO2", "CO<sub>2</sub>").replace("N2", "N<sub>2</sub>")
            
            # 脚注パターン: 数字の直後に1文字の小文字
            # 例: 160b -> 160<sup>b</sup>
            final_text = re.sub(r'(\d+)([a-z])\b', r'\1<sup>\2</sup>', final_text)
            
        return final_text
    except Exception:
        return ""


def _df_to_styled_markdown(df, page, table_obj, scale_factor):
    """
    DataFrameをMarkdown表に変換する際、PyMuPDFの情報を使ってスタイルを復元する
    """
    rows = []
    cell_map = table_obj.content
    
    for row_idx, row in df.iterrows():
        cells = []
        for col_idx, _ in enumerate(row):
            cell_obj = cell_map.get((row_idx, col_idx))
            styled_val = ""
            if cell_obj:
                styled_val = _get_styled_text_from_bbox(page, cell_obj.bbox, scale_factor)
            
            if not styled_val.strip():
                c = row[col_idx]
                val = "" if (c is None or (isinstance(c, float) and math.isnan(c))) else str(c)
                # フォールバック時も簡易補正
                val = val.replace("CO2", "CO<sub>2</sub>").replace("N2", "N<sub>2</sub>")
                val = re.sub(r'(\d+)([a-z])$', r'\1<sup>\2</sup>', val)
                styled_val = val
            
            styled_val = styled_val.replace("|", "\\|").replace("\n", " ").strip()
            cells.append(styled_val)
            
        rows.append("| " + " | ".join(cells) + " |")
        if row_idx == 0:
            rows.append("|" + " --- |" * len(cells))
            
    return "\n".join(rows)


def extract_tables_with_img2table(pdf_path):
    """img2tableでPDF全ページのテーブルを抽出し、スタイルを考慮したMarkdownリストを返す"""
    try:
        import fitz
        from img2table.document import PDF
        
        doc_fitz = fitz.open(str(pdf_path))
        # img2tableのデフォルトは 200 DPI
        doc_img = PDF(str(pdf_path))
        
        extracted = doc_img.extract_tables(
            ocr=None,
            implicit_rows=True,
            borderless_tables=True,
            min_confidence=40
        )
        
        # スケール係数 (ポイント 72 / ピクセル 200)
        scale_factor = 72 / 200
        
        result = {}
        for pg_idx, tables in extracted.items():
            if tables:
                page_fitz = doc_fitz[pg_idx]
                result[pg_idx] = [_df_to_styled_markdown(t.df, page_fitz, t, scale_factor) for t in tables]
                print(f"  img2table (Styled): Page {pg_idx+1} -> {len(tables)}個のテーブル検出")
        
        doc_fitz.close()
        return result
    except Exception as e:
        print(f"img2table styled extraction failed: {e}")
        traceback.print_exc()
        return {}


def _replace_tables_in_markdown(md_text, replacement_list):
    """
    Markdown内の崩れた表ブロック（|で始まる連続行）を置換する。
    """
    if not replacement_list:
        return md_text

    table_block_pattern = re.compile(r'((?:[ \t]*\|[^\n]*\n?)+)', re.MULTILINE)
    
    result_parts = []
    last_end = 0
    replace_idx = 0

    for match in table_block_pattern.finditer(md_text):
        if replace_idx >= len(replacement_list):
            break
        result_parts.append(md_text[last_end:match.start()])
        result_parts.append(replacement_list[replace_idx] + "\n\n")
        last_end = match.end()
        replace_idx += 1

    result_parts.append(md_text[last_end:])
    return "".join(result_parts)


def fix_table_with_llm(table_md):
    """
    LLM（Gemini）を使用して、崩れたMarkdown表を自動的に修正する。
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("  [LLM] GEMINI_API_KEYが見つからないため、表の修正をスキップします。")
        return table_md
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # 処理速度と精度のバランスから gemini-3-flash-preview を使用
        model = genai.GenerativeModel("gemini-3-flash-preview")
        
        # プロンプトを読み込み
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from paper_memory.prompts import get_table_fix_prompt
        prompt = get_table_fix_prompt(table_md)

        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # LLMの出力に会話文などが含まれている場合を考慮し、表ブロック（|で始まる行の連続）のみを正規表現で抽出
        import re
        match = re.search(r'((?:[ \t]*\|[^\n]*\n?)+)', result)
        if match:
            extracted_table = match.group(1).strip()
            if "|" in extracted_table:
                return extracted_table
    except Exception as e:
        print(f"  [LLM] 表の自動修正に失敗しました: {e}")
        
    return table_md

def _enhance_bad_tables_with_llm(md_text):
    """
    Markdownテキスト内の表をスキャンし、<br>が多用されている崩れた表をLLMで修正する。
    """
    table_block_pattern = re.compile(r'((?:[ \t]*\|[^\n]*\n?)+)', re.MULTILINE)
    
    result_parts = []
    last_end = 0
    
    for match in table_block_pattern.finditer(md_text):
        table_text = match.group(1)
        result_parts.append(md_text[last_end:match.start()])
        
        # <br>の数が一定以上なら崩れていると判定（閾値として3個以上）
        if table_text.count("<br>") >= 3:
            print("  [LLM] 崩壊した表を検知しました。LLMでレイアウト修復を試みます...")
            fixed_table = fix_table_with_llm(table_text)
            result_parts.append(fixed_table + "\n\n")
        else:
            result_parts.append(table_text)
            
        last_end = match.end()
        
    result_parts.append(md_text[last_end:])
    return "".join(result_parts)


def extract_with_pymupdf(pdf_path, output_path, enhance_tables=True):
    """Extract markdown using pymupdf4llm (fast) + img2table (accurate tables + style)"""
    print(f"Attempting extraction using pymupdf4llm: {pdf_path}")
    try:
        import pymupdf4llm

        base_dir = Path(output_path).parent
        
        # 蓄積用ディレクトリ（extracted配下）の場合は画像を直下のimagesに保存
        if "extracted" in base_dir.parts:
            image_dir = base_dir / "images"
            target_prefix = "images"
        else:
            pdf_stem = Path(pdf_path).stem
            short_dir_name = pdf_stem[:20].replace(" ", "_").strip("_")
            image_dir = base_dir / "images" / short_dir_name
            target_prefix = f"images/{short_dir_name}"
            
        image_dir.mkdir(parents=True, exist_ok=True)

        md_text = pymupdf4llm.to_markdown(
            str(pdf_path),
            write_images=True,
            image_path=str(image_dir),
            table_strategy="lines",
            header=False,
            footer=False
        )

        current_prefix = str(image_dir).replace("\\", "/")
        md_text = md_text.replace(current_prefix, target_prefix)
        md_text = md_text.replace(current_prefix.replace("/", "\\"), target_prefix)

        if enhance_tables:
            print("  img2tableでスタイル付きテーブル抽出を実行中...")
            img2table_tables = extract_tables_with_img2table(pdf_path)
            if img2table_tables:
                replacement_list = []
                for pg in sorted(img2table_tables.keys()):
                    replacement_list.extend(img2table_tables[pg])
                print(f"  合計 {len(replacement_list)} 個のテーブルを置換します")
                md_text = _replace_tables_in_markdown(md_text, replacement_list)
            
            # img2tableの置換後（または失敗時）に、残っている崩れた表（<br>を含む）をLLMで修復
            print("  LLMによる崩れた表の自動修復チェックを実行中...")
            md_text = _enhance_bad_tables_with_llm(md_text)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_text)

        print(f"Successfully extracted with pymupdf4llm to: {output_path}")
        print(f"Images saved to: {image_dir}")
        return True
    except Exception as e:
        print(f"pymupdf4llm extraction failed: {e}")
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Extract text/markdown from PDF")
    parser.add_argument("pdf_path", help="Path to input PDF")
    parser.add_argument("output_path", nargs="?", default=None, help="Legacy path to output text/markdown file (optional). Output is now systematically accumulated in the 'extracted' directory.")
    parser.add_argument("--use-marker", action="store_true", help="Use marker-pdf for high-accuracy markdown")
    parser.add_argument("--use-pymupdf", action="store_true", help="Use pymupdf4llm for fast markdown extraction")
    parser.add_argument("--light", action="store_true", help="Use lightweight settings for marker-pdf (CPU, No OCR)")
    parser.add_argument("--no-table-enhance", action="store_true", help="Skip img2table table enhancement")

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file not found at {pdf_path}")
        sys.exit(1)
        
    # PDF名からクリーンなディレクトリ名を生成
    clean_name = re.sub(r'[^\w\s-]', '', pdf_path.stem).strip().replace(' ', '_')
    acc_dir = Path("extracted") / clean_name
    acc_dir.mkdir(parents=True, exist_ok=True)
    
    # 実際の蓄積用出力パス
    actual_output_path = acc_dir / f"{clean_name}.md"

    success = False
    if args.use_marker:
        if shutil.which("marker_single"):
            success = extract_with_marker(str(pdf_path), str(actual_output_path), light_mode=args.light)
        else:
            print("marker_single command not found in PATH.")

        if not success:
            print("Falling back to pypdf...")
            success = extract_with_pypdf(str(pdf_path), str(actual_output_path))
    elif args.use_pymupdf:
        enhance = not args.no_table_enhance
        success = extract_with_pymupdf(str(pdf_path), str(actual_output_path), enhance_tables=enhance)
        if not success:
            print("Falling back to pypdf...")
            success = extract_with_pypdf(str(pdf_path), str(actual_output_path))
    else:
        success = extract_with_pypdf(str(pdf_path), str(actual_output_path))

    if not success:
        print("Failed to extract content from PDF.")
        sys.exit(1)
        
    # 過去互換性：古いワークフロー（scratch/output.mdへの出力等）を壊さないためのコピー
    if args.output_path:
        legacy_path = Path(args.output_path)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(actual_output_path, legacy_path)
        print(f"Copied output to legacy path for backward compatibility: {legacy_path}")
        
    print(f"\n[Success] 抽出結果と画像を以下のディレクトリに蓄積しました:\n  -> {acc_dir.absolute()}")

if __name__ == "__main__":
    main()
