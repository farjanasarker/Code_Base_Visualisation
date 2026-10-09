"""Static code analysis: multi-language parsing (tree-sitter + regex/AST
fallbacks), dead-code/architecture-violation heuristics, god-file chunking,
and the module/file/function graph + metrics builders behind the dashboard.

Split by responsibility across this package's modules; this file re-exports
the public entry points `main.py` uses so `from analyzer import ...` keeps
working unchanged.
"""

from .chunking import decide_render_strategy
from .graph_builder import (
    attach_edge_details,
    build_all_files_graph,
    build_file_graph,
    build_function_graph,
    build_module_graph,
)
from .metrics import compute_aggregate_metrics
from .pipeline import analyze_files

__all__ = [
    "attach_edge_details",
    "analyze_files",
    "build_module_graph",
    "build_all_files_graph",
    "build_file_graph",
    "build_function_graph",
    "decide_render_strategy",
    "compute_aggregate_metrics",
]
