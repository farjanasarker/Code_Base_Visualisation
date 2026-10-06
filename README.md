<div align="center">

# CodeFlow

**Understand any codebase visually.**
Upload source code and explore it as an interactive call graph, then run architecture, quality and design-pattern analysis on top of it.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-42b883?logo=vuedotjs&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-graph%20DB-008CC1?logo=neo4j&logoColor=white)
![Tree-sitter](https://img.shields.io/badge/Tree--sitter-AST-5c6bc0)

</div>

---

## Table of Contents

1. [What is CodeFlow?](#what-is-codeflow)
2. [Features](#features)
3. [How it works](#how-it-works)
4. [Supported languages and upload limits](#supported-languages-and-upload-limits)
5. [Prerequisites](#prerequisites)
6. [Installation](#installation)
7. [Configuration](#configuration)
8. [Running the app](#running-the-app)
9. [How to use CodeFlow](#how-to-use-codeflow)
10. [API reference](#api-reference)
11. [Running the tests](#running-the-tests)
12. [Project structure](#project-structure)
13. [Troubleshooting](#troubleshooting)
14. [Documentation](#documentation)

---

## What is CodeFlow?

Large codebases are hard to understand. Reading files one by one does not show how the pieces
connect. CodeFlow parses your code with Tree-sitter, stores the structure as a graph in Neo4j,
and shows it in the browser as a **3-tier, drill-down call graph**: modules, then files, then functions.

On top of the graph it can tell you:

- what breaks if you change a function (impact analysis)
- which code is dead or risky
- where the code smells and layer violations are
- which Gang-of-Four design patterns are in use
- how code quality changed over the git history

Every browser tab gets its own isolated session, so several people can use one server without seeing each other's data.

---

## Features

### Visualisation

| Feature | What it does |
|---|---|
| **3-tier graph navigation** | Drill down from **Modules**, to **Files**, to **Functions**. Large graphs stay readable. |
| **Large-file chunking** | Very large ("God") files are split into chunks so the graph does not freeze. |
| **Search** | Find functions, files and modules by name, then jump to them in the graph. |
| **Expand on demand** | Click a function to load its callers and callees. |
| **Minimap, zoom and controls** | Pan and zoom around big graphs. |

### Analysis

| Feature | What it does |
|---|---|
| **Impact analysis** | Pick a function and see everything that depends on it (reverse call graph). |
| **Dependency risk scoring** | Ranks functions by fan-in, so the riskiest ones to change come first. |
| **Dead-code detection** | Finds unreachable functions and unused imports. |
| **Code metrics** | Lines of code, cyclomatic and cognitive complexity, Halstead volume and difficulty, maintainability index, parameter counts, call depth, circular dependencies, orphan nodes and a debt score. |
| **Layer-violation detection** | Detects illegal cross-layer calls (for example a view calling the database directly). |
| **Architecture pattern detection** | Recognises MVC, Layered, Clean, Hexagonal and Repository structures. |
| **Gang-of-Four pattern detection** | Detects all 23 GoF patterns with a YAML rule engine, across languages. |
| **Code-smell analysis** | Finds smells per file, per layer, as an ROI-ordered plan, and as a "Fix Tree". |
| **AI refactor suggestions** | Optional. An LLM (Groq) explains smells and proposes a step-by-step refactor plan. If no key is set, a rule-based fallback is used. |
| **Git history analysis** | If the uploaded ZIP contains `.git`, shows per-commit quality trend, churn and changed files. |
| **Dynamic analysis and program slicing** | Python only. Runs a chosen function in a Docker sandbox with parameters you give, then shows the statements that influenced a result. |

### Platform

| Feature | What it does |
|---|---|
| **Flexible upload** | Single file, many files, a folder, or a ZIP. |
| **Session isolation** | Each browser tab gets a session ID. Data is isolated and auto-deleted after 3 hours of inactivity or when the tab closes. |
| **Upload safety** | Size, file-count and depth limits, plus ZIP path-traversal (zip-slip) protection. |

---

## How it works

```
 Upload (file / folder / ZIP)
        |
        v
 FastAPI backend ──> Tree-sitter parser ──> functions, classes, calls, imports
        |
        v
 Analyzers: metrics · layers · smells · GoF rules · dead code · git history
        |
        v
 Neo4j graph database (one isolated namespace per session)
        |
        v
 Vue 3 + Vue Flow frontend ──> interactive graph and analysis panels
```

---

## Supported languages and upload limits

**Source languages:** Python, JavaScript, TypeScript (`.js .jsx .ts .tsx`), Java, Go, Rust, plus `.c .cpp .cs` files, and `.zip` archives containing any of them.

| Limit | Value |
|---|---|
| Max upload size | 50 MB |
| Max size per source file | about 2 MB |
| Max source files per upload | 1000 |
| Max folder depth | 50 |
| Session lifetime | 3 hours of inactivity |

---

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.12 | Backend |
| Node.js | 20.19+ or 22.12+ | Frontend |
| Neo4j | 5.x (local, Docker or free [Neo4j Aura](https://neo4j.com/cloud/platform/aura-graph-database/)) | Graph storage (**required**) |
| Groq API key | any | AI refactor suggestions (optional) |
| Docker | any recent | Dynamic analysis and slicing (optional) |
| Git | any | Cloning the repo |

### Getting a Neo4j database (pick one)

**Option A: Neo4j Aura (free, easiest).** Create a free instance at neo4j.com/cloud. Download the credentials file. You will need the connection URI (`neo4j+s://...`), the username and the password.

**Option B: Local with Docker.**
```bash
docker run -d --name codeflow-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/choose-a-password neo4j:5
```
URI will be `bolt://localhost:7687`, user `neo4j`.

---

## Installation

### 1. Clone

```bash
git clone <your-repo-url> codeflow
cd codeflow
```

### 2. Backend

**Windows (PowerShell)**
```powershell
cd Backend
py -3.12 -m venv venv
Set-ExecutionPolicy -Scope Process RemoteSigned
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```bash
cd Backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### 3. Frontend

```bash
cd Frontend
npm install
```

### 4. (Optional) Dynamic-analysis sandbox

Only needed for the Python dynamic-analysis / slicing feature. Make sure Docker is running. The sandbox image is built automatically from `Backend/dynamic_analysis/docker/` the first time you use the feature.

---

## Configuration

Edit `Backend/.env` (this file is git-ignored, never commit it):

```ini
# Neo4j (required)
NEO4J_URI=neo4j+s://<your-instance>.databases.neo4j.io   # or bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# AI refactor suggestions (optional)
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=
```

Frontend: by default it talks to `http://localhost:8000`. To change that, create `Frontend/.env.local`:

```ini
VITE_API_URL=http://localhost:8000
```

---

## Running the app

Use **two terminals**.

**Terminal 1: Backend**
```bash
cd Backend
# activate the venv first (see Installation)
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Check it: open <http://127.0.0.1:8000/health>. Interactive API docs are at <http://127.0.0.1:8000/docs>.

**Terminal 2: Frontend**
```bash
cd Frontend
npm run dev
```
Open the URL Vite prints, usually <http://localhost:5173>.

**Production build of the frontend**
```bash
npm run build      # output in Frontend/dist
npm run preview
```

---

## How to use CodeFlow

1. **Open the app** in your browser. A session starts automatically.
2. **Upload code.** Choose a file, several files, a folder, or a ZIP of your project. For git-history analysis, upload a ZIP that includes the `.git` folder.
3. **Wait for analysis.** The code is parsed and stored in the graph.
4. **Explore the graph.**
   - Start at the **module** overview.
   - Click a module to open its **files**, then a file to see its **functions** and calls.
   - Use the **search box** to jump to a function or file.
5. **Inspect a function.** Open impact analysis to see what depends on it, or check its risk score.
6. **Open the analysis panels.**
   - **Metrics**: complexity, maintainability and debt per file and project.
   - **Layers**: layer violations.
   - **Patterns**: architecture and GoF design patterns found.
   - **Smells**: code smells, grouped by *Files*, *ROI Plan*, *By Layer* or *Fix Tree*. Request an AI refactor plan for a smell if a Groq key is configured.
   - **Dead code**: unreachable functions and unused imports.
   - **Git history**: commit-by-commit quality trend.
7. **Dynamic slicing (Python, optional).** Choose a function, fill in parameters, run it in the sandbox, then request a slice to see which statements affected a value.
8. **Finish.** Closing the tab ends the session and deletes your data. Idle sessions are removed after 3 hours.

---

## API reference

Full interactive docs: `http://127.0.0.1:8000/docs` when the backend is running. Main endpoints:

| Group | Endpoint |
|---|---|
| Health and sessions | `GET /health`, `POST /start-session`, `DELETE /end-session`, `GET /sessions/info` |
| Upload | `POST /upload` (files, folder or ZIP) |
| Graph | `GET /graph/tier1`, `/graph/tier2/{module}`, `/graph/files`, `/graph/tier3`, `/graph/chunk`, `/expand/{function}`, `/service-graph` |
| Search | `GET /search` |
| Analysis | `GET /impact-analysis/{function}`, `/risk-score`, `/dead-code`, `/layer-violations`, `/metrics`, `/git-history` |
| Smells and AI | `GET /smell-analysis`, `POST /llm-refactor-reason` |
| Patterns | `GET /api/patterns/{session_id}`, `/api/gof-patterns/{session_id}` |
| Dynamic analysis | `POST /dynamic/functions/{id}/params`, `/dynamic/functions/{id}/run`, `/dynamic/runs/{run_id}/slice` |

Requests are tied to a session via a session-ID header, which the frontend sets automatically.

---

## Running the tests

```bash
cd Backend
pip install -r requirements-dev.txt
pytest
```

- Tests whose names end in `_neo4j.py` need a reachable Neo4j database (see `.env`).
- Test fixtures for all GoF patterns live in `Backend/tests/fixtures/`.

---

## Project structure

```
.
├── Backend/
│   ├── main.py                 FastAPI app and all endpoints
│   ├── db.py                   Neo4j access layer
│   ├── analyzer/               Tree-sitter parsing, graph building, metrics, layers, chunking
│   ├── patterns/               GoF rule engine, YAML specs for 23 patterns
│   ├── smell_detector.py       Code-smell detection
│   ├── llm_engine.py           Groq-based refactor planning
│   ├── dynamic_analysis/       Sandboxed execution and slicing (Docker)
│   ├── tests/                  Pytest suite and fixtures
│   ├── .env.example            Config template
│   └── requirements*.txt
├── Frontend/
│   └── src/
│       ├── App.vue
│       ├── components/         GraphView, FunctionNode, SliceParamForm, ...
│       └── services/           Session manager and API calls
└── docs/                       SRS, technical report, and "how it works" explanations
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ServiceUnavailable` or cannot connect to Neo4j | Check `NEO4J_URI`, user and password in `Backend/.env`. For Aura use `neo4j+s://`. For local use `bolt://localhost:7687`. Make sure the DB is running. |
| Frontend shows network or CORS errors | Make sure the backend runs on port 8000, or set `VITE_API_URL` in `Frontend/.env.local`. |
| AI refactor plan says "not configured" | Add `GROQ_API_KEY` to `Backend/.env` and restart the backend. The rule-based fallback is used until then. |
| Dynamic analysis fails | Start Docker Desktop. Only Python and the standard library are available in the sandbox. |
| Git history says "No git repository detected" | Upload a ZIP that includes the `.git` folder. |
| Upload rejected | Check the [limits](#supported-languages-and-upload-limits) and file extension. |
| PowerShell blocks `Activate.ps1` | Run `Set-ExecutionPolicy -Scope Process RemoteSigned` in that window. |
| Session expired | Refresh the page and upload again. Sessions last 3 hours of inactivity. |

---

## Documentation

| Topic | File |
|---|---|
| Software Requirements Specification | [docs/SRS.md](docs/SRS.md) |
| Technical report | [docs/CodeLens_Technical_Report.docx](docs/CodeLens_Technical_Report.docx) |
| Visualisation pipeline | [docs/VISUALIZATION_PIPELINE_EXPLAINED.md](docs/VISUALIZATION_PIPELINE_EXPLAINED.md) |
| Code-smell detection | [docs/CODE_SMELL_DETECTION_EXPLAINED.md](docs/CODE_SMELL_DETECTION_EXPLAINED.md) |
| GoF pattern detection | [docs/GOF_PATTERN_DETECTION_EXPLAINED.md](docs/GOF_PATTERN_DETECTION_EXPLAINED.md) |
| Layer violations | [docs/LAYER_VIOLATION_EXPLAINED.md](docs/LAYER_VIOLATION_EXPLAINED.md) |
| Metrics | [docs/METRICS_CALCULATION_EXPLAINED.md](docs/METRICS_CALCULATION_EXPLAINED.md) |
| Git history analysis | [docs/GIT_COMMIT_HISTORY_EXPLAINED.md](docs/GIT_COMMIT_HISTORY_EXPLAINED.md) |
| Session management | [Backend/SESSION_MANAGEMENT.md](Backend/SESSION_MANAGEMENT.md) and [diagrams](docs/SESSION_MANAGEMENT_DIAGRAMS.md) |
