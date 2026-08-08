"""In-memory normalized session graph the rule engine builds once per scan
and every predicate reads from — no predicate issues its own Cypher.

This is a deliberate deviation from a literal reading of "predicates are
Python functions wrapping parametrized Cypher queries": building the whole
class graph in a handful of batched queries (`db.get_class_graph`) up front
and then evaluating every predicate for every rule spec against one in-memory
structure satisfies the design brief's own efficiency requirements ("batch
predicate evaluation per session, not per pattern per class"; "build the
normalized view once, evaluate all specs against it") more directly than
literal per-predicate Cypher calls would, while all graph *access* remains
Cypher-based (this view is only ever built from `get_class_graph`'s output).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class ClassInfo:
    name: str
    file: str
    kind: str
    language: str
    labels: List[str] = field(default_factory=list)
    field_names: List[str] = field(default_factory=list)
    method_names: List[str] = field(default_factory=list)
    unresolved_bases: List[str] = field(default_factory=list)
    unresolved_interfaces: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0

    @property
    def is_interface_like(self) -> bool:
        return "INTERFACE_LIKE" in self.labels

    @property
    def is_abstract_like(self) -> bool:
        return "ABSTRACT_LIKE" in self.labels


@dataclass
class FieldEdge:
    owner: str
    owner_file: str
    target: str
    field_name: str
    is_collection: bool


@dataclass
class MethodInfo:
    fn_name: str
    file: str
    class_name: str
    # [(callee_name, callee_class_or_None)] — callee_class is None when the
    # callee isn't a known method of any class in this session (a free
    # function, or a call the parser couldn't resolve).
    calls: List[tuple] = field(default_factory=list)
    # True only for Python's @abstractmethod — see ParsedFunction.is_abstract.
    is_abstract: bool = False
    # Class names this method constructs an instance of, filtered to only
    # names that resolve to a known Class in this session (raw_instantiates
    # -> resolved by direct name lookup, not the bare_name_to_classes/
    # method-name matching `calls` uses — class names are looked up by
    # their own identity, not by "who declares a method with this name").
    instantiates: List[str] = field(default_factory=list)


class SessionGraphView:
    """Read-only, name-indexed view over one session's class graph.

    Classes are indexed by bare name only (not name+file) — the same
    ambiguity tradeoff store_all()/store_class_graph() already accept for
    cross-file name resolution (base/interface/field-type names carry no
    file path at the declaration site). Two same-named classes in different
    files will collide here; acceptable for Phase 0, worth revisiting if a
    real project's false-positive rate demands file-scoped resolution.
    """

    def __init__(
        self,
        classes: Dict[str, ClassInfo],
        implementers_of: Dict[str, Set[str]],
        subclasses_of: Dict[str, Set[str]],
        fields_of: Dict[str, List[FieldEdge]],
        fields_by_owner_and_name: Dict[tuple, FieldEdge],
        methods_of: Dict[str, List[MethodInfo]],
    ):
        self.classes = classes
        self.implementers_of = implementers_of
        self.subclasses_of = subclasses_of
        self.fields_of = fields_of
        self.fields_by_owner_and_name = fields_by_owner_and_name
        self.methods_of = methods_of

        # class -> every type it implements/inherits, TRANSITIVELY —
        # computed as the closure over implementers_of/subclasses_of's
        # direct edges, not just one level. GoF's is-a-and-has-a patterns
        # (Decorator/Proxy/Chain of Responsibility) very commonly implement
        # the shared interface on an ABSTRACT BASE class, with concrete
        # subclasses only extending that base and never naming the
        # interface themselves (`MilkDecorator extends BeverageDecorator`,
        # where only `BeverageDecorator implements Beverage`) — a one-level
        # index would say MilkDecorator doesn't implement Beverage at all,
        # same as Java itself wouldn't. Used to test "is this field typed as
        # one of my own interfaces/bases" (field_typed_as_own_interface,
        # self_referential_types) and to find inherited fields
        # (effective_fields_of/effective_field, below).
        direct_parents: Dict[str, Set[str]] = defaultdict(set)
        for parent, children in implementers_of.items():
            for child in children:
                direct_parents[child].add(parent)
        for parent, children in subclasses_of.items():
            for child in children:
                direct_parents[child].add(parent)

        self.interfaces_of: Dict[str, Set[str]] = defaultdict(set)
        for child in direct_parents:
            seen: Set[str] = set()
            frontier = list(direct_parents[child])
            while frontier:
                parent = frontier.pop()
                if parent in seen or parent == child:
                    continue
                seen.add(parent)
                frontier.extend(direct_parents.get(parent, ()))
            self.interfaces_of[child] = seen

    @classmethod
    def from_raw(cls, raw: dict) -> "SessionGraphView":
        """Build from `db.get_class_graph()`'s return shape (or an
        equivalently-shaped hand-built dict in tests — no Neo4j required).
        """
        classes: Dict[str, ClassInfo] = {}
        for c in raw.get("classes", []):
            classes[c["name"]] = ClassInfo(
                name=c["name"], file=c.get("file", ""), kind=c.get("kind", ""),
                language=c.get("language", ""), labels=list(c.get("labels") or []),
                field_names=list(c.get("field_names") or []),
                method_names=list(c.get("method_names") or []),
                unresolved_bases=list(c.get("unresolved_bases") or []),
                unresolved_interfaces=list(c.get("unresolved_interfaces") or []),
                line_start=c.get("line_start", 0), line_end=c.get("line_end", 0),
            )

        implementers_of: Dict[str, Set[str]] = defaultdict(set)
        for r in raw.get("implements", []):
            implementers_of[r["parent"]].add(r["child"])

        subclasses_of: Dict[str, Set[str]] = defaultdict(set)
        for r in raw.get("inherits", []):
            subclasses_of[r["parent"]].add(r["child"])
            # Python (no separate `implements` keyword — `class Foo(ABC):`
            # both inherits from AND implements its ABC) and any language
            # where a concrete class `extends` an abstract class rather than
            # `implements` a separate interface: since abstract_class now
            # counts as INTERFACE_LIKE (see normalization.py), a class
            # extending one *is* implementing it in the sense the Strategy
            # predicates care about. Fold INHERITS_FROM edges whose parent
            # is interface-like into implementers_of too.
            parent_class = classes.get(r["parent"])
            if parent_class is not None and parent_class.is_interface_like:
                implementers_of[r["parent"]].add(r["child"])

        fields_of: Dict[str, List[FieldEdge]] = defaultdict(list)
        fields_by_owner_and_name: Dict[tuple, FieldEdge] = {}
        for r in raw.get("has_field", []):
            edge = FieldEdge(
                owner=r["owner"], owner_file=r.get("owner_file", ""), target=r["target"],
                field_name=r["field_name"], is_collection=bool(r.get("is_collection")),
            )
            fields_of[r["owner"]].append(edge)
            fields_by_owner_and_name[(r["owner"], r["field_name"])] = edge

        raw_methods = raw.get("methods", [])

        # Which classes declare a method named X, by bare name — union of
        # every class's declared method_names (covers bodyless interface/
        # trait signatures, and Go interfaces) and its concrete methods'
        # names from the raw METHOD_OF rows (covers Go structs, whose
        # methods live outside the type body entirely and so never appear
        # in method_names — see _METHOD_NODE_TYPES's Go note). Built before
        # resolving calls below, since call resolution needs it.
        # Go's Function.name is compound ("ReceiverType.MethodName" — see
        # parser.py's Go receiver handling) since the parser needs it
        # globally unique; every other language's is already bare. Strip to
        # the bare suffix uniformly so it's comparable to call-site names
        # (which are always bare — a call site has no receiver-type prefix).
        def _bare(fn_name: str) -> str:
            return fn_name.rsplit(".", 1)[-1]

        bare_name_to_classes: Dict[str, Set[str]] = defaultdict(set)
        for name, c in classes.items():
            for method_name in c.method_names:
                bare_name_to_classes[method_name].add(name)
        for r in raw_methods:
            bare_name_to_classes[_bare(r["fn_name"])].add(r["class_name"])

        def _resolve_callee_class(bare_name: str) -> Optional[str]:
            matches = bare_name_to_classes.get(bare_name)
            if matches and len(matches) == 1:
                return next(iter(matches))
            return None  # ambiguous (matches 2+ classes) or unknown — same
            # name-only resolution ambiguity store_all() already accepts
            # elsewhere in this codebase (e.g. CALLS-edge callee matching).

        methods_of: Dict[str, List[MethodInfo]] = defaultdict(list)
        for r in raw_methods:
            calls = [
                (bare_name, _resolve_callee_class(bare_name))
                for bare_name in (r.get("raw_calls") or [])
            ]
            instantiates = [
                name for name in (r.get("raw_instantiates") or []) if name in classes
            ]
            methods_of[r["class_name"]].append(MethodInfo(
                fn_name=_bare(r["fn_name"]), file=r.get("file", ""),
                class_name=r["class_name"], calls=calls,
                is_abstract=bool(r.get("is_abstract", False)),
                instantiates=instantiates,
            ))

        return cls(classes, implementers_of, subclasses_of, fields_of,
                    fields_by_owner_and_name, methods_of)

    def get_class(self, name: str) -> Optional[ClassInfo]:
        return self.classes.get(name)

    def methods_named(self, class_name: str) -> Set[str]:
        """Every method name known for a class — bodied methods (from
        METHOD_OF/Function nodes) union bodyless declarations (interface
        signatures, abstract methods — `ClassInfo.method_names`, since
        those never get a Function node to begin with). Delegation targets
        are very often an interface, so skipping method_names here would
        make delegates_to_field silently unable to match its most common
        case.
        """
        names = {m.fn_name for m in self.methods_of.get(class_name, [])}
        c = self.classes.get(class_name)
        if c is not None:
            names |= set(c.method_names)
        return names

    def self_referential_types(self, class_name: str) -> Set[str]:
        """Every type name a field on `class_name` could be typed as and
        still count as "self-referential" for Composite/Decorator/Proxy/
        Chain of Responsibility purposes: the class's own name, every
        interface/base it implements or inherits (Decorator's actual shape
        — a field typed as the *shared* interface, not literally its own
        class name), and any interface name that didn't resolve to a known
        in-session class (best-effort — still worth treating as "its own
        interface" per the design brief's predicate description).
        """
        c = self.classes.get(class_name)
        if c is None:
            return {class_name}
        return {class_name} | self.interfaces_of.get(class_name, set()) | set(c.unresolved_interfaces)

    def effective_fields_of(self, class_name: str) -> List[FieldEdge]:
        """class_name's own fields, plus any it INHERITS from an ancestor
        (implemented interface or base class) but doesn't redeclare itself
        — own fields shadow an inherited one of the same name. Needed
        because the field predicates otherwise only see `fields_of`'s
        directly-declared-on-this-class edges: Decorator/Proxy/Chain of
        Responsibility's canonical shape declares the shared wrapped/next
        field ONCE on an abstract base class, with every concrete
        subclass inheriting it rather than redeclaring it — a lookup
        scoped to the subclass alone would find no field there at all.
        """
        own = list(self.fields_of.get(class_name, []))
        seen_names = {e.field_name for e in own}
        result = list(own)
        for ancestor in sorted(self.interfaces_of.get(class_name, ())):
            for e in self.fields_of.get(ancestor, []):
                if e.field_name in seen_names:
                    continue
                seen_names.add(e.field_name)
                result.append(e)
        return result

    def effective_field(self, class_name: str, field_name: str) -> Optional[FieldEdge]:
        """The FieldEdge for `field_name` as seen from `class_name`: its
        own declaration if present, else the nearest ancestor's — see
        effective_fields_of. Used wherever a caller already knows the
        field name it's looking for (a `field:` param resolved by a prior
        role binding) and just needs that field's edge, without building
        the whole effective field list.
        """
        edge = self.fields_by_owner_and_name.get((class_name, field_name))
        if edge is not None:
            return edge
        for ancestor in sorted(self.interfaces_of.get(class_name, ())):
            edge = self.fields_by_owner_and_name.get((ancestor, field_name))
            if edge is not None:
                return edge
        return None
