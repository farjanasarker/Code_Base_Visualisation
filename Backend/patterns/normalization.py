"""GoF pattern engine — normalization layer.

Per-language `kind` differences (Python's ABC/Protocol, Go's `interface`,
Rust's `trait`, TS's `interface`/`abstract class`, Java's `interface`/
`abstract class`) are already collapsed to one of five canonical values —
`class` / `abstract_class` / `interface` / `struct` / `trait` — at parse time
in `analyzer/parser.py`'s `ParsedClass.kind`. This module is the thin layer
on top: mapping `kind` to the two graph-queryable concepts every pattern
predicate cares about (INTERFACE_LIKE, ABSTRACT_LIKE), and loading the
method-role alias config.
"""

from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import yaml

_CONFIG_PATH = Path(__file__).parent / "config" / "method_roles.yaml"

# `abstract_class` counts as INTERFACE_LIKE too (in addition to
# ABSTRACT_LIKE, below — the two aren't mutually exclusive): GoF's Strategy/
# Template Method/etc. don't require a literal `interface` keyword, and an
# abstract class whose contract is "one abstract method, implemented by
# concrete subclasses" is structurally the same shape a pattern cares about.
# This also happens to be the *only* idiom Python's ABC actually has (no
# separate `interface` keyword exists in the language at all), and Java/TS
# abstract classes are used the same way in real code often enough that
# excluding them would just create language-specific false negatives.
INTERFACE_LIKE_KINDS = {"interface", "trait", "abstract_class"}
ABSTRACT_LIKE_KINDS = {"abstract_class"}


def is_interface_like(kind: str) -> bool:
    return kind in INTERFACE_LIKE_KINDS


def is_abstract_like(kind: str) -> bool:
    return kind in ABSTRACT_LIKE_KINDS


def load_method_roles(config_path: Path = _CONFIG_PATH) -> Dict[str, List[str]]:
    """Load the canonical method-role alias map (role name -> alias names),
    e.g. `{"ITERATOR_NEXT": ["next", "__next__", "Next", "hasNext"]}`.
    Returns {} if the config has no roles defined yet (Phase 0's case).
    """
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data.get("roles") or {}


def infer_go_structural_implements(classes: List[dict], functions: List[dict]) -> List[dict]:
    """Go has no `implements` keyword at all — interface satisfaction is
    purely structural (a struct satisfies an interface iff its method set is
    a superset of the interface's method set). Without this, no Go struct
    could ever get an IMPLEMENTS edge, since there's no explicit clause in
    the language to capture in the first place — this is a genuine language-
    idiom gap, not a parser oversight, and the fix is real structural
    inference (not a naming heuristic).

    Returns extra `{"child": struct_name, "file": ..., "parent": interface_name}`
    rows in the same shape store_class_graph()'s `implements_rows` uses, for
    the caller to merge in.
    """
    go_interfaces = [c for c in classes if c.get("language") == "go" and c.get("kind") == "interface"]
    go_structs = [c for c in classes if c.get("language") == "go" and c.get("kind") == "struct"]
    if not go_interfaces or not go_structs:
        return []

    methods_by_struct: Dict[str, set] = defaultdict(set)
    for f in functions:
        class_name = f.get("class_name")
        if f.get("language") == "go" and class_name:
            bare_name = f["name"].rsplit(".", 1)[-1]
            methods_by_struct[class_name].add(bare_name)

    rows = []
    for iface in go_interfaces:
        required = set(iface.get("method_names") or [])
        if not required:
            continue
        for struct in go_structs:
            if required <= methods_by_struct.get(struct["name"], set()):
                rows.append({"child": struct["name"], "file": struct["file"], "parent": iface["name"]})
    return rows


def build_role_lookup(roles: Dict[str, List[str]]) -> Dict[str, str]:
    """Invert the role map to alias-name -> role, lowercased, for O(1)
    role lookup of a given method name.
    """
    lookup: Dict[str, str] = {}
    for role, aliases in roles.items():
        for alias in aliases:
            lookup[alias.lower()] = role
    return lookup
