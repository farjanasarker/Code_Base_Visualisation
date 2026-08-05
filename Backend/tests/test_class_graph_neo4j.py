"""Integration test for the GoF pattern engine's Neo4j class graph
(store_class_graph / get_class_graph / ensure_schema). Hits the live Neo4j
instance configured in db.py, using an isolated, clearly-tagged session_id
that is deleted again at the end of the test — never left behind.

Skips gracefully if Neo4j isn't reachable from the current environment,
since this is the one test in the suite with an external dependency.
"""

import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402
from analyzer.pipeline import analyze_files  # noqa: E402

TEST_SESSION_ID = f"gof-phase0-test-{uuid.uuid4().hex[:8]}"


def _neo4j_available() -> bool:
    try:
        db.driver.verify_connectivity()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _neo4j_available(), reason="Neo4j instance not reachable")


@pytest.fixture(autouse=True)
def cleanup_test_session():
    yield
    try:
        db.delete_session_data(TEST_SESSION_ID)
    except Exception:
        pass


def test_store_and_read_class_graph_round_trip():
    ts_source = """
interface Shape {
  area(): number;
}
class Circle implements Shape {
  radius: number;
  area(): number { return 3.14 * this.radius * this.radius; }
}
class ScaledCircle extends Circle {
  factor: number;
}
abstract class Base {
  abstract go(): void;
}
"""
    files = [{"path": "shape.ts", "language": "typescript", "content": ts_source}]
    functions, classes, _unused, _layer = analyze_files(files)

    db.ensure_schema()
    db.store_all(functions, TEST_SESSION_ID, files)
    db.store_class_graph(classes, functions, TEST_SESSION_ID)

    graph = db.get_class_graph(TEST_SESSION_ID)
    by_name = {c["name"]: c for c in graph["classes"]}

    assert set(by_name) == {"Shape", "Circle", "ScaledCircle", "Base"}
    assert by_name["Shape"]["kind"] == "interface"
    assert "INTERFACE_LIKE" in by_name["Shape"]["labels"]
    assert "INTERFACE_LIKE" not in by_name["Circle"]["labels"]
    assert by_name["Circle"]["kind"] == "class"
    assert "ABSTRACT_LIKE" in by_name["Base"]["labels"]
    assert "ABSTRACT_LIKE" not in by_name["Circle"]["labels"]
    # abstract_class is deliberately also INTERFACE_LIKE (see normalization.py)
    assert "INTERFACE_LIKE" in by_name["Base"]["labels"]

    implements_pairs = {(r["child"], r["parent"]) for r in graph["implements"]}
    assert ("Circle", "Shape") in implements_pairs

    inherits_pairs = {(r["child"], r["parent"]) for r in graph["inherits"]}
    assert ("ScaledCircle", "Circle") in inherits_pairs

    method_entry = next(m for m in graph["methods"] if m["fn_name"] == "area")
    assert method_entry["class_name"] == "Circle"


def test_store_class_graph_is_additive_to_existing_function_data():
    """Confirms store_class_graph() runs as a genuinely separate write from
    store_all() — Function/CALLS data persisted by store_all() must still be
    intact and queryable via the existing tier endpoints after store_class_graph()
    also runs for the same session.
    """
    src = """
class Engine {
  start() { return this.ignite(); }
  ignite() { return true; }
}
"""
    files = [{"path": "engine.js", "language": "javascript", "content": src}]
    functions, classes, _unused, _layer = analyze_files(files)

    db.store_all(functions, TEST_SESSION_ID, files)
    db.store_class_graph(classes, functions, TEST_SESSION_ID)

    tier3 = db.get_tier3("engine.js", TEST_SESSION_ID)
    fn_names = {n["id"] for n in tier3["nodes"]}
    assert {"start", "ignite"} <= fn_names

    graph = db.get_class_graph(TEST_SESSION_ID)
    assert {c["name"] for c in graph["classes"]} == {"Engine"}


def test_instantiation_tracking_round_trip():
    """Factory Method/Abstract Factory/Builder/Prototype (Phase 2) all need
    'does this method construct an instance of class X' — a genuinely
    different AST shape from a call in every language but Python (`new
    Foo()`, `object_creation_expression`, `composite_literal`, ...). Confirm
    it survives the full analyze_files -> Neo4j -> get_class_graph round trip.
    """
    src = """
class Product {}
class Creator {
  make() { return new Product(); }
}
"""
    files = [{"path": "factory.ts", "language": "typescript", "content": src}]
    functions, classes, _unused, _layer = analyze_files(files)

    db.store_all(functions, TEST_SESSION_ID, files)
    db.store_class_graph(classes, functions, TEST_SESSION_ID)

    graph = db.get_class_graph(TEST_SESSION_ID)
    make_method = next(m for m in graph["methods"] if m["fn_name"] == "make")
    assert make_method["raw_instantiates"] == ["Product"]
