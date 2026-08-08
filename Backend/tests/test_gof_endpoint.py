"""Integration test for GET /api/gof-patterns/{session_id} through the real
FastAPI app — the final assembly point of Phase 0: upload path's Neo4j
class-graph writes -> the endpoint -> the rule engine -> a JSON response.
Skips gracefully if Neo4j isn't reachable, same as the other Neo4j tests.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402


def _neo4j_available() -> bool:
    try:
        db.driver.verify_connectivity()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _neo4j_available(), reason="Neo4j instance not reachable")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def session_id(client):
    resp = client.post("/start-session")
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    yield sid
    try:
        db.delete_session_data(sid)
    except Exception:
        pass


def test_gof_patterns_endpoint_detects_strategy(client, session_id):
    from analyzer.pipeline import analyze_files

    src = """
interface PaymentStrategy {
  pay(amount: number): void;
}
class CreditCardStrategy implements PaymentStrategy {
  pay(amount: number): void { this.charge(amount); }
  charge(amount: number): void {}
}
class PayPalStrategy implements PaymentStrategy {
  pay(amount: number): void { this.send(amount); }
  send(amount: number): void {}
}
class Checkout {
  strategy: PaymentStrategy;
  process(amount: number): void { this.strategy.pay(amount); }
}
"""
    files = [{"path": "checkout.ts", "language": "typescript", "content": src}]
    functions, classes, _unused, _layer = analyze_files(files)
    db.store_all(functions, session_id, files)
    db.store_class_graph(classes, functions, session_id)

    resp = client.get(f"/api/gof-patterns/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["patterns_found"] >= 1

    strategy = next(p for p in body["patterns"] if p["pattern"] == "Strategy")
    assert strategy["tier"] == "high"
    # Not a perfect 1.0: Checkout.process()'s call to pay() resolves
    # ambiguously (PaymentStrategy, CreditCardStrategy and PayPalStrategy
    # all declare a "pay" method), so delegates_to_field matches on its
    # weaker name-only fallback rather than an exact callee-class match —
    # see predicates.delegates_to_field's strength grading.
    assert strategy["confidence"] == 0.94
    assert strategy["bindings"] == {"strategy_interface": "PaymentStrategy", "context": "Checkout"}
    assert len(strategy["evidence"]) >= 4


def test_second_upload_replaces_first_project_in_same_session(client, session_id):
    """Regression test for the session-leak bug: session_id persists in the
    browser (sessionStorage) across uploads, only cleared on tab close/
    explicit end-session — so a second, unrelated /upload in the same
    session must fully replace the first project's Neo4j graph, not layer
    on top of it (the underlying writes are MERGE-based and would otherwise
    accumulate both projects' classes under the same session_id forever).
    """
    strategy_src = """
interface PaymentStrategy {
  pay(amount: number): void;
}
class CreditCardStrategy implements PaymentStrategy {
  pay(amount: number): void { this.charge(amount); }
  charge(amount: number): void {}
}
class PayPalStrategy implements PaymentStrategy {
  pay(amount: number): void { this.send(amount); }
  send(amount: number): void {}
}
class Checkout {
  strategy: PaymentStrategy;
  process(amount: number): void { this.strategy.pay(amount); }
}
"""
    resp1 = client.post(
        "/upload",
        headers={"X-Session-ID": session_id},
        files={"file": ("checkout.ts", strategy_src, "text/plain")},
    )
    assert resp1.status_code == 200

    unrelated_src = "class Widget {\n  render(): void {}\n}\n"
    resp2 = client.post(
        "/upload",
        headers={"X-Session-ID": session_id},
        files={"file": ("widget.ts", unrelated_src, "text/plain")},
    )
    assert resp2.status_code == 200

    class_graph = db.get_class_graph(session_id)
    class_names = {c["name"] for c in class_graph.get("classes", [])}
    assert "Widget" in class_names
    assert not class_names & {"Checkout", "PaymentStrategy", "CreditCardStrategy", "PayPalStrategy"}

    gof_resp = client.get(f"/api/gof-patterns/{session_id}")
    assert gof_resp.status_code == 200
    body = gof_resp.json()
    # Strategy only ever existed in the FIRST upload — it must not survive
    # into pattern detection run against the second project.
    assert not [p for p in body["patterns"] if p["pattern"] == "Strategy"]


def test_gof_patterns_endpoint_empty_session_returns_no_patterns(client, session_id):
    resp = client.get(f"/api/gof-patterns/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patterns_found"] == 0
    assert body["patterns"] == []


def test_gof_patterns_endpoint_unknown_session_404(client):
    resp = client.get("/api/gof-patterns/not-a-real-session")
    assert resp.status_code == 404


def test_gof_patterns_endpoint_merges_singleton_idiom_matches(client, session_id):
    """Confirms the Phase 3 language-idiom addition: singleton_idiom_matches
    (computed and cached at upload time — see main.py's upload handler) is
    merged into the response as a separately, explicitly heuristic-flagged
    entry, distinct from the structural rule engine's own tier/confidence.
    """
    import main
    main.SESSION_CACHE[session_id] = {
        "singleton_idiom_matches": [{"file": "config.go", "line": 6, "idiom": "sync.Once"}],
    }

    resp = client.get(f"/api/gof-patterns/{session_id}")
    assert resp.status_code == 200
    body = resp.json()

    idiom_matches = [p for p in body["patterns"] if p["pattern"] == "Singleton (language idiom)"]
    assert len(idiom_matches) == 1
    assert idiom_matches[0]["heuristic"] is True
    assert idiom_matches[0]["tier"] == "heuristic"
    assert idiom_matches[0]["confidence"] is None
    assert "sync.Once found in config.go:6" in idiom_matches[0]["evidence"]


def test_existing_patterns_endpoint_is_untouched(client, session_id):
    """Regression check at the HTTP layer: /api/patterns must still work
    exactly as before for a session with no upload yet (no functions cached)
    -- confirms the new endpoint didn't disturb the old one's wiring.
    """
    resp = client.get(f"/api/patterns/{session_id}")
    assert resp.status_code == 404  # no upload for this session yet, same as before this migration


def _load_fixture_files(root: Path) -> list[dict]:
    import os
    from analyzer.tree_sitter_runtime import SUPPORTED_EXTENSIONS
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


def test_legacy_gof_patterns_no_longer_in_architecture_panel(client, session_id):
    """Confirms Singleton/Observer/Factory/Facade no longer appear in
    /api/patterns — ArchitecturePatternDetector.detect_all() dropped them
    entirely (the naming-heuristic detect_singleton/_observer/_factory/
    _facade methods were deleted, not just excluded from the list) since
    they're now detected structurally instead, in patterns/specs/*.yaml
    (see test_phase4_fixtures.py for their true-positive verification).
    Still uses the legacy_mixed fixture since it's the one place that
    deliberately triggers all 5 remaining architecture detectors together.
    """
    import main
    from analyzer.pipeline import analyze_files

    all_files = _load_fixture_files(Path(__file__).parent / "fixtures" / "legacy_mixed")
    functions, classes, _unused, _layer = analyze_files(all_files)
    main.SESSION_CACHE[session_id] = {
        "functions": functions,
        "classes": classes,
        "all_files": [{"path": f["path"], "language": f["language"]} for f in all_files],
    }

    arch_resp = client.get(f"/api/patterns/{session_id}")
    assert arch_resp.status_code == 200
    arch_found = {p["pattern"] for p in arch_resp.json()["patterns"]}
    assert not arch_found & {"Singleton", "Observer", "Factory", "Facade"}
    assert {"MVC", "Layered/N-Tier", "Clean Architecture", "Hexagonal Architecture",
            "Repository Pattern"} <= arch_found
