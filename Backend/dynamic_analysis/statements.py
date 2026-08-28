"""
Lazy Statement/CONTROL_DEP builder for the dynamic-analysis tier.

The static Function-tier graph (Backend/db.py) stops at function granularity —
no per-statement nodes exist. This module builds them on demand, the first
time a user runs dynamic analysis on a given Python function, by re-parsing
the function's already-persisted source (see the /upload change in main.py)
with the stdlib `ast` module (Python functions are parsed via `ast`, not
Tree-sitter — see analyzer/parser.py's _parse_python_ast). Results are written
to Neo4j and cached (skip rebuild if HAS_STATEMENT already exists for this
function+session) — see db.py's has_statements_for_function /
create_statements_and_control_dep.

Statement numbering is a pre-order walk starting from an implicit S1 "param
entry" statement, then each statement in source order — nested branch bodies
inline where they occur. This exactly reproduces the canonical
S1(entry),S2(if),S3,S4,S5(nested if),S6,S7,S8,S9,S10(write Y),S11(write Z)
numbering the acceptance test (CodeLens spec §10) depends on.
"""
import ast


class FunctionNotFoundError(Exception):
    pass


def _name_ids(node, ctx_type):
    return sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ctx_type)})


def _simple_reads_writes(stmt):
    """Reads/writes for a statement with no nested statement blocks."""
    if isinstance(stmt, ast.AugAssign):
        # `X += 1` reads X (via the implicit load) as well as writing it, but ast
        # represents the target's ctx as Store only — add it to reads explicitly.
        target_names = _name_ids(stmt.target, ast.Store)
        reads = sorted(set(_name_ids(stmt.value, ast.Load)) | set(target_names))
        return reads, target_names
    return _name_ids(stmt, ast.Load), _name_ids(stmt, ast.Store)


def _header_reads_writes(stmt):
    """Reads/writes for just a compound statement's own header (its test/iter/
    items expression) — excludes its nested body/orelse blocks, which are
    walked separately as their own statements."""
    if isinstance(stmt, (ast.If, ast.While)):
        return _name_ids(stmt.test, ast.Load), []
    if isinstance(stmt, ast.For):
        return _name_ids(stmt.iter, ast.Load), _name_ids(stmt.target, ast.Store)
    if isinstance(stmt, ast.With):
        reads = []
        writes = []
        for item in stmt.items:
            reads += _name_ids(item.context_expr, ast.Load)
            if item.optional_vars is not None:
                writes += _name_ids(item.optional_vars, ast.Store)
        return sorted(set(reads)), sorted(set(writes))
    if isinstance(stmt, ast.Try):
        return [], []
    # Fallback for any other compound statement we don't special-case.
    return [], []


_COMPOUND_TYPES = (ast.If, ast.For, ast.While, ast.With, ast.Try)


def _kind_of(stmt):
    return type(stmt).__name__.lower()


def _find_function(tree, function_name, line_start):
    candidates = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function_name]
    if not candidates:
        raise FunctionNotFoundError(f"function '{function_name}' not found in source")
    if len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda n: abs(n.lineno - (line_start or n.lineno)))


def build_statements_for_function(source: str, function_name: str, line_start: int = None):
    """
    Returns {"statements": [{id_suffix, line_no, order, kind, source_text,
    reads, writes}], "control_dep_edges": [{from_suffix, to_suffix, branch}]}.
    id_suffix is the "S<n>" part — callers prefix it with the function's own id.
    """
    tree = ast.parse(source)
    func = _find_function(tree, function_name, line_start)

    statements = []
    control_edges = []
    counter = [1]

    entry_writes = sorted({a.arg for a in func.args.args})
    statements.append({
        "id_suffix": "S1", "line_no": func.lineno, "static_seq": 1, "kind": "entry",
        "source_text": f"def {func.name}({', '.join(a.arg for a in func.args.args)}):",
        "reads": [], "writes": entry_writes,
    })

    def next_suffix():
        counter[0] += 1
        return f"S{counter[0]}"

    def walk_block(body, predecessor_suffix, branch):
        for stmt in body:
            suffix = next_suffix()
            static_seq = counter[0]
            if isinstance(stmt, _COMPOUND_TYPES):
                reads, writes = _header_reads_writes(stmt)
            else:
                reads, writes = _simple_reads_writes(stmt)

            statements.append({
                "id_suffix": suffix, "line_no": stmt.lineno, "static_seq": static_seq,
                "kind": _kind_of(stmt), "source_text": ast.unparse(stmt).split("\n")[0],
                "reads": reads, "writes": writes,
            })
            if predecessor_suffix is not None:
                control_edges.append({"from_suffix": predecessor_suffix, "to_suffix": suffix, "branch": branch})

            if isinstance(stmt, (ast.If, ast.While)):
                walk_block(stmt.body, suffix, "true")
                if stmt.orelse:
                    walk_block(stmt.orelse, suffix, "false")
            elif isinstance(stmt, ast.For):
                walk_block(stmt.body, suffix, "body")
                if stmt.orelse:
                    walk_block(stmt.orelse, suffix, "orelse")
            elif isinstance(stmt, ast.With):
                walk_block(stmt.body, suffix, "body")
            elif isinstance(stmt, ast.Try):
                walk_block(stmt.body, suffix, "try")
                for handler in stmt.handlers:
                    walk_block(handler.body, suffix, "except")
                if stmt.orelse:
                    walk_block(stmt.orelse, suffix, "else")
                if stmt.finalbody:
                    walk_block(stmt.finalbody, suffix, "finally")

    walk_block(func.body, None, None)

    return {"statements": statements, "control_dep_edges": control_edges}
