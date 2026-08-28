"""
Host-side Docker sandbox orchestration for the dynamic-analysis tier.

Runs the target Python function inside an isolated, network-less container
(see dynamic_analysis/docker/) and returns the traced result. No network, a
read-only bind mount of the session's persisted source, and CPU/memory/PID
limits enforced by the container runtime — Windows lacks the `resource`
module, and Docker Desktop is already the deployment's isolation mechanism.
"""
import hashlib
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("dynamic_analysis.sandbox")

IMAGE_NAME = "codelens-py-sandbox"
DOCKER_DIR = Path(__file__).parent / "docker"
WALL_CLOCK_TIMEOUT_S = 8  # covers the 5s CPU budget + container startup overhead

_resolved_image_tag = None


class SandboxUnavailableError(Exception):
    """Docker itself isn't reachable — distinct from a failure inside the sandbox."""


def _docker(args, **kwargs):
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kwargs)


def _content_tag() -> str:
    """Hashes the docker/ directory's contents (Dockerfile, tracer_runner.py)
    so an edit to either automatically triggers a rebuild — a fixed image
    name+tag would otherwise silently keep serving a stale build forever."""
    digest = hashlib.sha256()
    for path in sorted(DOCKER_DIR.iterdir()):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def ensure_sandbox_image() -> str:
    """Builds the content-tagged sandbox image if it doesn't already exist;
    returns the full "name:tag" to run. No-op (just returns the cached tag)
    once resolved for this process and the source hasn't changed since."""
    global _resolved_image_tag
    if _resolved_image_tag is not None:
        return _resolved_image_tag

    tag = f"{IMAGE_NAME}:{_content_tag()}"

    try:
        check = _docker(["images", "-q", tag], timeout=15)
    except FileNotFoundError:
        raise SandboxUnavailableError("Docker is not installed or not on PATH")
    except subprocess.TimeoutExpired:
        raise SandboxUnavailableError("Docker did not respond (is Docker Desktop running?)")

    if check.returncode != 0:
        raise SandboxUnavailableError(f"docker images failed: {check.stderr.strip()}")

    if not check.stdout.strip():
        logger.info(f"Building sandbox image {tag} (source changed or first use)...")
        build = _docker(["build", "-t", tag, str(DOCKER_DIR)], timeout=180)
        if build.returncode != 0:
            raise SandboxUnavailableError(f"failed to build sandbox image: {build.stderr.strip()}")

    _resolved_image_tag = tag
    return tag


def run_in_sandbox(session_upload_dir: str, file_relpath: str, function_name: str,
                    inputs: dict, run_id: str) -> dict:
    """
    Returns a dict shaped like:
        {"status": "ok"|"error"|"timeout"|"truncated",
         "executed_lines": [...], "result": ..., "error": str|None}
    Never raises for failures *inside* the sandbox — only for the sandbox
    infrastructure itself being unavailable (SandboxUnavailableError).
    """
    image_tag = ensure_sandbox_image()

    # main.py's UPLOADS_BASE_DIR is a relative path ("./uploads") — Docker's -v
    # flag requires an absolute host path, otherwise it's parsed as a named
    # volume (and rejected outright on Windows for containing backslashes).
    abs_upload_dir = str(Path(session_upload_dir).resolve())

    container_name = f"codelens-run-{run_id}"
    payload = json.dumps({
        "file_relpath": file_relpath,
        "function_name": function_name,
        "inputs": inputs,
    })

    cmd = [
        "docker", "run", "-i", "--rm",
        "--name", container_name,
        "--network", "none",
        "--memory", "256m",
        "--cpus", "0.5",
        "--pids-limit", "128",
        "--read-only",
        "--tmpfs", "/tmp",
        "-v", f"{abs_upload_dir}:/workspace:ro",
        image_tag,
    ]

    try:
        proc = subprocess.run(
            cmd, input=payload, capture_output=True, text=True,
            timeout=WALL_CLOCK_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        # `docker run`'s own client process is killed by the timeout above, but the
        # detached container it started keeps running unless explicitly killed.
        _docker(["kill", container_name], timeout=10)
        return {"status": "timeout", "executed_lines": [], "result": None,
                "error": f"execution exceeded the {WALL_CLOCK_TIMEOUT_S}s wall-clock limit"}

    if proc.returncode != 0 and not proc.stdout.strip():
        return {"status": "error", "executed_lines": [], "result": None,
                "error": f"sandbox exited abnormally: {proc.stderr.strip() or 'no output'}"}

    try:
        last_line = proc.stdout.strip().splitlines()[-1]
        return json.loads(last_line)
    except (IndexError, json.JSONDecodeError) as e:
        return {"status": "error", "executed_lines": [], "result": None,
                "error": f"could not parse sandbox output: {e}"}
