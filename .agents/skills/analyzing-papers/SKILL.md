---
name: analyzing-papers
description: Parses research paper PDFs and generates/registers knowledge notes. Used when extracting papers, generating notes, extracting references, and building links. Triggered by requests like "analyze this paper," "read the PDF," "generate notes," or "extract references."
---

# Paper Analysis Skill (Revised)

This revised version clarifies ambiguous constraints and defines explicit fallbacks and triggers so automated and conversational agents behave predictably.

---

## Executive Summary (Runtime Decisions)

- Follow the short MUST list below for runtime behavior. Refer to the full rules for details only when explicitly requested by the user.
- Constraint precedence (apply in order):
  1. Produce JSON that conforms to the schema exactly (see schema or minimal fallback below).
  2. Enforce exact `Type` string outputs; if no match, use `other`.
  3. If filesystem access exists, save JSON to `scratch/` as instructed; otherwise use the FILE fallback described below.
  4. Always produce bilingual `local` fields based on the `.env` `local_language` setting.

Additions in this file are explicitly marked as "CLARIFICATION" or "FALLBACK" where applicable.

---

## Basic Rules for PDF Analysis (Balancing Efficiency and Accuracy)

"When running this project, always use `dir_path="pdf"` as the default PDF location."

1. **Extraction Method Selection**: To balance speed and quality, execute in the following priority order (decision triggers are explicit):
   - **Preferred (Standard)**: High-quality extraction using `docling` (takes a few minutes)
     ```powershell
     python -m paper_memory extract "pdf/path.pdf"
     ```
     *Note: Extracts structured text and converts figures/tables to images. The extracted Markdown and images are automatically stored in the `extracted/<PDF Name>/` directory.*
   - **For High-Accuracy Table Extraction**: Run LLM-based table image analysis when the user requests `--analyze-tables` or when tables with >6 columns are detected.
     ```powershell
     python -m paper_memory extract "pdf/path.pdf" --analyze-tables
     ```
   - **Fallback for Troubleshooting**: `pypdf` (text only)
     ```powershell
     python -m paper_memory extract "pdf/path.pdf" --use-pypdf
     ```
   - **Special (marker-pdf)**: `marker-pdf` runs ONLY when the user explicitly types the trigger phrase `run marker-pdf` or `use marker-pdf`. Do not run marker-pdf otherwise.
     ```powershell
     python -m paper_memory extract "pdf/path.pdf" --use-marker --light
     ```
     *CLARIFICATION: marker-pdf is long-running and should be used only with explicit user consent (exact trigger phrase required).* 

2. **Text-First Analysis**: First base analysis on the Markdown under `extracted/`. Only access images if needed for figure/table verification.
   - **Search Efficiency**: Use the correct tool for each search type to minimize token usage and latency:
     - **File Name Search/Path Resolution** (e.g., finding PDF or Markdown files): Use the `list_dir` tool to get the directory listing, and let the agent perform pattern matching internally. Do NOT use shell commands like `dir`, `ls`, or `Get-ChildItem` for this purpose.
     - **File Content Search** (e.g., searching text inside extracted Markdown): Use the `grep_search` tool (ripgrep). Avoid reading the entire file contents or running shell commands for search.
     - **Example**: When looking for a specific paper PDF in the `pdf/` folder -> use `list_dir("pdf/")` to get the list -> filter the name yourself (do not use shell `Where-Object` or `grep`).
   - **FALLBACK**: If the agent cannot access the filesystem, request the user to upload the extracted Markdown or provide the file contents in chat.

3. **Phased Note Generation**: Recommended 3-turn workflow:
   - Turn 1: `method`, `background`, `definition`
   - Turn 2: `result`, `discussion`
   - Turn 3: `conclusion`, `limitation`, `future_work`, `insight` AND Reference Extraction (Reading List)
     - CLARIFICATION: In Turn 3, attempt to identify and register key references according to the "Reference Extraction Rules". If no applicable literature is found, explicitly return an empty `references` array (e.g., `"references": []`) and include the note `"no_references_found"`. Do NOT silently skip the step.

---

## Rules During Paper Analysis

### Atomicity

When extracting knowledge from a paper, you MUST classify each element into exactly one of the following `Type`s and you MUST output the EXACT string listed in the `Type` column (e.g., "background"). Do NOT output the `Description` or any other variations.

CLARIFICATION: If you cannot match the element to an exact canonical `Type`, you MUST use `"other"`. Only the types listed in the table above are valid.

| Type | Description |
|------|-------------|
| `background` | Background / Prior research |
| `method` | Methodology / Approach |
| `result` | Results / Experimental data |
| `discussion` | Discussion / Interpretation |
| `conclusion` | Conclusion |
| `insight` | Author's insights / Inspiration |
| `limitation` | Limitations / Challenges |
| `future_work` | Future perspectives |
| `definition` | Important term definitions |
| `other` | Other (when difficult to classify) |

### Output Format

When knowledge is extracted from a paper, it MUST be generated according to the JSON structure defined in `references/note-schema.json`.
**[CRITICAL]** Create a single JSON object containing both the `"source_paper"` information and the `"notes"` array.

**FALLBACK (file write unavailable)**: If the assistant does not have filesystem or shell access, output the JSON in a code block prefixed with the exact filename label `FILE: scratch/new_notes.json` and include exact, copy-pastable shell commands the user can run to save it. Example:

```
FILE: scratch/new_notes.json
<JSON content here>

# Commands the user can run (PowerShell):
# mkdir -Force scratch
# Set-Content -Path scratch/new_notes.json -Value '<JSON content>' -Encoding UTF8
```

**[CRITICAL BILINGUAL REQUIREMENT]** For fields defined as bilingual dictionaries (such as `content`, `context`, `keywords`, `reason`), produce both `"en"` and `"local"` keys.
- Determining `local` language: Do **not** use `get-content` or equivalent file reads on `.env` because it may contain secrets such as `GEMINI_API_KEY`.
- Prefer the `PAPER_MEMORY_LANGUAGE` environment variable if it is already set. If it is not set, default to `en`.
- If a runtime setting file is needed, use a non-secret config file and never store API keys there.
- Use the literal key name `local`; do not use ISO codes.
- `en`: Always produce English text.
- `local`: Produce text in the language specified by `PAPER_MEMORY_LANGUAGE` or `en` by default.

### Quality Standards

- Each note MUST be independently understandable.
- Numeric extraction rule (CLARIFICATION): Record all explicit numeric values from the main text, tables, figure captions, and appendices. For values only visible in figures (plots), extract numeric labels if present. If a value must be estimated from a plot, annotate it as `"estimated_from_figure"` and include an estimated uncertainty and units.
- ALWAYS specify units for numeric values.
- For separation membrane performance, include test conditions (CO2 concentration, pressure, temperature, humidity) alongside numbers.
- Identify novelty and the "core" idea; extract verification methods and limitations as presented by the authors.

---

## Minimal Schema Fallback

FALLBACK: If `references/note-schema.json` is unavailable, use this minimal schema so outputs remain consistent:

```json
{
  "source_paper": {"title": "", "authors": [], "year": "", "doi": ""},
  "notes": [
    {
      "id": "",
      "type": "", 
      "content": {"en": "", "local": ""},
      "context": {"en": "", "local": ""},
      "keywords": {"en": [], "local": []}
    }
  ]
}
```

---

## Note Registration Procedure (CLARIFIED)

After extracting the knowledge, register it using the following steps if filesystem access is available:

```powershell
# 1. Save the extracted JSON to scratch/new_notes.json in UTF-8.
# 2. Run the following command:
python -m paper_memory add --file scratch/new_notes.json --cleanup
```

If you run in `auto_register: false` mode (see Operation Mode below), instead present the FILE block and commands to the user and do not attempt to execute registration commands.

Operation mode (CLARIFICATION): Add a setting `auto_register: true|false` at runtime:
- `auto_register: true` — agent performs registration and reports the result.
- `auto_register: false` — agent writes the file (if possible) or outputs the FILE block and commands; the user runs registration.

---

## Link Generation Rules (A-Mem Evolution Principle)

(unchanged) Run `python -m paper_memory autolink --paper-title "Paper Title" --yes --quiet` after registration if desired.

---

## Reference Extraction Rules (Reading List) — CLARIFIED

Select cited literature that directly supports the core findings. If no applicable literature is found, return `"references": []` and the note `"no_references_found"` rather than skipping silently.

### Selection Criteria (ONLY if they match the following)
- Foundation works for core methods/findings.
- Papers directly compared against or improved upon.
- Works implicitly required by authors' claims.

### Exclusions
- Generic background citations.
- Standard methodology citations.
- Casual or passing citations.

### Output Format
Follow `references/reference-schema.json`. FALLBACK: If unavailable, use the analogous minimal structure and require `en` + `local` for `reason` only when `local` is confirmed. `keywords` should be a simple array of strings.

### Registration Procedure
1. If DOI is explicit in the text, include it; otherwise leave empty string `""` (do NOT invent DOIs).
2. Save JSON to `scratch/new_refs.json` and run:
```
python -m paper_memory refs-add --file scratch/new_refs.json --cleanup
```

---

## Reporting to the User

- Summarize analysis results and counts (notes added, references added, link candidates) in the user's preferred language.
- DO NOT include the generated JSON object inline unless in FILE fallback mode.
