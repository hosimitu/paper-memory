# Paper Memory — Research Knowledge Accumulation System

[日本語版 (Japanese)](README.md)

A system to extract, accumulate, and organize knowledge elements from research paper PDFs, based on the A-Mem design philosophy (Zettelkasten principles: Atomicity, Linking, Evolution).

## 💻 Environment

This system is developed and tested in the following environment. Shell commands and scripts are designed for **PowerShell**.

- **OS**: Windows 10/11
- **Shell**: Windows PowerShell 5.1 / PowerShell 7+
- **Python**: 3.10+
- **Node.js**: 18+ (for Gemini CLI)


## ✨ Key Features and Architecture

This system employs a hybrid architecture combining advanced text analysis via LLM (Gemini CLI) and robust data management with a Python backend.

- **Zettelkasten Principles**: Maintains note atomicity and builds link structures based on semantic relationships (both automated and manual).
- **SQLite Integration**: Centralized management of metadata and link relationships using a robust SQLite database.
- **Web Dashboard**: Beautiful browser-based visualization for intuitive knowledge exploration.
- **Semantic Search**: High-performance vector search using Gemini Embeddings (`models/gemini-embedding-2`).
- **Automatic DOI Fetching & Validation**: Automatically completes and validates DOIs using Crossref / OpenAlex APIs based on title and author metadata.
- **Flexible PDF Parsing**: Uses `docling` as the default for fast and high-precision extraction, with alternative backends (`pypdf`, `marker-pdf`) available.

```text
[Gemini CLI (Frontend)]
  - PDF reading & summarization
  - Extraction of knowledge elements (Background, Methods, Results, etc.)
  - Link generation decision making
       ↓ Shell command integration
[Python Helper (Backend)]
  - Centralized data management via SQLite (`paper_memory.db`)
  - Semantic search using ChromaDB (`.chromadb`)
  - DOI auto-completion & AI-driven link management (`autolink`)
       ↓ API delivery
[Web Dashboard (Viewer)]
  - Knowledge visualization & graph exploration
  - Dark/Light mode support
```

---

## 🚀 Setup

To fully utilize all features (high-precision search, AI-driven auto-linking, etc.), please follow these 3 steps to set up your environment.

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

### 2. Environment Variables (Highly Recommended)
Create a `.env` file in the project root and set your Gemini API key.
*Note: While basic functions (local search, DOI fetching) work without this, it is **required for high-precision semantic search and the AI-driven `autolink` feature**.*

```powershell
# Create .env file
New-Item .env -ItemType File
```

Add the following to `.env`:
```env
GEMINI_API_KEY="your_api_key_here"
```
*(You can obtain an API key for free from [Google AI Studio](https://aistudio.google.com/app/apikey))*

### 3. Gemini CLI Installation (Required)
Used as the frontend for reading and analyzing papers.

```powershell
npm install -g @google/gemini-cli
```

### 4. Verification
```powershell
# Verify backend
python -m paper_memory stats

# Verify frontend
gemini
```

---

## 📖 Basic Usage (Knowledge Lifecycle)

### Step 1: Paper Analysis and Knowledge Extraction
Place the PDF you want to analyze in the `pdf/` folder and instruct Gemini CLI to analyze it.

```powershell
cd c:\github\paper-memory
gemini
```
Enter the following in the prompt:
```text
/paper:add pdf/your_paper_filename.pdf
```
*(You can also use natural language like "Analyze pdf/filename.pdf")*

**What happens behind the scenes:**
1. AI reads the PDF and splits it into atomic knowledge elements.
2. The backend **automatically completes the DOI** for the main paper.
3. Notes are saved to the **SQLite database** and vector index (ChromaDB).
4. AI searches existing notes and **automatically generates related links**.

### Step 2: Searching and Listing Knowledge
You can search and browse your accumulated knowledge at any time.

```text
# Semantic search
/paper:search performance evaluation of membrane separation

# List notes
/paper:list
/paper:list method
/paper:list "Paper Title"
```

### Step 3: Knowledge Evolution
Re-evaluate links for existing notes and automatically update tags or context.

```text
/paper:evolve
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
python -m paper_memory extract "pdf/paper.pdf"            # Extract text from PDF
python -m paper_memory add --file scratch/notes.json      # Add notes from file
python -m paper_memory search --query "search query"      # Semantic search
python -m paper_memory list [--paper "title"]             # List notes
python -m paper_memory autolink --paper-title "title"     # AI-driven linking
python -m paper_memory serve [--port 8080]                # Start Web Dashboard
python -m paper_memory stats                              # Show statistics
python -m paper_memory delete --note-id "xxx"             # Delete note
python -m paper_memory cleanup                            # Clean scratch/ folder
```

### Reference (Reading List) Management
Track and manage "important papers to read next" mentioned in your analysis.

```powershell
python -m paper_memory refs                              # List unread references
python -m paper_memory refs --relevance high             # Filter by relevance
python -m paper_memory refs-add --file refs.json         # Register new references
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
│   ├── database.py        # SQLite schema & connection management
│   ├── server.py          # REST API server
│   ├── dashboard/         # Web dashboard static files
│   └── ...
├── paper_memory.db        # Main Database (SQLite)
├── .chromadb/             # Vector search index
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

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
For details on third-party library licenses, please refer to [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
