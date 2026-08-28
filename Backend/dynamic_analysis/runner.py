"""
Orchestrates the three dynamic-analysis API operations (params / run / slice)
by wiring together statements.py, params.py, sandbox.py, slicer.py and the
Neo4j helpers in db.py. Kept separate from main.py's route handlers so those
stay thin and consistent with every other route's try/except/validate style.
"""
import json
import logging
from pathlib import Path

import db
from . import params as params_mod
from . import statements as statements_mod
from .sandbox import SandboxUnavailableError, run_in_sandbox
from .slicer import build_lookups, compute_backward_slice
from .statements import FunctionNotFoundError

logger = logging.getLogger("dynamic_analysis.runner")


class UnsupportedFunctionError(Exception):
    pass


def _function_id(file_path: str, function_name: str) -> str:
    return f"{file_path}::{function_name}"


def _read_source(upload_dir: str, file_path: str) -> str:
    source_path = Path(upload_dir) / file_path
    if not source_path.is_file():
        raise FileNotFoundError(f"source for {file_path} was not found in this session's upload")
    return source_path.read_text(encoding="utf-8")


def get_function_params(session_id: str, upload_dir: str, file_path: str, function_name: str) -> dict:
    source = _read_source(upload_dir, file_path)
    return params_mod.extract_function_params(source, function_name)


def _ensure_statements(session_id: str, upload_dir: str, file_path: str, function_name: str,
                        line_start: int = None) -> str:
    """Builds and stores Statement/CONTROL_DEP nodes for this function if they
    don't already exist. Returns the function_id used to key everything."""
    function_id = _function_id(file_path, function_name)
    if db.has_statements_for_function(session_id, function_id):
        return function_id

    source = _read_source(upload_dir, file_path)
    built = statements_mod.build_statements_for_function(source, function_name, line_start)
    db.create_statements_and_control_dep(session_id, function_id, file_path, function_name, built)
    return function_id


def run_dynamic_function(session_id: str, upload_dir: str, file_path: str, function_name: str,
                          inputs: dict, run_id: str) -> dict:
    param_info = get_function_params(session_id, upload_dir, file_path, function_name)
    if param_info["is_method"]:
        raise UnsupportedFunctionError("dynamic analysis of class methods is not supported in this MVP")
    for p in param_info["params"]:
        if p["unsupported"]:
            raise UnsupportedFunctionError(
                f"parameter '{p['name']}' has an unsupported type ({p['type_hint']}) for dynamic analysis"
            )

    function_id = _ensure_statements(session_id, upload_dir, file_path, function_name)

    try:
        sandbox_result = run_in_sandbox(upload_dir, file_path, function_name, inputs, run_id)
    except SandboxUnavailableError as e:
        return {"run_id": run_id, "executed_node_ids": [], "execution_order": {}, "truncated": False,
                "status": "sandbox_unavailable", "error": str(e)}

    status = sandbox_result["status"]
    executed_lines = sandbox_result.get("executed_lines", [])

    statements = db.get_statements_for_function(session_id, function_id)
    line_to_stmt = {s["line_no"]: s["id"] for s in statements}
    entry_stmt = next(s for s in statements if s["id_suffix"] == "S1")

    # The function's entry line (parameter binding) never appears in the trace's
    # 'line' events (sys.settrace only fires 'line' for statements inside the
    # body), but parameters are logically "written" there — seed it unconditionally.
    executed_ids_in_order = [entry_stmt["id"]]
    for line_no in executed_lines:
        stmt_id = line_to_stmt.get(line_no)
        if stmt_id is not None:
            executed_ids_in_order.append(stmt_id)

    stmt_by_id = {s["id"]: s for s in statements}
    execution_order = {}  # stmt_id -> order of first occurrence
    data_dep_edges = []
    last_writer = {}

    for order, stmt_id in enumerate(executed_ids_in_order, start=1):
        if stmt_id not in execution_order:
            execution_order[stmt_id] = order
        stmt = stmt_by_id[stmt_id]
        for var in stmt.get("reads", []):
            writer = last_writer.get(var)
            if writer is not None and writer != stmt_id:
                data_dep_edges.append({"from_id": writer, "to_id": stmt_id, "variable_name": var})
        for var in stmt.get("writes", []):
            last_writer[var] = stmt_id

    db.create_run(session_id, function_id, run_id, inputs, status, sandbox_result.get("error"))
    db.record_execution(session_id, run_id, executed_ids_in_order, data_dep_edges)

    executed_node_ids = sorted(execution_order, key=execution_order.get)
    # Statement detail (source_text/reads/writes) for just the executed set —
    # lets the frontend offer a "pick a variable at this statement" slice
    # criterion picker without a separate round-trip.
    executed_statements = [
        {k: stmt_by_id[sid][k] for k in ("id", "id_suffix", "line_no", "kind", "source_text", "reads", "writes")}
        for sid in executed_node_ids
    ]

    return {
        "run_id": run_id,
        "executed_node_ids": executed_node_ids,
        "execution_order": execution_order,
        "statements": executed_statements,
        "called_functions": sandbox_result.get("called_functions", []),
        "truncated": status == "truncated",
        "status": status,
        "result": sandbox_result.get("result"),
        "error": sandbox_result.get("error"),
    }


def compute_slice_for_run(session_id: str, run_id: str, statement_node_id: str, variable_name: str) -> dict:
    statements, data_dep_edges, control_dep_edges = db.get_run_edges(session_id, run_id)
    executed_by_id, control_predecessors, data_dep_lookup = build_lookups(
        statements, data_dep_edges, control_dep_edges
    )
    slice_ids = compute_backward_slice(
        executed_by_id, control_predecessors, data_dep_lookup, statement_node_id, variable_name
    )
    return {"slice_node_ids": slice_ids}
