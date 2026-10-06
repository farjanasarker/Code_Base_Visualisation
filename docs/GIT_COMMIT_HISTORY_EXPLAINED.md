# Git Commit History Feature — Explained

Ei document-e explain kora hoyeche: user jokhon `.git` shoho ZIP upload kore, tokhon **commit gulo already-te ki ki metric change korche** ta kibhabe Backend theke ber hoy ar Frontend-e kibhabe dekhano hoy.

> Source files:
> - Backend: [Backend/main.py](Backend/main.py) — `_find_git_root`, `_get_git_history`, `/upload`, `/git-history`
> - Backend metrics: [Backend/analyzer/metrics.py](Backend/analyzer/metrics.py) — `_maintainability_index`, `compute_aggregate_metrics`
> - Frontend: [Frontend/src/components/GraphView.vue](Frontend/src/components/GraphView.vue) — "Git History — Metrics Trend" panel, `gitCommitsWithLoc`

---

## 1. Big picture (end-to-end flow)

```
User uploads ZIP (with .git folder)
        │
        ▼
POST /upload  (Backend/main.py)
  ├─ ZIP extract  → temp dir
  ├─ _find_git_root()      → .git kothay ache khuje ber kore
  ├─ _get_git_history()    → `git log` / `git show` chalay, per-commit raw stats ber kore
  ├─ analyze_files() + compute_aggregate_metrics()  → CURRENT snapshot-er metrics
  └─ SESSION_CACHE[session_id]["git_history"] = {...}   (temp dir delete hoyar AGEI capture)
        │
        ▼
Frontend upload shesh hole fetchAnalysisPanels() chalay
  ├─ GET /metrics       → current snapshot metrics (sloc, total_functions, MI, ...)
  └─ GET /git-history   → raw per-commit stats
        │
        ▼
gitCommitsWithLoc (computed)  → current snapshot theke PICHONE hete
                                 proti commit-e LOC / Fns / MI ESTIMATE kore
        │
        ▼
Sidebar-e "Git History — Metrics Trend" table
```

Gurutwopurno kotha: **Backend shudhu raw commit data (insertions, deletions, fn added/removed) dey. Per-commit LOC / Fns / MI Backend-e calculate hoy na — Frontend current snapshot theke pichone giye estimate kore.**

---

## 2. Backend — kibhabe commit data ber hoy

### 2.1 Git repo detect kora — `_find_git_root`

```python
def _find_git_root(base_path):
    if (base_path / ".git").is_dir(): return base_path
    for child in base_path.iterdir():          # ZIP-er bhitore ekta subfolder-e thakle
        if child.is_dir() and (child / ".git").is_dir(): return child
```

- ZIP extract korar por extract-folder-er root-e ba **ek level niche** `.git` khuje.
- Pay na → `git_history = None` → Frontend-e "Not detected" hint dekhay.

### 2.2 `/upload` endpoint-e kokhon call hoy

- Shudhu **ZIP upload** hole (`file_name.endswith(".zip")`) git history ber kora hoy.
- Single file ba folder-upload (`files=`) path-e git history ber kora hoy na → panel-e hint dekhay.
- Call-ta `tempfile.TemporaryDirectory()` block-er **bhitore** hoy, karon block shesh hole extracted `.git` delete hoye jay.
- Result `SESSION_CACHE[session_id]["git_history"]`-te rakha hoy.

### 2.3 `_get_git_history(repo_path)` — step by step

| Step | Git command | Ki ber hoy |
|---|---|---|
| 1 | `git log --pretty=format:COMMIT\|%h\|%s\|%an\|%ad --date=short --numstat -30` | Last **30** commit: `hash`, `message`, `author`, `date` + proti file-er insertions/deletions |
| 2 | `git rev-list --count HEAD` | `total_commits` (sob commit-er sonkha, 30 na) |
| 3 | `git branch --show-current` | `current_branch` (na thakle `"HEAD"`) |
| 4 | `git show --unified=0 --no-color <hash> -- *.py *.js *.ts ...` | Proti commit-er diff — function add/remove gunte (shudhu **prothom 20** commit) |

**Step 1 parse kora:** output-e `COMMIT|...` header line ar tar niche numstat line (`<ins>\t<del>\t<file>`) thake. Proti numstat line-er jonno:

```python
current["insertions"]    += int(cols[0])   # binary file-e "-" thake → 0 dhora hoy
current["deletions"]     += int(cols[1])
current["files_changed"] += 1
```

**Churn:**
```python
commit["churn"] = commit["insertions"] + commit["deletions"]
```

**Function delta (regex diff-er upor):**
```python
fn_re_add = r'^\+[^+].*\b(?:def |function |func |fn |class )\s+\w'
fn_re_del = r'^\-[^-].*\b(?:def |function |func |fn |class )\s+\w'
fn_added   = count of added   lines matching fn_re_add
fn_removed = count of removed lines matching fn_re_del
```
- Language: Python (`def`), JS/TS (`function`), Go (`func`), Rust (`fn`), ar `class` keyword.
- Shudhu code file (`.py .js .ts .jsx .tsx .java .go .rs .cs`) dhora hoy.
- `[^+]` / `[^-]` diff-er `+++` / `---` file-header line bad dey.
- Ei ta **approximation** — regex-based, tai arrow function / method (Java `public void foo()`) miss hote pare, ar `class` keyword-o function count-e dhora hoy.

### 2.4 Final response shape

`GET /git-history` (header `X-Session-ID` lage):

```json
{
  "available": true,
  "total_commits": 80,
  "current_branch": "branch1",
  "commits": [
    {
      "hash": "adae877", "message": "...", "author": "...", "date": "2026-10-01",
      "insertions": 12, "deletions": 4, "files_changed": 2,
      "churn": 16, "fn_added": 1, "fn_removed": 0
    }
  ]
}
```

Git na thakle: `{"available": false, "message": "No git repository detected in the upload."}`.

---

## 3. Je metrics gulo commit-er sathe change hoy

### 3.1 Raw (Backend theke, exact)

| Metric | Meaning | Kibhabe ber hoy |
|---|---|---|
| `insertions` | Koto line add hoyeche | `git log --numstat` column 1 sum |
| `deletions` | Koto line delete hoyeche | `git log --numstat` column 2 sum |
| `files_changed` | Koto file touch hoyeche | numstat line-er sonkha |
| `churn` | Code volatility | `insertions + deletions` |
| `fn_added` / `fn_removed` | Function/class definition add/remove | diff-er upor regex |

### 3.2 Derived (Frontend-e, ESTIMATE)

| Column | Formula | Meaning |
|---|---|---|
| **Δ LOC** (`netDelta`) | `insertions − deletions` | Oi commit-e project koto line barlo/komlo |
| **fnDelta** | `fn_added − fn_removed` | Oi commit-e function sonkha koto change |
| **LOC** (`estimatedLoc`) | Current `sloc` theke pichone: `loc_prev = loc − netDelta` | Oi commit-er shomoy project-er LOC koto chilo |
| **Fns** (`estimatedFns`) | Current `total_functions` theke pichone: `fns_prev = fns − fnDelta` | Oi commit-er shomoy function koto chilo |
| **MI** (`estimatedMi`) | Niche dekho | Oi commit-er shomoy Maintainability Index |

### 3.3 Pichone hete estimate kora (Frontend, `gitCommitsWithLoc`)

Commits **newest-first** ashe. Prothom (newest) commit = current state, tai:

```js
let loc = metricsData.sloc;               // current
let fns = metricsData.total_functions;    // current

commits.map(c => {
  netDelta     = c.insertions - c.deletions;
  fnDelta      = c.fn_added   - c.fn_removed;
  estimatedLoc = max(0, loc);             // ei commit-er por state
  estimatedFns = max(0, fns);
  estimatedMi  = estimateMi(estimatedLoc);
  loc = max(0, loc - netDelta);           // ekhon ager commit-er jonno undo kore
  fns = max(0, fns - fnDelta);
});
```

**Udahoron:** current LOC = 1000.
- Commit A (newest): +50 −10 → netDelta = +40. Dekhabe LOC = **1000**. Tarpor loc = 960.
- Commit B: +20 −30 → netDelta = −10. Dekhabe LOC = **960**. Tarpor loc = 970.
- Commit C: dekhabe LOC = **970**.

### 3.4 MI estimation

```js
estimateMi(loc) {
  avgLocPerFile = max(1, loc / total_files);
  raw = 171 − 5.2·ln(halstead_volume) − 0.23·avg_cyclomatic − 16.2·ln(avgLocPerFile);
  return round(clamp(raw * 100 / 171, 0, 100));
}
```

- Shudhu **LOC** commit-wise change hoy (ar tai `avgLocPerFile`).
- `halstead_volume`, `avg_cyclomatic`, `total_files` **current snapshot-er value-i constant** thake, purano commit-er jonno recalculate hoy na.
- Tai MI trend = "LOC barle / komle MI kemon change hoto" — actual historical MI na.

**Note (inconsistency):** Backend `_maintainability_index` (metrics.py) **avg SLOC per function** use kore (`avg_loc_per_fn`), kintu Frontend estimate **avg LOC per file** use kore. Tai Frontend-er newest commit-er MI ar upore-er "Quality snapshot"-er MI hubohu mile na-o jete pare.

### 3.5 Current snapshot-er metrics (Quality bar)

Panel-er upore ekta "quality bar" ache — eita commit-wise na, **current upload-er** `/metrics` theke:
- **MI** — `maintainability_index` (≥65 green, ≥40 yellow, else red)
- **Cyclo CC** — `avg_cyclomatic` (>10 red, >5 yellow, else green)
- **Cognitive** — `cognitive_complexity` (>15 red, >8 yellow, else green)

---

## 4. Frontend — UI kibhabe kaj kore

### 4.1 Data load

`fetchAnalysisPanels()` ([GraphView.vue](Frontend/src/components/GraphView.vue)) parallel-e `/metrics` ar `/git-history` call kore:

```js
const gh = await results[3].json();
gitHistory.value = gh?.available ? gh : null;   // na thakle panel-er jaygay hint
```

Notun upload-er age `gitHistory.value = null` kora hoy (reset).

### 4.2 Panel rendering

| Condition | Ki dekhay |
|---|---|
| `gitHistory` ache | **"Git History — Metrics Trend"** panel |
| `gitHistory` nai, kintu analysis shesh | "Not detected in this upload" hint + ZIP-e `.git` kibhabe rakhte hobe tar steps |

Panel-er ongsho:
1. **Header** — branch name (`🌿`) + `total_commits` (real total, 30 na).
2. **Quality bar** — MI, Cyclo CC, Cognitive (current).
3. **Table header** — `Commit | LOC | Fns | MI | Δ LOC`.
4. **Commit row** (`gitCommitsPage`):
   - Short hash, message, date
   - `⚡churn` badge — rong: `>200` red (high), `>50` yellow (medium), otherwise grey (low)
   - `📄files_changed`
   - `LOC`, `Fns` (estimated), `MI` (green ≥65, yellow ≥40, red <40)
   - `Δ LOC` — positive green (`+`), negative red, zero grey
   - Hover tooltip: full message, author, files changed, churn
5. **Pagination** — default 10 ta; "Show more" 10 kore baray, "Show less" 10-e fere jay.
6. **Note** — "LOC, Fns, MI estimated backwards from current snapshot."

---

## 5. Limitations (jana dorkar)

| Limitation | Karon |
|---|---|
| Shudhu **last 30 commit** | `git log -30` |
| Function delta shudhu **prothom 20 commit**-er | Performance — `git show` slow; baki commit-e `fn_added` thake na (undefined → `0` dhora hoy) |
| LOC / Fns / MI **exact na, estimate** | Purano commit checkout kore re-analyze kora hoy na; current snapshot theke backwards calculate |
| MI-te shudhu LOC change dhora hoy | Halstead, cyclomatic, file count constant |
| Function count regex-based | Tree-sitter na, diff-er text-er upor regex |
| Shudhu ZIP upload-e kaj kore | Folder/single-file path-e git history capture kora hoy na |
| Binary file-er insertions/deletions `0` | numstat-e `-` ashe |
| Merge commit-e numstat khali thakte pare | `git log --numstat` default-e merge-er diff dey na |
| LOC = SLOC, whole-repo-er | Non-code file (md, json) churn-e dhora hoy, kintu LOC estimate-e na — tai pichone gele drift hote pare |

---

## 6. Quick reference

```
Backend   GET /git-history                → raw: insertions, deletions, files_changed, churn, fn_added, fn_removed
Backend   GET /metrics                    → current: sloc, total_functions, total_files, halstead_volume, avg_cyclomatic, MI
Frontend  gitCommitsWithLoc (computed)    → netDelta, fnDelta, estimatedLoc, estimatedFns, estimatedMi
Frontend  Git History panel               → table + churn badge + pagination
```
