"""
Backward program slicing over one run's executed statements.

Deliberately an application-level worklist/BFS closure, not a single Cypher
path query (per CodeLens spec §7's own fallback allowance) — the traversal
mixes two different kinds of hops that don't compose into one graph pattern:

  - DYNAMIC_DATA_DEP hops are variable-scoped: from a statement, only follow
    the edge for the specific variable currently "of interest" there.
  - CONTROL_DEP hops are unconditional: any visited statement's controlling
    predicate is always pulled in, regardless of variable.

See dynamic_analysis/statements.py for how CONTROL_DEP edges are built and
why the statement numbering reproduces the canonical acceptance test.
"""


def build_lookups(statements: list[dict], data_dep_edges: list[dict], control_dep_edges: list[dict]):
    """
    statements: [{"id", "order", "reads"}] for this run's executed statements.
    data_dep_edges: [{"from_id", "to_id", "variable_name"}] (this run only).
    control_dep_edges: [{"from_id", "to_id"}] restricted to pairs where both
        ends are in this run's executed set.

    Returns (executed_by_id, control_predecessors, data_dep_lookup) shaped for
    compute_backward_slice.
    """
    executed_by_id = {s["id"]: {"order": s["order"], "reads": s.get("reads", [])} for s in statements}
    control_predecessors = {e["to_id"]: e["from_id"] for e in control_dep_edges}
    data_dep_lookup = {(e["to_id"], e["variable_name"]): e["from_id"] for e in data_dep_edges}
    return executed_by_id, control_predecessors, data_dep_lookup


def compute_backward_slice(executed_by_id: dict, control_predecessors: dict, data_dep_lookup: dict,
                            criterion_stmt_id: str, criterion_variable: str) -> list[str]:
    """Returns the slice's statement ids, ordered by this run's execution order."""
    visited_stmts = set()
    control_expanded = set()
    data_dep_expanded = set()
    queue = [(criterion_stmt_id, {criterion_variable})]

    while queue:
        stmt_id, vars_of_interest = queue.pop()
        visited_stmts.add(stmt_id)

        if stmt_id not in control_expanded:
            control_expanded.add(stmt_id)
            pred = control_predecessors.get(stmt_id)
            if pred is not None:
                pred_reads = set(executed_by_id.get(pred, {}).get("reads", []))
                queue.append((pred, pred_reads))

        for var in vars_of_interest:
            key = (stmt_id, var)
            if key in data_dep_expanded:
                continue
            data_dep_expanded.add(key)
            writer = data_dep_lookup.get(key)
            if writer is not None:
                writer_reads = set(executed_by_id.get(writer, {}).get("reads", []))
                queue.append((writer, writer_reads))

    return sorted(visited_stmts, key=lambda sid: executed_by_id.get(sid, {}).get("order", float("inf")))
