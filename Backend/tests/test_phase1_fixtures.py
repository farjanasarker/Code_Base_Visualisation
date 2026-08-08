"""Phase 1 pattern verification: same harness as test_strategy_fixtures.py
(walk fixture dir -> analyze_files -> Neo4j -> rule engine), one function
per pattern added this phase. Skips gracefully if Neo4j isn't reachable.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402
from analyzer.pipeline import analyze_files  # noqa: E402
from analyzer.tree_sitter_runtime import SUPPORTED_EXTENSIONS  # noqa: E402
from patterns.graph_view import SessionGraphView  # noqa: E402
from patterns.rule_engine import evaluate_all  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _neo4j_available() -> bool:
    try:
        db.driver.verify_connectivity()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _neo4j_available(), reason="Neo4j instance not reachable")


def _load_fixture_files(root: Path) -> list[dict]:
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            filepath = Path(dirpath) / filename
            ext = filepath.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            files.append({
                "path": filepath.relative_to(root).as_posix(),
                "language": SUPPORTED_EXTENSIONS[ext],
                "content": content,
            })
    return files


def _detect_gof_patterns(fixture_name: str, session_id: str) -> list:
    all_files = _load_fixture_files(FIXTURES_DIR / fixture_name)
    functions, classes, _unused, _layer = analyze_files(all_files)
    db.store_all(functions, session_id, all_files)
    db.store_class_graph(classes, functions, session_id)
    raw = db.get_class_graph(session_id)
    view = SessionGraphView.from_raw(raw)
    return evaluate_all(view)


@pytest.fixture
def session_id():
    sid = f"gof-phase1-{uuid.uuid4().hex[:8]}"
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


def test_template_method_detected(session_id):
    matches = _detect_gof_patterns("template_method_python", session_id)
    tm_matches = [m for m in matches if m.pattern == "Template Method"]
    bindings = {m.bindings["template_class"] for m in tm_matches}
    assert "CaffeineBeverage" in bindings
    # Tea/Coffee just override brew() with no cross-method call of their own
    # abstract methods (they don't declare any) — must not false-positive.
    assert "Tea" not in bindings
    assert "Coffee" not in bindings


def test_template_method_detected_java(session_id):
    """Regression test: Java's `method_declaration` node is the SAME AST
    node type for both a concrete method and a bodyless abstract method
    (`abstract void step();`) — unlike Python's @abstractmethod (a real,
    flagged body) or TS/Rust's bodyless forms (distinct node types that
    never reach the parser's function-extraction path at all). Without
    is_abstract being computed from body presence, an abstract Java method
    got parsed as an ordinary concrete one, so abstract_method_called_
    from_concrete_sibling_method could never find any abstract methods on
    a Java Template Method class — this is THE textbook Java shape
    (`abstract class Game { abstract void initialize(); ... void play() {
    initialize(); ... } }`) and it went completely undetected before the
    fix in analyzer/parser.py's _extract_functions.
    """
    matches = _detect_gof_patterns("template_method_java", session_id)
    tm_matches = [m for m in matches if m.pattern == "Template Method"]
    bindings = {m.bindings["template_class"] for m in tm_matches}
    assert "Game" in bindings
    # Football just overrides the abstract steps with no cross-method call
    # of its own — must not false-positive.
    assert "Football" not in bindings


def test_template_method_detected_typescript(session_id):
    """Regression test: TS's abstract-class abstract method (`abstract
    initialize(): void;`) is node type `abstract_method_signature` — a
    different node type from both interface members (`method_signature`)
    and concrete class methods (`method_definition`), and easy to miss
    since all three print identically as bodyless-looking signatures.
    Without it in _METHOD_NODE_TYPES, an abstract class's abstract methods
    vanished from ClassInfo.method_names entirely, so
    abstract_method_called_from_concrete_sibling_method had no abstract
    method to find at all.
    """
    matches = _detect_gof_patterns("template_method_ts", session_id)
    tm_matches = [m for m in matches if m.pattern == "Template Method"]
    bindings = {m.bindings["template_class"] for m in tm_matches}
    assert "Game" in bindings
    assert "Football" not in bindings


def test_state_detected_via_bidirectional_edge(session_id):
    matches = _detect_gof_patterns("state_ts", session_id)
    state_matches = [m for m in matches if m.pattern == "State"]
    assert len(state_matches) == 1
    assert state_matches[0].bindings == {"state_interface": "State", "context": "TrafficLight"}

    # State's shape is a structural superset of Strategy's (interface + 2+
    # implementers + composition + delegation, minus the bidirectional
    # edge) — Strategy legitimately also fires on the same classes, since
    # nothing in Strategy's own spec excludes it. Documented, not a bug.
    strategy_matches = [m for m in matches if m.pattern == "Strategy"]
    assert len(strategy_matches) == 1


def test_strategy_fixture_does_not_false_positive_as_state(session_id):
    """False-positive discipline: Strategy's implementers hold no
    back-reference to their context, so State's extra requirement must
    reject it even though the first four requirements are identical.
    """
    matches = _detect_gof_patterns("strategy_ts", session_id)
    assert not [m for m in matches if m.pattern == "State"]


def test_composite_detected(session_id):
    matches = _detect_gof_patterns("composite_python", session_id)
    composite_matches = [m for m in matches if m.pattern == "Composite"]
    assert len(composite_matches) == 1
    assert composite_matches[0].bindings["component"] == "CompoundGraphic"

    # Dot is a leaf with no self-typed field at all — must not false-positive.
    assert not any(m.bindings.get("component") == "Dot" for m in composite_matches)


def test_decorator_vs_proxy_classification(session_id):
    matches = _detect_gof_patterns("decorator_proxy_python", session_id)

    decorator_wrappers = {m.bindings["wrapper"] for m in matches if m.pattern == "Decorator"}
    proxy_wrappers = {m.bindings["wrapper"] for m in matches if m.pattern == "Proxy"}

    assert decorator_wrappers == {"MilkDecorator"}
    assert proxy_wrappers == {"LoggingProxy"}
    # Each must fire as exactly one classification, not both.
    assert "LoggingProxy" not in decorator_wrappers
    assert "MilkDecorator" not in proxy_wrappers
    # SimpleCoffee has no self-typed field at all — must not false-positive.
    assert "SimpleCoffee" not in decorator_wrappers | proxy_wrappers


def test_decorator_detected_with_field_on_abstract_base_java(session_id):
    """Regression test for two compounding bugs that together made GoF's
    OWN textbook Decorator shape (not just a hypothetical) undetectable:

    1. decorator_proxy_python's fixture (above) declares the wrapped field
       directly on each concrete decorator — but the canonical shape
       declares it ONCE on an abstract base class instead (`abstract class
       BeverageDecorator implements Beverage { protected Beverage
       beverage; }`), with concrete decorators (MilkDecorator,
       SugarDecorator) only extending that base and inheriting the field.
       Every field-lookup predicate used to check only a class's own
       directly-declared fields, so the concrete decorators — which have
       the delegating cost() method but not the field itself — were never
       even considered as candidates. Fixed via
       SessionGraphView.effective_fields_of/effective_field walking the
       (now transitive) interfaces_of ancestor chain.
    2. Once the field was found, cost() calling beverage.cost() (same
       method name as the enclosing method — the single most common
       Decorator/Proxy delegation shape there is) was being silently
       dropped by analyzer/parser.py's _extract_calls, which excluded any
       call whose bare name matched the enclosing function's own name on
       a mistaken self-recursion assumption. Fixed by removing that
       filter — class-aware resolution downstream is the right layer to
       disambiguate same-name calls, not a bare string-equality guard
       with no receiver context.
    """
    matches = _detect_gof_patterns("decorator_java", session_id)
    decorator_wrappers = {m.bindings["wrapper"] for m in matches if m.pattern == "Decorator"}
    assert decorator_wrappers == {"MilkDecorator", "SugarDecorator"}
    # BeverageDecorator holds the field but has no cost() override of its
    # own (abstract) — must not itself false-positive as the wrapper.
    assert "BeverageDecorator" not in decorator_wrappers


def test_chain_of_responsibility_overlaps_proxy_by_design(session_id):
    """Documents the acknowledged ambiguity from chain_of_responsibility.yaml:
    a conditional "handle or forward" chain is structurally identical to a
    near-passthrough Proxy wrap once you're only looking at the composition
    graph (no control-flow data) — both patterns are expected to co-fire on
    the same classes here, not a bug to suppress.
    """
    matches = _detect_gof_patterns("chain_of_responsibility_python", session_id)

    chain_handlers = {m.bindings["handler"] for m in matches if m.pattern == "Chain of Responsibility"}
    assert chain_handlers == {"Manager", "Director"}

    chain_match = next(m for m in matches if m.pattern == "Chain of Responsibility")
    assert chain_match.tier == "medium"

    proxy_wrappers = {m.bindings["wrapper"] for m in matches if m.pattern == "Proxy"}
    assert proxy_wrappers == {"Manager", "Director"}


def test_iterator_detected_via_next_and_hasnext_pairing(session_id):
    matches = _detect_gof_patterns("iterator_java", session_id)
    iterator_classes = {m.bindings["iterator_class"] for m in matches if m.pattern == "Iterator"}
    assert "BookIterator" in iterator_classes
    # BookCollection only has createIterator() — neither next- nor hasNext-
    # role method — must not false-positive.
    assert "BookCollection" not in iterator_classes


def test_visitor_detected_via_double_dispatch(session_id):
    matches = _detect_gof_patterns("visitor_python", session_id)
    elements = {m.bindings["element"] for m in matches if m.pattern == "Visitor"}
    assert elements == {"Circle", "Square"}
    # ShapeVisitor itself never calls back into anything that calls back
    # into it — it's the callee side of the pair, not a candidate "element".
    assert "ShapeVisitor" not in elements
