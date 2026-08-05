"""Phase 0 deliverable verification: run the full pipeline (walk fixture dir
-> analyze_files -> Neo4j -> rule engine) against a real on-disk Strategy
instance in each of the 6 target languages, plus one negative/near-miss
case, per the plan's Step 6 ("verify against known test projects, confirm
Strategy fires on the planted positive fixtures and not on the negative
ones"). Skips gracefully if Neo4j isn't reachable, same as the other
Neo4j-backed tests.

JS is a deliberate, documented EXPECTED NON-MATCH — see
fixtures/strategy_js/payment.js's header comment: plain JavaScript has no
type annotations anywhere, so composition_field_of_type has no field-type
signal to work with at all. This isn't a bug; it's recorded here as a
structural finding for the Phase 0 report.
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
    sid = f"gof-phase0-strategy-fixtures-{uuid.uuid4().hex[:8]}"
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


@pytest.mark.parametrize("fixture_name", [
    "strategy_python", "strategy_ts", "strategy_java", "strategy_go", "strategy_rust",
])
def test_strategy_detected_in_typed_languages(fixture_name, session_id):
    matches = _detect_gof_patterns(fixture_name, session_id)
    strategy_matches = [m for m in matches if m.pattern == "Strategy"]
    assert len(strategy_matches) == 1, (
        f"expected exactly one Strategy match in {fixture_name}, got {len(strategy_matches)}: "
        f"{[m.bindings for m in strategy_matches]}"
    )
    assert strategy_matches[0].bindings["strategy_interface"] == "PaymentStrategy"
    assert strategy_matches[0].bindings["context"] == "Checkout"
    assert strategy_matches[0].confidence >= 0.6


def test_strategy_not_detected_in_untyped_javascript(session_id):
    """Documented Phase 0 finding: composition-based patterns are
    structurally undetectable in plain JS without a type source.
    """
    matches = _detect_gof_patterns("strategy_js", session_id)
    assert not [m for m in matches if m.pattern == "Strategy"]


def test_strategy_not_detected_with_single_implementer(session_id):
    matches = _detect_gof_patterns("strategy_negative_single_implementer", session_id)
    assert not [m for m in matches if m.pattern == "Strategy"]
