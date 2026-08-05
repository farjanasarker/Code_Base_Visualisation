"""Phase 4 pattern verification: Singleton/Observer/Factory/Facade, now
detected structurally instead of via the old naming-heuristic detector
(ArchitecturePatternDetector.detect_singleton/_observer/_factory/_facade,
deleted from pattern_detector.py). Same harness as test_phase1/2_fixtures.py.
Skips gracefully if Neo4j isn't reachable.
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
    sid = f"gof-phase4-{uuid.uuid4().hex[:8]}"
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


def test_singleton_detected_structurally(session_id):
    matches = _detect_gof_patterns("singleton_python", session_id)
    singleton_matches = [m for m in matches if m.pattern == "Singleton"]
    assert len(singleton_matches) == 1
    assert singleton_matches[0].bindings["singleton_class"] == "Config"
    assert singleton_matches[0].tier == "medium"


def test_observer_detected_structurally(session_id):
    matches = _detect_gof_patterns("observer_python", session_id)
    observer_matches = [m for m in matches if m.pattern == "Observer"]
    assert len(observer_matches) == 1
    assert observer_matches[0].bindings == {"observer_interface": "Observer", "subject": "Subject"}
    assert observer_matches[0].tier == "high"

    # Strategy's own composition_field_of_type predicate doesn't filter by
    # cardinality, so it legitimately also matches here (a field of type
    # Observer, regardless of it being a list) — same documented overlap
    # as State/Bridge co-firing with Strategy elsewhere in this suite, not
    # a bug to suppress.
    strategy_matches = [m for m in matches if m.pattern == "Strategy"]
    assert len(strategy_matches) == 1
    assert strategy_matches[0].bindings == {"strategy_interface": "Observer", "context": "Subject"}


def test_factory_simple_detected_structurally(session_id):
    matches = _detect_gof_patterns("factory_simple_python", session_id)
    factory_matches = [m for m in matches if m.pattern == "Factory"]
    assert len(factory_matches) == 1
    assert factory_matches[0].bindings["factory_class"] == "VehicleFactory"
    assert factory_matches[0].tier == "medium"

    # Car/Truck are plain data classes with no constructing methods of
    # their own — must not false-positive as factories themselves.
    assert not any(m.bindings.get("factory_class") in ("Car", "Truck") for m in factory_matches)


def test_facade_detected_structurally(session_id):
    matches = _detect_gof_patterns("facade_python", session_id)
    facade_matches = [m for m in matches if m.pattern == "Facade"]
    assert len(facade_matches) == 1
    assert facade_matches[0].bindings["facade_class"] == "ComputerFacade"
    assert facade_matches[0].tier == "medium"

    # CPU/Memory/HardDrive/Monitor/Keyboard call nothing themselves — must
    # not false-positive as facades.
    subsystem = {"CPU", "Memory", "HardDrive", "Monitor", "Keyboard"}
    assert not any(m.bindings.get("facade_class") in subsystem for m in facade_matches)
