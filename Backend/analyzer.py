from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple
import importlib
import ast
import logging
import re

from db import add_edge

logger = logging.getLogger(__name__)


# Supported language mapping (file extension -> language name)
SUPPORTED_EXTENSIONS = {
    '.py': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.java': 'java',
    '.go': 'go',
    '.rs': 'rust',
    '.cpp': 'cpp',
    '.c': 'c',
    '.cs': 'csharp',
}


# Try importing tree-sitter language bindings; if unavailable, we degrade gracefully.
def _load_tree_sitter_runtime():
    try:
        tree_sitter_module = importlib.import_module("tree_sitter")
        tspython = importlib.import_module("tree_sitter_python")
        tsjavascript = importlib.import_module("tree_sitter_javascript")
        tsjava = importlib.import_module("tree_sitter_java")
        tsgo = importlib.import_module("tree_sitter_go")
        tsrust = importlib.import_module("tree_sitter_rust")

        Language = tree_sitter_module.Language
        Parser = tree_sitter_module.Parser

        tree_sitter_languages = {
            "python":     Language(tspython.language()),
            "javascript": Language(tsjavascript.language()),
            "typescript": Language(tsjavascript.language()),
            "java":       Language(tsjava.language()),
            "go":         Language(tsgo.language()),
            "rust":       Language(tsrust.language()),
        }

        def get_parser(language: str):
            lang = tree_sitter_languages[language]
            parser = Parser()
            parser.set_language(lang)
            return parser

        return tree_sitter_languages, get_parser
    except Exception:
        return {}, None


TREE_SITTER_LANGUAGES, get_parser = _load_tree_sitter_runtime()

if get_parser is None:
    def get_parser(language: str):
        raise RuntimeError("tree-sitter is not available in this environment")


# Tree-sitter queries for function and call extraction (language specific)
FUNCTION_QUERIES = {
    "python": """
        (function_definition
          name: (identifier) @fn_name) @fn_def

        (class_definition
          name: (identifier) @class_name
          body: (block
            (function_definition
              name: (identifier) @method_name) @fn_def))
    """,

    "javascript": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_definition
          name: (property_identifier) @fn_name) @fn_def

        (arrow_function) @fn_def

        (variable_declarator
          name: (identifier) @fn_name
          value: (arrow_function) @fn_def)
    """,

    "typescript": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_definition
          name: (property_identifier) @fn_name) @fn_def

        (arrow_function) @fn_def
    """,

    "java": """
        (method_declaration
          name: (identifier) @fn_name) @fn_def

        (constructor_declaration
          name: (identifier) @fn_name) @fn_def
    """,

    "go": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_declaration
          name: (field_identifier) @fn_name) @fn_def
    """,

    "rust": """
        (function_item
          name: (identifier) @fn_name) @fn_def

        (impl_item
          body: (declaration_list
            (function_item
              name: (identifier) @fn_name) @fn_def))
    """,
}

CALL_QUERIES = {
    "python": """
        (call (identifier) @called_fn)
        (call (attribute attribute: (identifier) @called_fn))
    """,
    "javascript": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (member_expression
          property: (property_identifier) @called_fn))
    """,
    "typescript": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (member_expression
          property: (property_identifier) @called_fn))
    """,
    "java": """
        (method_invocation name: (identifier) @called_fn)
    """,
    "go": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (selector_expression
          field: (field_identifier) @called_fn))
    """,
    "rust": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (field_expression
          field: (field_identifier) @called_fn))
    """,
}


@dataclass
class ParsedFunction:
    name: str
    file: str
    language: str
    module: str
    virtual_module: str
    line_start: int
    line_end: int
    complexity: int = 1
    calls: List[str] = field(default_factory=list)
    fan_in: int = 0
    fan_out: int = 0


class UniversalParser:
    def parse_file(self, filepath: str, content: str, language: str) -> List[ParsedFunction]:
        if language == "python":
            parsed = self._parse_python_ast(filepath, content)
            if parsed:
                return parsed

        try:
            parser = get_parser(language)
        except Exception:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)
            return []

        try:
            tree = parser.parse(bytes(content, "utf8"))
        except Exception:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)
            return []

        functions = self._extract_functions(tree, content, filepath, language)
        if not functions:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)

        for fn in functions:
            fn.calls = self._extract_calls(tree, content, language, fn.name)
            fn.fan_out = len(fn.calls)
        return functions

    def _parse_java_regex(self, filepath: str, content: str) -> List[ParsedFunction]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        class_name = class_match.group(1) if class_match else None

        # Match Java methods and constructors with bodies.
        method_pattern = re.compile(
            r"(?ms)^\s*(?:@[\w.]+\s*)*(?:public|protected|private|static|final|native|synchronized|abstract|strictfp|\s)+"
            r"(?:[\w<>\[\],.?]+\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{"
        )

        functions: List[ParsedFunction] = []
        seen = set()
        keywords = {
            "if", "for", "while", "switch", "catch", "return", "new", "throw", "super", "this",
            "try", "else", "case", "do", "synchronized",
        }

        for match in method_pattern.finditer(content):
            fn_name = match.group(1)
            key = (fn_name, match.start())
            if key in seen:
                continue
            seen.add(key)

            start_line = content.count("\n", 0, match.start()) + 1

            # Find body range by brace matching.
            brace_start = content.find("{", match.end() - 1)
            if brace_start < 0:
                continue
            depth = 0
            end_idx = brace_start
            for i in range(brace_start, len(content)):
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break

            method_body = content[brace_start:end_idx + 1]
            end_line = content.count("\n", 0, end_idx) + 1

            calls = []
            for call_match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", method_body):
                callee = call_match.group(1)
                if callee not in keywords and callee != fn_name:
                    calls.append(callee)

            complexity = 1
            for kw in ["if", "for", "while", "case", "catch", "&&", "||"]:
                complexity += method_body.count(kw)

            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language="java",
                module=module,
                virtual_module=class_name or module,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=sorted(set(calls)),
                fan_out=len(set(calls)),
            ))

        return functions

    def _parse_python_ast(self, filepath: str, content: str) -> List[ParsedFunction]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        functions: List[ParsedFunction] = []
        seen = set()

        class PythonVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_class = None

            def visit_ClassDef(self, node):
                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def visit_FunctionDef(self, node):
                key = (node.name, node.lineno)
                if key in seen:
                    return
                seen.add(key)
                line_end = getattr(node, "end_lineno", node.lineno)
                functions.append(ParsedFunction(
                    name=node.name,
                    file=filepath,
                    language="python",
                    module=module,
                    virtual_module=self.current_class or module,
                    line_start=node.lineno,
                    line_end=line_end,
                    complexity=self._estimate_python_complexity(node),
                    calls=self._extract_python_calls(node),
                ))

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

            def _estimate_python_complexity(self, node):
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Try, ast.BoolOp, ast.Match)):
                        complexity += 1
                return complexity

            def _extract_python_calls(self, node):
                calls = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = None
                        if isinstance(child.func, ast.Name):
                            callee = child.func.id
                        elif isinstance(child.func, ast.Attribute):
                            callee = child.func.attr
                        if callee:
                            calls.add(callee)
                return list(calls)

        visitor = PythonVisitor()
        visitor.visit(tree)
        for fn in functions:
            fn.fan_out = len(fn.calls)
        return functions

    def _extract_functions(self, tree, content: str, filepath: str, language: str) -> List[ParsedFunction]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []

        query = lang_obj.query(FUNCTION_QUERIES[language])
        captures = query.captures(tree.root_node)
        functions: List[ParsedFunction] = []
        seen = set()

        for node, capture_name in captures:
            if "fn_def" not in capture_name:
                continue
            # attempt to get the name child
            name_node = node.child_by_field_name("name")
            fn_name = (
                content[name_node.start_byte:name_node.end_byte]
                if name_node is not None
                else f"anonymous_{node.start_point[0]}"
            )
            key = (fn_name, node.start_point[0])
            if key in seen:
                continue
            seen.add(key)

            module = Path(filepath).parts[0] if Path(filepath).parts else "root"
            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language=language,
                module=module,
                virtual_module=module,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                complexity=self._estimate_complexity(node, content),
            ))
        return functions

    def _extract_calls(self, tree, content: str, language: str, current_fn_name: str) -> List[str]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []
        query = lang_obj.query(CALL_QUERIES[language])
        calls = set()
        for node, _ in query.captures(tree.root_node):
            called = content[node.start_byte:node.end_byte]
            if called and called != current_fn_name:
                calls.add(called)
        return list(calls)

    def _estimate_complexity(self, node, content: str) -> int:
        body_text = content[node.start_byte:node.end_byte]
        keywords = ["if ", "elif ", "else:", "for ", "while ",
                    "case ", "catch", "except", "&&", "||"]
        return 1 + sum(body_text.count(kw) for kw in keywords)

    def compute_fan_in(self, all_functions: List[ParsedFunction]) -> List[ParsedFunction]:
        call_counts: Dict[str, int] = {}
        for fn in all_functions:
            for called in fn.calls:
                call_counts[called] = call_counts.get(called, 0) + 1
        for fn in all_functions:
            fn.fan_in = call_counts.get(fn.name, 0)
        return all_functions


def count_functions_ast(filepath: str, content: str) -> int:
    ext = Path(filepath).suffix.lower()
    language_name = SUPPORTED_EXTENSIONS.get(ext)
    if language_name == "python":
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0

        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count += 1
        return count

    if not language_name or language_name not in TREE_SITTER_LANGUAGES:
        return 0
    try:
        parser = get_parser(language_name)
        tree = parser.parse(bytes(content, "utf8"))
        query = TREE_SITTER_LANGUAGES[language_name].query(FUNCTION_QUERIES[language_name])
        captures = query.captures(tree.root_node)
        return sum(1 for _, name in captures if "fn_def" in name)
    except Exception:
        return 0


def detect_file_strategy(filepath: str, content: str) -> str:
    """
    Returns one of: "data_file", "large_normal", "god_file", "normal"
    """
    lines = content.split("\n")
    line_count = len(lines)
    if line_count <= 10_000:
        return "normal"

    fn_count = count_functions_ast(filepath, content)

    if fn_count < 10:
        return "data_file"
    elif fn_count <= 100:
        return "large_normal"
    else:
        return "god_file"


def chunk_god_file(filepath: str, content: str, language: str, functions: List[Dict]) -> List[Dict]:
    # Strategy 1: class-based chunking
    try:
        classes = []
        if language == "python":
            # lightweight class extractor using AST to avoid extra dependencies
            import ast as _ast
            tree = _ast.parse(content)
            for node in [n for n in tree.body if isinstance(n, _ast.ClassDef)]:
                start = node.lineno
                end = max(getattr(n, 'end_lineno', start) for n in node.body) if node.body else start
                classes.append({"name": node.name, "line_start": start, "line_end": end})
        # For other languages, attempt tree-sitter class extraction
        if not classes and language in TREE_SITTER_LANGUAGES:
            parser = get_parser(language)
            tree = parser.parse(bytes(content, "utf8"))
            q = TREE_SITTER_LANGUAGES[language].query("(class_definition name: (identifier) @class_name) @class_def")
            for node, _ in q.captures(tree.root_node):
                # rough line range
                classes.append({"name": content[node.start_byte:node.end_byte], "line_start": node.start_point[0]+1, "line_end": node.end_point[0]+1})

        if classes:
            chunks = []
            for cls in classes:
                methods = [f for f in functions if cls["line_start"] <= f["line_start"] <= cls["line_end"]]
                chunks.append({
                    "virtual_module": cls["name"],
                    "functions": methods,
                    "line_range": (cls["line_start"], cls["line_end"]),
                    "chunk_strategy": "class",
                })
            return chunks
    except Exception:
        logger.exception("class-based chunking failed")

    # Strategy 2: complexity-based clustering
    high = [f for f in functions if f.get("complexity", 0) > 15]
    medium = [f for f in functions if 5 < f.get("complexity", 0) <= 15]
    low = [f for f in functions if f.get("complexity", 0) <= 5]
    if high or medium:
        return [
            {"virtual_module": "High Complexity", "functions": high, "chunk_strategy": "complexity"},
            {"virtual_module": "Medium Complexity", "functions": medium, "chunk_strategy": "complexity"},
            {"virtual_module": "Low Complexity", "functions": low, "chunk_strategy": "complexity"},
        ]

    # Strategy 3: Line range chunking (fallback)
    CHUNK_SIZE = 50
    sorted_fns = sorted(functions, key=lambda f: f["line_start"])
    chunks = []
    for i in range(0, len(sorted_fns), CHUNK_SIZE):
        batch = sorted_fns[i:i+CHUNK_SIZE]
        if not batch:
            continue
        chunks.append({
            "virtual_module": f"Group {i//CHUNK_SIZE+1} (lines {batch[0]['line_start']}–{batch[-1]['line_end']})",
            "functions": batch,
            "chunk_strategy": "line_range",
        })
    return chunks


def decide_render_strategy(node_count: int) -> Dict:
    if node_count < 100:
        return {"strategy": "show_all", "description": "Render all nodes, no clustering", "max_nodes": node_count}
    elif node_count <= 500:
        return {"strategy": "make_group", "description": "Collapse low-fan nodes into group summary nodes", "max_nodes": 100, "collapse_threshold": 2}
    else:
        return {"strategy": "search_only", "description": "Show top 100 by importance only. User must search to find others.", "max_nodes": 100}


def filter_top_nodes(functions: List[Dict], max_n: int = 100) -> List[Dict]:
    return sorted(functions, key=lambda f: f.get("fan_in", 0) + f.get("fan_out", 0), reverse=True)[:max_n]


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


def analyze_files(files: List[Dict]) -> List[Dict]:
    """Parse all supported files, apply file strategies, chunk god files and store edges via `add_edge`.

    Returns list of parsed function dicts.
    """
    parser = UniversalParser()
    all_functions: List[ParsedFunction] = []
    
    # Detect module structure
    module_map = _detect_module_structure(files)
    file_import_map = {}

    for file_info in files:
        file_path = file_info.get("path", "<in-memory>")
        file_import_map[file_path] = _extract_file_imports(file_info.get("content", ""), file_info.get("language", ""))

    # First pass: parse files and decide strategies
    for file_info in files:
        lang = file_info.get("language")
        if not lang or lang == "unknown":
            continue

        content = file_info.get("content", "")
        if not content.strip():
            continue

        file_path = file_info.get("path", "<in-memory>").replace("\\", "/")
        strategy = detect_file_strategy(file_path, content)
        if strategy == "data_file":
            continue

        parsed = parser.parse_file(file_path, content, lang)
        
        # Override module based on detected structure
        detected_module = module_map.get(file_info.get("path", ""), "root")
        for p in parsed:
            p.module = detected_module

        # convert ParsedFunction objects to dicts for chunking convenience
        parsed_dicts = [p.__dict__ for p in parsed]

        if strategy == "god_file":
            chunks = chunk_god_file(file_path, content, lang, parsed_dicts)
            # assign virtual modules
            for chunk in chunks:
                names_in_chunk = {f["name"] for f in chunk["functions"]}
                for p in parsed:
                    if p.name in names_in_chunk:
                        p.virtual_module = chunk["virtual_module"]

        all_functions.extend(parsed)

    # compute fan-in
    all_functions = parser.compute_fan_in(all_functions)

    # CALLS edges are persisted later in store_all() with proper session scoping.

    # Build set of files that already have at least one parsed function
    files_with_functions = {fn.file for fn in all_functions}

    # For files that produced 0 functions (e.g. JS without tree-sitter), inject a
    # lightweight sentinel dict so their imports still flow into the graph builders.
    file_sentinels: List[Dict] = []
    for file_info in files:
        lang = file_info.get("language")
        if not lang or lang == "unknown":
            continue
        raw_path = file_info.get("path", "<in-memory>")
        norm_path = raw_path.replace("\\", "/")
        if norm_path in files_with_functions:
            continue  # already covered by real function dicts
        detected_module = module_map.get(raw_path, "")
        file_sentinels.append({
            "name": "__file__",
            "file": norm_path,
            "language": lang,
            "module": detected_module,
            "virtual_module": detected_module or norm_path,
            "line_start": 0,
            "line_end": 0,
            "complexity": 0,
            "calls": [],
            "fan_in": 0,
            "fan_out": 0,
            "imports": file_import_map.get(raw_path, []),
        })

    # return serializable list of dicts
    return [
        {
            "name": fn.name,
            "file": fn.file,
            "language": fn.language,
            "module": fn.module,
            "virtual_module": fn.virtual_module,
            "line_start": fn.line_start,
            "line_end": fn.line_end,
            "complexity": fn.complexity,
            "calls": fn.calls,
            "fan_in": fn.fan_in,
            "fan_out": fn.fan_out,
            "imports": file_import_map.get(fn.file, []),
        }
        for fn in all_functions
    ] + file_sentinels


def build_module_graph(all_functions: List[Dict]) -> Dict:
    group_stats = {}
    fn_to_group = {}

    file_to_imports = {}

    for fn in all_functions:
        is_sentinel = fn.get("name") == "__file__"
        module_name = (fn.get("module") or "").strip()
        if module_name:
            group_id = module_name
            group_type = "module"
            label = module_name
        else:
            group_id = fn.get("file")
            group_type = "file"
            label = fn.get("file")

        if not is_sentinel:
            fn_to_group[fn.get("name")] = group_id

        if group_id not in group_stats:
            group_stats[group_id] = {
                "id": group_id,
                "type": group_type,
                "label": label,
                "loc": 0,
                "fn_count": 0,
                "languages": set(),
            }

        if not is_sentinel:
            group_stats[group_id]["loc"] += (fn.get("line_end", 0) - fn.get("line_start", 0))
            group_stats[group_id]["fn_count"] += 1
        group_stats[group_id]["languages"].add(fn.get("language"))
        if fn.get("imports"):
            file_to_imports.setdefault(fn.get("file"), set()).update(fn.get("imports", []))

    file_to_group = {}
    for fn in all_functions:
        file_path = fn.get("file")
        if not file_path:
            continue
        module_name = (fn.get("module") or "").strip()
        file_to_group[file_path] = module_name if module_name else file_path

    file_name_to_group = {}
    for fn in all_functions:
        file_path = fn.get("file")
        if not file_path:
            continue
        file_key = Path(file_path).stem
        file_name_to_group.setdefault(file_key, file_to_group.get(file_path, file_path))

    # Build stem->files map for directory-hint resolution
    stem_to_files_global = _build_stem_to_files(all_functions)

    group_calls = {}
    for fn in all_functions:
        src_group = fn_to_group.get(fn.get("name"))
        for called in fn.get("calls", []):
            tgt_group = fn_to_group.get(called)
            if tgt_group and tgt_group != src_group:
                key = (src_group, tgt_group)
                group_calls[key] = group_calls.get(key, 0) + 1

    for file_path, imported_names in file_to_imports.items():
        src_group = file_to_group.get(file_path)
        for imported_name in imported_names:
            # Try directory-hint resolution first, fall back to stem lookup
            resolved_file = _resolve_import(imported_name, stem_to_files_global, file_path)
            if resolved_file:
                tgt_group = file_to_group.get(resolved_file)
            else:
                tgt_group = file_name_to_group.get(_module_basename(imported_name))
            if tgt_group and tgt_group != src_group:
                key = (src_group, tgt_group)
                group_calls[key] = group_calls.get(key, 0) + 1

    nodes = [
        {
            "id": s["id"],
            "type": s["type"],
            "label": s["label"],
            "loc": s["loc"],
            "fn_count": s["fn_count"],
            "languages": list(s["languages"]),
        }
        for s in group_stats.values()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in group_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": 1}


def build_all_files_graph(all_functions: List[Dict]) -> Dict:
    """Build a flat file-relations graph across all files (no module grouping)."""
    files_map: Dict[str, Dict] = {}
    file_imports: Dict[str, set] = {}
    for fn in all_functions:
        f = fn.get("file")
        if not f:
            continue
        is_sentinel = fn.get("name") == "__file__"
        if f not in files_map:
            files_map[f] = {"language": fn.get("language"), "fn_count": 0}
        if not is_sentinel:
            files_map[f]["fn_count"] += 1
        if fn.get("imports"):
            file_imports.setdefault(f, set()).update(fn.get("imports", []))

    fn_to_file = {fn.get("name"): fn.get("file") for fn in all_functions}
    stem_to_files = _build_stem_to_files(all_functions)
    file_calls: Dict[tuple, int] = {}
    for fn in all_functions:
        for called in fn.get("calls", []):
            src_f = fn.get("file")
            tgt_f = fn_to_file.get(called)
            if src_f and tgt_f and tgt_f != src_f:
                key = (src_f, tgt_f)
                file_calls[key] = file_calls.get(key, 0) + 1

    for src_file, imported_names in file_imports.items():
        for imported_name in imported_names:
            tgt_f = _resolve_import(imported_name, stem_to_files, src_file)
            if tgt_f and tgt_f != src_file:
                key = (src_file, tgt_f)
                file_calls[key] = file_calls.get(key, 0) + 1

    nodes = [
        {"id": f, "type": "file", "language": info["language"], "fn_count": info["fn_count"]}
        for f, info in files_map.items()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in file_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": "files"}


def build_file_graph(module_name: str, all_functions: List[Dict]) -> Dict:
    files_in_module = {}
    for fn in all_functions:
        if fn.get("module") != module_name:
            continue
        f = fn.get("file")
        if f not in files_in_module:
            files_in_module[f] = {"language": fn.get("language"), "functions": []}
        files_in_module[f]["functions"].append(fn.get("name"))

    fn_to_file = {fn.get("name"): fn.get("file") for fn in all_functions if fn.get("module") == module_name}
    file_calls = {}
    file_imports = {}
    for fn in all_functions:
        if fn.get("module") != module_name:
            continue
        if fn.get("imports"):
            file_imports.setdefault(fn.get("file"), set()).update(fn.get("imports", []))
        for called in fn.get("calls", []):
            target_file = fn_to_file.get(called)
            if target_file and target_file != fn.get("file"):
                key = (fn.get("file"), target_file)
                file_calls[key] = file_calls.get(key, 0) + 1

    # Build stem->files restricted to this module for resolution
    module_fns = [fn for fn in all_functions if fn.get("module") == module_name]
    stem_to_files_module = _build_stem_to_files(module_fns)

    for src_file, imported_names in file_imports.items():
        for imported_name in imported_names:
            target_file = _resolve_import(imported_name, stem_to_files_module, src_file)
            if target_file and target_file != src_file:
                key = (src_file, target_file)
                file_calls[key] = file_calls.get(key, 0) + 1

    nodes = [
        {"id": f, "type": "file", "language": info["language"], "fn_count": len(info["functions"])}
        for f, info in files_in_module.items()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in file_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": 2, "module": module_name}


def build_function_graph(file_path: str, all_functions: List[Dict]) -> Dict:
    # Support two modes:
    # 1) Normal file-level function graph (nodes are functions)
    # 2) Chunked / virtual-module graph for very large (god) files
    file_fns = [fn for fn in all_functions if fn.get("file") == file_path or fn.get("virtual_module") == file_path]
    if not file_fns:
        # Try matching by virtual_module name if caller passed a virtual module id
        file_fns = [fn for fn in all_functions if fn.get("virtual_module") == file_path]

    fn_names = {fn.get("name") for fn in file_fns}

    # Detect whether functions are grouped into virtual modules (chunking)
    virtual_modules = {}
    for fn in file_fns:
        vm = fn.get("virtual_module") or fn.get("module") or file_path
        virtual_modules.setdefault(vm, []).append(fn)

    # If more than one virtual module/group exists, return a chunked view
    if len(virtual_modules) > 1:
        nodes = []
        for vm_name, fns in virtual_modules.items():
            nodes.append({
                "id": vm_name,
                "type": "chunk",
                "fn_count": len(fns),
                "language": fns[0].get("language"),
            })

        # Build edges between chunks based on function-level calls
        # map function name -> its virtual module
        fn_to_vm = {fn.get("name"): (fn.get("virtual_module") or fn.get("module") or file_path) for fn in file_fns}
        chunk_calls = {}
        for fn in file_fns:
            src_vm = fn_to_vm.get(fn.get("name"))
            for called in fn.get("calls", []):
                tgt_vm = fn_to_vm.get(called)
                if tgt_vm and tgt_vm != src_vm:
                    key = (src_vm, tgt_vm)
                    chunk_calls[key] = chunk_calls.get(key, 0) + 1

        edges = [{"source": src, "target": tgt, "call_count": cnt} for (src, tgt), cnt in chunk_calls.items()]
        return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": True}

    # Fallback: simple function-level graph
    nodes = [
        {
            "id": fn.get("name"),
            "type": "function",
            "line_start": fn.get("line_start"),
            "line_end": fn.get("line_end"),
            "complexity": fn.get("complexity"),
            "fan_in": fn.get("fan_in"),
            "fan_out": fn.get("fan_out"),
            "language": fn.get("language"),
        }
        for fn in file_fns
    ]
    edges = [
        {"source": fn.get("name"), "target": called}
        for fn in file_fns
        for called in fn.get("calls", [])
        if called in fn_names
    ]
    return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": False}