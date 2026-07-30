"""File-size triage and "god file" chunking.

Large files get bucketed into normal/large/god-file strategies by function
count, and god files get split into pseudo-modules (by class, then by
complexity, then by line range) so the graph/UI can render them without one
giant node swallowing everything.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Dict, List

from .tree_sitter_runtime import (
    FUNCTION_QUERIES,
    SUPPORTED_EXTENSIONS,
    TREE_SITTER_LANGUAGES,
    get_parser,
    run_query,
)

logger = logging.getLogger(__name__)


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
        # ── tree-sitter নেই, regex fallback ──
        if language_name == "go":
            return len(re.findall(
                r'\bfunc\s+(?:\([^)]*\)\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(',
                content
            ))
        if language_name == "rust":
            return len(re.findall(r'\bfn\s+[a-zA-Z_][a-zA-Z0-9_]*\s*[<(]', content))
        if language_name in ("javascript", "typescript"):
            return len(re.findall(r'\bfunction\s+[A-Za-z_$]', content))
        return 0

    try:
        parser = get_parser(language_name)
        tree = parser.parse(bytes(content, "utf8"))
        captures = run_query(TREE_SITTER_LANGUAGES[language_name], FUNCTION_QUERIES[language_name], tree.root_node)
        return len(captures.get("fn_def", []))
    except Exception:
        # tree-sitter আছে কিন্তু parse fail → regex fallback
        if language_name == "go":
            return len(re.findall(
                r'\bfunc\s+(?:\([^)]*\)\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(',
                content
            ))
        return 0


def detect_file_strategy(filepath: str, content: str) -> str:
    """
    Returns one of: "data_file", "large_normal", "god_file", "normal"
    """
    filename = Path(filepath).name.lower()
    generated_patterns = ['.pb.go', '.pb.gw.go', '_grpc.pb.go', '.gen.go',
                          '.generated.go', '_generated.go']
    if any(filename.endswith(p) for p in generated_patterns):
        lines = content.split('\n')
        # অনেক বড় generated file (100k lines ≈ 6MB+) skip করো
        if len(lines) > 100_000:
            return "data_file"
        # generated files সবসময় god_file হিসেবে chunk করো
        # "normal" return করলে module graph-এ fn_count=0 দেখায়
        return "god_file"

    lines = content.split("\n")
    line_count = len(lines)
    if line_count <= 10_000:
        return "normal"

    fn_count = count_functions_ast(filepath, content)

    if fn_count < 3:      # 10 থেকে 3: tree-sitter ছাড়া undercount হলেও safe
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
            try:
                parser = get_parser(language)
                tree = parser.parse(bytes(content, "utf8"))
                raw = run_query(
                    TREE_SITTER_LANGUAGES[language],
                    "(class_definition name: (identifier) @class_name) @class_def",
                    tree.root_node,
                )
                pairs = [(n, name) for name, nodes in raw.items() for n in nodes]
                for node, capture_name in pairs:
                    if "class_def" in capture_name:
                        classes.append({
                            "name": content[node.start_byte:node.end_byte],
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                        })
            except Exception:
                pass  # class chunking ব্যর্থ হলে complexity/line-range fallback এ যাবে

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
