# Paper Memory — Research Knowledge Accumulation System

[日本語版 (Japanese)](README_JA.md)

A system to extract, accumulate, and organize knowledge elements from research paper PDFs, based on the design philosophy (Zettelkasten principles: Atomicity, Linking, Evolution).
Rather than searching for connections by generating a graph using a specific framework like GraphRAG, the system is designed based on the concept of explicitly defining relationships between notes from the outset, allowing you to retrieve information by following a chain of interconnected links.

## 💻 Environment

This system is developed and tested in the following environment. Shell commands and scripts are designed for **PowerShell**.

- **OS**: Windows 10/11
- **Shell**: Windows PowerShell 5.1/PowerShell 7+
- **Python**: 3.10+


## ✨ Key Features and Architecture

This system employs an architecture combining advanced text analysis via Gemini API and robust data management with a Python backend.

- **Zettelkasten Principles**: Maintains note atomicity and builds link structures based on semantic relationships (both automated and manual).
- **SQLite Integration**: Centralized management of metadata, link relationships, and vector embeddings using SQLite database (`paper_memory.db`) with `sqlite-vec`.
- **Web Dashboard**: Beautiful browser-based visualization for intuitive knowledge exploration. Integrated PDF upload and automated analysis.
- **Semantic Search**: High-performance vector search using Gemini Embeddings (`models/gemini-embedding-2`) powered by `sqlite-vec`.
- **Automatic DOI Fetching & Validation**: Automatically completes and validates DOIs using Crossref/OpenAlex APIs based on title and author metadata.
- **Flexible PDF Parsing**: Uses `docling` as the default for fast and high-precision extraction (including table image LLM analysis), with alternative backends (`pypdf`, `marker-pdf`) available.

```text
[Web Dashboard (Frontend)]
  - Knowledge visualization & graph exploration
  - PDF upload and status management
       ↓ REST API
[Python Backend]
  - Gemini API Integration (Extraction of knowledge elements, summarization, link generation)
  - Centralized data management & vector search via SQLite (`paper_memory.db` with `sqlite-vec`)
  - DOI auto-completion & AI-driven link management (`autolink`)
```

---

## 🚀 Setup

To fully utilize all features (high-precision search, AI-driven auto-linking, etc.), please follow these steps to set up your environment.

### 1. Python Environment Setup (Required)
Set up the Python environment for backend processing.

```powershell
# Navigate to project directory
cd c:\github\paper-memory

# Create virtual environment
python -m venv .venv

# Activate virtual environment (PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. High-Precision PDF Extraction (Optional)
The system supports multiple parsing backends:

- **Default (Recommended)**: `docling` — Fast and high-precision extraction for body text, tables, and figures.
- **High-Precision**: `marker-pdf` (`--use-marker` flag) — Useful for complex LaTeX formulas (requires manual installation `pip install marker-pdf`).
- **Lightweight**: `pypdf` (`--use-pypdf` flag) — Fast fallback for extracting plain text only.

```powershell
# Extract PDF to Markdown and images
python -m paper_memory extract "pdf/paper.pdf"
```

### 3. Environment Variables (Highly Recommended)
Create a `.env` file in the project root and set your Gemini API key.

```powershell
# Create .env file
New-Item .env -ItemType File
```

Add the following to `.env`:
```env
GEMINI_API_KEY="your_api_key_here"
```
*(If you want to change default settings, edit `paper_memory/config.py` directly.)*
*(You can obtain an API key for free from [Google AI Studio](https://aistudio.google.com/app/apikey))*

### 4. Verification
```powershell
# Verify statistics
python -m paper_memory stats
```

---

## 📖 Basic Usage (Knowledge Lifecycle)

### Step 1: Paper Analysis and Knowledge Extraction
Start the Web Dashboard and upload the PDF from your browser to analyze it.

```powershell
cd c:\github\paper-memory
python -m paper_memory serve
```
Once started, access **`http://localhost:8080`** in your browser and upload the target PDF from the UI.

**What happens behind the scenes:**
1. AI reads the PDF and splits it into atomic knowledge elements.
2. The backend **automatically completes the DOI** for the main paper.
3. Notes and vector embeddings are saved to the **SQLite database**.
4. AI searches existing notes and **automatically generates related links**.

### Step 2: Searching and Listing Knowledge
You can search and browse your accumulated knowledge from the Web Dashboard or via the backend CLI.

```powershell
# Semantic search
python -m paper_memory search --query "performance evaluation of membrane separation"

# Search with threshold & link expansion
python -m paper_memory search --query "membrane separation" --threshold 0.45 --expand-paper

# List notes
python -m paper_memory list
python -m paper_memory list --type method
python -m paper_memory list --paper "Paper Title"
```

### Step 3: Knowledge Evolution
Re-evaluate links for existing notes and automatically update tags or context.

```powershell
# AI-driven link building
python -m paper_memory autolink --paper-title "Paper Title"
```

### Step 4: Visualization (Web Dashboard)
Browse and explore your accumulated knowledge graphically in your browser.

```powershell
python -m paper_memory serve
```
Once started, access **`http://localhost:8080`** in your browser. It supports dark mode and interactive graph visualization.

---

## 🛠️ Backend CLI (Manual Operation & Management)

You can call the Python helper directly for detailed data management.

### Knowledge Note Management
```powershell
python -m paper_memory extract "pdf/paper.pdf" [--analyze-tables] [--no-footnotes] # Extract text & images from PDF (auto footnote conversion)
python -m paper_memory add --file scratch/notes.json [--cleanup]   # Add notes from JSON file
python -m paper_memory search --query "query" [--n 10] [--threshold 0.45] [--expand-paper]
python -m paper_memory list [--paper "title"] [--type "type"]    # List notes
python -m paper_memory get --note-id "id"                        # Get note details
python -m paper_memory link --source "id1" --target "id2" --reason "reason" # Add manual link
python -m paper_memory unlink --source "id1" --target "id2"     # Remove link
python -m paper_memory neighbors --note-id "id" [--n 5]          # Find neighbor notes
python -m paper_memory autolink --note-id "id"                  # AI-driven linking (single note)
python -m paper_memory autolink --paper-title "title" [--yes]   # AI-driven linking (entire paper)
python -m paper_memory serve [--port 8080]                      # Start Web Dashboard
python -m paper_memory stats                                    # Show statistics
python -m paper_memory scan                                     # Scan pdf/ folder
python -m paper_memory reindex                                  # Rebuild vector search index
python -m paper_memory delete --note-id "id"                    # Delete note
python -m paper_memory delete-paper --paper-id 1                # Delete paper, notes & markdown
python -m paper_memory cleanup                                  # Clean scratch/ folder
```

### Reference (Reading List) Management
Track and manage "important papers to read next" mentioned in your analysis.

```powershell
python -m paper_memory refs                              # List unread references
python -m paper_memory refs --relevance high             # Filter by relevance
python -m paper_memory refs --cited-by "Paper Title"     # Filter by citing paper
python -m paper_memory refs --history                    # List completed references
python -m paper_memory refs-add --file refs.json --cleanup # Register new references
python -m paper_memory refs-update --ref-id "id" --status done  # Mark as read
python -m paper_memory refs-stats                        # Show reference statistics
```

---

## 📁 Data Structure

### Directory Layout
```text
paper-memory/
├── GEMINI.md              # Gemini CLI Context (System prompt/rules)
├── .gemini/               # Gemini CLI command definitions
├── paper_memory/          # Python backend modules
│   ├── database.py        # SQLite schema, connection & sqlite-vec vector search
│   ├── server.py          # REST API server
│   ├── store.py           # Note Store business logic
│   ├── dashboard/         # Web dashboard static files
│   └── ...
├── paper_memory.db        # Main Database & Vector Store (SQLite)
├── pdf/                   # Repository for paper PDFs
├── extracted/             # Extracted Markdown & Images (Auto-generated)
├── logs/                  # Execution logs (autolink, etc.)
└── scratch/               # Temporary workspace
```

### Data Model (Note)
| Field               | Description                                                 |
| ------------------- | ----------------------------------------------------------- |
| `id`                | Unique UUID                                                 |
| `content`           | Summary text of the knowledge element                       |
| `source_paper`      | Source paper info (Title, Authors, Year, DOI, etc.)         |
| `element_type`      | Type of element (background, method, result, insight, etc.) |
| `keywords`          | Keywords for search                                         |
| `context`           | Context or prerequisites for the knowledge                  |
| `tags`              | Classification tags                                         |
| `links`             | IDs of related notes                                        |
| `evolution_history` | History of updates/evolution                                |

### Data Model (Reference)
| Field       | Description                |
| ----------- | -------------------------- |
| `id`        | Unique UUID                |
| `title`     | Paper Title                |
| `authors`   | List of Authors            |
| `year`      | Publication Year           |
| `doi`       | DOI                        |
| `journal`   | Journal / Conference Name  |
| `cited_by`  | Title of the citing paper  |
| `relevance` | Relevance (high / medium)  |
| `reason`    | Reason for high relevance  |
| `status`    | Status (unread / done)     |

*Note: When `status` becomes `done` (read), the data is moved to the `reference_history` table.*

### Database Reset (Initialization)
If you want to completely reset all accumulated knowledge (notes, links, references, etc.) and return the system to its initial state, delete the following file:

- `paper_memory.db` (SQLite database managing metadata, link relationships, and vector index)

*(Optionally, if you also want to re-do the extraction of Markdown files and images, clear the contents of the `extracted/` folder as well.)*

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
For details on third-party library licenses, please refer to [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
