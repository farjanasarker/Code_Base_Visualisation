# Dynamic Slicing – Kivabe Kaj Kore (Simple Explanation)

## Dynamic slice ki?

Ekta function **ekbar run** kore dekha hoy kon kon statement actually execute holo.
Tarpor ekta **(statement, variable)** pick kora hoy — eta holo *slicing criterion*.
Dynamic slice bole: "**ei run e**, ei variable er value ta ei statement e kon kon statement er karone ashlo?"

Static slicing sob possible path dhore. Dynamic slicing sudhu **je path ta sotti execute holo** seta dhore, tai slice choto ar precise hoy.

Ei project e eta **backward slice** (criterion theke pichone jaoa).

---

## Example

File: `Backend/tests/fixtures/dynamic_slice_example/program_slice_example.py`

```python
def f(X):
    if X < 0:            # S2
        Y = f1(X)        # S3
        Z = g1(X)        # S4
    else:
        if X == 0:       # S5
            Y = f2(X)    # S6
            Z = g2(X)    # S7
        else:
            Y = f3(X)    # S8
            Z = g3(X)    # S9
    write(Y)             # S10
    write(Z)             # S11
```
(`S1` = function entry, jekhane parameter `X` bind hoy.)

Dhoro `X = 5` diye run korlam. Executed path: `S1 → S2 → S5 → S8 → S9 → S10 → S11`.
Criterion: `(S10, Y)`. Slice = **S1, S2, S5, S8, S10**.
`S3, S4, S6, S7` slice e nai karon segulo run hoy-i ni. `S9` o nai karon `Z` ta `Y` er upor depend kore na.

---

## Step-by-step pipeline

### Step 1 — Statement gulo toiri (static, ekbar)
File: `Backend/dynamic_analysis/statements.py`

Function er source ke Python `ast` diye parse kore protita statement ke ekta id (`S1, S2, ...`) deya hoy. Protita statement er jonno save hoy:
- `line_no`, `kind`, `source_text`
- **`reads`** – kon variable pore
- **`writes`** – kon variable likhe

Sathe **CONTROL_DEP edge** banano hoy: kono statement `if`/`while` er bhitore thakle, oi `if` ta tar *controller*.
(Jemon `S3 ← S2`, `S6 ← S5`, `S5 ← S2`.)

### Step 2 — Function ta sandbox e run kora
File: `Backend/dynamic_analysis/runner.py` → `run_dynamic_function`

- User input deya parameter diye function sandbox e run hoy (`sandbox.py`).
- `sys.settrace` diye **kon kon line execute holo, kon order e** — seta record hoy (`executed_lines`).
- Entry line (`S1`) trace e ashe na, tai seta manually shurute add kora hoy.
- Line number ke statement id te map kora hoy.

### Step 3 — DYNAMIC_DATA_DEP edge banano
Same function (`run_dynamic_function`), executed order e ghure:

```python
last_writer = {}
for stmt in executed_in_order:
    for var in stmt.reads:
        # ei variable ke last ke likhechilo?
        edge: last_writer[var] -> stmt   (variable_name = var)
    for var in stmt.writes:
        last_writer[var] = stmt
```

Mane: "ei statement ta jei variable pore, seta **sorboshesh kon executed statement** likhechilo" — oi statement er sathe data-dependency edge.
Eta static na, **ei run er actual order** onujayi, tai dynamic.

Edge gulo database e save hoy (`db.record_execution`).

### Step 4 — Backward slice compute kora
File: `Backend/dynamic_analysis/slicer.py` → `compute_backward_slice`
API: `POST /dynamic/runs/{run_id}/slice` (body: `statement_node_id`, `variable_name`)

Eta ekta **worklist (queue) traversal**. Dui dhoroner hop ache:

| Hop | Kon shorte | Kivabe |
|---|---|---|
| **DYNAMIC_DATA_DEP** | variable-specific | Current statement e jei variable "of interest", sudhu tar writer ke follow koro |
| **CONTROL_DEP** | unconditional | Je statement visit hoy, tar controlling `if`/`while` always slice e ashbe |

Algorithm:

```
queue = [(criterion_stmt, {criterion_variable})]
while queue:
    stmt, vars = queue.pop()
    visited.add(stmt)

    # 1. control hop
    pred = control_predecessor[stmt]
    if pred: queue.push(pred, pred.reads)

    # 2. data hop
    for var in vars:
        writer = data_dep[(stmt, var)]
        if writer: queue.push(writer, writer.reads)

return visited, sorted by execution order
```

Mul idea: kono statement slice e dhukle, tar **reads** variable gulor writer gulo o slice e dhukbe (karon tara value dey). Ar tar controlling predicate-o dhukbe (karon predicate decide korche statement ta run hobe ki na). Eta repeat hoy jotokkhon na ar notun kichu paoa jai.

`data_dep_expanded` / `control_expanded` set diye ekই jinis duibar process kora hoy na — loop thakleo infinite loop hoy na.

### Step 5 — Result
Response: `{"slice_node_ids": [...]}` — execution order e sajano statement id. Frontend (`GraphView.vue`, `FunctionNode.vue`, `SliceParamForm.vue`) ei node gulo highlight kore dekhay.

---

## Example trace (X = 5, criterion = (S10, Y))

1. Start: `(S10, {Y})`
2. S10 er control pred: top-level, tai nai. Data: `Y` er last writer = **S8** → queue e `(S8, {X})`
3. S8: control pred = **S5** → `(S5, {X})`. Data: `X` er writer = **S1** → `(S1, {})`
4. S5: control pred = **S2** → `(S2, {X})`. Data: `X` → S1
5. S2: control pred nai. Data: `X` → S1
6. S1: kichu nai.

Visited = `{S10, S8, S5, S2, S1}` ✅

---

## File summary

| File | Kaj |
|---|---|
| `dynamic_analysis/statements.py` | AST theke statement + reads/writes + CONTROL_DEP |
| `dynamic_analysis/sandbox.py` | Function run kore executed lines trace kore |
| `dynamic_analysis/runner.py` | Run orchestrate kore, DATA_DEP edge banay, slice call kore |
| `dynamic_analysis/slicer.py` | Backward slice algorithm |
| `main.py` | `/dynamic/runs/{run_id}/slice` API endpoint |
| `tests/test_dynamic_slice_endpoint.py` | Slice test |

## Limitation (MVP)
- Class method support nai.
- Unsupported type er parameter hole dynamic analysis hobe na.
- Trace boro hole `truncated` status ashe.
