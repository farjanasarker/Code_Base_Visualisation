"""Integrated codebase metrics: cycle/call-chain structural analysis,
Halstead volume/difficulty, and the Microsoft Maintainability Index, rolled
up into the aggregate metrics dict the dashboard reads.
"""

import math
import re
from collections import deque
from typing import Dict, List, Optional

from .heuristics import _is_entry_point

# ── Integrated Metrics Computation ─────────────────────────────────────────

def _detect_cycles(functions: List[Dict]) -> List[List[str]]:
    """DFS-based cycle detection on the call graph. Returns up to 10 short cycles."""
    fn_set = {fn["name"] for fn in functions if fn.get("name") != "__file__"}
    adj: Dict[str, List[str]] = {}
    for fn in functions:
        n = fn.get("name", "")
        if n == "__file__":
            continue
        call_targets = fn.get("call_targets") or {}
        adj[n] = [
            c for c in fn.get("calls", [])
            if c in fn_set
            # A `super().<name>()` call to a method sharing the caller's own
            # name (e.g. `super().__init__()`) is a real edge to the parent
            # implementation, not a same-node self-loop — don't let it read
            # as a circular dependency.
            and not (c == n and call_targets.get(c) == "__super__")
        ]

    found: List[List[str]] = []
    visited: set = set()
    stack: List[str] = []
    on_stack: Dict[str, int] = {}

    def _dfs(node: str) -> None:
        if len(found) >= 10:
            return
        visited.add(node)
        on_stack[node] = len(stack)
        stack.append(node)
        for nxt in adj.get(node, []):
            if nxt not in visited:
                _dfs(nxt)
            elif nxt in on_stack and (len(stack) - on_stack[nxt]) <= 6:
                found.append(stack[on_stack[nxt]:] + [nxt])
        stack.pop()
        del on_stack[node]

    for node in list(adj):
        if node not in visited:
            _dfs(node)

    seen_keys: set = set()
    unique: List[List[str]] = []
    for c in found:
        k = frozenset(c)
        if k not in seen_keys:
            seen_keys.add(k)
            unique.append(c)
    return unique[:10]


def _max_call_chain_depth(functions: List[Dict]) -> int:
    """BFS from root functions to find the longest call chain."""
    fn_set = {fn["name"] for fn in functions if fn.get("name") != "__file__"}
    adj: Dict[str, List[str]] = {}
    in_deg: Dict[str, int] = {}
    for fn in functions:
        n = fn.get("name", "")
        if n == "__file__":
            continue
        calls = [c for c in fn.get("calls", []) if c in fn_set]
        adj[n] = calls
        in_deg.setdefault(n, 0)
        for c in calls:
            in_deg[c] = in_deg.get(c, 0) + 1

    roots = [n for n, d in in_deg.items() if d == 0] or list(adj)[:5]
    max_d = 0
    for root in roots[:8]:
        q: deque = deque([(root, 0, frozenset([root]))])
        while q:
            node, d, vis = q.popleft()
            if d > max_d:
                max_d = d
            if d >= 40:
                continue
            for nxt in adj.get(node, []):
                if nxt not in vis:
                    q.append((nxt, d + 1, vis | {nxt}))
    return max_d


def _halstead_metrics(files: List[Dict]) -> Dict:
    """Compute simplified Halstead program metrics across all source files."""
    op_re = re.compile(
        r'\b(?:if|elif|else|while|for|switch|case|default|do|'
        r'return|break|continue|throw|raise|yield|'
        r'new|delete|typeof|instanceof|'
        r'class|function|def|lambda|'
        r'try|catch|except|finally|'
        r'async|await|import|from|'
        r'and|or|not|in|is|with|'
        r'var|let|const|pub|fn|impl|use|match|struct|enum)\b|'
        r'(?:<<=?|>>=?|>>>|<<|>>'
        r'|\*\*|//|->|=>|::'
        r'|[+\-*/%&|^~]=?|[<>!=]=?|&&|\|\||[?:,;])'
    )
    id_re = re.compile(r'\b[A-Za-z_]\w*\b')
    noise_re = re.compile(
        r'(""".*?"""|\'\'\'.*?\'\'\'|"[^"\\]*"|\'[^\'\\]*\'|`[^`]*`'
        r'|//[^\n]*|/\*.*?\*/|#[^\n]*)',
        re.DOTALL,
    )

    all_ops: List[str] = []
    all_ids: List[str] = []
    op_kw_cache: Optional[set] = None

    for f in files:
        raw = f.get("content", "")
        cleaned = noise_re.sub(" ", raw)
        ops = op_re.findall(cleaned)
        if op_kw_cache is None:
            op_kw_cache = set(ops)
        else:
            op_kw_cache.update(ops)
        all_ops.extend(ops)
        all_ids.extend(i for i in id_re.findall(cleaned) if i not in (op_kw_cache or set()))

    n1 = len(set(all_ops))
    n2 = len(set(all_ids))
    N1, N2 = len(all_ops), len(all_ids)
    vocab = n1 + n2
    length = N1 + N2
    volume = length * math.log2(max(vocab, 2))
    difficulty = (n1 / 2) * (N2 / max(n2, 1))
    return {
        "volume": round(volume, 1),
        "difficulty": round(difficulty, 1),
        "effort": round(difficulty * volume, 0),
        "vocab": vocab,
    }


def _maintainability_index(hv: float, avg_cc: float, avg_loc: float) -> float:
    """Microsoft Maintainability Index (0–100, higher = more maintainable)."""
    try:
        raw = (171 - 5.2 * math.log(max(hv, 1))
               - 0.23 * avg_cc
               - 16.2 * math.log(max(avg_loc, 1)))
        return round(max(0.0, min(100.0, raw * 100 / 171)), 1)
    except Exception:
        return 50.0


def compute_aggregate_metrics(all_functions: List[Dict], files: List[Dict]) -> Dict:
    """Compute comprehensive Integrated Metrics Dashboard data."""
    real = [fn for fn in all_functions if fn.get("name") != "__file__"]

    # Build content map for parameter extraction
    content_map: Dict[str, str] = {f.get("path", ""): f.get("content", "") for f in files}

    # ── LOC / SLOC ──────────────────────────────────────────────────────────
    total_loc = total_sloc = 0
    for f in files:
        lines = f.get("content", "").split("\n")
        total_loc += len(lines)
        total_sloc += sum(
            1 for ln in lines
            if ln.strip() and not ln.strip().startswith(("#", "//", "/*", "*", "'''", '"""'))
        )

    n_files = len(files)
    n_fns = len(real)
    total_calls = sum(fn.get("fan_out", 0) for fn in real)

    # ── Cyclomatic Complexity ────────────────────────────────────────────────
    ccs = [fn.get("complexity", 1) for fn in real]
    avg_cc = round(sum(ccs) / max(len(ccs), 1), 2)
    max_cc = max(ccs, default=1)
    total_decision = sum(max(0, c - 1) for c in ccs)

    # ── Cognitive Complexity (approximation) ────────────────────────────────
    # Full cognitive CC requires a complete AST nesting walk; this is an
    # approximation that weights avg cyclomatic CC by a base factor and adds a
    # nesting penalty derived from the per-function max_nesting_depth values we
    # already have.  Reported in the UI as an approximation.
    nesting_penalty = sum(fn.get("max_nesting_depth", 0) for fn in real)
    cognitive_cc = round(avg_cc * 1.2 + (nesting_penalty / max(n_fns, 1)) * 0.5, 2)

    # ── Parameters ──────────────────────────────────────────────────────────
    param_counts: List[int] = []
    for fn in real:
        content = content_map.get(fn.get("file", ""), "")
        ls = fn.get("line_start", 0)
        if content and 0 < ls <= content.count("\n") + 1:
            fn_lines = content.split("\n")
            # Join up to 10 lines from line_start so multi-line signatures are handled.
            sig_lines: List[str] = []
            for line in fn_lines[ls - 1: ls + 10]:
                sig_lines.append(line)
                if ")" in line:
                    break
            sig = " ".join(sig_lines)
            ps, pe = sig.find("("), sig.rfind(")")
            if ps != -1 and pe > ps:
                pstr = sig[ps + 1:pe].strip()
                if pstr:
                    pl = [p.strip() for p in pstr.split(",") if p.strip()]
                    if fn.get("language") == "python" and pl and pl[0] in ("self", "cls"):
                        pl = pl[1:]
                    param_counts.append(len(pl))
                else:
                    param_counts.append(0)

    avg_params = round(sum(param_counts) / max(len(param_counts), 1), 1)
    max_params = max(param_counts, default=0)

    # ── Orphan Nodes ────────────────────────────────────────────────────────
    orphans = sum(
        1 for fn in real
        if fn.get("fan_in", 0) == 0
        and fn.get("fan_out", 0) == 0
        and not _is_entry_point(fn.get("name", ""))
    )

    # ── Structural Analysis ─────────────────────────────────────────────────
    cycles = _detect_cycles(real)
    max_depth = _max_call_chain_depth(real)

    # ── Halstead ────────────────────────────────────────────────────────────
    hs = _halstead_metrics(files)

    # ── Maintainability Index ────────────────────────────────────────────────
    # Microsoft MI formula uses average LOC *per function*, not per file.
    # Using per-file LOC artificially deflates MI for large codebases.
    avg_loc_per_fn = total_sloc / max(n_fns, 1)
    mi = _maintainability_index(hs["volume"], avg_cc, avg_loc_per_fn)
    mi_label = (
        "Highly Maintainable" if mi >= 85 else
        "Maintainable"        if mi >= 65 else
        "Needs Attention"     if mi >= 40 else
        "Hard to Maintain"
    )

    return {
        "loc": total_loc,
        "sloc": total_sloc,
        "total_files": n_files,
        "total_functions": n_fns,
        "total_calls": total_calls,
        "avg_cyclomatic": avg_cc,
        "max_cyclomatic": max_cc,
        "decision_points": total_decision,
        "cognitive_complexity": cognitive_cc,
        "avg_parameters": avg_params,
        "max_parameters": max_params,
        "orphan_nodes": orphans,
        "circular_deps": len(cycles),
        "circular_dep_details": [" → ".join(c) for c in cycles[:5]],
        "max_call_chain_depth": max_depth,
        "halstead_volume": hs["volume"],
        "halstead_difficulty": hs["difficulty"],
        "maintainability_index": mi,
        "maintainability_label": mi_label,
    }
