"""Unit tests for the GoF pattern engine's predicate library
(patterns/predicates.py), against hand-built SessionGraphView instances —
no Neo4j required. See test_predicates_neo4j.py for the live end-to-end
version exercising the real analyze_files -> Neo4j -> get_class_graph path.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from patterns.graph_view import SessionGraphView  # noqa: E402
from patterns import predicates as P  # noqa: E402


def _raw_strategy_shape():
    """Hand-built raw graph matching what get_class_graph() would return for:
        interface PaymentStrategy { pay(amount): void; }
        class CreditCardStrategy implements PaymentStrategy { pay() { this.charge(); } charge() {} }
        class PayPalStrategy implements PaymentStrategy { pay() { this.send(); } send() {} }
        class Checkout { strategy: PaymentStrategy; process() { this.strategy.pay(); } }
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


def test_interface_with_single_method():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    candidates = P.interface_with_single_method(view)
    names = {c.binding for c in candidates}
    assert names == {"PaymentStrategy"}
    assert candidates[0].extra["method"] == "pay"


def test_min_implementers():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    assert P.min_implementers(view, "PaymentStrategy", 2).matched is True
    assert P.min_implementers(view, "PaymentStrategy", 3).matched is False


def test_composition_field_of_type():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    candidates = P.composition_field_of_type(view, "PaymentStrategy")
    assert [c.binding for c in candidates] == ["Checkout"]
    assert candidates[0].extra["field_name"] == "strategy"


def test_delegates_to_field_matches_via_interface_method_names():
    """The important case: the field's target is an INTERFACE (bodyless
    method signature, no METHOD_OF/Function node) — delegation must still
    resolve via ClassInfo.method_names, not just methods_of.
    """
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    result = P.delegates_to_field(view, "Checkout", "strategy")
    assert result.matched is True


def test_delegates_to_field_no_match_for_unrelated_field():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    result = P.delegates_to_field(view, "Checkout", "nonexistent_field")
    assert result.matched is False


def test_has_self_referential_field():
    raw = {
        "classes": [
            {"name": "Node", "file": "n.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["children"], "method_names": [],
             "line_start": 1, "line_end": 5},
        ],
        "inherits": [], "implements": [],
        "has_field": [
            {"owner": "Node", "owner_file": "n.py", "target": "Node",
             "field_name": "children", "is_collection": True},
        ],
        "methods": [],
    }
    view = SessionGraphView.from_raw(raw)
    assert P.has_self_referential_field(view, "Node").matched is True
    assert P.has_list_of_own_type_field(view, "Node").matched is True
    assert P.has_single_field_of_own_type(view, "Node").matched is False


def test_wraps_and_extends_classifies_decorator_vs_proxy():
    raw = {
        "classes": [
            {"name": "Component", "file": "c.py", "kind": "interface", "language": "python",
             "labels": ["Class", "INTERFACE_LIKE"], "field_names": [], "method_names": ["op"],
             "line_start": 1, "line_end": 2},
            {"name": "Decorator", "file": "c.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["wrapped"], "method_names": ["op"],
             "line_start": 3, "line_end": 6},
            {"name": "Proxy", "file": "c.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["wrapped"], "method_names": ["op"],
             "line_start": 7, "line_end": 9},
        ],
        "inherits": [], "implements": [],
        "has_field": [
            {"owner": "Decorator", "owner_file": "c.py", "target": "Component",
             "field_name": "wrapped", "is_collection": False},
            {"owner": "Proxy", "owner_file": "c.py", "target": "Component",
             "field_name": "wrapped", "is_collection": False},
        ],
        "methods": [
            {"fn_name": "op", "file": "c.py", "class_name": "Decorator",
             "raw_calls": ["op", "log_extra_work"]},
            {"fn_name": "op", "file": "c.py", "class_name": "Proxy", "raw_calls": ["op"]},
        ],
    }
    view = SessionGraphView.from_raw(raw)
    decorator_result = P.wraps_and_extends(view, "Decorator", "wrapped")
    assert decorator_result.matched is True
    assert decorator_result.extra["classification"] == "decorator"

    proxy_result = P.wraps_and_extends(view, "Proxy", "wrapped")
    assert proxy_result.matched is True
    assert proxy_result.extra["classification"] == "proxy"


def test_abstract_method_called_from_concrete_sibling_method():
    raw = {
        "classes": [
            {"name": "Algorithm", "file": "a.py", "kind": "abstract_class", "language": "python",
             "labels": ["Class", "ABSTRACT_LIKE"], "field_names": [],
             "method_names": ["template_method", "step"], "line_start": 1, "line_end": 6},
        ],
        "inherits": [], "implements": [], "has_field": [],
        "methods": [
            {"fn_name": "template_method", "file": "a.py", "class_name": "Algorithm",
             "raw_calls": ["step"]},
        ],
    }
    view = SessionGraphView.from_raw(raw)
    result = P.abstract_method_called_from_concrete_sibling_method(view, "Algorithm")
    assert result.matched is True


def test_double_dispatch_pair():
    raw = {
        "classes": [
            {"name": "Visitor", "file": "v.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["visitCircle"],
             "line_start": 1, "line_end": 2},
            {"name": "Circle", "file": "v.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["accept"],
             "line_start": 3, "line_end": 4},
        ],
        "inherits": [], "implements": [], "has_field": [],
        "methods": [
            {"fn_name": "accept", "file": "v.py", "class_name": "Circle",
             "raw_calls": ["visitCircle"]},
            {"fn_name": "visitCircle", "file": "v.py", "class_name": "Visitor",
             "raw_calls": ["accept"]},
        ],
    }
    view = SessionGraphView.from_raw(raw)
    result = P.double_dispatch_pair(view, "Circle", "accept", "Visitor", "visitCircle")
    assert result.matched is True

    no_callback = P.double_dispatch_pair(view, "Circle", "accept", "Visitor", "some_other_method")
    assert no_callback.matched is False


def test_fan_out_to_common_hub_and_no_direct_edges_between():
    raw = {
        "classes": [
            {"name": "ColleagueA", "file": "m.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["send"], "line_start": 1, "line_end": 2},
            {"name": "ColleagueB", "file": "m.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["send"], "line_start": 3, "line_end": 4},
            {"name": "Mediator", "file": "m.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["notify"], "line_start": 5, "line_end": 6},
        ],
        "inherits": [], "implements": [], "has_field": [],
        "methods": [
            {"fn_name": "send", "file": "m.py", "class_name": "ColleagueA", "raw_calls": ["notify"]},
            {"fn_name": "send", "file": "m.py", "class_name": "ColleagueB", "raw_calls": ["notify"]},
        ],
    }
    view = SessionGraphView.from_raw(raw)
    hub_result = P.fan_out_to_common_hub(view, ["ColleagueA", "ColleagueB"])
    assert hub_result.matched is True

    no_edges_result = P.no_direct_edges_between(view, ["ColleagueA", "ColleagueB"])
    assert no_edges_result.matched is True


def test_stubbed_predicates_are_honest_about_phase0_gap():
    view = SessionGraphView.from_raw(_raw_strategy_shape())
    assert P.fluent_return_self(view, "Checkout", "process").matched is False
    assert P.cache_keyed_return(view, "Checkout", "process").matched is False


def _raw_decorator_shape():
    """GoF's actual Decorator shape: Component (interface), ConcreteComponent
    implements it, TextDecorator ALSO implements Component AND holds a field
    typed as Component (not literally "TextDecorator" itself) — the case
    the original has_self_referential_field/has_single_field_of_own_type
    implementation missed before it was broadened to check interfaces_of.
    """
    return {
        "classes": [
            {"name": "Component", "file": "c.py", "kind": "interface", "language": "python",
             "labels": ["Class", "INTERFACE_LIKE"], "field_names": [], "method_names": ["render"],
             "line_start": 1, "line_end": 2},
            {"name": "ConcreteComponent", "file": "c.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["render"],
             "line_start": 3, "line_end": 4},
            {"name": "TextDecorator", "file": "c.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["wrapped"], "method_names": ["render"],
             "line_start": 5, "line_end": 8},
        ],
        "inherits": [], "implements": [
            {"child": "ConcreteComponent", "child_file": "c.py", "parent": "Component"},
            {"child": "TextDecorator", "child_file": "c.py", "parent": "Component"},
        ],
        "has_field": [
            {"owner": "TextDecorator", "owner_file": "c.py", "target": "Component",
             "field_name": "wrapped", "is_collection": False},
        ],
        "methods": [
            {"fn_name": "render", "file": "c.py", "class_name": "TextDecorator",
             "raw_calls": ["render", "add_formatting"]},
        ],
    }


def test_has_single_field_of_own_type_covers_shared_interface_shape():
    """Regression check: the original implementation only matched a field
    typed as the class's OWN literal name — Decorator's field is typed as
    the shared interface the class also implements, which this must catch.
    """
    view = SessionGraphView.from_raw(_raw_decorator_shape())
    result = P.has_single_field_of_own_type(view, "TextDecorator")
    assert result.matched is True


def test_single_field_of_own_type_candidates_generator():
    view = SessionGraphView.from_raw(_raw_decorator_shape())
    candidates = P.single_field_of_own_type_candidates(view)
    by_binding = {c.binding: c for c in candidates}
    assert "TextDecorator" in by_binding
    assert by_binding["TextDecorator"].extra["field_name"] == "wrapped"


def test_implements_or_inherits():
    view = SessionGraphView.from_raw(_raw_decorator_shape())
    assert P.implements_or_inherits(view, "TextDecorator", "Component").matched is True
    assert P.implements_or_inherits(view, "ConcreteComponent", "TextDecorator").matched is False


def test_every_class_generator():
    view = SessionGraphView.from_raw(_raw_decorator_shape())
    candidates = P.every_class(view)
    assert {c.binding for c in candidates} == {"Component", "ConcreteComponent", "TextDecorator"}
