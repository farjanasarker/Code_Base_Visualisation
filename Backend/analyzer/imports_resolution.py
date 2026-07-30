"""Module-structure detection, import extraction/resolution, and unused-import
detection across the supported languages, plus per-function parameter counts.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from .parser import ParsedFunction


def _detect_module_structure(files: List[Dict]) -> Dict[str, str]:
    """
    Detect module assignments from the uploaded folder hierarchy.

    Rules:
    1. Prefer the path that starts at the uploaded root folder.
     2. If a file lives directly under src/, it has no module and should be
         rendered as a file node.
     3. If a file lives under src/<subdir>/..., its module is the subdir path
         relative to src.
     4. If a file is not under src/, its module is its parent directory.

    Examples:
    - lab6/src/Builder.java -> lab6/src
    - lab6/src/lab6b/Image.java -> lab6/src/lab6b
    - lab6/README.md -> lab6

    Returns a mapping of file path -> module name.
    """
    module_map = {}

    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/")

    def _as_module_path(path: str) -> str:
        normalized = _normalize_path(path)
        parts = Path(normalized).parts
        if not parts:
            return "root"

        try:
            src_index = parts.index("src")
        except ValueError:
            src_index = -1

        if src_index >= 0:
            remaining = parts[src_index + 1:]
            if len(remaining) <= 1:
                return ""

            module_parts = list(remaining[:-1])
            return Path(*module_parts).as_posix() if module_parts else ""

        if len(parts) > 1:
            return Path(*parts[:-1]).as_posix()

        return ""

    for file_info in files:
        path = file_info.get("path", "")
        if path:
            module_map[path] = _as_module_path(path)

    return module_map


def _module_basename(module_path: str) -> str:
    """
    Extract a usable stem from a module specifier string.

    Examples
    --------
    './utils/helpers'  → 'helpers'
    '../db'            → 'db'
    'lodash'           → 'lodash'
    'pkg/name'         → 'name'
    """
    # take the last path component's stem (handles multi-level paths too)
    stem = Path(module_path.rstrip("/")).stem if module_path else ""
    return stem


def _build_stem_to_files(all_functions: List[Dict]) -> Dict[str, List[str]]:
    """Build a mapping of file stem -> list of file paths (handles duplicate stems)."""
    from collections import defaultdict
    stem_map: Dict[str, List[str]] = defaultdict(list)
    seen: set = set()
    for fn in all_functions:
        fp = fn.get("file")
        if fp and fp not in seen:
            seen.add(fp)
            stem = Path(fp).stem
            stem_map[stem].append(fp)
            # Also index without extension in case require() includes '.js'
            # e.g. require('../controllers/ticketController.js') -> stem already correct
    return stem_map


def _resolve_import(raw_import: str, stem_to_files: Dict[str, List[str]], importing_file: str = "") -> str | None:
    """
    Resolve a raw import/require path to an actual file path.

    When multiple files share the same stem (e.g. controllers/auth.js and
    routes/auth.js both have stem 'auth'), use the directory hint embedded
    in the import specifier to pick the best match.

    Examples
    --------
    '../controllers/auth'  → 'controllers/auth.js'   (not routes/auth.js)
    '../utils/sendMail'    → 'utils/sendMail.js'
    """
    stem = Path(raw_import.rstrip("/")).stem
    candidates = stem_to_files.get(stem, [])

    if not candidates:
        return None

    # Filter out self-reference (a file importing itself makes no sense)
    if importing_file:
        candidates = [c for c in candidates if c != importing_file]
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Use directory segments from the import specifier as hints
    # e.g. '../controllers/auth' -> parts after stripping leading dots: ['controllers', 'auth']
    hint_parts = [p for p in Path(raw_import).parts if p not in (".", "..")]
    # Walk hint parts from most-specific to least-specific (excluding the final filename)
    dir_hints = [h.lower() for h in hint_parts[:-1]]

    for hint in reversed(dir_hints):
        for candidate in candidates:
            cand_dirs = [p.lower() for p in Path(candidate).parts[:-1]]
            if hint in cand_dirs:
                return candidate

    # Fallback: first candidate
    return candidates[0]


def _extract_file_imports(content: str, language: str) -> List[str]:
    imports = []

    if language == "java":
        # import com.example.Foo; → "Foo"
        for match in re.finditer(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[-1])
        # new ClassName(  /  extends X  /  implements X, Y
        for match in re.finditer(r"\bnew\s+([A-Z][A-Za-z0-9_]*)\s*\(", content):
            imports.append(match.group(1))
        for match in re.finditer(r"\bextends\s+([A-Z][A-Za-z0-9_]*)\b", content):
            imports.append(match.group(1))
        for match in re.finditer(r"\bimplements\s+([A-Z][A-Za-z0-9_\s,]*)\b", content):
            names = [p.strip() for p in match.group(1).split(",") if p.strip()]
            imports.extend(names)

    elif language in ("javascript", "typescript"):
        # ES module:  import X from './foo'   /  import { X } from './foo'
        # require():  require('./foo')
        # Store the raw specifier so callers can do directory-hint resolution.
        # External packages (no leading dot) are stored as their stem only.
        for match in re.finditer(
            r"""import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""", content
        ):
            raw = match.group(1)
            imports.append(raw if raw.startswith(".") else _module_basename(raw))
        for match in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", content):
            raw = match.group(1)
            imports.append(raw if raw.startswith(".") else _module_basename(raw))

    elif language == "python":
        # import foo.bar  /  from foo.bar import baz
        for match in re.finditer(r"^\s*import\s+([\w.]+)", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[0])
        for match in re.finditer(r"^\s*from\s+([\w.]+)\s+import", content, re.MULTILINE):
            raw = match.group(1)
            # relative imports like "from . import x" are skipped (no useful file target)
            if raw.startswith("."):
                continue
            imports.append(raw.split(".")[0])

    elif language == "go":
        # import "pkg/name"  /  import ( "pkg/name" \n "other" )
        for match in re.finditer(r'"([\w./\-]+)"', content):
            imports.append(_module_basename(match.group(1)))

    elif language == "rust":
        # use crate::foo::bar;  /  use foo::{Bar, Baz};
        for match in re.finditer(r"^\s*use\s+([\w:]+)", content, re.MULTILINE):
            first = match.group(1).split("::")[0]
            if first not in ("crate", "super", "self", "std", "core", "alloc"):
                imports.append(first)
            else:
                # intra-crate: take second segment as the local module name
                parts = match.group(1).split("::")
                if len(parts) >= 2 and parts[1]:
                    imports.append(parts[1])

    elif language in ("cpp", "c"):
        # #include "localfile.h"  — angle-bracket system headers are intentionally skipped
        for match in re.finditer(r'#include\s+"([^"]+)"', content):
            imports.append(Path(match.group(1)).stem)

    elif language == "csharp":
        # using Foo.Bar;  /  using static Foo.Bar;
        for match in re.finditer(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[-1])

    # De-duplicate while preserving order
    seen: set = set()
    deduped: List[str] = []
    for name in imports:
        if name and name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def detect_unused_imports(content: str, language: str, imports: List[str]) -> List[str]:
    """Return import names from `imports` that never appear in the non-import body of `content`."""
    # Strip import statement lines so we don't count the declaration itself as usage
    lines = content.split("\n")
    body_lines: List[str] = []
    in_import_block = False  # for Go multi-line import blocks

    for line in lines:
        s = line.strip()
        if language == "python":
            if s.startswith("import ") or s.startswith("from "):
                continue
        elif language in ("javascript", "typescript"):
            if s.startswith("import ") or ("require(" in s and "=" in s):
                continue
        elif language == "java":
            if s.startswith("import "):
                continue
        elif language == "go":
            if s.startswith("import ("):
                in_import_block = True
                continue
            if in_import_block:
                if s == ")":
                    in_import_block = False
                continue
            if s.startswith("import "):
                continue
        elif language == "rust":
            if s.startswith("use "):
                continue
        elif language in ("c", "cpp"):
            if s.startswith("#include"):
                continue
        elif language == "csharp":
            if s.startswith("using "):
                continue
        body_lines.append(line)

    body = "\n".join(body_lines)
    unused: List[str] = []
    for imp in imports:
        if not re.search(r"\b" + re.escape(imp) + r"\b", body):
            unused.append(imp)
    return unused


def _fn_param_count(fn: "ParsedFunction", content_map: Dict[str, str]) -> int:
    """Extract parameter count for a function from its signature line."""
    content = content_map.get(fn.file, "")
    ls = fn.line_start
    if not content or ls <= 0:
        return 0
    lines = content.split("\n")
    if ls > len(lines):
        return 0
    sig = lines[ls - 1]
    ps, pe = sig.find("("), sig.rfind(")")
    if ps == -1 or pe <= ps:
        return 0
    pstr = sig[ps + 1:pe].strip()
    if not pstr:
        return 0
    pl = [p.strip() for p in pstr.split(",") if p.strip()]
    if fn.language == "python" and pl and pl[0] in ("self", "cls"):
        pl = pl[1:]
    return len(pl)
