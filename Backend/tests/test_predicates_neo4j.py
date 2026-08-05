"""End-to-end predicate library test through the real pipeline: source code
-> analyze_files() -> Neo4j (store_all/store_class_graph) -> get_class_graph()
-> SessionGraphView -> predicates. Confirms the hand-built fixtures in
test_predicates.py actually match what real parsing produces. Skips
gracefully if Neo4j isn't reachable, same as test_class_graph_neo4j.py.
"""

import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402
from analyzer.pipeline import analyze_files  # noqa: E402
from patterns.graph_view import SessionGraphView  # noqa: E402
from patterns import predicates as P  # noqa: E402

TEST_SESSION_ID = f"gof-phase0-predicates-{uuid.uuid4().hex[:8]}"


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


def test_strategy_shape_end_to_end():
    src = """
interface PaymentStrategy {
  pay(amount: number): void;
}
class CreditCardStrategy implements PaymentStrategy {
  pay(amount: number): void { this.charge(amount); }
  charge(amount: number): void {}
}
class PayPalStrategy implements PaymentStrategy {
  pay(amount: number): void { this.send(amount); }
  send(amount: number): void {}
}
class Checkout {
  strategy: PaymentStrategy;
  process(amount: number): void { this.strategy.pay(amount); }
}
"""
    files = [{"path": "checkout.ts", "language": "typescript", "content": src}]
    functions, classes, _unused, _layer = analyze_files(files)

    db.ensure_schema()
    db.store_all(functions, TEST_SESSION_ID, files)
    db.store_class_graph(classes, functions, TEST_SESSION_ID)

    raw = db.get_class_graph(TEST_SESSION_ID)
    view = SessionGraphView.from_raw(raw)

    interface_candidates = P.interface_with_single_method(view)
    assert {c.binding for c in interface_candidates} == {"PaymentStrategy"}

    assert P.min_implementers(view, "PaymentStrategy", 2).matched is True

    composition_candidates = P.composition_field_of_type(view, "PaymentStrategy")
    assert {c.binding for c in composition_candidates} == {"Checkout"}

    delegation = P.delegates_to_field(view, "Checkout", "strategy")
    assert delegation.matched is True
