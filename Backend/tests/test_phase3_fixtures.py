"""Phase 3 pattern verification: same harness as test_phase2_fixtures.py.
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
    sid = f"gof-phase3-{uuid.uuid4().hex[:8]}"
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


def test_memento_detected_as_low_tier(session_id):
    matches = _detect_gof_patterns("memento_python", session_id)
    memento_matches = [m for m in matches if m.pattern == "Memento"]
    assert len(memento_matches) == 1
    assert memento_matches[0].bindings["originator"] == "Editor"
    assert memento_matches[0].tier == "low"


def test_interpreter_overlaps_composite_by_design(session_id):
    """Documents the acknowledged ambiguity from interpreter.yaml: an AST
    node interpreting its children is structurally identical to a
    composite node operating on its children without grammar-specific
    data. Both patterns are expected to co-fire, not a bug to suppress.
    """
    matches = _detect_gof_patterns("interpreter_python", session_id)

    interpreter_matches = [m for m in matches if m.pattern == "Interpreter"]
    assert len(interpreter_matches) == 1
    assert interpreter_matches[0].bindings["expression"] == "Add"
    assert interpreter_matches[0].tier == "low"

    composite_matches = [m for m in matches if m.pattern == "Composite"]
    assert len(composite_matches) == 1
    assert composite_matches[0].bindings["component"] == "Add"
