"""Regression tests for the `super().X()` spurious-self-loop bug.

`_extract_python_calls` (analyzer/parser.py) used to record the bare method
name of every `Attribute` call into `calls`, including `super().X(...)`.
Because `_detect_cycles` (analyzer/metrics.py) builds its call graph from
those bare names, a method calling `super().<same_name>(...)` — the extremely
common `__init__`/`__new__` pattern — produced a `name -> name` self-loop
that got reported as a CRITICAL circular dependency.

The fix tags `super().X()` edges with the `call_targets["X"] = "__super__"`
sentinel at parse time, and `_detect_cycles` drops an edge back to the same
function name when it carries that sentinel — without dropping the edge
itself (fan_out/call-graph data is preserved) and without touching any other
same-name-call collision (e.g. Decorator-style `self.wrapped.cost()`).

`build_function_graph` (analyzer/graph_builder.py) — the source of the
function-level dependency-graph visualization — builds its edges from the
same `calls`/`call_targets` data independently of `_detect_cycles`, so it
needed the identical self-loop exclusion; otherwise the graph view kept
showing a `__new__ -> __new__` / `__init__ -> __init__` loop even after the
smell-detector metric stopped flagging it.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from analyzer.parser import UniversalParser  # noqa: E402
from analyzer.pipeline import analyze_files  # noqa: E402
from analyzer.metrics import compute_aggregate_metrics  # noqa: E402
from analyzer.graph_builder import build_function_graph  # noqa: E402

parser = UniversalParser()


def _analyze(content: str, path: str = "mod.py"):
    all_files = [{"path": path, "language": "python", "content": content}]
    functions, _classes, _unused, _layer = analyze_files(all_files)
    metrics = compute_aggregate_metrics(functions, all_files)
    return functions, metrics


def _fn(functions, name: str, class_name: str):
    return next(f for f in functions if f["name"] == name and f["class_name"] == class_name)


def test_singleton_new_super_call_not_a_cycle():
    src = """
class Singleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
"""
    functions, metrics = _analyze(src)
    fn = _fn(functions, "__new__", "Singleton")
    assert fn["call_targets"].get("__new__") == "__super__"
    assert not any(
        detail == "__new__ → __new__" for detail in metrics["circular_dep_details"]
    )


def test_subclass_init_super_call_not_a_cycle_but_still_an_edge():
    src = """
class Base:
    def __init__(self):
        self.x = 1

class Child(Base):
    def __init__(self):
        super().__init__()
        self.y = 2
"""
    functions, metrics = _analyze(src)
    child_init = _fn(functions, "__init__", "Child")
    assert child_init["call_targets"].get("__init__") == "__super__"
    # the call is still real call-graph info: fan_out must still count it
    # (the AST also has a nested `super()` call of its own, hence >= 1 here
    # rather than an exact count)
    assert "__init__" in child_init["calls"]
    assert child_init["fan_out"] == len(child_init["calls"]) >= 1
    assert not any(
        detail == "__init__ → __init__" for detail in metrics["circular_dep_details"]
    )


def test_decorator_style_same_name_delegation_not_treated_as_super():
    src = """
class Coffee:
    def cost(self):
        return 5

class Decorator:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def cost(self):
        return self.wrapped.cost() + 1
"""
    functions, _metrics = _analyze(src)
    decorator_cost = _fn(functions, "cost", "Decorator")
    assert "cost" in decorator_cost["calls"]
    assert decorator_cost["call_targets"].get("cost") != "__super__"


def test_genuine_circular_dependency_still_detected():
    src = """
def a():
    b()

def b():
    a()
"""
    _functions, metrics = _analyze(src)
    assert metrics["circular_deps"] >= 1
    assert any(
        set(detail.split(" → ")) == {"a", "b"} for detail in metrics["circular_dep_details"]
    )


def test_function_graph_view_has_no_super_self_loop():
    src = """
class Singleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
"""
    functions, _metrics = _analyze(src, path="db.py")
    graph = build_function_graph("db.py", functions)
    assert {"source": "__new__", "target": "__new__"} not in graph["edges"]


def test_function_graph_view_keeps_real_super_edge_to_parent():
    src = """
class Base:
    def __init__(self):
        self.x = 1

class Child(Base):
    def __init__(self):
        super().__init__()
        self.y = 2
"""
    functions, _metrics = _analyze(src)
    graph = build_function_graph("mod.py", functions)
    child_id = next(n["id"] for n in graph["nodes"] if n["class_name"] == "Child")
    base_id = next(n["id"] for n in graph["nodes"] if n["class_name"] == "Base")
    assert {"source": child_id, "target": base_id} in graph["edges"]
    assert {"source": child_id, "target": child_id} not in graph["edges"]
