"""Unit tests for the GoF pattern engine's normalization layer
(patterns/normalization.py) — kind -> INTERFACE_LIKE/ABSTRACT_LIKE mapping
and the method-role alias config loader.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from patterns.normalization import (  # noqa: E402
    build_role_lookup,
    is_abstract_like,
    is_interface_like,
    load_method_roles,
)


def test_interface_like_kinds():
    assert is_interface_like("interface") is True
    assert is_interface_like("trait") is True
    assert is_interface_like("class") is False
    assert is_interface_like("struct") is False
    # abstract_class is deliberately BOTH interface-like and abstract-like:
    # GoF patterns don't require a literal `interface` keyword, and it's the
    # only idiom Python's ABC has at all (see normalization.py's comment).
    assert is_interface_like("abstract_class") is True


def test_abstract_like_kinds():
    assert is_abstract_like("abstract_class") is True
    assert is_abstract_like("class") is False
    assert is_abstract_like("interface") is False


def test_load_method_roles_returns_dict_even_when_empty():
    roles = load_method_roles()
    assert isinstance(roles, dict)


def test_build_role_lookup_inverts_and_lowercases():
    roles = {"ITERATOR_NEXT": ["next", "__next__", "Next", "hasNext"]}
    lookup = build_role_lookup(roles)
    assert lookup["next"] == "ITERATOR_NEXT"
    assert lookup["hasnext"] == "ITERATOR_NEXT"
    assert lookup["__next__"] == "ITERATOR_NEXT"
