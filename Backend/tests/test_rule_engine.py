"""Tests for the rule-spec engine (patterns/rule_engine.py) against the
Strategy proof-of-concept spec — the Phase 0 deliverable: a normalization
layer + predicate library + rule engine that can already re-implement
Strategy end-to-end.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from patterns.graph_view import SessionGraphView  # noqa: E402
from patterns.rule_engine import evaluate_all, load_all_specs, load_spec  # noqa: E402

_SPECS_DIR = BACKEND_DIR / "patterns" / "specs"


def _raw_strategy_shape():
    """Same shape as test_predicates.py's fixture of the same name:
        interface PaymentStrategy { pay(amount): void; }
        class CreditCardStrategy implements PaymentStrategy { pay() { this.charge(); } charge() {} }
        class PayPalStrategy implements PaymentStrategy { pay() { this.send(); } send() {} }
        class Checkout { strategy: PaymentStrategy; process() { this.strategy.pay(); } }
    Kept as a local copy rather than a cross-test-module import to avoid
    depending on `tests/` being an importable package.
    """
    return {
        "classes": [
            {"name": "PaymentStrategy", "file": "pay.ts", "kind": "interface", "language": "typescript",
             "labels": ["Class", "INTERFACE_LIKE"], "field_names": [], "method_names": ["pay"],
             "line_start": 1, "line_end": 3},
            {"name": "CreditCardStrategy", "file": "pay.ts", "kind": "class", "language": "typescript",
             "labels": ["Class"], "field_names": [], "method_names": ["pay", "charge"],
             "line_start": 4, "line_end": 7},
            {"name": "PayPalStrategy", "file": "pay.ts", "kind": "class", "language": "typescript",
             "labels": ["Class"], "field_names": [], "method_names": ["pay", "send"],
             "line_start": 8, "line_end": 11},
            {"name": "Checkout", "file": "pay.ts", "kind": "class", "language": "typescript",
             "labels": ["Class"], "field_names": ["strategy"], "method_names": ["process"],
             "line_start": 12, "line_end": 15},
        ],
        "inherits": [],
        "implements": [
            {"child": "CreditCardStrategy", "child_file": "pay.ts", "parent": "PaymentStrategy"},
            {"child": "PayPalStrategy", "child_file": "pay.ts", "parent": "PaymentStrategy"},
        ],
        "has_field": [
            {"owner": "Checkout", "owner_file": "pay.ts", "target": "PaymentStrategy",
             "field_name": "strategy", "is_collection": False},
        ],
        "methods": [
            {"fn_name": "pay", "file": "pay.ts", "class_name": "CreditCardStrategy",
             "raw_calls": ["charge"]},
            {"fn_name": "charge", "file": "pay.ts", "class_name": "CreditCardStrategy", "raw_calls": []},
            {"fn_name": "pay", "file": "pay.ts", "class_name": "PayPalStrategy",
             "raw_calls": ["send"]},
            {"fn_name": "send", "file": "pay.ts", "class_name": "PayPalStrategy", "raw_calls": []},
            {"fn_name": "process", "file": "pay.ts", "class_name": "Checkout",
             "raw_calls": ["pay"]},
        ],
    }


def test_load_strategy_spec():
    spec = load_spec(_SPECS_DIR / "strategy.yaml")
    assert spec.pattern == "Strategy"
    assert spec.tier == "high"
    assert len(spec.requires) == 4
    assert spec.min_confidence_to_report == 0.6


def test_strategy_matches_true_positive_shape():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    specs = load_all_specs()
    matches = evaluate_all(view, specs)

    strategy_matches = [m for m in matches if m.pattern == "Strategy"]
    assert len(strategy_matches) == 1
    match = strategy_matches[0]
    assert match.bindings == {"strategy_interface": "PaymentStrategy", "context": "Checkout"}
    # Not a perfect 1.0: Checkout.process()'s call to pay() resolves
    # ambiguously (PaymentStrategy, CreditCardStrategy and PayPalStrategy
    # all declare a "pay" method), so delegates_to_field matches on its
    # weaker name-only fallback rather than an exact callee-class match —
    # see predicates.delegates_to_field's strength grading.
    assert match.confidence == 0.94
    assert match.tier == "high"
    assert len(match.evidence) >= 4
    assert match.category == "Behavioral"
    # evidence_detail groups the same evidence per requirement, labeled with
    # what structural check produced it — one entry per requirement in
    # strategy.yaml's `requires` list (interface shape, implementer count,
    # composition, delegation).
    assert len(match.evidence_detail) == 4
    labels = [d["label"] for d in match.evidence_detail]
    assert labels == ["Interface shape", "Implementer count", "Composition", "Delegation"]
    delegation_entry = next(d for d in match.evidence_detail if d["predicate"] == "delegates_to_field")
    assert delegation_entry["strength"] < 1.0


def test_strategy_does_not_match_single_implementer():
    """False-positive discipline: only one implementer of the interface ->
    min_implementers(count=2) must reject the branch, no match reported.
    """
    raw = _raw_strategy_shape()
    raw["classes"] = [c for c in raw["classes"] if c["name"] != "PayPalStrategy"]
    raw["implements"] = [r for r in raw["implements"] if r["child"] != "PayPalStrategy"]
    raw["methods"] = [m for m in raw["methods"] if m["class_name"] != "PayPalStrategy"]

    view = SessionGraphView.from_raw(raw)
    matches = evaluate_all(view, load_all_specs())
    assert not [m for m in matches if m.pattern == "Strategy"]


def test_strategy_does_not_match_without_composition():
    """False-positive discipline: interface + 2 implementers exist, but
    nothing holds a field of that type -> no Strategy match (an interface
    with 2 implementers alone isn't Strategy without the composition+
    delegation shape).
    """
    raw = _raw_strategy_shape()
    raw["classes"] = [c for c in raw["classes"] if c["name"] != "Checkout"]
    raw["has_field"] = []
    raw["methods"] = [m for m in raw["methods"] if m["class_name"] != "Checkout"]

    view = SessionGraphView.from_raw(raw)
    matches = evaluate_all(view, load_all_specs())
    assert not [m for m in matches if m.pattern == "Strategy"]


def test_strategy_does_not_match_without_delegation():
    """False-positive discipline: composition field exists but the context
    class never actually calls through it -> delegates_to_field fails.
    """
    raw = _raw_strategy_shape()
    for m in raw["methods"]:
        if m["class_name"] == "Checkout":
            m["raw_calls"] = []  # holds the field but never calls through it

    view = SessionGraphView.from_raw(raw)
    matches = evaluate_all(view, load_all_specs())
    assert not [m for m in matches if m.pattern == "Strategy"]
