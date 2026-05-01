# Paper Memory — Research Knowledge Accumulation System

[日本語版 (Japanese)](README.md)

A system to extract, accumulate, and organize knowledge elements from research paper PDFs, based on the A-Mem design philosophy (Zettelkasten principles: Atomicity, Linking, Evolution).

## ✨ Key Features and Architecture

This system employs a hybrid architecture combining advanced text analysis via LLM (Gemini CLI) and robust data management with a Python backend.

- **Zettelkasten Principles**: Maintains note atomicity and builds link structures based on semantic relationships (both automated and manual).
- **Semantic Search**: High-performance Japanese/English vector search using Gemini Embeddings.
- **Automatic DOI Fetching & Validation**: Automatically completes and validates DOIs using Crossref / OpenAlex APIs based on title and author metadata during analysis.

```text
[Gemini CLI (Frontend)]
  - PDF reading & summarization
  - Extraction of knowledge elements (Background, Methods, Results, etc.)
  - Link generation decision making
       ↓ Shell command integration
[Python Helper (Backend)]
  - Semantic search using ChromaDB
  - Reliable data persistence via JSON
  - DOI auto-completion & Link management
```

---

## 🚀 Setup

To fully utilize all features (high-precision search, AI-driven auto-linking, etc.), please follow these 3 steps to set up your environment.

### 1. Python Environment Setup (Required)
Set up the Python environment for backend processing.

```bash
cd c:\github\paper-memory
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables (Highly Recommended)
Create a `.env` file in the project root and set your Gemini API key.
*Note: While basic functions (local search, DOI fetching) work without this, it is **required for high-precision semantic search and the AI-driven `autolink` feature**.*

```bash
# In PowerShell
New-Item .env -ItemType File
```

Add the following to `.env`:
```env
GEMINI_API_KEY="your_api_key_here"
```
*(You can obtain an API key for free from [Google AI Studio](https://aistudio.google.com/app/apikey))*

### 3. Gemini CLI Installation (Required)
Used as the frontend for reading and analyzing papers.

```bash
npm install -g @google/gemini-cli
```

### 4. Verification
```bash
# Verify backend
python -m paper_memory stats

# Verify frontend
gemini
```

---

## 📖 Basic Usage (Knowledge Lifecycle)

### Step 1: Paper Analysis and Knowledge Extraction
Place the PDF you want to analyze in the `pdf/` folder and instruct Gemini CLI to analyze it.

```bash
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
3. Notes are saved to ChromaDB and JSON files.
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

---

## 🛠️ Backend CLI (Manual Operation & Management)

You can call the Python helper directly for detailed data management.

### Knowledge Note Management
```bash
python -m paper_memory add --json '[{...}]'               # Add notes directly from JSON
python -m paper_memory search --query "search query"      # Search
python -m paper_memory list [--paper "title"] [--type "type"] # List
python -m paper_memory link --source "id1" --target "id2" --reason "reason" # Manual link
python -m paper_memory neighbors --note-id "xxx"          # Search neighbor notes
python -m paper_memory stats                              # Show statistics
python -m paper_memory get --note-id "xxx"                # Get note details
python -m paper_memory delete --note-id "xxx"             # Delete note
```

### Reference (Reading List) Management
Track and manage "important papers to read next" mentioned in your analysis. (Supports DOI auto-completion)

```bash
python -m paper_memory refs                              # List unread references
python -m paper_memory refs --relevance high             # Filter by relevance
python -m paper_memory refs --cited-by "title"           # Filter by source paper
python -m paper_memory refs --history                    # View completed history
python -m paper_memory refs-add --file refs.json         # Register new references (JSON)
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
│   ├── note.py            # Note data model
│   ├── reference.py       # Reference data model
│   ├── autolinker.py      # AI auto-link logic
│   ├── doi_fetcher.py     # API-based DOI completion logic
│   └── store.py           # Storage management (JSON + ChromaDB)
├── notes/                 # Note persistence (JSON)
├── references/            # Unread references (JSON)
│   └── _history.json      # Completed reference history
├── .chromadb/             # Vector search index (Auto-generated)
└── pdf/                   # Repository for paper PDFs
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

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
For details on third-party library licenses, please refer to [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
