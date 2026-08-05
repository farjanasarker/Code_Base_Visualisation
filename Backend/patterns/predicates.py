"""Reusable structural predicate library — the shared vocabulary every GoF
rule spec composes instead of writing its own graph logic. Every predicate
is a plain Python function over a `SessionGraphView` (built once per scan,
see graph_view.py) and returns evidence alongside its verdict, never a bare
bool — design principle #4 (every match must carry class/method/line
evidence a user can verify in the graph view).

Two shapes of predicate:
  - "generator" predicates (`interface_with_single_method`,
    `composition_field_of_type`) search the whole session and return a list
    of `Candidate` bindings — used by the rule engine to try each candidate
    for a role (e.g. `strategy_interface`) before checking the rest of a
    spec's requirements against that binding.
  - "checker" predicates take already-bound names and return a single
    `PredicateResult` — true/false plus evidence.

Known Phase-0 gaps (documented rather than faked): `fluent_return_self` and
`cache_keyed_return` need method return-type/return-expression data the
parser doesn't capture yet (no pattern in Phase 0 needs them — Strategy
doesn't, and they're stubbed out returning matched=False with an
explanatory evidence string rather than a fabricated heuristic).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List

from .graph_view import SessionGraphView
from .normalization import build_role_lookup, load_method_roles

# Loaded once at import time — method_roles.yaml rarely changes at runtime,
# and every predicate call would otherwise re-parse + re-invert the same
# small YAML file for no reason.
_ROLE_LOOKUP = build_role_lookup(load_method_roles())


@dataclass
class PredicateResult:
    matched: bool
    evidence: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class Candidate:
    """A single binding a generator predicate found, plus the evidence for
    why it qualifies and any extra fields later requirements need (e.g. the
    field name a composition edge was found on).
    """
    binding: str
    evidence: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _loc(view: SessionGraphView, class_name: str) -> str:
    c = view.get_class(class_name)
    if c is None:
        return class_name
    return f"{class_name} ({c.file}:{c.line_start})"


# ── General-purpose generator ────────────────────────────────────────────

def every_class(view: SessionGraphView) -> List[Candidate]:
    """Every class in the session, as a candidate for a role — the entry
    point for single-class structural patterns (Template Method, Composite,
    Decorator, Chain of Responsibility, Iterator, ...) that don't need
    Strategy's multi-role search, just "does this one class have shape X".
    Composing `every_class` + existing checker predicates covers them
    without a bespoke generator function per pattern.
    """
    return [Candidate(binding=name, evidence=[]) for name in view.classes]


def implements_or_inherits(view: SessionGraphView, class_name: str, type_name: str) -> PredicateResult:
    """Does `class_name` IMPLEMENT or INHERIT_FROM `type_name` (directly)?
    The key Decorator disambiguator: a Decorator is-a *and* has-a the same
    abstraction it wraps — Chain of Responsibility's "next handler" field is
    typically the same shape (self-typed field + shared base class) without
    that requirement being the point of the pattern, so this doesn't fully
    separate them on its own (see decorator.yaml's tier note).
    """
    matched = type_name in view.interfaces_of.get(class_name, set())
    return PredicateResult(matched=matched, evidence=[
        f"{class_name} {'implements/inherits' if matched else 'does not implement/inherit'} {type_name}"
    ])


def has_role_method(view: SessionGraphView, class_name: str, role_name: str) -> PredicateResult:
    """Does `class_name` declare a method matching a canonical role from
    method_roles.yaml (e.g. ITERATOR_NEXT covers next/__next__/Next)? The
    normalization layer's payoff: a rule spec asks for a role, not a
    per-language method-name literal.
    """
    if class_name not in view.classes:
        return PredicateResult(matched=False, evidence=[f"{class_name} not found"])
    for method_name in view.methods_named(class_name):
        if _ROLE_LOOKUP.get(method_name.lower()) == role_name:
            return PredicateResult(matched=True, evidence=[
                f"{_loc(view, class_name)} has {role_name}-role method: {method_name}()"])
    return PredicateResult(matched=False, evidence=[f"{class_name} has no {role_name}-role method"])


# ── Strategy-specific predicates ─────────────────────────────────────────

def interface_with_single_method(view: SessionGraphView) -> List[Candidate]:
    """Every INTERFACE_LIKE class/trait declaring exactly one method."""
    out = []
    for name, c in view.classes.items():
        if not c.is_interface_like:
            continue
        if len(c.method_names) == 1:
            out.append(Candidate(
                binding=name,
                evidence=[f"{_loc(view, name)} declares exactly one method: {c.method_names[0]}()"],
                extra={"method": c.method_names[0]},
            ))
    return out


def min_implementers(view: SessionGraphView, interface_name: str, count: int) -> PredicateResult:
    implementers = view.implementers_of.get(interface_name, set())
    matched = len(implementers) >= count
    evidence = [f"{len(implementers)} implementer(s) of {interface_name}: {', '.join(sorted(implementers)) or '(none)'}"]
    return PredicateResult(matched=matched, evidence=evidence)


def any_implementer_has_field_of_type(view: SessionGraphView, of: str, type_name: str) -> PredicateResult:
    """Does any implementer of interface `of` hold a field typed as
    `type_name`? State's disambiguator from Strategy: a State's concrete
    implementers typically hold a back-reference to the Context that owns
    them (to trigger `context.set_state(...)` on transition) — a
    bidirectional context<->state composition edge Strategy never has
    (a Strategy implementation has no reason to know its Context at all).
    """
    implementers = view.implementers_of.get(of, set())
    for impl in implementers:
        for e in view.fields_of.get(impl, []):
            if e.target == type_name:
                return PredicateResult(matched=True, evidence=[
                    f"{_loc(view, impl)} (implementer of {of}) has field '{e.field_name}: {type_name}' "
                    f"— bidirectional context<->state edge"
                ])
    return PredicateResult(matched=False, evidence=[
        f"no implementer of {of} holds a field typed as {type_name} — no bidirectional edge found"
    ])


def composition_field_of_type(view: SessionGraphView, type_name: str) -> List[Candidate]:
    """Every class holding a field (any cardinality) typed as `type_name`."""
    out = []
    for owner, edges in view.fields_of.items():
        for e in edges:
            if e.target == type_name:
                out.append(Candidate(
                    binding=owner,
                    evidence=[f"{_loc(view, owner)} has field '{e.field_name}: {type_name}'"],
                    extra={"field_name": e.field_name, "is_collection": e.is_collection},
                ))
    return out


def collection_composition_field_of_type(view: SessionGraphView, type_name: str) -> List[Candidate]:
    """Like composition_field_of_type, but only the collection-cardinality
    fields — Observer's differentiator from Strategy: a Subject holds a
    *list* of observers, not a single one. Same list-vs-single distinction
    that already separates Composite from Decorator/Proxy/Chain of
    Responsibility elsewhere in this library.
    """
    out = []
    for owner, edges in view.fields_of.items():
        for e in edges:
            if e.target == type_name and e.is_collection:
                out.append(Candidate(
                    binding=owner,
                    evidence=[f"{_loc(view, owner)} has collection field '{e.field_name}: {type_name}[]'"],
                    extra={"field_name": e.field_name, "is_collection": True},
                ))
    return out


def delegates_to_field(view: SessionGraphView, class_name: str, field_name: str) -> PredicateResult:
    """Does some method on `class_name` call a method that also exists on
    the field's target class?

    Known Phase-0 approximation: the parser doesn't track *how* a call was
    made (`self.field.method()` vs. an unrelated bare call to a same-named
    method elsewhere), only that function A calls function B — so this
    checks "class has the field, and some method on the class calls a
    method that also exists on the field's target type", not a verified
    call-through-that-specific-field. Confidence weighting in the rule spec
    is expected to offset the false-positive risk this introduces; a
    precise fix means threading call-site receiver-expression info through
    the parser (candidate Phase 1 enhancement if false positives show up).
    """
    edge = view.fields_by_owner_and_name.get((class_name, field_name))
    if edge is None:
        return PredicateResult(matched=False, evidence=[f"{class_name} has no field '{field_name}'"])

    target_methods = view.methods_named(edge.target)
    if not target_methods:
        return PredicateResult(matched=False, evidence=[f"{edge.target} has no known methods to delegate to"])

    for m in view.methods_of.get(class_name, []):
        for callee_name, _callee_class in m.calls:
            if callee_name in target_methods:
                return PredicateResult(matched=True, evidence=[
                    f"{class_name}.{m.fn_name}() calls {callee_name}(), also defined on "
                    f"{edge.target} (field '{field_name}') — approximate: not verified as a "
                    f"call through that specific field"
                ])
    return PredicateResult(matched=False, evidence=[
        f"no method on {class_name} calls a method also defined on {edge.target}"
    ])


# ── Foundation predicates (Phase 1's Composite/Decorator/Chain/Iterator/... ) ─

def has_self_referential_field(view: SessionGraphView, class_name: str) -> PredicateResult:
    """Class holds a field typed as itself, or as one of its own interfaces
    (the shape Decorator/Proxy/Chain of Responsibility actually have — a
    field typed as the *shared* abstraction the class also implements, not
    literally its own class name)."""
    if class_name not in view.classes:
        return PredicateResult(matched=False, evidence=[f"{class_name} not found"])
    self_types = view.self_referential_types(class_name)
    for e in view.fields_of.get(class_name, []):
        if e.target in self_types:
            qualifier = "its own class" if e.target == class_name else f"its own interface {e.target}"
            return PredicateResult(matched=True, evidence=[
                f"{_loc(view, class_name)} has field '{e.field_name}' typed as {qualifier}"])
    return PredicateResult(matched=False, evidence=[f"{class_name} has no self-referential field"])


def has_list_of_own_type_field(view: SessionGraphView, class_name: str) -> PredicateResult:
    self_types = view.self_referential_types(class_name)
    for e in view.fields_of.get(class_name, []):
        if e.target in self_types and e.is_collection:
            return PredicateResult(matched=True, evidence=[
                f"{_loc(view, class_name)} has collection field '{e.field_name}' of its own type — Composite signal"])
    return PredicateResult(matched=False, evidence=[f"{class_name} has no list-of-own-type field"])


def has_single_field_of_own_type(view: SessionGraphView, class_name: str) -> PredicateResult:
    self_types = view.self_referential_types(class_name)
    for e in view.fields_of.get(class_name, []):
        if e.target in self_types and not e.is_collection:
            return PredicateResult(matched=True, evidence=[
                f"{_loc(view, class_name)} has single field '{e.field_name}' of its own type — "
                f"Decorator/Proxy/Chain signal"])
    return PredicateResult(matched=False, evidence=[f"{class_name} has no single field of its own type"])


def list_of_own_type_field_candidates(view: SessionGraphView) -> List[Candidate]:
    """Generator variant of has_list_of_own_type_field — every class with
    such a field, carrying which field it is (needed to chain into
    delegates_to_field/wraps_and_extends without a second lookup step)."""
    out = []
    for name in view.classes:
        self_types = view.self_referential_types(name)
        for e in view.fields_of.get(name, []):
            if e.target in self_types and e.is_collection:
                out.append(Candidate(
                    binding=name,
                    evidence=[f"{_loc(view, name)} has collection field '{e.field_name}' of its own type"],
                    extra={"field_name": e.field_name},
                ))
    return out


def single_field_of_own_type_candidates(view: SessionGraphView) -> List[Candidate]:
    """Generator variant of has_single_field_of_own_type — see above."""
    out = []
    for name in view.classes:
        self_types = view.self_referential_types(name)
        for e in view.fields_of.get(name, []):
            if e.target in self_types and not e.is_collection:
                out.append(Candidate(
                    binding=name,
                    evidence=[f"{_loc(view, name)} has single field '{e.field_name}' of its own type"],
                    extra={"field_name": e.field_name},
                ))
    return out


def wraps_and_extends(view: SessionGraphView, class_name: str, field_name: str) -> PredicateResult:
    """delegates_to_field is true AND the wrapping method does more than
    forward the call (its own call count > 1) -> Decorator signal;
    a near-pure passthrough (<=1 call) -> Proxy signal instead.
    """
    delegate_result = delegates_to_field(view, class_name, field_name)
    if not delegate_result.matched:
        return PredicateResult(matched=False, evidence=delegate_result.evidence)

    edge = view.fields_by_owner_and_name.get((class_name, field_name))
    target_methods = view.methods_named(edge.target) if edge else set()
    for m in view.methods_of.get(class_name, []):
        delegating_calls = [c for c in m.calls if c[0] in target_methods]
        if delegating_calls:
            classification = "decorator" if len(m.calls) > 1 else "proxy"
            return PredicateResult(
                matched=True,
                evidence=[
                    f"{class_name}.{m.fn_name}() makes {len(m.calls)} call(s) total while delegating "
                    f"through '{field_name}' -> {classification} signal"
                ],
                extra={"classification": classification},
            )
    return PredicateResult(matched=False, evidence=["no delegating method found to classify"])


def field_typed_as_own_interface(view: SessionGraphView, class_name: str, field_name: str) -> PredicateResult:
    """Does class_name's `field_name` field share a type with something
    class_name itself implements/inherits? Decorator's defining trait: it
    is-a *and* has-a the same abstraction it wraps. (Chain of
    Responsibility's "next handler" field is typically the same shape
    without that being the point of the pattern — see decorator.yaml and
    chain_of_responsibility.yaml's tier notes on why this alone doesn't
    fully separate the two.)
    """
    edge = view.fields_by_owner_and_name.get((class_name, field_name))
    if edge is None:
        return PredicateResult(matched=False, evidence=[f"{class_name} has no field '{field_name}'"])
    matched = edge.target in view.interfaces_of.get(class_name, set())
    return PredicateResult(matched=matched, evidence=[
        f"{class_name} {'implements/inherits' if matched else 'does not implement/inherit'} "
        f"{edge.target}, the same type its '{field_name}' field is typed as"
    ])


def is_decorator_wrapping(view: SessionGraphView, class_name: str, field_name: str) -> PredicateResult:
    """wraps_and_extends, filtered to the 'decorator' classification —
    split out as its own predicate so decorator.yaml/proxy.yaml can each
    require one specific classification declaratively, without the rule
    engine needing a general "check a prior predicate's extra value"
    capability that nothing else in Phase 1 needs.
    """
    result = wraps_and_extends(view, class_name, field_name)
    matched = result.matched and result.extra.get("classification") == "decorator"
    return PredicateResult(matched=matched, evidence=result.evidence)


def is_proxy_wrapping(view: SessionGraphView, class_name: str, field_name: str) -> PredicateResult:
    """wraps_and_extends, filtered to the 'proxy' classification — see
    is_decorator_wrapping's docstring."""
    result = wraps_and_extends(view, class_name, field_name)
    matched = result.matched and result.extra.get("classification") == "proxy"
    return PredicateResult(matched=matched, evidence=result.evidence)


def fluent_return_self(view: SessionGraphView, class_name: str, method_name: str) -> PredicateResult:
    return PredicateResult(matched=False, evidence=[
        "not derivable in Phase 0 — method return-type/return-expression data "
        "isn't captured by the parser yet (needed before this predicate can be "
        "anything but a guess); revisit when a pattern that needs it is implemented"
    ])


def abstract_method_called_from_concrete_sibling_method(view: SessionGraphView, class_name: str) -> PredicateResult:
    """Template Method's core shape: an abstract method declared on the
    class is called by another (concrete, has-a-body) method on the same
    class.
    """
    c = view.get_class(class_name)
    if c is None:
        return PredicateResult(matched=False, evidence=[f"{class_name} not found"])
    # A method is abstract if it never got a Function/METHOD_OF node at all
    # (TS/Java/Go/Rust's bodyless interface/abstract-method signatures —
    # `method_names` covers those but methods_of doesn't) OR if it did but
    # was explicitly flagged (Python's @abstractmethod, which still has a
    # syntactic body — see ParsedFunction.is_abstract).
    concrete_methods = {m.fn_name for m in view.methods_of.get(class_name, []) if not m.is_abstract}
    abstract_methods = set(c.method_names) - concrete_methods
    if not abstract_methods:
        return PredicateResult(matched=False, evidence=[f"{class_name} has no abstract methods"])

    for m in view.methods_of.get(class_name, []):
        called_abstracts = {name for name, _cls in m.calls if name in abstract_methods}
        if called_abstracts:
            return PredicateResult(matched=True, evidence=[
                f"{class_name}.{m.fn_name}() calls abstract method(s) {sorted(called_abstracts)} "
                f"declared on the same class"
            ])
    return PredicateResult(matched=False, evidence=[
        f"{class_name} has abstract methods {sorted(abstract_methods)} but no concrete sibling method calls them"
    ])


def double_dispatch_pair(
    view: SessionGraphView, class_a: str, method_x: str, class_b: str, method_y: str
) -> PredicateResult:
    """A.methodX calls B.methodY, and B.methodY calls back A.methodX — Visitor's shape."""
    a_calls_b = any(
        callee == method_y and callee_cls == class_b
        for m in view.methods_of.get(class_a, []) if m.fn_name == method_x
        for callee, callee_cls in m.calls
    )
    b_calls_a = any(
        callee == method_x and callee_cls == class_a
        for m in view.methods_of.get(class_b, []) if m.fn_name == method_y
        for callee, callee_cls in m.calls
    )
    matched = a_calls_b and b_calls_a
    evidence = [
        f"{class_a}.{method_x}() -> {class_b}.{method_y}(): {'yes' if a_calls_b else 'no'}",
        f"{class_b}.{method_y}() -> {class_a}.{method_x}(): {'yes' if b_calls_a else 'no'}",
    ]
    return PredicateResult(matched=matched, evidence=evidence)


def double_dispatch_candidates(view: SessionGraphView) -> List[Candidate]:
    """Generator variant of the double-dispatch shape, auto-discovering
    (element, visitor) pairs rather than requiring the spec to name
    specific classes/methods.

    Deliberately looser than double_dispatch_pair's exact-same-method-name
    callback requirement: real Visitor code is `Element.accept(visitor)`
    calling `Visitor.visitX(element)`, which typically calls back a
    *different* method on Element (a getter, e.g. `element.get_radius()`) —
    calling `accept()` again would just recurse. This only requires A to
    call some method on B, and B's callee method to call *some* method back
    on A — still a genuine two-classes-calling-each-other signal, just not
    pinned to one specific method pair.
    """
    out = []
    seen_pairs = set()
    for class_a, methods_a in view.methods_of.items():
        for m in methods_a:
            for callee_name, callee_class in m.calls:
                if not callee_class or callee_class == class_a:
                    continue
                for m2 in view.methods_of.get(callee_class, []):
                    if m2.fn_name != callee_name:
                        continue
                    calls_back = [cn for cn, cc in m2.calls if cc == class_a]
                    if not calls_back:
                        continue
                    pair_key = (class_a, callee_class)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    out.append(Candidate(
                        binding=class_a,
                        evidence=[
                            f"{class_a}.{m.fn_name}() -> {callee_class}.{callee_name}() -> "
                            f"back to {class_a}.{calls_back[0]}() (double dispatch)"
                        ],
                        extra={"visitor_class": callee_class},
                    ))
    return out


def fan_out_to_common_hub(view: SessionGraphView, class_names: List[str]) -> PredicateResult:
    """All of `class_names` call methods on some common class outside the group — Mediator signal."""
    call_targets_by_class = {}
    for cn in class_names:
        targets = {
            callee_cls for m in view.methods_of.get(cn, []) for _callee, callee_cls in m.calls
            if callee_cls and callee_cls not in class_names
        }
        call_targets_by_class[cn] = targets

    common = set.intersection(*call_targets_by_class.values()) if call_targets_by_class else set()
    matched = bool(common)
    evidence = [f"{cn} -> {sorted(t)}" for cn, t in call_targets_by_class.items()]
    if matched:
        evidence.append(f"common hub(s): {sorted(common)}")
    return PredicateResult(matched=matched, evidence=evidence)


def no_direct_edges_between(view: SessionGraphView, class_names: List[str]) -> PredicateResult:
    """None of `class_names` call each other directly — Mediator's other half."""
    names = set(class_names)
    violations = []
    for cn in class_names:
        for m in view.methods_of.get(cn, []):
            for _callee, callee_cls in m.calls:
                if callee_cls in names and callee_cls != cn:
                    violations.append(f"{cn}.{m.fn_name}() -> {callee_cls}")
    matched = not violations
    evidence = violations if violations else [f"no direct calls found among {sorted(names)}"]
    return PredicateResult(matched=matched, evidence=evidence)


def cache_keyed_return(view: SessionGraphView, class_name: str, method_name: str) -> PredicateResult:
    """Flyweight, Phase 2: does `method_name` construct a product AND does
    `class_name` also hold a *collection* field of that same product type?

    Known approximation, not a bug: a real Flyweight cache is a Dict/Map
    keyed by some identity (`Dict[str, Product]`), not a List — but per-field
    TYPE TEXT was never persisted to Neo4j (only field *names*, plus
    HAS_FIELD edges for fields whose type resolves to a known class), so
    List-vs-Dict can't be distinguished from the graph alone. A collection
    field of the constructed product's type is used as a loose proxy for
    "there's a cache of these somewhere on this class" — tier: low in
    flyweight.yaml reflects this being a weaker signal than the rest of
    Phase 2's predicates, not a detection bug.
    """
    m = next((m for m in view.methods_of.get(class_name, []) if m.fn_name == method_name), None)
    if m is None or not m.instantiates:
        return PredicateResult(matched=False, evidence=[f"{class_name}.{method_name}() does not construct anything"])
    for product in m.instantiates:
        for e in view.fields_of.get(class_name, []):
            if e.target == product and e.is_collection:
                return PredicateResult(matched=True, evidence=[
                    f"{class_name}.{method_name}() constructs {product}, and {class_name} holds a "
                    f"collection field '{e.field_name}' of that same type — approximate cache signal"
                ])
    return PredicateResult(matched=False, evidence=[
        f"no collection field matching {class_name}.{method_name}()'s constructed type(s) found"
    ])


# ── Phase 2: creational + structural + behavioral patterns ──────────────

def factory_method_candidates(view: SessionGraphView) -> List[Candidate]:
    """GoF-strict Factory Method (stronger than the existing simple
    create/build/make-naming Factory heuristic): an abstract/interface
    Creator class declares an abstract method; 2+ concrete subclasses each
    override it, each constructing a DIFFERENT product class. Real subclass-
    level product differentiation, not just a suggestively-named method.
    """
    out = []
    for creator_name, creator in view.classes.items():
        if not (creator.is_interface_like or creator.is_abstract_like):
            continue
        concrete_names = {m.fn_name for m in view.methods_of.get(creator_name, []) if not m.is_abstract}
        abstract_names = set(creator.method_names) - concrete_names
        if not abstract_names:
            continue
        subclasses = view.subclasses_of.get(creator_name, set()) | view.implementers_of.get(creator_name, set())
        if len(subclasses) < 2:
            continue
        for method_name in abstract_names:
            products_by_subclass = {}
            for sub in subclasses:
                for m in view.methods_of.get(sub, []):
                    if m.fn_name == method_name and m.instantiates:
                        products_by_subclass[sub] = m.instantiates[0]
            distinct_products = set(products_by_subclass.values())
            if len(products_by_subclass) >= 2 and len(distinct_products) >= 2:
                out.append(Candidate(
                    binding=creator_name,
                    evidence=[
                        f"{_loc(view, creator_name)}.{method_name}() overridden by "
                        f"{len(products_by_subclass)} subclasses, each constructing a distinct product: "
                        f"{products_by_subclass}"
                    ],
                    extra={"method": method_name, "products": products_by_subclass},
                ))
    return out


def abstract_factory_candidates(view: SessionGraphView) -> List[Candidate]:
    """Abstract Factory: an interface with 2+ creation methods, and 2+
    concrete implementers where each implementer's own overrides construct
    a distinct product per method — Factory Method's shape extended across
    a whole family of products that vary together per implementer.
    """
    out = []
    for factory_name, factory in view.classes.items():
        if not factory.is_interface_like or len(factory.method_names) < 2:
            continue
        implementers = view.implementers_of.get(factory_name, set()) | view.subclasses_of.get(factory_name, set())
        if len(implementers) < 2:
            continue
        per_implementer_products = {}
        for impl in implementers:
            products = {
                m.fn_name: m.instantiates[0]
                for m in view.methods_of.get(impl, [])
                if m.fn_name in factory.method_names and m.instantiates
            }
            if len(products) >= 2:
                per_implementer_products[impl] = products
        if len(per_implementer_products) < 2:
            continue
        product_families = {frozenset(p.values()) for p in per_implementer_products.values()}
        if len(product_families) >= 2:
            out.append(Candidate(
                binding=factory_name,
                evidence=[
                    f"{_loc(view, factory_name)} has {len(per_implementer_products)} concrete factories, "
                    f"each producing a distinct product family: {per_implementer_products}"
                ],
                extra={"implementers": list(per_implementer_products.keys())},
            ))
    return out


def builder_candidates(view: SessionGraphView) -> List[Candidate]:
    """Builder: a class with a build()-role method that constructs a
    DIFFERENT product class, alongside 2+ other methods that don't
    themselves construct anything (the incremental setter/configuration
    methods that accumulate state before build() assembles it)."""
    out = []
    for name, methods in view.methods_of.items():
        build_method = next(
            (m for m in methods if _ROLE_LOOKUP.get(m.fn_name.lower()) == "BUILDER_BUILD"), None)
        if build_method is None:
            continue
        products = [p for p in build_method.instantiates if p != name]
        if not products:
            continue
        setter_like = [m for m in methods if m.fn_name != build_method.fn_name and not m.instantiates]
        if len(setter_like) < 2:
            continue
        out.append(Candidate(
            binding=name,
            evidence=[
                f"{_loc(view, name)}.{build_method.fn_name}() constructs {products[0]}, alongside "
                f"{len(setter_like)} configuration method(s): {sorted(m.fn_name for m in setter_like)}"
            ],
            extra={"product": products[0], "build_method": build_method.fn_name},
        ))
    return out


def prototype_candidates(view: SessionGraphView) -> List[Candidate]:
    """Prototype: a class with a clone()-role method that constructs a NEW
    instance of its OWN class — self-instantiation, the inverse of Factory
    Method's "constructs a different class" signal."""
    out = []
    for name, methods in view.methods_of.items():
        for m in methods:
            if _ROLE_LOOKUP.get(m.fn_name.lower()) == "PROTOTYPE_CLONE" and name in m.instantiates:
                out.append(Candidate(
                    binding=name,
                    evidence=[f"{_loc(view, name)}.{m.fn_name}() constructs a new {name} instance"],
                    extra={"clone_method": m.fn_name},
                ))
                break
    return out


def interface_with_single_role_method(view: SessionGraphView, role_name: str) -> List[Candidate]:
    """Like interface_with_single_method, but also requires that one method
    match a canonical role — Command's differentiator from generic Strategy:
    the single method must specifically be execute()-role, not any name.
    """
    out = []
    for name, c in view.classes.items():
        if not c.is_interface_like or len(c.method_names) != 1:
            continue
        method = c.method_names[0]
        if _ROLE_LOOKUP.get(method.lower()) == role_name:
            out.append(Candidate(
                binding=name,
                evidence=[f"{_loc(view, name)} declares exactly one method: {method}() (role: {role_name})"],
                extra={"method": method},
            ))
    return out


def adapter_candidates(view: SessionGraphView) -> List[Candidate]:
    """Adapter: implements/inherits some Target type, holds a field typed as
    something that does NOT itself implement/inherit that same Target (the
    Adaptee — an unrelated type), and delegates to it. The key structural
    difference from Decorator/Chain of Responsibility (see decorator.yaml):
    Decorator's field IS typed as the same abstraction it implements;
    Adapter's is deliberately typed as something else entirely.
    """
    out = []
    for name, edges in view.fields_of.items():
        implemented = view.interfaces_of.get(name, set())
        if not implemented:
            continue
        for e in edges:
            if e.target in implemented or e.target == name:
                continue
            target_methods = view.methods_named(e.target)
            if not target_methods:
                continue
            for m in view.methods_of.get(name, []):
                if any(callee in target_methods for callee, _cc in m.calls):
                    out.append(Candidate(
                        binding=name,
                        evidence=[
                            f"{_loc(view, name)} implements {sorted(implemented)} and delegates to "
                            f"unrelated field '{e.field_name}: {e.target}'"
                        ],
                        extra={"adaptee": e.target, "field_name": e.field_name},
                    ))
                    break
    return out


def has_min_subclasses(view: SessionGraphView, class_name: str, count: int) -> PredicateResult:
    """Bridge's differentiator from Strategy/State: the composing
    ('Abstraction') class has its own subclass hierarchy, not just a plain
    context holding a strategy/state field."""
    subs = view.subclasses_of.get(class_name, set())
    matched = len(subs) >= count
    return PredicateResult(matched=matched, evidence=[
        f"{class_name} has {len(subs)} subclass(es): {sorted(subs) or '(none)'}"])


def flyweight_candidates(view: SessionGraphView) -> List[Candidate]:
    """Generator variant of cache_keyed_return — every (class, method) pair
    matching that approximate signal."""
    out = []
    for name, methods in view.methods_of.items():
        for m in methods:
            result = cache_keyed_return(view, name, m.fn_name)
            if result.matched:
                out.append(Candidate(binding=name, evidence=result.evidence,
                                      extra={"factory_method": m.fn_name}))
    return out


def mediator_candidates(view: SessionGraphView) -> List[Candidate]:
    """Mediator: 2+ classes ('colleagues') all call into a common hub class,
    and none of the colleagues call each other directly — fan_out_to_common_
    hub and no_direct_edges_between's shape, auto-discovering the hub and
    colleague group instead of requiring the spec to name them.
    """
    callers_of: dict = defaultdict(set)
    for name, methods in view.methods_of.items():
        for m in methods:
            for _callee, callee_class in m.calls:
                if callee_class and callee_class != name:
                    callers_of[callee_class].add(name)

    out = []
    for hub, colleagues in callers_of.items():
        if len(colleagues) < 2:
            continue
        result = no_direct_edges_between(view, list(colleagues))
        if result.matched:
            out.append(Candidate(
                binding=hub,
                evidence=[
                    f"{_loc(view, hub)} is called by {len(colleagues)} colleague(s) with no direct "
                    f"edges between them: {sorted(colleagues)}"
                ],
                extra={"colleagues": list(colleagues)},
            ))
    return out


# ── Phase 3: explicitly low-confidence patterns ──────────────────────────

def memento_candidates(view: SessionGraphView) -> List[Candidate]:
    """Memento: an Originator with a save()-role method that constructs a
    DIFFERENT class (the Memento snapshot) and also has a restore()-role
    method. Deliberately weak (tier: low in memento.yaml): there's no
    parameter-type data in this graph, so "has a restore-role method" is
    an existence check only — it can't verify that method actually takes
    a Memento instance as its argument, only that a plausibly-named method
    exists somewhere on the same class.
    """
    out = []
    for name, methods in view.methods_of.items():
        save_method = next(
            (m for m in methods if _ROLE_LOOKUP.get(m.fn_name.lower()) == "MEMENTO_SAVE"), None)
        if save_method is None:
            continue
        mementos = [p for p in save_method.instantiates if p != name]
        if not mementos:
            continue
        has_restore = any(_ROLE_LOOKUP.get(m.fn_name.lower()) == "MEMENTO_RESTORE" for m in methods)
        if not has_restore:
            continue
        out.append(Candidate(
            binding=name,
            evidence=[
                f"{_loc(view, name)}.{save_method.fn_name}() constructs {mementos[0]} (Memento), "
                f"and {name} also has a restore-role method — unverified whether it actually "
                f"takes a {mementos[0]} argument (no parameter-type data available)"
            ],
            extra={"memento_class": mementos[0], "save_method": save_method.fn_name},
        ))
    return out


def interpreter_candidates(view: SessionGraphView) -> List[Candidate]:
    """Interpreter: a class with a self-referential field whose
    interpret()-role method delegates to that field's own interpret()-role
    method — structurally identical to Composite (see composite.yaml)
    otherwise. Explicitly flagged ambiguity, not a bug: nothing in a pure
    composition-graph view distinguishes "AST node interpreting its
    children" from "composite node operating on its children" without
    grammar-specific data this engine doesn't have. The only differentiator
    available is that the delegating method must specifically be
    interpret()-role rather than an arbitrary name — expect overlap with
    Composite whenever a composite's own operation happens to be named
    interpret() too.
    """
    out = []
    for name in view.classes:
        self_types = view.self_referential_types(name)
        for e in view.fields_of.get(name, []):
            if e.target not in self_types:
                continue
            interpret_method = next(
                (m for m in view.methods_of.get(name, [])
                 if _ROLE_LOOKUP.get(m.fn_name.lower()) == "INTERPRETER_INTERPRET"), None)
            if interpret_method is None:
                continue
            delegates = any(
                callee in view.methods_named(e.target) and _ROLE_LOOKUP.get(callee.lower()) == "INTERPRETER_INTERPRET"
                for callee, _cc in interpret_method.calls
            )
            if delegates:
                out.append(Candidate(
                    binding=name,
                    evidence=[
                        f"{_loc(view, name)}.{interpret_method.fn_name}() delegates to "
                        f"'{e.field_name}: {e.target}'.{interpret_method.fn_name}() — "
                        f"Interpreter/Composite-ambiguous shape"
                    ],
                    extra={"field_name": e.field_name},
                ))
                break
    return out


# ── Structural replacements for the old naming-heuristic Singleton/
# Observer/Factory/Facade detectors (ArchitecturePatternDetector) — same
# vocabulary and evidence discipline as the rest of this library, no
# file/class/method naming keywords required. ─────────────────────────────

def singleton_candidates(view: SessionGraphView) -> List[Candidate]:
    """Singleton: a class holds a field of its own type (the private/static
    "instance" slot) AND has a method that constructs an instance of itself
    (the lazily-initializing accessor) — co-occurrence, not a verified
    assignment from the method into that field (same approximation
    delegates_to_field already documents elsewhere: the parser doesn't
    trace assignment targets that precisely). Doesn't require a private
    constructor or a null-check guard — neither is visible in this graph —
    so tier: medium in singleton.yaml, not high.
    """
    out = []
    for name, c in view.classes.items():
        self_types = view.self_referential_types(name)
        has_self_field = any(
            e.target in self_types and not e.is_collection
            for e in view.fields_of.get(name, [])
        )
        if not has_self_field:
            continue
        self_instantiating = next(
            (m for m in view.methods_of.get(name, []) if name in m.instantiates), None)
        if self_instantiating is None:
            continue
        out.append(Candidate(
            binding=name,
            evidence=[
                f"{_loc(view, name)} holds a field of its own type and "
                f"{self_instantiating.fn_name}() constructs a new {name} instance"
            ],
        ))
    return out


def factory_candidates(view: SessionGraphView) -> List[Candidate]:
    """Simple Factory: a class with 2+ methods, each constructing a
    DIFFERENT product class (not itself) — the class's role is
    manufacturing objects. Weaker than Factory Method (no abstract Creator/
    subclass-override requirement) or Abstract Factory (no shared-interface
    requirement across implementers) — this is the plain "factory class"
    shape the old create/build/make-naming heuristic approximated by
    keyword, needing no such naming at all.
    """
    out = []
    for name, methods in view.methods_of.items():
        products = {}
        for m in methods:
            targets = [p for p in m.instantiates if p != name]
            if targets:
                products[m.fn_name] = targets[0]
        if len(products) >= 2 and len(set(products.values())) >= 2:
            out.append(Candidate(
                binding=name,
                evidence=[f"{_loc(view, name)} has {len(products)} methods each constructing a distinct product: {products}"],
                extra={"products": products},
            ))
    return out


def facade_candidates(view: SessionGraphView) -> List[Candidate]:
    """Facade: a class that calls into 5+ distinct other classes, while
    itself being called by relatively few (<=40% of its own fan-out) — a
    simplified entry point in front of a larger subsystem. Direct class-
    level translation of the old detector's already-structural fan-out/
    fan-in candidate path (it also had a `facade`-named-file shortcut this
    version deliberately drops).
    """
    callees_of: dict = defaultdict(set)
    callers_of: dict = defaultdict(set)
    for name, methods in view.methods_of.items():
        for m in methods:
            for _callee_name, callee_class in m.calls:
                if callee_class and callee_class != name:
                    callees_of[name].add(callee_class)
                    callers_of[callee_class].add(name)

    out = []
    for name, callees in callees_of.items():
        callers = callers_of.get(name, set())
        if len(callees) >= 5 and len(callers) <= len(callees) * 0.4:
            out.append(Candidate(
                binding=name,
                evidence=[
                    f"{_loc(view, name)} calls {len(callees)} distinct classes "
                    f"({sorted(callees)}) while being called by only {len(callers)}"
                ],
                extra={"subsystem_classes": sorted(callees)},
            ))
    return out
