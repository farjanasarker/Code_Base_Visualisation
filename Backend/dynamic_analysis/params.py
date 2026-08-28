"""
Extracts parameter names + type hints for the auto-generated input form.

Python functions never go through the Tree-sitter pipeline in this codebase
(analyzer/parser.py routes Python through the stdlib `ast` module instead, and
ParsedFunction carries no params/type-hint fields at all) — so this re-parses
the function's persisted source directly, matching statements.py's approach.
"""
import ast

from .statements import FunctionNotFoundError, _find_function

SUPPORTED_SCALARS = {"int", "float", "str", "bool", "list", "tuple", "dict"}
_GENERIC_PREFIXES = {
    "list": "list", "List": "list",
    "tuple": "tuple", "Tuple": "tuple",
    "dict": "dict", "Dict": "dict",
}


def _classify_annotation(annotation) -> tuple[str | None, bool]:
    """Returns (widget_type, unsupported). widget_type is one of
    SUPPORTED_SCALARS or None (no/unrecognized annotation -> generic JSON widget
    unless explicitly unsupported)."""
    if annotation is None:
        return None, False

    text = ast.unparse(annotation).strip()

    if text in SUPPORTED_SCALARS:
        return text, False

    # Optional[X] / X | None -> unwrap to X
    if isinstance(annotation, ast.Subscript) and _base_name(annotation.value) == "Optional":
        return _classify_annotation(annotation.slice)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left, unsupported_l = _classify_annotation(annotation.left)
        if _is_none(annotation.right):
            return left, unsupported_l
        right, unsupported_r = _classify_annotation(annotation.right)
        if _is_none(annotation.left):
            return right, unsupported_r

    # list[int] / List[int] / dict[str, int] / Dict[str, int] / tuple[int, ...]
    if isinstance(annotation, ast.Subscript):
        base = _base_name(annotation.value)
        if base in _GENERIC_PREFIXES:
            return _GENERIC_PREFIXES[base], False

    return text, True


def _base_name(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def extract_function_params(source: str, function_name: str, line_start: int = None) -> dict:
    """
    Returns {"is_method": bool, "params": [{"name", "type_hint", "unsupported"}]}.
    `type_hint` is one of SUPPORTED_SCALARS, or None (no annotation -> generic
    JSON-literal widget). `unsupported` True means the annotation names a type
    dynamic analysis can't accept as a JSON-literal input (e.g. a custom class).
    """
    tree = ast.parse(source)
    parent_map = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[child] = node

    func = _find_function(tree, function_name, line_start)
    is_method = isinstance(parent_map.get(func), ast.ClassDef)

    params = []
    for arg in func.args.args:
        if is_method and arg.arg in ("self", "cls") and arg is func.args.args[0]:
            continue
        widget_type, unsupported = _classify_annotation(arg.annotation)
        params.append({"name": arg.arg, "type_hint": widget_type, "unsupported": unsupported})

    return {"is_method": is_method, "params": params}
