from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple
import importlib
import ast
import logging

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
            return self._parse_python_ast(filepath, content) if language == "python" else []

        try:
            tree = parser.parse(bytes(content, "utf8"))
        except Exception:
            return self._parse_python_ast(filepath, content) if language == "python" else []

        functions = self._extract_functions(tree, content, filepath, language)
        if not functions and language == "python":
            return self._parse_python_ast(filepath, content)

        for fn in functions:
            fn.calls = self._extract_calls(tree, content, language, fn.name)
            fn.fan_out = len(fn.calls)
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


def analyze_files(files: List[Dict]) -> List[Dict]:
    """Parse all supported files, apply file strategies, chunk god files and store edges via `add_edge`.

    Returns list of parsed function dicts.
    """
    parser = UniversalParser()
    all_functions: List[ParsedFunction] = []

    # First pass: parse files and decide strategies
    for file_info in files:
        lang = file_info.get("language")
        if not lang or lang == "unknown":
            continue

        content = file_info.get("content", "")
        if not content.strip():
            continue

        strategy = detect_file_strategy(file_info.get("path", "<in-memory>"), content)
        if strategy == "data_file":
            continue

        parsed = parser.parse_file(file_info.get("path", "<in-memory>"), content, lang)

        # convert ParsedFunction objects to dicts for chunking convenience
        parsed_dicts = [p.__dict__ for p in parsed]

        if strategy == "god_file":
            chunks = chunk_god_file(file_info.get("path", "<in-memory>"), content, lang, parsed_dicts)
            # assign virtual modules
            for chunk in chunks:
                names_in_chunk = {f["name"] for f in chunk["functions"]}
                for p in parsed:
                    if p.name in names_in_chunk:
                        p.virtual_module = chunk["virtual_module"]
                        p.module = chunk["virtual_module"]

        all_functions.extend(parsed)

    # compute fan-in
    all_functions = parser.compute_fan_in(all_functions)

    # store edges in DB for functions that call other parsed functions
    name_set = {fn.name for fn in all_functions}
    for fn in all_functions:
        for called in fn.calls:
            if called in name_set:
                try:
                    add_edge(fn.name, called)
                except Exception:
                    logger.exception("failed to add edge to DB")

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
        }
        for fn in all_functions
    ]


def build_module_graph(all_functions: List[Dict]) -> Dict:
    module_stats = {}
    for fn in all_functions:
        m = fn.get("module")
        if m not in module_stats:
            module_stats[m] = {"loc": 0, "fn_count": 0, "languages": set()}
        module_stats[m]["loc"] += (fn.get("line_end", 0) - fn.get("line_start", 0))
        module_stats[m]["fn_count"] += 1
        module_stats[m]["languages"].add(fn.get("language"))

    fn_to_module = {fn.get("name"): fn.get("module") for fn in all_functions}
    module_calls = {}
    for fn in all_functions:
        for called in fn.get("calls", []):
            target_module = fn_to_module.get(called)
            if target_module and target_module != fn.get("module"):
                key = (fn.get("module"), target_module)
                module_calls[key] = module_calls.get(key, 0) + 1

    nodes = [
        {"id": m, "type": "module", "loc": s["loc"], "fn_count": s["fn_count"], "languages": list(s["languages"])}
        for m, s in module_stats.items()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in module_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": 1}


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
    for fn in all_functions:
        if fn.get("module") != module_name:
            continue
        for called in fn.get("calls", []):
            target_file = fn_to_file.get(called)
            if target_file and target_file != fn.get("file"):
                key = (fn.get("file"), target_file)
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
