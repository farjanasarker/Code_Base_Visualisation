# Software Requirements Specification (SRS)
## CodeFlow — Code Base Visualisation & Architectural Analysis Platform

**Version:** 1.0
**Date:** June 22, 2026
**Prepared from:** Actual implementation in `/Backend` (FastAPI + Neo4j) and `/Frontend` (Vue 3 + Vue Flow)

> Diagrams in this document use **Mermaid** syntax. They render automatically on GitHub, GitLab, Notion, and in VS Code with the "Markdown Preview Mermaid Support" extension. To convert this file to Word/PDF with diagrams rendered as images, use Pandoc with a Mermaid filter, or open the rendered preview and "Print to PDF/Word".

---

## Table of Contents
1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [System Architecture](#3-system-architecture)
4. [Use Case Model](#4-use-case-model)
5. [Functional Requirements (System Features)](#5-functional-requirements-system-features)
6. [Data Flow Diagrams](#6-data-flow-diagrams)
7. [Data Model (ER Diagram)](#7-data-model-er-diagram)
8. [Sequence Diagrams](#8-sequence-diagrams)
9. [State Diagram](#9-state-diagram)
10. [External Interface Requirements](#10-external-interface-requirements)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [Other Constraints & Assumptions](#12-other-constraints--assumptions)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for **CodeFlow**, a web-based platform that ingests a developer's source code (single file, ZIP archive, or full folder) and produces an interactive, multi-tier visual map of the codebase together with automated architectural, quality, and risk analysis. The SRS is derived from the **actual implemented system** (not just the design plan) so that it reflects working, verifiable behavior.

### 1.2 Scope
CodeFlow allows a user to:
- Upload source code (Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, C#).
- Visualize the codebase as a drill-down graph: **Module → File → Function → Chunk**.
- Visualize a monorepo containing multiple microservices as a **Service tier** above Module, with automatically detected HTTP/REST and message-queue connections between services.
- Search for any function/file/module across the uploaded project.
- Detect software architecture patterns (MVC, Layered, Clean, Hexagonal, Repository, GoF patterns).
- Detect layered-architecture rule violations.
- Detect code smells (function, module, and architecture level) and obtain an AI-generated refactor plan.
- Compute dependency risk scores and change-impact (reverse call graph) analysis for any function.
- Detect dead/unreachable code and unused imports.
- View aggregated code metrics (LOC, cyclomatic/cognitive complexity, Halstead metrics, Maintainability Index).
- View Git commit history with estimated quality metrics per commit (if `.git` is included in the upload).
- Operate within an isolated, auto-expiring user session backed by a Neo4j graph database.

Out of scope: code editing/modification, real-time collaborative editing, CI/CD integration, and IDE plugin delivery.

### 1.3 Definitions, Acronyms and Abbreviations
| Term | Meaning |
|---|---|
| AST | Abstract Syntax Tree |
| CC | Cyclomatic Complexity |
| MI | Maintainability Index |
| Fan-in / Fan-out | Number of callers / callees of a function |
| God File/Module | A file/module with disproportionately high function count or complexity |
| Tier 1/2/3 | Module-level / File-level / Function-level graph view |
| DFD | Data Flow Diagram |
| ERD | Entity Relationship Diagram |
| LLM | Large Language Model (Groq `llama-3.3-70b-versatile`) |
| Service (monorepo) | A top-level upload folder detected as an independently deployable microservice, via a manifest file or *_service/-service style naming |
| Tier 0 | Service-level graph view, shown above Tier 1 only for monorepos with 2+ detected services |

### 1.4 References
- Backend source: `Backend/main.py`, `analyzer.py`, `pattern_detector.py`, `smell_detector.py`, `smell_graph.py`, `db.py`, `llm_engine.py`
- Frontend source: `Frontend/src/components/GraphView.vue`, `FunctionNode.vue`, `BottomBackEdge.vue`, `Frontend/src/services/sessionManager.js`
- Project planning docs: `CONTEXT.md`, `.instructions.md`, `PHASES.md`

### 1.5 Overview
Section 2 describes the product context and actors. Section 3 shows system architecture. Section 4 gives the use-case model. Section 5 lists detailed functional requirements per feature. Sections 6–9 provide DFDs, the ER/graph data model, sequence diagrams, and the session state diagram. Sections 10–12 cover interfaces, non-functional requirements, and constraints.

---

## 2. Overall Description

### 2.1 Product Perspective
CodeFlow is a standalone, self-contained web application with a decoupled frontend (Vue 3 SPA) and backend (FastAPI REST API), backed by a Neo4j graph database for persisted code-graph storage and an external LLM API (Groq) for AI-assisted refactor reasoning.

### 2.2 Product Functions (Summary)
| # | Feature | Description |
|---|---|---|
| F1 | Code Upload & Ingestion | Accepts file / ZIP / folder, validates and parses source |
| F2 | Multi-language Parsing | Tree-sitter based AST parsing across 6+ languages |
| F3 | 3-Tier Graph Visualization | Module → File → Function drill-down with Vue Flow |
| F4 | Search | Full text search across functions/files/modules |
| F5 | Architecture Pattern Detection | MVC, Layered, Clean, Hexagonal, Repository, GoF patterns |
| F6 | Layer Violation Analysis | Detects illegal cross-layer calls |
| F7 | Code Smell Analysis | Static smell detection + LLM refactor plan |
| F8 | Change Impact Analysis | Reverse call graph for a selected function |
| F9 | Dependency Risk Scoring | Fan-in based risk ranking |
| F10 | Dead Code Detection | Unreachable functions & unused imports |
| F11 | Code Metrics Dashboard | LOC, complexity, Halstead, Maintainability Index |
| F12 | Git History & Evolution | Per-commit quality trend (if `.git` present) |
| F13 | Session Management | Isolated, auto-expiring per-user sessions |
| F14 | Service Tier & Monorepo Detection | Detects microservices from folder manifests/naming; scopes Neo4j storage and all analyses per service |
| F15 | Automatic Inter-Service Call Detection | Static scan for HTTP/REST calls and message-queue pub/sub correlation between services |

### 2.3 User Classes and Characteristics
| User Class | Description |
|---|---|
| **Developer / Code Reviewer** | Uploads a project to understand structure, locate risky/dead code, and review architecture before refactoring |
| **Software Architect** | Uses pattern detection and layer-violation analysis to audit architectural compliance |
| **QA / Tech Lead** | Uses code smell, metrics, and Git history panels to track quality trends over time |
| **System Administrator** | Monitors active sessions via `/admin/sessions`, ensures cleanup and resource limits |

### 2.4 Operating Environment
- **Frontend:** Modern browsers (Chrome, Edge, Firefox) — Vue 3 SPA served via Vite.
- **Backend:** Python 3.x, FastAPI + Uvicorn, runs on any OS with network access to Neo4j Aura (cloud) and Groq API.
- **Database:** Neo4j (cloud-hosted, v6.1.0), with in-memory cache fallback if unreachable.

### 2.5 Design and Implementation Constraints
- Parsing is AST-based (Tree-sitter); dynamic/reflective calls are not tracked.
- Maximum upload: 50 MB total, 1000 files, 2 MB per source file.
- Git history limited to the last 30 commits for performance.
- Session data isolated by `session_id`; not designed for real-time multi-user collaboration on the same project.

### 2.6 Assumptions and Dependencies
- Internet connectivity is required for Neo4j Aura and Groq LLM calls.
- Uploaded code is trusted enough to parse (no code execution occurs server-side).
- If Neo4j is temporarily unavailable, the system falls back to an in-memory cache for the current session only.

---

## 3. System Architecture

```mermaid
flowchart TB
    subgraph Client["Client (Browser)"]
        UI["Vue 3 SPA<br/>GraphView.vue"]
        VF["Vue Flow + Dagre<br/>(Graph Rendering)"]
        SM["sessionManager.js"]
    end

    subgraph Server["Backend (FastAPI / Uvicorn)"]
        API["main.py — REST API & Session Mgmt"]
        AN["analyzer.py — AST Parsing & Metrics"]
        PD["pattern_detector.py — Architecture Patterns"]
        SD["smell_detector.py — Code Smell Rules"]
        SG["smell_graph.py — Smell Dependency Graph"]
        LE["llm_engine.py — LLM Refactor Reasoning"]
        DB_MOD["db.py — Neo4j Access Layer"]
    end

    subgraph External["External Services"]
        NEO[("Neo4j Aura<br/>Graph Database")]
        GROQ["Groq LLM API<br/>llama-3.3-70b-versatile"]
        GIT["Local Git Repository<br/>(if .git uploaded)"]
    end

    UI <--> SM
    SM <-- "HTTPS / JSON<br/>X-Session-ID header" --> API
    API --> AN
    API --> PD
    API --> SD
    SD --> SG
    API --> LE
    LE -- "prompt/response" --> GROQ
    API --> DB_MOD
    DB_MOD <--> NEO
    API -- "git log / git show" --> GIT
    AN --> VF
```

### 3.1 Service Tier Architecture (Monorepo / Microservice Detection)

A monorepo containing 2+ detected services is analyzed with an added pipeline stage above the existing
Module tier. Single-project uploads are unaffected — this stage only activates when `detect_services()`
finds 2 or more services.

```mermaid
flowchart TB
    UP["User uploads ZIP / folder"]
    DETECT["detect_services(root)<br/>manifest file OR *_service/-service naming;<br/>unwraps one wrapper level if needed"]
    DECIDE{"≥2 services<br/>detected?"}

    SINGLE["Single-project pipeline (unchanged)<br/>analyze_files(all_files) once<br/>store_all(functions, session_id)"]
    NEO_SINGLE[("Neo4j — tagged by session_id only")]

    PARTITION["Partition all_files by service<br/>(bucket by rel_path prefix)"]
    PERSERVICE["Per service bucket:<br/>analyze_files(bucket)<br/>store_all(bucket, service_id=X)"]
    CALLDETECT["detect_service_connections()<br/>HTTP/REST hostname+keyword scan<br/>MQ publish/consume queue-name correlation"]
    NEO_MULTI[("Neo4j — session_id + service property")]
    CACHE["SESSION_CACHE<br/>functions[], services[], service_connections[]"]

    RESPONSE["/upload response<br/>is_multi_service, tier1_graph OR service_graph"]
    FRONTEND["Frontend: renderTier0Graph() or existing tier1 flow"]
    CLICK["User clicks a service node"]
    TIER1REQ["GET /graph/tier1?service_id=X"]
    REUSE["renderTier1Graph() — reused, unmodified<br/>existing module→file→function drill-down"]

    UP --> DETECT --> DECIDE
    DECIDE -- No --> SINGLE --> NEO_SINGLE --> RESPONSE
    DECIDE -- Yes --> PARTITION --> PERSERVICE
    PERSERVICE --> NEO_MULTI --> CACHE
    PERSERVICE -- "file contents" --> CALLDETECT -- "connections[]" --> CACHE
    CACHE --> RESPONSE
    RESPONSE --> FRONTEND --> CLICK --> TIER1REQ --> REUSE
```

---

## 4. Use Case Model

### 4.1 Use Case Diagram

```mermaid
graph TB
    Dev["👤 Developer"]
    Arch["👤 Software<br/>Architect"]
    Lead["👤 Tech Lead"]
    Admin["👤 System<br/>Administrator"]

    subgraph CodeFlow["CodeFlow System"]
        UC1((Upload Source Code))
        UC2((Browse 3-Tier<br/>Code Graph))
        UC3((Search Code Entities))
        UC4((View Code Metrics))
        UC5((Detect Architecture<br/>Patterns))
        UC6((Analyze Layer<br/>Violations))
        UC7((Run Code Smell<br/>Analysis))
        UC8((Request AI<br/>Refactor Plan))
        UC9((View Dependency<br/>Risk Score))
        UC10((Run Change Impact<br/>Analysis))
        UC11((Detect Dead Code))
        UC12((View Git History &<br/>Quality Trend))
        UC13((Manage Session))
        UC14((Monitor Active<br/>Sessions))
    end

    Dev --> UC1
    Dev --> UC2
    Dev --> UC3
    Dev --> UC4
    Dev --> UC9
    Dev --> UC10
    Dev --> UC11
    Dev --> UC12
    Dev --> UC13

    Arch --> UC2
    Arch --> UC5
    Arch --> UC6
    Arch --> UC7
    Arch --> UC8
    Arch --> UC13

    Lead --> UC7
    Lead --> UC12
    Lead --> UC13

    Admin --> UC14

    UC2 -.includes.-> UC1
    UC8 -.extends.-> UC7
    UC10 -.extends.-> UC2
```

### 4.2 Use Case Descriptions

**UC1 — Upload Source Code**
- **Actor:** Developer
- **Precondition:** Active session exists (auto-created on app load).
- **Flow:** User selects a single file, a ZIP, or a folder → frontend validates extension/size → POST `/upload` → backend extracts (if ZIP), filters ignored directories, parses with Tree-sitter, builds graphs, stores in Neo4j, returns Tier-1 graph + metrics.
- **Postcondition:** Session now holds the parsed project graph; Tier-1 view is rendered.
- **Alternate flow:** Invalid file type / oversized upload / zip-slip path → reject with error message.

**UC2 — Browse 3-Tier Code Graph**
- **Actor:** Developer / Architect
- **Flow:** User clicks a Module node → GET `/graph/tier2/{module_name}` → file-level graph rendered. User clicks a File node → GET `/graph/tier3?file_path=...` → function-level graph rendered. User clicks a Function node → GET `/expand/{function_name}` → inline callers/callees shown.
- **Postcondition:** Breadcrumb trail updated; user can navigate back via "← Back".

**UC3 — Search Code Entities**
- **Actor:** Developer
- **Flow:** User types a query in the search box → client-side/REST search returns matching functions/files/modules with risk badge → clicking a result focuses/centers that node in the graph (loading the relevant tier if not visible).

**UC5 — Detect Architecture Patterns**
- **Actor:** Architect
- **Flow:** GET `/api/patterns/{session_id}` → `pattern_detector.py` runs rule-based detectors (MVC/MVP, Layered, Clean, Hexagonal, Repository, GoF) against the parsed graph → confidence-scored results with evidence and violations rendered in the Architecture Patterns panel.

**UC6 — Analyze Layer Violations**
- **Actor:** Architect
- **Precondition:** Folder/ZIP upload (multi-file structure required).
- **Flow:** GET `/layer-violations` → backend checks Controller→Service→Repository→Model call ordering → violations grouped by module/severity → displayed in Layer Analysis panel.

**UC7 — Run Code Smell Analysis**
- **Actor:** Architect / Tech Lead
- **Flow:** GET `/smell-analysis` → `smell_detector.py` evaluates function/module/architecture-level smell rules → `smell_graph.py` builds a smell dependency graph and root-cause ranking → results (severity chips, ranked files, expandable detail) shown in Smell Analysis panel.

**UC8 — Request AI Refactor Plan** (extends UC7)
- **Actor:** Architect
- **Flow:** User clicks "AI Refactor Plan" → POST `/llm-refactor-reason` with smell summary → `llm_engine.py` prompts Groq LLM → response parsed into executive summary, root cause, prioritized steps (pattern, target, effort, risk), and long-term recommendation → rendered in LLM plan box.

**UC9 — View Dependency Risk Score**
- **Actor:** Developer
- **Flow:** GET `/risk-score` → functions ranked by fan-in into High/Medium/Low/None risk buckets → top functions shown with "Changing this will affect N caller(s)" warning.

**UC10 — Run Change Impact Analysis** (extends UC2)
- **Actor:** Developer
- **Flow:** User hovers/selects a function node → GET `/impact-analysis/{function_name}` → backend performs BFS over the reverse call graph → affected functions/files/modules with hop-depth returned → impact overlay tooltip rendered on canvas.

**UC11 — Detect Dead Code**
- **Actor:** Developer
- **Flow:** GET `/dead-code` → backend flags functions with fan-in = 0 that are not recognized entry points, classified by confidence (high for private, medium for public); unused imports listed per file.

**UC12 — View Git History & Quality Trend**
- **Actor:** Developer / Tech Lead
- **Precondition:** Uploaded ZIP/folder contains a `.git` directory.
- **Flow:** GET `/git-history` → backend runs `git log`/`git show` (last 30 commits), estimates LOC/function count/MI per commit → paginated commit table with churn and net delta rendered.

**UC13 — Manage Session**
- **Actor:** Any user
- **Flow:** On app load, frontend calls POST `/start-session` (or restores ID from `sessionStorage`); all subsequent requests carry `X-Session-ID`; on tab close, `sendBeacon` triggers DELETE `/end-session`; backend also auto-expires sessions after 3 hours via a background cleanup task.

**UC14 — Monitor Active Sessions**
- **Actor:** Administrator
- **Flow:** GET `/admin/sessions` → returns list of all active sessions with metadata for operational monitoring.

> **Note:** The Service Tier / monorepo microservice-detection capability (service graph, per-service drill-down, auto-detected inter-service connections) is implemented in code — see `service_call_detector.py`, `GET /service-graph`, and FR-14/FR-15 below — but is intentionally left out of the use case model for now and will be documented here once the feature is finalized for release.

---

## 5. Functional Requirements (System Features)

### 5.1 FR-1: Code Upload & Ingestion
- FR-1.1: System shall accept a single source file, a ZIP archive, or a directory (via folder picker).
- FR-1.2: System shall reject files exceeding 2 MB (single file) or uploads exceeding 50 MB / 1000 files in total.
- FR-1.3: System shall sanitize ZIP entries to prevent path traversal ("zip-slip") and skip directories such as `node_modules`, `.git` (except for history extraction), `venv`, `dist`, `build`.
- FR-1.4: System shall display upload progress with stage labels.

### 5.2 FR-2: Multi-Language Parsing & Metrics
- FR-2.1: System shall parse Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, and C# using Tree-sitter.
- FR-2.2: System shall extract, per function: name, parameters, line range, cyclomatic complexity, fan-in, fan-out.
- FR-2.3: System shall build an internal call graph using only same-project function calls (external/stdlib calls excluded).
- FR-2.4: System shall classify large files by line count and AST function count, and chunk "god files" into virtual modules for readability, as follows:
  - FR-2.4.1: A file with ≤ 10,000 lines is classified “normal”. Above that threshold, it is classified by AST-parsed function count: < 3 functions → “data file” (excluded from god-file chunking); 3–100 functions → “large normal”; > 100 functions → “god file”.
  - FR-2.4.2: Recognized generated-file suffixes (`.pb.go`, `.pb.gw.go`, `_grpc.pb.go`, `.gen.go`, `.generated.go`, `_generated.go`) are always classified “god file” regardless of size, unless they exceed 100,000 lines, in which case they are treated as a “data file” and skipped.
  - FR-2.4.3: A god file is split into virtual modules using the first strategy that yields a usable result, in priority order: (1) class-based — one virtual module per class, containing its methods; (2) complexity-based — High (cyclomatic complexity > 15) / Medium (5–15) / Low (≤ 5) buckets, used when no classes are found; (3) line-range — fixed groups of 50 functions labeled by line span, used as the final fallback.
  - FR-2.4.4: A Tier-3 (file-level) request for a chunked god file shall return the chunk-level graph (one node per virtual module) instead of every function individually; selecting a chunk (Tier-4) drills into that chunk’s own functions.
  - FR-2.4.5: Chunking is a purely structural, read-only grouping — it does not alter parsed function identity, call-graph edges, or computed metrics.

### 5.3 FR-3: 3-Tier Graph Visualization
- FR-3.1: System shall render Tier-1 (module), Tier-2 (file), Tier-3 (function), and Tier-4 (chunk) graphs using Vue Flow with Dagre auto-layout.
- FR-3.2: System shall support click-to-drill-down and a breadcrumb/back-navigation stack.
- FR-3.3: System shall provide a MiniMap and pan/zoom Controls.
- FR-3.4: System shall visually distinguish node types (Module, File, Function, Chunk, Root/orphan file) and risk levels by color/icon.

### 5.4 FR-4: Search
- FR-4.1: System shall support full-text search across function, file, and module names.
- FR-4.2: Search results shall display entity type, file path, and risk badge.
- FR-4.3: Selecting a result shall load the relevant tier (if not already visible) and focus the node.

### 5.5 FR-5: Architecture Pattern Detection
- FR-5.1: System shall detect MVC/MVP, Layered Architecture, Clean Architecture, Hexagonal Architecture, Repository Pattern, and common GoF design patterns (Singleton, Observer, Factory, Facade).
- FR-5.2: Each detected pattern shall include a confidence score, supporting evidence, and component-to-layer mapping.
- FR-5.3: System shall list architecture rule violations associated with detected patterns.

### 5.6 FR-6: Layer Violation Analysis
- FR-6.1: System shall validate that calls only flow Controller → Service → Repository → Model (utility layers callable from any layer).
- FR-6.2: Violations shall be reported with source file, target reference, severity (High/Medium), and explanation, grouped by module.
- FR-6.3: This feature requires folder/ZIP upload (not applicable to single-file upload).

### 5.7 FR-7: Code Smell Analysis & AI Refactor Plan
- FR-7.1: System shall detect function-level smells: Long Method, Too Many Parameters, Dead Code, Feature Envy, Deep Nesting, Switch Smell, Magic Numbers.
- FR-7.2: System shall detect module-level smells: God Module, God Class, Large Module, Lazy Class, Duplicate Code, Data Clumps, Shotgun Surgery.
- FR-7.3: System shall detect architecture-level smells: Circular Dependency, Long Call Chain, Inappropriate Intimacy, Divergent Change.
- FR-7.4: System shall build a smell dependency graph and compute root-cause ranking via BFS and a greedy set-cover fix-ordering algorithm.
- FR-7.5: On user request, system shall call an LLM (Groq `llama-3.3-70b-versatile`) to generate an executive summary, root cause, prioritized refactor steps (with effort/risk), and a long-term recommendation.

### 5.8 FR-8: Change Impact Analysis
- FR-8.1: For a selected function, system shall compute the full reverse call graph (all transitive callers) via BFS.
- FR-8.2: Results shall indicate hop-depth (direct vs. indirect caller) and aggregate affected files/modules.
- FR-8.3: System shall render an overlay showing the top affected functions with an option to view the full list.

### 5.9 FR-9: Dependency Risk Scoring
- FR-9.1: System shall classify every function into High (≥10 callers), Medium (3–9), Low (1–2), or None (0) risk based on fan-in.
- FR-9.2: System shall rank and display the top 50 highest-risk functions with a caller-count warning.

### 5.10 FR-10: Dead Code Detection
- FR-10.1: System shall flag functions with zero fan-in that are not recognized entry points (e.g., `main`, lifecycle hooks, test methods, web route handlers).
- FR-10.2: Flagged functions shall carry a confidence level: High (private, no callers) or Medium (public, no callers — may be used dynamically/externally).
- FR-10.3: System shall list unused imports per file.

### 5.11 FR-11: Code Metrics Dashboard
- FR-11.1: System shall compute and display LOC, SLOC, file/function counts, average/max cyclomatic complexity, cognitive complexity, decision points, Halstead volume/difficulty, and Maintainability Index (0–100, color-coded).
- FR-11.2: System shall report max call-chain depth, circular dependency count (with chains), and orphan node count.

### 5.12 FR-12: Git History & Evolution Tracking
- FR-12.1: If the upload contains a `.git` directory, system shall extract up to the last 30 commits via `git log`/`git show`.
- FR-12.2: For each commit, system shall report hash, message, author, date, insertions/deletions, churn, and net delta, plus estimated LOC/function count/MI at that point in history.
- FR-12.3: The commit table shall be paginated (10 rows per page, "load more").

### 5.13 FR-13: Session Management
- FR-13.1: System shall create a unique session (UUID) per user on first load and persist it in `sessionStorage`.
- FR-13.2: All API requests shall carry an `X-Session-ID` header; backend data (Neo4j nodes, disk uploads, in-memory cache) shall be isolated per session.
- FR-13.3: Sessions shall auto-expire after 3 hours of inactivity via a background cleanup task (every 30 minutes); explicit cleanup shall occur via `sendBeacon` on tab close.
- FR-13.4: An admin endpoint shall list all active sessions for monitoring.

### 5.14 FR-14: Service Tier & Monorepo Detection
- FR-14.1: System shall detect monorepo services from top-level upload folders using either (a) a recognized manifest file (`package.json`, `requirements.txt`, `pyproject.toml`, `setup.py`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `go.mod`, `Cargo.toml`, `Dockerfile`, `*.csproj`) directly inside the folder, or (b) a microservice-style folder name (`*_service`, `*-service`, `*service`, `*svc`, `service*`).
- FR-14.2: If an uploaded ZIP extracts to a single wrapping folder with the real services nested one level inside it, the wrapper shall be transparently unwrapped so services are still detected.
- FR-14.3: The Service tier shall only activate when 2 or more services are detected; a single-folder or flat upload (the common case) renders exactly as it does without a Service tier — this is a hard backward-compatibility guarantee.
- FR-14.4: Every Module and File node created for a detected service shall carry a `service` property, scoping Neo4j storage per service within the existing per-session namespace, with no cross-service leakage.
- FR-14.5: The Module, File, and Function tier endpoints shall accept an optional `service_id` parameter to scope results to one service, reusing the existing drill-down interaction without introducing a new navigation paradigm.
- FR-14.6: Dead-code, layer-violation, code-smell, and architecture-pattern analyses shall each be filterable by `service_id`, with no cross-service leakage between analyses.

### 5.15 FR-15: Automatic Inter-Service Call Detection
- FR-15.1: System shall automatically detect inter-service HTTP/REST calls by scanning source text for a known service’s hostname appearing near an HTTP-call keyword (e.g. `axios`, `fetch`, `requests.get/post`, `RestTemplate`, `WebClient`, `http.Get/Post`, `reqwest`, `HttpClient`) or a `http://` or `https://` URL scheme.
- FR-15.2: System shall automatically detect inter-service message-queue relationships by correlating publish/produce calls in one service with consume/subscribe calls in another service that reference the same queue or topic name string.
- FR-15.3: Detected connections shall be returned via GET `/service-graph` and rendered as colored, labeled edges between service nodes in the Tier 0 view, distinguished by type (REST, MessageQueue).
- FR-15.4: Detection is static-text-based and best-effort; it does not execute code, does not detect gRPC calls or database connection strings, and can miss dynamically constructed URLs — consistent with the static-analysis limitations already documented for Dead Code Detection (FR-10).
- FR-15.5: There is no manual override file (e.g. a hand-authored service-map) — all inter-service connections shown are automatically detected from source code.

---

## 6. Data Flow Diagrams

### 6.1 DFD — Level 0 (Context Diagram)

```mermaid
flowchart LR
    User["Developer / Architect<br/>(External Entity)"]
    System(("CodeFlow<br/>System"))
    Neo[("Neo4j Graph DB")]
    Groq["Groq LLM API"]

    User -- "Source code (file/zip/folder)" --> System
    System -- "Graphs, metrics, reports,<br/>diagrams, recommendations" --> User
    System -- "Store / query code graph" --> Neo
    Neo -- "Graph data" --> System
    System -- "Smell summary prompt" --> Groq
    Groq -- "Refactor plan (text)" --> System
```

### 6.2 DFD — Level 1 (Major Processes)

```mermaid
flowchart TB
    User["Developer"]

    P0["0.0<br/>Detect Services<br/>(monorepo)"]
    P1["1.0<br/>Upload & Validate<br/>Source Code"]
    P2["2.0<br/>Parse Code &<br/>Build Call Graph"]
    P2B["2.5<br/>Detect Inter-Service<br/>Calls"]
    P3["3.0<br/>Generate Tiered<br/>Visualization Graph"]
    P4["4.0<br/>Detect Patterns /<br/>Layer Violations"]
    P5["5.0<br/>Detect Code Smells &<br/>Generate AI Refactor Plan"]
    P6["6.0<br/>Compute Risk / Impact /<br/>Dead Code / Metrics"]
    P7["7.0<br/>Extract Git History"]
    P8["8.0<br/>Manage Session"]

    D1[("D1: Uploaded Files<br/>(disk)")]
    D2[("D2: Code Graph<br/>(Neo4j, session + service scoped)")]
    D3[("D3: Session Store<br/>(in-memory + Neo4j)")]

    User -- "raw code" --> P1
    P1 -- "validated files" --> D1
    P1 -- "validated files" --> P0
    P0 -- "service buckets (or all_files)" --> P2
    P2 -- "AST / functions / calls" --> D2
    P2 -- "file contents" --> P2B
    P2B -- "service_connections" --> D3
    P2 --> P3
    D2 --> P3
    P3 -- "tier graphs (incl. Tier 0 services)" --> User

    D2 --> P4
    P4 -- "patterns / violations" --> User

    D2 --> P5
    P5 -- "LLM prompt" --> User
    P5 -- "smell report + plan" --> User

    D2 --> P6
    P6 -- "risk / impact / dead code / metrics" --> User

    P1 -- ".git data" --> P7
    P7 -- "commit history" --> User

    User -- "session id" --> P8
    P8 <--> D3
    P8 -. "scopes all access" .-> D1
    P8 -. "scopes all access" .-> D2
```

---

## 7. Data Model (ER Diagram)

CodeFlow's persistent store is a **property graph (Neo4j)** rather than a relational database. The diagram below is expressed in ER notation to show entities, attributes, and relationships.

```mermaid
erDiagram
    MODULE {
        string id
        string name
        string path
        string service "NEW, nullable"
        int file_count
        int function_count
        float avg_complexity
        datetime created_at
    }
    FILE {
        string id
        string name
        string path
        string language
        string service "NEW, nullable"
        int size_bytes
        int line_count
        int function_count
        boolean is_data_file
        boolean is_god_file
        string checksum
    }
    SERVICE {
        string service_id "logical, NOT a Neo4j node"
        int module_count
        int file_count
    }
    SERVICE_CONNECTION {
        string from_service "logical, NOT a Neo4j node"
        string to_service
        string type "REST or MessageQueue"
        string label
        float confidence
        string evidence "file:line"
    }
    FUNCTION {
        string id
        string name
        string file_path
        int line_start
        int line_end
        int cyclomatic_complexity
        int fan_in
        int fan_out
        boolean is_public
    }
    VIRTUAL_MODULE {
        string id
        string name
        string source_file
        string chunk_strategy
        int line_start
        int line_end
        int function_count
    }
    SESSION {
        string session_id
        datetime created_at
        datetime last_active
        string upload_path
    }

    MODULE ||--o{ FILE : "BELONGS_TO"
    FILE ||--o{ FUNCTION : "DEFINED_IN"
    FILE ||--o{ VIRTUAL_MODULE : "BELONGS_TO (god file)"
    VIRTUAL_MODULE ||--o{ FUNCTION : "DEFINED_IN (chunked)"
    FUNCTION }o--o{ FUNCTION : "CALLS (frequency, line)"
    SESSION ||--o{ MODULE : "scopes"
    SESSION ||--o{ FILE : "scopes"
    SESSION ||--o{ FUNCTION : "scopes"
    MODULE }o..o| SERVICE : "tagged by (derived, not stored)"
    FILE }o..o| SERVICE : "tagged by (derived, not stored)"
    SERVICE ||--o{ SERVICE_CONNECTION : "from / to (derived, not stored)"
```

**Notes:**
- All nodes are tagged with `session_id` to isolate per-user data within the shared Neo4j instance.
- `CALLS` is a many-to-many self-relationship on `FUNCTION`, carrying `frequency` and `line` properties.
- `VIRTUAL_MODULE` exists only for "god files" that are split for readability; it sits between `FILE` and `FUNCTION`.
- `SERVICE` and `SERVICE_CONNECTION` are **logical groupings only** — they are never written to Neo4j as nodes/relationships. `SERVICE` is derived by grouping `MODULE`/`FILE` on their `service` property; `SERVICE_CONNECTION` is computed once at upload time by `detect_service_connections()` and held in the in-memory `SESSION_CACHE`.

---

## 8. Sequence Diagrams

### 8.1 Sequence — Upload & Initial Analysis (UC1)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as GraphView.vue
    participant SM as sessionManager.js
    participant API as FastAPI (main.py)
    participant AN as analyzer.py
    participant DB as db.py / Neo4j

    U->>FE: Select file / ZIP / folder
    FE->>SM: getSessionId()
    SM->>API: POST /start-session (if none)
    API-->>SM: session_id
    FE->>API: POST /upload (X-Session-ID, file data)
    API->>API: validate size, type, zip-slip
    API->>API: detect_services(root)
    API->>AN: analyze_files() once, or per service bucket
    AN->>AN: Tree-sitter AST parse,<br/>build call graph, compute metrics
    AN-->>API: functions, metrics (per bucket if multi-service)
    API->>DB: store_all(..., service_id=X if multi-service)
    DB->>Neo4j: CREATE nodes/relationships
    Neo4j-->>DB: ack
    API->>API: detect_service_connections() [multi-service only]
    API-->>FE: is_multi_service, tier1_graph OR service_graph
    FE->>FE: renderTier0Graph() or renderTier1Graph()
```

### 8.2 Sequence — Drill-Down Navigation (UC2)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as GraphView.vue
    participant API as FastAPI (main.py)
    participant DB as db.py / Neo4j

    U->>FE: Click Service node (Tier 0, monorepo only)
    FE->>API: GET /graph/tier1?service_id=X
    API-->>FE: module nodes+edges (service-scoped)
    FE->>FE: renderTier1Graph() shows modules

    U->>FE: Click Module node
    FE->>API: GET /graph/tier2/{module_name}
    API->>DB: query files in module
    DB-->>API: file nodes + edges
    API-->>FE: tier2_graph
    FE->>FE: push breadcrumb, render Tier-2

    U->>FE: Click File node
    FE->>API: GET /graph/tier3?file_path=...
    API->>DB: query functions in file
    DB-->>API: function nodes + CALLS edges
    API-->>FE: tier3_graph
    FE->>FE: push breadcrumb, render Tier-3

    U->>FE: Click Function node
    FE->>API: GET /expand/{function_name}
    API->>DB: query direct callers/callees
    DB-->>API: neighbor nodes
    API-->>FE: expanded subgraph
    FE->>FE: merge into canvas inline
```

### 8.3 Sequence — Change Impact Analysis (UC10)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as GraphView.vue
    participant API as FastAPI (main.py)
    participant DB as db.py / Neo4j

    U->>FE: Hover/select Function node
    FE->>API: GET /impact-analysis/{function_name}
    API->>DB: fetch reverse CALLS edges
    DB-->>API: caller graph
    API->>API: BFS transitive closure,<br/>compute hop-depth per caller
    API-->>FE: { affected_functions, files, modules, depth }
    FE->>FE: Render impact overlay tooltip<br/>(direct → vs indirect ⇢ callers)
```

### 8.4 Sequence — Code Smell Analysis + AI Refactor Plan (UC7, UC8)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as GraphView.vue
    participant API as FastAPI (main.py)
    participant SD as smell_detector.py
    participant SG as smell_graph.py
    participant LE as llm_engine.py
    participant GROQ as Groq LLM API

    U->>FE: Open "Smell Analysis" panel
    FE->>API: GET /smell-analysis?service_id= (optional)
    API->>SD: detect_smells(graph)
    SD-->>API: function/module/architecture smells
    API->>SG: build_dependency_graph(smells)
    SG->>SG: root-cause BFS + greedy set-cover
    SG-->>API: ranked fix plan
    API-->>FE: { severity_summary, ranked_files, fix_plan }
    FE->>FE: Render smell panel

    U->>FE: Click "AI Refactor Plan"
    FE->>API: POST /llm-refactor-reason (smell summary)
    API->>LE: generate_refactor_reasoning(summary)
    LE->>GROQ: prompt (architectural context)
    GROQ-->>LE: completion (root cause, steps)
    LE-->>API: parsed plan
    API-->>FE: { executive_summary, root_cause, steps, recommendation }
    FE->>FE: Render LLM plan box
```

### 8.5 Sequence — Session Lifecycle (UC13)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as App (main.js)
    participant SM as sessionManager.js
    participant API as FastAPI (main.py)
    participant DB as db.py / Neo4j

    FE->>SM: init()
    SM->>SM: check sessionStorage for existing session_id
    alt no existing session
        SM->>API: POST /start-session
        API-->>SM: new session_id
        SM->>SM: persist in sessionStorage
    end

    loop every API call
        FE->>API: request + X-Session-ID header
        API->>API: scope query by session_id
    end

    Note over API: Background task every 30 min
    API->>API: scan sessions, expire if idle > 3h
    API->>DB: delete expired session nodes
    API->>API: delete expired upload dirs

    U->>FE: Close tab
    FE->>API: DELETE /end-session (via sendBeacon)
    API->>DB: delete session nodes
    API->>API: delete disk uploads, clear cache
```

---

## 9. State Diagram

### 9.1 Session Lifecycle State Diagram

The diagram below models the lifecycle states of a single user **session** — the central stateful entity in CodeFlow (see FR-13 and UC13) — from creation to cleanup.

```mermaid
stateDiagram-v2
    [*] --> Created : POST /start-session

    Created --> Active : Upload received\n(POST /upload)

    Active --> Idle : No API request\nfor a period
    Idle --> Active : New request\n(X-Session-ID header)

    Idle --> Expired : Idle > 3 hours\n(background cleanup task, every 30 min)

    Active --> Ended : DELETE /end-session\n(sendBeacon on tab close)
    Idle --> Ended : DELETE /end-session

    Expired --> Cleaned : Delete Neo4j nodes,\ndisk uploads, in-memory cache
    Ended --> Cleaned : Delete Neo4j nodes,\ndisk uploads, in-memory cache

    Cleaned --> [*]

    note right of Active
        Tier-1/2/3 graphs, patterns,
        smells, metrics all scoped
        to this session_id
    end note

    note right of Expired
        Auto-expiry guards against
        resource leakage from
        abandoned sessions
    end note
```

**State descriptions:**
| State | Meaning |
|---|---|
| **Created** | Session UUID issued via `POST /start-session`; no project data yet |
| **Active** | At least one upload processed; session holds a live code graph in Neo4j/cache |
| **Idle** | Session exists but has received no requests recently |
| **Expired** | Idle session that crossed the 3-hour inactivity threshold; picked up by the 30-minute background cleanup task |
| **Ended** | User explicitly closed the tab/session (`DELETE /end-session` via `sendBeacon`) |
| **Cleaned** | Terminal housekeeping state — Neo4j nodes, disk uploads, and in-memory cache for the session are deleted |

---

## 10. External Interface Requirements

### 10.1 User Interfaces
- Single-page application (Vue 3) with a resizable left sidebar (upload, status, search, legend, metrics, git history, smell analysis, risk, dead code, patterns, layer analysis panels) and a main canvas (Vue Flow graph with MiniMap and Controls).

### 10.2 Software Interfaces (REST API)
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check + active session count |
| POST | `/start-session` | Create a new session |
| DELETE | `/end-session` | Clean up a session |
| GET | `/sessions/info` | Current session metadata |
| GET | `/admin/sessions` | List all active sessions |
| POST | `/upload` | Upload & analyze file/zip/folder |
| GET | `/graph/tier1` | Module-level graph (optional `service_id` param scopes to one service) |
| GET | `/graph/tier2/{module_name}` | File-level graph (optional `service_id` param) |
| GET | `/graph/tier3?file_path=` | Function-level graph (optional `service_id` param) |
| GET | `/graph/chunk?file_path=&chunk_name=` | Function graph for a chunked god file |
| GET | `/graph/files` | All-files flat graph |
| GET | `/expand/{function_name}` | Direct callers/callees of a function |
| GET | `/risk-score` | Dependency risk ranking |
| GET | `/impact-analysis/{function_name}` | Reverse call graph / change impact |
| GET | `/dead-code` | Unreachable functions & unused imports (optional `service_id` param) |
| GET | `/layer-violations` | Architectural layer rule violations (optional `service_id` param) |
| GET | `/metrics` | Aggregated code metrics |
| GET | `/git-history` | Commit history with quality estimation |
| GET | `/smell-analysis` | Code smell detection + fix plan (optional `service_id` param) |
| POST | `/llm-refactor-reason` | LLM-based architectural reasoning |
| GET | `/api/patterns/{session_id}` | Architecture pattern detection (optional `service_id` param) |
| GET | `/service-graph` | Service tier graph: detected services + auto-detected inter-service connections |

### 10.3 Communication Interfaces
- Frontend ↔ Backend: HTTPS/JSON REST, `X-Session-ID` custom header for session scoping.
- Backend ↔ Neo4j: Bolt protocol (Neo4j driver) to Neo4j Aura cloud instance.
- Backend ↔ Groq: HTTPS REST call to Groq Chat Completions API.

---

## 11. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Performance** | Parse 100 files in <2s; Tier-1 graph in <5s; Tier-2 in <1s; Tier-3 in <500ms; search over 1000+ functions in <1s; god-file chunking in <10s |
| **Security** | Zip-slip prevention, filename sanitization, symlink rejection, max file size/count enforcement, no server-side code execution, per-session data isolation |
| **Scalability** | Designed to support 500+ concurrent isolated sessions; in-memory + Neo4j dual caching |
| **Reliability** | Falls back to in-memory cache if Neo4j is unreachable; conservative (false-negative biased) dead-code detection to avoid false positives; service detection (manifest file or naming pattern) and inter-service call detection (static text scan) are both heuristic/best-effort, consistent with the system's static-analysis approach elsewhere |
| **Maintainability** | Modular backend (`analyzer`, `pattern_detector`, `smell_detector`, `smell_graph`, `llm_engine`, `db`, `service_call_detector` separated by responsibility) |
| **Usability** | Drill-down navigation with breadcrumbs, color-coded risk/severity indicators, in-app "How to Use" guidance |
| **Availability** | Session auto-cleanup every 30 minutes prevents resource leakage; sessions expire after 3 hours of inactivity |

---

## 12. Other Constraints & Assumptions

- Dynamic/reflective function calls (e.g., calls via string lookup, `eval`, decorators that wrap call sites) are **not** tracked by the static AST-based analyzer — this is a known limitation acknowledged in the Dead Code and Risk Score panels.
- Layer Violation Analysis and Git History features require a **folder/ZIP upload**; they do not apply to single-file uploads.
- The AI Refactor Plan feature depends on third-party LLM availability (Groq); if the API is unavailable, the static smell report is still available without the AI-generated plan.
- Git History extraction assumes the uploaded archive/folder includes a valid `.git` directory with accessible commit objects.
- Service detection (FR-14) is heuristic — a folder counts as a service only if it has a recognized manifest file or a microservice-style name (`*_service`, `*-service`, `*service`, `*svc`, `service*`); a monorepo whose service folders carry neither signal will not be detected and will render as a single project.
- Automatic inter-service call detection (FR-15) is static-text-based and best-effort — it does not detect gRPC calls, database connection strings, or dynamically constructed URLs/queue names, and cannot verify that a detected call executes at runtime.
- Multi-repo upload (multiple independent repositories in a single upload) is not supported — only a single monorepo archive or folder containing all services is recognized.

---

*End of Software Requirements Specification.*
