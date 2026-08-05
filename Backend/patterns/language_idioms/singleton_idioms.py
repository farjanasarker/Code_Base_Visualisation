"""Language-idiom Singleton detection — Go's `sync.Once` and Rust's
`lazy_static!`/`OnceCell`/`OnceLock` express Singleton without a self-typed
field + self-instantiating method anywhere in the graph (no field holds the
instance at all — the runtime/macro owns it), which is what
patterns/specs/singleton.yaml's structural predicate (singleton_candidates)
looks for.

This is the one case in the whole GoF engine that genuinely can't be
structural — `sync.Once`/`lazy_static!` are language keywords/macros, not a
graph shape, so this operates on raw file *content*, not the class graph
everything else in `patterns/` works from. Deliberately isolated in its own
`language_idioms/` package rather than folded into `predicates.py`:
everything else in that module is graph-only; this is the one opt-in,
idiom-specific exception the design brief calls out explicitly.

Results from this module are never blended into the core rule-engine
confidence scores — they're surfaced as a separately-tagged, explicitly
"heuristic match — verify manually" addition alongside the structural
Singleton spec's output (see main.py's `/api/gof-patterns` wiring).
"""

import re
from typing import Dict, List

_GO_IDIOM_PATTERNS = [
    (re.compile(r'\bsync\.Once\b'), "sync.Once"),
]

_RUST_IDIOM_PATTERNS = [
    (re.compile(r'\blazy_static!\s*\{'), "lazy_static!"),
    (re.compile(r'\bOnceCell\s*<'), "OnceCell"),
    (re.compile(r'\bOnceLock\s*<'), "OnceLock"),
]

_PATTERNS_BY_LANGUAGE = {"go": _GO_IDIOM_PATTERNS, "rust": _RUST_IDIOM_PATTERNS}


def scan_file(path: str, content: str, language: str) -> List[Dict]:
    """Every language-idiom Singleton marker found in one file's content,
    as [{file, line, idiom}]."""
    patterns = _PATTERNS_BY_LANGUAGE.get(language)
    if not patterns:
        return []
    matches = []
    for pattern, idiom_name in patterns:
        for m in pattern.finditer(content):
            line = content.count("\n", 0, m.start()) + 1
            matches.append({"file": path, "line": line, "idiom": idiom_name})
    return matches


def scan_files(files: List[Dict]) -> List[Dict]:
    """Scan every file in `files` (each needs `path`, `content`, `language`)
    for Singleton idiom markers. Called once at upload time, while file
    content is still available — see main.py's upload handler, which
    discards content from the cached file list shortly after this runs.
    """
    out = []
    for f in files:
        out.extend(scan_file(f.get("path", ""), f.get("content", ""), f.get("language", "")))
    return out
