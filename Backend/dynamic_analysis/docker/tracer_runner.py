"""
Runs inside the sandbox container (no network, read-only /workspace, memory/CPU
capped by the docker run flags in sandbox.py). Reads one JSON payload from stdin:

    {"file_relpath": "pkg/mod.py", "function_name": "f", "inputs": {"X": -1}}

Imports the target file as a standalone module, traces exactly one call to the
named top-level function via sys.settrace (calls into *other* functions are
never traced into — the global trace function returns None for any frame whose
code object isn't the target function's, which is what keeps callees opaque),
and writes one JSON result line to stdout:

    {"status": "ok"|"error"|"truncated",
     "executed_lines": [12, 13, 14, ...],   # in execution order, 1 per line-event
     "result": <json-safe return value or null>,
     "error": "<message>" or null}

Deliberately minimal: no attempt to support arbitrary package-relative imports,
class methods, or anything requiring more than "import this one file, call this
one top-level function with JSON-literal inputs" — matches the MVP scope.
"""
import importlib.util
import json
import sys

MAX_STEPS = 100_000


class _StepLimitExceeded(Exception):
    pass


def _load_module(file_path):
    spec = importlib.util.spec_from_file_location("_target_module", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_target_module"] = module
    spec.loader.exec_module(module)
    return module


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def main():
    payload = json.loads(sys.stdin.read())
    file_relpath = payload["file_relpath"]
    function_name = payload["function_name"]
    inputs = payload.get("inputs", {})

    # /workspace is the read-only bind mount of the session's persisted source
    # (see sandbox.py) — its root is also added to sys.path so plain
    # `import othermodule` works for other files in the same upload.
    sys.path.insert(0, "/workspace")

    out = {"status": "ok", "executed_lines": [], "called_functions": [], "result": None, "error": None}

    try:
        module = _load_module("/workspace/" + file_relpath)
    except ImportError as e:
        out["status"] = "error"
        out["error"] = f"dependency not available in sandbox: {e}"
        print(json.dumps(out))
        return
    except Exception as e:
        out["status"] = "error"
        out["error"] = f"failed to import target file: {e}"
        print(json.dumps(out))
        return

    target = getattr(module, function_name, None)
    if target is None or not callable(target):
        out["status"] = "error"
        out["error"] = f"function '{function_name}' not found in {file_relpath}"
        print(json.dumps(out))
        return

    target_code = target.__code__
    executed_lines = []
    called_functions = []
    step_count = 0

    def line_tracer(frame, event, arg):
        nonlocal step_count
        if event == "line":
            step_count += 1
            if step_count > MAX_STEPS:
                sys.settrace(None)
                raise _StepLimitExceeded()
            executed_lines.append(frame.f_lineno)
        return line_tracer

    def global_tracer(frame, event, arg):
        if event == "call":
            if frame.f_code is target_code:
                return line_tracer
            # A call into another function — kept opaque (never traced into,
            # per the single-function MVP scope) but the callee's name is
            # still worth surfacing for a coarse "which functions ran" view.
            called_functions.append(frame.f_code.co_name)
        return None

    sys.settrace(global_tracer)
    try:
        result = target(**inputs)
    except _StepLimitExceeded:
        sys.settrace(None)
        out["status"] = "truncated"
        out["error"] = f"execution exceeded the {MAX_STEPS}-step trace limit"
    except Exception as e:
        sys.settrace(None)
        out["status"] = "error"
        out["error"] = f"{type(e).__name__}: {e}"
    else:
        # Disable tracing *before* any further calls (e.g. _json_safe's own
        # json.dumps probe below) so post-processing doesn't pollute
        # called_functions with tracer/serialization internals.
        sys.settrace(None)
        out["result"] = _json_safe(result)

    out["executed_lines"] = executed_lines
    out["called_functions"] = sorted(set(called_functions))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
