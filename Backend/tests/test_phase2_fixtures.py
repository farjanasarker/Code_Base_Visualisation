"""Phase 2 pattern verification: same harness as test_phase1_fixtures.py
(walk fixture dir -> analyze_files -> Neo4j -> rule engine). Skips
gracefully if Neo4j isn't reachable.
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
    sid = f"gof-phase2-{uuid.uuid4().hex[:8]}"
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


def test_factory_method_detected(session_id):
    matches = _detect_gof_patterns("factory_method_python", session_id)
    creators = {m.bindings["creator"] for m in matches if m.pattern == "Factory Method"}
    assert creators == {"Creator"}


def test_abstract_factory_detected(session_id):
    matches = _detect_gof_patterns("abstract_factory_python", session_id)
    factories = {m.bindings["factory"] for m in matches if m.pattern == "Abstract Factory"}
    assert factories == {"GUIFactory"}


def test_builder_detected(session_id):
    matches = _detect_gof_patterns("builder_python", session_id)
    builders = {m.bindings["builder"] for m in matches if m.pattern == "Builder"}
    assert builders == {"CarBuilder"}


def test_prototype_detected(session_id):
    matches = _detect_gof_patterns("prototype_python", session_id)
    prototypes = {m.bindings["prototype"] for m in matches if m.pattern == "Prototype"}
    assert prototypes == {"Shape"}


def test_command_detected(session_id):
    matches = _detect_gof_patterns("command_python", session_id)
    command_matches = [m for m in matches if m.pattern == "Command"]
    assert len(command_matches) == 1
    assert command_matches[0].bindings == {"command_interface": "Command"}


def test_adapter_detected(session_id):
    matches = _detect_gof_patterns("adapter_python", session_id)
    adapters = {m.bindings["adapter"] for m in matches if m.pattern == "Adapter"}
    assert adapters == {"Adapter"}


def test_bridge_detected(session_id):
    matches = _detect_gof_patterns("bridge_python", session_id)
    bridge_matches = [m for m in matches if m.pattern == "Bridge"]
    assert len(bridge_matches) == 1
    assert bridge_matches[0].bindings == {"implementor": "Implementor", "abstraction": "Abstraction"}
    assert bridge_matches[0].tier == "medium"

    # Bridge is a structural superset of Strategy's shape (same first 4
    # requirements + has_min_subclasses) — Strategy legitimately co-fires,
    # same documented situation as State in Phase 1.
    strategy_matches = [m for m in matches if m.pattern == "Strategy"]
    assert len(strategy_matches) == 1


def test_flyweight_detected_as_low_tier(session_id):
    matches = _detect_gof_patterns("flyweight_python", session_id)
    flyweight_matches = [m for m in matches if m.pattern == "Flyweight"]
    assert len(flyweight_matches) == 1
    assert flyweight_matches[0].bindings["factory"] == "TreeFactory"
    assert flyweight_matches[0].tier == "low"


def test_mediator_detected(session_id):
    matches = _detect_gof_patterns("mediator_python", session_id)
    hubs = {m.bindings["hub"] for m in matches if m.pattern == "Mediator"}
    assert hubs == {"Mediator"}
