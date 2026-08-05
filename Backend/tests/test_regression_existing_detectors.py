"""Golden-snapshot regression test for the existing 9 architecture detectors.

This is the mandatory gate for the GoF Phase 0 migration: every step that touches
shared infrastructure (parser, pipeline, Neo4j schema/ingestion) must leave this
test's output unchanged, since `ArchitecturePatternDetector.detect_all()` silently
swallows exceptions per-detector and would otherwise mask breakage.

Deliberately does not import `main.py` (FastAPI app / Neo4j driver) — it drives the
same parsing path (`walk_folder` -> `analyze_files` -> session_data ->
`ArchitecturePatternDetector`) directly against on-disk fixtures, so it has no
network/DB dependency and runs anywhere.
"""

import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from analyzer.pipeline import analyze_files  # noqa: E402
from analyzer.tree_sitter_runtime import SUPPORTED_EXTENSIONS  # noqa: E402
from pattern_detector import ArchitecturePatternDetector  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_PATH = Path(__file__).parent / "golden" / "legacy_mixed_patterns.json"


def load_fixture_files(root: Path) -> list[dict]:
    """Minimal, dependency-free re-implementation of main.py's walk_folder()."""
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
                "size": len(content),
                "content": content,
            })
    return files


def detect_patterns_for_fixture(fixture_name: str) -> list[dict]:
    """Mirrors GET /api/patterns/{session_id} (main.py:1781-1839) end to end,
    without the FastAPI/SESSION_CACHE layer.
    """
    all_files = load_fixture_files(FIXTURES_DIR / fixture_name)
    functions, _classes, _unused_imports, _layer_violations = analyze_files(all_files)

    files = [f["path"] for f in all_files]
    fn_name_to_file = {fn["name"]: fn.get("file", "") for fn in functions}
    call_edges = []
    for fn in functions:
        for callee_name in fn.get("calls", []):
            call_edges.append({
                "caller_file": fn.get("file", ""),
                "caller_function": fn.get("name", ""),
                "callee_function": callee_name,
                "callee_file": fn_name_to_file.get(callee_name, ""),
            })

    session_data = {"files": files, "functions": functions, "call_edges": call_edges}
    detector = ArchitecturePatternDetector(session_data)
    return detector.detect_all()


def test_legacy_mixed_fixture_triggers_all_architecture_detectors():
    """Sanity check on the fixture itself: every remaining architecture
    detector should fire. Singleton/Observer/Factory/Facade were deliberately
    removed from detect_all() (GoF patterns, not architecture patterns —
    relocated to /api/gof-patterns instead, see main.py's endpoint docstring
    and test_gof_endpoint.py's test_legacy_gof_patterns_moved_out_of_architecture_panel).
    """
    patterns = detect_patterns_for_fixture("legacy_mixed")
    found = {p["pattern"] for p in patterns}
    expected = {
        "MVC", "Layered/N-Tier", "Clean Architecture", "Hexagonal Architecture",
        "Repository Pattern",
    }
    missing = expected - found
    assert not missing, f"Fixture no longer triggers: {missing} (got {found})"
    assert not found & {"Singleton", "Observer", "Factory", "Facade"}, (
        "these were deliberately moved out of ArchitecturePatternDetector.detect_all()"
    )


def test_legacy_mixed_matches_golden_snapshot():
    """The mandatory regression gate: output must match the pre-migration golden
    snapshot exactly (pattern names + confidence). If this fails during the GoF
    migration, a shared-infrastructure change broke an existing detector — stop
    and investigate before proceeding, don't just regenerate the golden file.
    """
    patterns = detect_patterns_for_fixture("legacy_mixed")
    actual = sorted(
        [{"pattern": p["pattern"], "confidence": p["confidence"]} for p in patterns],
        key=lambda p: p["pattern"],
    )

    if not GOLDEN_PATH.exists():
        pytest.skip(
            f"No golden snapshot yet at {GOLDEN_PATH} — run "
            f"`python -m tests.test_regression_existing_detectors --write-golden` "
            f"once to establish the baseline before making any migration changes."
        )

    expected = json.loads(GOLDEN_PATH.read_text())
    assert actual == expected, (
        "Existing-detector output changed! This must be a false alarm from a "
        "deliberate, reviewed change to pattern_detector.py itself (untouched by "
        "this migration) — otherwise a shared parser/pipeline/Neo4j change broke "
        "one of the 9 existing detectors."
    )


if __name__ == "__main__":
    # One-time baseline capture: `python -m tests.test_regression_existing_detectors`
    result = detect_patterns_for_fixture("legacy_mixed")
    snapshot = sorted(
        [{"pattern": p["pattern"], "confidence": p["confidence"]} for p in result],
        key=lambda p: p["pattern"],
    )
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Wrote golden snapshot ({len(snapshot)} patterns) to {GOLDEN_PATH}")
    for p in snapshot:
        print(f"  {p['pattern']}: {p['confidence']}")
