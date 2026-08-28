"""Acceptance test for the dynamic-analysis tier (CodeLens spec §10): the
canonical f(X) example run with X=-1 must produce the executed sequence
S1,S2,S3,S4,S10,S11, and a backward slice on Y at write(Y) must exclude the
Z=g1(X) statement (S4). Exercises the real FastAPI app end-to-end: /upload
(which now also persists .py source — see main.py's Gap-2 fix) -> /dynamic/
functions/{id}/run (sandboxed execution + tracing) -> /dynamic/runs/{id}/slice.

Skips gracefully if Neo4j or Docker aren't reachable, same spirit as the
other Neo4j-backed integration tests (test_gof_endpoint.py).
"""
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402

FIXTURE_FILE = Path(__file__).parent / "fixtures" / "dynamic_slice_example" / "program_slice_example.py"


def _neo4j_available() -> bool:
    try:
        db.driver.verify_connectivity()
        return True
    except Exception:
        return False


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                 capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(not _neo4j_available(), reason="Neo4j instance not reachable"),
    pytest.mark.skipif(not _docker_available(), reason="Docker is not reachable"),
]


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


def _suffix(statement_id: str) -> str:
    return statement_id.rsplit("::", 1)[-1]


def test_canonical_slice_example(client, session_id):
    upload_resp = client.post(
        "/upload",
        headers={"X-Session-ID": session_id},
        files={"file": ("program_slice_example.py", FIXTURE_FILE.read_text(), "text/plain")},
    )
    assert upload_resp.status_code == 200

    function_node_id = "program_slice_example.py::f"
    run_resp = client.post(
        f"/dynamic/functions/{function_node_id}/run",
        headers={"X-Session-ID": session_id},
        json={"inputs": {"X": -1}},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_body = run_resp.json()
    assert run_body["status"] == "ok", run_body

    executed_suffixes = [_suffix(sid) for sid in run_body["executed_node_ids"]]
    assert executed_suffixes == ["S1", "S2", "S3", "S4", "S10", "S11"]

    run_id = run_body["run_id"]
    s10_id = f"{function_node_id}::S10"  # write(Y)
    s4_id = f"{function_node_id}::S4"    # Z = g1(X)

    slice_resp = client.post(
        f"/dynamic/runs/{run_id}/slice",
        headers={"X-Session-ID": session_id},
        json={"statement_node_id": s10_id, "variable_name": "Y"},
    )
    assert slice_resp.status_code == 200, slice_resp.text
    slice_ids = slice_resp.json()["slice_node_ids"]

    assert s4_id not in slice_ids
    slice_suffixes = {_suffix(sid) for sid in slice_ids}
    assert slice_suffixes == {"S1", "S2", "S3", "S10"}
