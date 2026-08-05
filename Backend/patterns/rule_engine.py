"""Declarative rule-spec engine — loads YAML rule specs (see specs/*.yaml)
and evaluates them against a SessionGraphView, using the predicate library
as its only vocabulary. Adding pattern #N is writing a spec file, not new
Python detection logic, for every pattern whose shape the predicate library
already covers.

Binding model: a rule spec's `requires` list is processed as an ordered
chain. A requirement whose predicate is a *generator* (returns a list of
`Candidate` bindings — currently `interface_with_single_method` and
`composition_field_of_type`) introduces a new named role via its `role:`
key; the engine tries every candidate for that role — a small backtracking
search — before evaluating later requirements. A requirement whose
predicate is a *checker* (returns one `PredicateResult`) validates
already-bound roles; the moment a checker fails for the current binding
combination, that search branch is dropped (yields no match).

Role-reference resolution: a requirement param value that names an
already-bound role resolves to that role's bound class/interface name —
*except* the `field` param, which resolves to the field name recorded on
that *same requirement's* `class` role's binding (the field name
`composition_field_of_type` discovered when it bound that role), since a
rule spec's `field: <role>` means "the field on `class` that is typed as
<role>", not <role>'s own name. This is a small, specific convention rather
than a fully generic constraint solver, because Strategy is the only Phase
0 pattern that needs multi-role chaining at all; revisit if a later pattern
needs a different shape.

All requirements in Phase 0's schema are mandatory (no optional/soft
signals yet), so a successful match's confidence is always the sum of every
matched requirement's weight — `confidence_weights` becomes meaningful once
a future pattern spec allows a requirement to be optional.
"""

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, Iterator, List

import yaml

from . import predicates as P
from .graph_view import SessionGraphView

_SPECS_DIR = Path(__file__).parent / "specs"

# predicate name -> (view, **resolved_params) -> List[Candidate]
GENERATORS = {
    "interface_with_single_method": lambda view, **kw: P.interface_with_single_method(view),
    "composition_field_of_type": lambda view, **kw: P.composition_field_of_type(view, kw["type"]),
    "every_class": lambda view, **kw: P.every_class(view),
    "list_of_own_type_field_candidates": lambda view, **kw: P.list_of_own_type_field_candidates(view),
    "single_field_of_own_type_candidates": lambda view, **kw: P.single_field_of_own_type_candidates(view),
    "double_dispatch_candidates": lambda view, **kw: P.double_dispatch_candidates(view),
    "factory_method_candidates": lambda view, **kw: P.factory_method_candidates(view),
    "abstract_factory_candidates": lambda view, **kw: P.abstract_factory_candidates(view),
    "builder_candidates": lambda view, **kw: P.builder_candidates(view),
    "prototype_candidates": lambda view, **kw: P.prototype_candidates(view),
    "interface_with_single_role_method": lambda view, **kw: P.interface_with_single_role_method(
        view, kw["role_name"]),
    "adapter_candidates": lambda view, **kw: P.adapter_candidates(view),
    "flyweight_candidates": lambda view, **kw: P.flyweight_candidates(view),
    "mediator_candidates": lambda view, **kw: P.mediator_candidates(view),
    "memento_candidates": lambda view, **kw: P.memento_candidates(view),
    "interpreter_candidates": lambda view, **kw: P.interpreter_candidates(view),
    "collection_composition_field_of_type": lambda view, **kw: P.collection_composition_field_of_type(
        view, kw["type"]),
    "singleton_candidates": lambda view, **kw: P.singleton_candidates(view),
    "factory_candidates": lambda view, **kw: P.factory_candidates(view),
    "facade_candidates": lambda view, **kw: P.facade_candidates(view),
}

# predicate name -> (view, **resolved_params) -> PredicateResult
CHECKERS = {
    "min_implementers": lambda view, **kw: P.min_implementers(view, kw["of"], kw["count"]),
    "any_implementer_has_field_of_type": lambda view, **kw: P.any_implementer_has_field_of_type(
        view, kw["of"], kw["type"]),
    "delegates_to_field": lambda view, **kw: P.delegates_to_field(view, kw["class"], kw["field"]),
    "has_self_referential_field": lambda view, **kw: P.has_self_referential_field(view, kw["class"]),
    "has_list_of_own_type_field": lambda view, **kw: P.has_list_of_own_type_field(view, kw["class"]),
    "has_single_field_of_own_type": lambda view, **kw: P.has_single_field_of_own_type(view, kw["class"]),
    "wraps_and_extends": lambda view, **kw: P.wraps_and_extends(view, kw["class"], kw["field"]),
    "field_typed_as_own_interface": lambda view, **kw: P.field_typed_as_own_interface(
        view, kw["class"], kw["field"]),
    "is_decorator_wrapping": lambda view, **kw: P.is_decorator_wrapping(view, kw["class"], kw["field"]),
    "is_proxy_wrapping": lambda view, **kw: P.is_proxy_wrapping(view, kw["class"], kw["field"]),
    "fluent_return_self": lambda view, **kw: P.fluent_return_self(view, kw["class"], kw["method"]),
    "abstract_method_called_from_concrete_sibling_method":
        lambda view, **kw: P.abstract_method_called_from_concrete_sibling_method(view, kw["class"]),
    "double_dispatch_pair": lambda view, **kw: P.double_dispatch_pair(
        view, kw["class_a"], kw["method_x"], kw["class_b"], kw["method_y"]),
    "fan_out_to_common_hub": lambda view, **kw: P.fan_out_to_common_hub(view, kw["classes"]),
    "no_direct_edges_between": lambda view, **kw: P.no_direct_edges_between(view, kw["classes"]),
    "cache_keyed_return": lambda view, **kw: P.cache_keyed_return(view, kw["class"], kw["method"]),
    "implements_or_inherits": lambda view, **kw: P.implements_or_inherits(view, kw["class"], kw["type"]),
    "has_role_method": lambda view, **kw: P.has_role_method(view, kw["class"], kw["role_name"]),
    "has_min_subclasses": lambda view, **kw: P.has_min_subclasses(view, kw["class"], kw["count"]),
}



@dataclass
class RuleSpec:
    pattern: str
    tier: str
    requires: List[dict]
    confidence_weights: Dict[str, float]
    min_confidence_to_report: float


@dataclass
class RuleMatch:
    pattern: str
    tier: str
    confidence: float
    bindings: Dict[str, str]
    evidence: List[str] = dc_field(default_factory=list)


def load_spec(path: Path) -> RuleSpec:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RuleSpec(
        pattern=data["pattern"],
        tier=data["tier"],
        requires=data["requires"],
        confidence_weights=data.get("confidence_weights", {}),
        min_confidence_to_report=data.get("min_confidence_to_report", 0.0),
    )


def load_all_specs(specs_dir: Path = _SPECS_DIR) -> List[RuleSpec]:
    return [load_spec(p) for p in sorted(specs_dir.glob("*.yaml"))]


def _resolve_params(raw_params: dict, context: dict) -> dict:
    resolved = {}
    for key, value in raw_params.items():
        # `field: <role>` means "the field on this requirement's `class`
        # role that is typed as <role>" — the field NAME was recorded on the
        # `class` role's own binding extra when its generator discovered it
        # (composition_field_of_type), not on <role>'s (the type's) extra.
        if key == "field" and isinstance(value, str) and value in context:
            owner_role = raw_params.get("class")
            owner_binding = context.get(owner_role) if isinstance(owner_role, str) else None
            if owner_binding and "field_name" in owner_binding["extra"]:
                resolved[key] = owner_binding["extra"]["field_name"]
                continue

        if isinstance(value, str) and value in context:
            resolved[key] = context[value]["binding"]
        else:
            resolved[key] = value
    return resolved


def _search(
    view: SessionGraphView, requirements: List[dict], idx: int,
    context: Dict[str, dict], evidence_acc: List[str],
) -> Iterator[tuple]:
    if idx == len(requirements):
        yield dict(context), list(evidence_acc)
        return

    req = requirements[idx]
    pred_name = req["predicate"]
    role = req.get("role")
    raw_params = {k: v for k, v in req.items() if k not in ("predicate", "role")}
    resolved_params = _resolve_params(raw_params, context)

    if pred_name in GENERATORS:
        for cand in GENERATORS[pred_name](view, **resolved_params):
            new_context = dict(context)
            if role:
                new_context[role] = {"binding": cand.binding, "extra": cand.extra}
            yield from _search(view, requirements, idx + 1, new_context, evidence_acc + cand.evidence)
    elif pred_name in CHECKERS:
        result = CHECKERS[pred_name](view, **resolved_params)
        if result.matched:
            yield from _search(view, requirements, idx + 1, context, evidence_acc + result.evidence)
        # else: this branch is dropped — no match, no partial credit (Phase 0
        # has no optional requirements, so a failed checker kills the branch).
    else:
        raise ValueError(f"Unknown predicate '{pred_name}' — not registered in GENERATORS or CHECKERS")


def evaluate_spec(view: SessionGraphView, spec: RuleSpec) -> List[RuleMatch]:
    matches = []
    for context, evidence in _search(view, spec.requires, 0, {}, []):
        confidence = round(min(sum(spec.confidence_weights.values()), 1.0), 2)
        if confidence < spec.min_confidence_to_report:
            continue
        bindings = {role: b["binding"] for role, b in context.items()}
        matches.append(RuleMatch(
            pattern=spec.pattern, tier=spec.tier, confidence=confidence,
            bindings=bindings, evidence=evidence,
        ))
    return matches


def evaluate_all(view: SessionGraphView, specs: List[RuleSpec] = None) -> List[RuleMatch]:
    """Evaluate every loaded rule spec against one SessionGraphView built
    once for the session (see graph_view.py) — all specs share the same
    view, so adding pattern specs doesn't re-traverse the graph per pattern.
    """
    if specs is None:
        specs = load_all_specs()
    results = []
    for spec in specs:
        results.extend(evaluate_spec(view, spec))
    return sorted(results, key=lambda m: m.confidence, reverse=True)
