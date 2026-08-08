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

All requirements are mandatory (no optional requirements — a failed checker
still kills the branch outright, no partial credit for skipping one). What
*is* graded is evidence quality within a passed requirement: a checker's
`PredicateResult.strength` (see predicates.py) multiplies that
requirement's `confidence_weights` entry — 1.0 for an ordinary pass, lower
when a predicate matched on weaker evidence than its strongest case (e.g.
delegates_to_field's name-only fallback), higher when it cleared its bar
with room to spare (e.g. min_implementers matching well past its threshold).
The summed, weighted confidence is still capped at 1.0.
"""

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, Iterator, List

import yaml

from . import predicates as P
from .graph_view import SessionGraphView

_SPECS_DIR = Path(__file__).parent / "specs"

# Human-readable label for each predicate — surfaced per-requirement in
# RuleMatch.evidence_detail so the UI can show *which structural check* each
# bundle of evidence proves, not just a flat, unlabeled evidence dump.
PREDICATE_LABELS: Dict[str, str] = {
    # generators
    "interface_with_single_method": "Interface shape",
    "composition_field_of_type": "Composition",
    "every_class": "Candidate class",
    "list_of_own_type_field_candidates": "Self-referential list field",
    "single_field_of_own_type_candidates": "Self-referential field",
    "double_dispatch_candidates": "Double-dispatch pair",
    "factory_method_candidates": "Factory Method shape",
    "abstract_factory_candidates": "Abstract Factory shape",
    "builder_candidates": "Builder shape",
    "prototype_candidates": "Prototype shape",
    "interface_with_single_role_method": "Role-method interface",
    "adapter_candidates": "Adapter shape",
    "flyweight_candidates": "Flyweight shape",
    "mediator_candidates": "Mediator shape",
    "memento_candidates": "Memento shape",
    "interpreter_candidates": "Interpreter shape",
    "collection_composition_field_of_type": "Collection composition",
    "singleton_candidates": "Singleton shape",
    "factory_candidates": "Factory shape",
    "facade_candidates": "Facade shape",
    # checkers
    "min_implementers": "Implementer count",
    "any_implementer_has_field_of_type": "Bidirectional context link",
    "delegates_to_field": "Delegation",
    "has_self_referential_field": "Self-referential field",
    "has_list_of_own_type_field": "Self-referential list field",
    "has_single_field_of_own_type": "Self-referential single field",
    "wraps_and_extends": "Wrap-and-extend behavior",
    "field_typed_as_own_interface": "Shared-interface field",
    "is_decorator_wrapping": "Decorator classification",
    "is_proxy_wrapping": "Proxy classification",
    "fluent_return_self": "Fluent return",
    "abstract_method_called_from_concrete_sibling_method": "Template call",
    "double_dispatch_pair": "Double dispatch",
    "fan_out_to_common_hub": "Common hub fan-out",
    "no_direct_edges_between": "No direct peer calls",
    "cache_keyed_return": "Cached construction",
    "implements_or_inherits": "Type relationship",
    "has_role_method": "Role method",
    "has_min_subclasses": "Subclass count",
}

# GoF's own three-way grouping, keyed by each spec's `pattern:` value —
# purely presentational (which section of the catalog this belongs to),
# doesn't affect detection at all.
PATTERN_CATEGORIES: Dict[str, str] = {
    "Factory Method": "Creational", "Abstract Factory": "Creational",
    "Builder": "Creational", "Prototype": "Creational", "Singleton": "Creational",
    "Factory": "Creational",
    "Adapter": "Structural", "Bridge": "Structural", "Composite": "Structural",
    "Decorator": "Structural", "Facade": "Structural", "Flyweight": "Structural",
    "Proxy": "Structural",
    "Chain of Responsibility": "Behavioral", "Command": "Behavioral",
    "Interpreter": "Behavioral", "Iterator": "Behavioral", "Mediator": "Behavioral",
    "Memento": "Behavioral", "Observer": "Behavioral", "State": "Behavioral",
    "Strategy": "Behavioral", "Template Method": "Behavioral", "Visitor": "Behavioral",
}

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
    "facade_candidates": lambda view, **kw: P.facade_candidates(
        view, min_fan_out=kw.get("min_fan_out", 5), max_caller_ratio=kw.get("max_caller_ratio", 0.4)),
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
    # Purely presentational, derived from `pattern` via PATTERN_CATEGORIES —
    # "Creational"/"Structural"/"Behavioral", GoF's own grouping.
    category: str = "Uncategorized"
    # Same evidence as `evidence`, but grouped per requirement instead of
    # flattened — each entry is one requirement's contribution: which
    # structural check it was (`label`/`predicate`), how strong the match
    # was (`strength` — see predicates.PredicateResult), and the raw
    # evidence line(s) that check produced. `evidence` stays flat for
    # existing consumers; this is the answer to "why did this match, per
    # requirement" rather than "why did this match, as one undifferentiated
    # blob".
    evidence_detail: List[dict] = dc_field(default_factory=list)


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
    context: Dict[str, dict], evidence_acc: List[str], strengths_acc: Dict[str, float],
    detail_acc: List[dict],
) -> Iterator[tuple]:
    if idx == len(requirements):
        yield dict(context), list(evidence_acc), dict(strengths_acc), list(detail_acc)
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
            detail_entry = {
                "predicate": pred_name,
                "label": PREDICATE_LABELS.get(pred_name, pred_name),
                "role": role,
                "strength": 1.0,
                "evidence": list(cand.evidence),
            }
            yield from _search(
                view, requirements, idx + 1, new_context,
                evidence_acc + cand.evidence, strengths_acc, detail_acc + [detail_entry])
    elif pred_name in CHECKERS:
        result = CHECKERS[pred_name](view, **resolved_params)
        if result.matched:
            # A predicate used more than once in one spec (e.g. iterator.yaml's
            # two has_role_method requirements sharing one confidence_weights
            # key) combines conservatively via min() — the weakest of its
            # occurrences sets the shared weight's multiplier.
            new_strengths = dict(strengths_acc)
            prior = new_strengths.get(pred_name)
            new_strengths[pred_name] = result.strength if prior is None else min(prior, result.strength)
            detail_entry = {
                "predicate": pred_name,
                "label": PREDICATE_LABELS.get(pred_name, pred_name),
                "role": None,
                "strength": result.strength,
                "evidence": list(result.evidence),
            }
            yield from _search(
                view, requirements, idx + 1, context,
                evidence_acc + result.evidence, new_strengths, detail_acc + [detail_entry])
        # else: this branch is dropped — no match, no partial credit (every
        # requirement is mandatory; a failed checker kills the branch).
    else:
        raise ValueError(f"Unknown predicate '{pred_name}' — not registered in GENERATORS or CHECKERS")


def evaluate_spec(view: SessionGraphView, spec: RuleSpec) -> List[RuleMatch]:
    matches = []
    category = PATTERN_CATEGORIES.get(spec.pattern, "Uncategorized")
    for context, evidence, strengths, detail in _search(view, spec.requires, 0, {}, [], {}, []):
        weighted = sum(
            weight * strengths.get(pred_name, 1.0)
            for pred_name, weight in spec.confidence_weights.items()
        )
        confidence = round(min(weighted, 1.0), 2)
        if confidence < spec.min_confidence_to_report:
            continue
        bindings = {role: b["binding"] for role, b in context.items()}
        matches.append(RuleMatch(
            pattern=spec.pattern, tier=spec.tier, confidence=confidence,
            bindings=bindings, evidence=evidence, category=category, evidence_detail=detail,
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
