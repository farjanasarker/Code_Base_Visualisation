"""Pins down what actually happens when two unrelated classes share a bare
name across different files — SessionGraphView.from_raw() documents this as
an accepted Phase-0 tradeoff (bare-name indexing, no name+file key), but it
hadn't been exercised with an actual same-named-classes-in-different-files
fixture. This is exactly that fixture: it doesn't assert the collision is
handled "correctly" (there's no correct answer under bare-name indexing —
the whole point is the two classes are indistinguishable), it pins down the
CURRENT behavior so a future file-scoped resolution fix has a regression
anchor, and demonstrates the concrete false-positive risk this creates for
pattern predicates.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from patterns.graph_view import SessionGraphView  # noqa: E402
from patterns import predicates as P  # noqa: E402


def _raw_two_unrelated_handlers():
    """Two classes named "Handler" in different files/packages, with no
    relationship to each other:
      - auth/session_handler.py: Handler holds a 'secret' field (Vault) and
        an encrypt() method — nothing to do with Chain of Responsibility.
      - chain/request_handler.py: Handler implements AbstractHandler and
        holds a 'next_handler' field typed as AbstractHandler (self type),
        the actual Chain of Responsibility shape.
    """
    return {
        "classes": [
            {"name": "Vault", "file": "auth/vault.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": [], "method_names": ["unlock"],
             "line_start": 1, "line_end": 2},
            {"name": "Handler", "file": "auth/session_handler.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["secret"], "method_names": ["encrypt"],
             "line_start": 1, "line_end": 5},
            {"name": "AbstractHandler", "file": "chain/request_handler.py", "kind": "interface",
             "language": "python", "labels": ["Class", "INTERFACE_LIKE"], "field_names": [],
             "method_names": ["handle"], "line_start": 1, "line_end": 2},
            {"name": "Handler", "file": "chain/request_handler.py", "kind": "class", "language": "python",
             "labels": ["Class"], "field_names": ["next_handler"], "method_names": ["handle"],
             "line_start": 3, "line_end": 6},
        ],
        "inherits": [],
        "implements": [
            {"child": "Handler", "child_file": "chain/request_handler.py", "parent": "AbstractHandler"},
        ],
        "has_field": [
            {"owner": "Handler", "owner_file": "auth/session_handler.py", "target": "Vault",
             "field_name": "secret", "is_collection": False},
            {"owner": "Handler", "owner_file": "chain/request_handler.py", "target": "AbstractHandler",
             "field_name": "next_handler", "is_collection": False},
        ],
        "methods": [
            {"fn_name": "encrypt", "file": "auth/session_handler.py", "class_name": "Handler",
             "raw_calls": []},
            {"fn_name": "handle", "file": "chain/request_handler.py", "class_name": "Handler",
             "raw_calls": ["handle"]},
        ],
    }


def test_same_named_classes_collapse_to_one_class_entry():
    """classes[] is a plain dict keyed by bare name — the second "Handler"
    silently overwrites the first. Only chain/request_handler.py's metadata
    survives; auth/session_handler.py's is gone, not merged.
    """
    view = SessionGraphView.from_raw(_raw_two_unrelated_handlers())
    handler = view.get_class("Handler")
    assert handler is not None
    assert handler.file == "chain/request_handler.py"
    assert "secret" not in handler.field_names
    assert "next_handler" in handler.field_names


def test_same_named_classes_cross_contaminate_fields_and_methods():
    """Unlike `classes[]`, fields_of/methods_of are keyed by owner name and
    *accumulate* (append/add, no overwrite) — so the two unrelated Handlers'
    fields and methods end up merged under one bucket, each visible as if
    it belonged to the other.
    """
    view = SessionGraphView.from_raw(_raw_two_unrelated_handlers())
    field_names = {e.field_name for e in view.fields_of["Handler"]}
    assert field_names == {"secret", "next_handler"}

    method_names = {m.fn_name for m in view.methods_of["Handler"]}
    assert method_names == {"encrypt", "handle"}


def test_collision_creates_false_positive_self_referential_field():
    """Concrete consequence: auth's Handler.encrypt() has nothing to do
    with Chain of Responsibility, but because it shares a bare name with
    chain's Handler (which legitimately holds a self-typed 'next_handler'
    field), has_self_referential_field reports a match for "Handler" that
    reads as if it applies to both — there is no way, at this bare-name
    index, to ask the question only about auth's Handler.
    """
    view = SessionGraphView.from_raw(_raw_two_unrelated_handlers())
    result = P.has_self_referential_field(view, "Handler")
    assert result.matched is True
