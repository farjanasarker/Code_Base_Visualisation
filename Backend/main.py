import os
import re
import subprocess
import tempfile
import zipfile
import uuid
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from db import clear_graph, get_full_graph, get_neighbors, store_all, get_tier1, get_tier2, get_tier3, get_all_files_graph, delete_session_data, get_chunk_functions, ensure_schema, store_class_graph, get_class_graph, get_function_node
from patterns.graph_view import SessionGraphView
from patterns.rule_engine import evaluate_all, pattern_info
from patterns.language_idioms.singleton_idioms import scan_files as scan_singleton_idioms
from analyzer import analyze_files, build_module_graph, decide_render_strategy, build_all_files_graph, compute_aggregate_metrics
from smell_detector import SmellDetector, SMELL_CAUSATION, SEVERITY_WEIGHTS
from smell_graph import build_smell_graph
import llm_engine
from pattern_detector import ArchitecturePatternDetector
from service_call_detector import detect_service_connections
from dynamic_analysis import runner as dynamic_runner
from dynamic_analysis.runner import UnsupportedFunctionError
from dynamic_analysis.statements import FunctionNotFoundError
import logging

logger = logging.getLogger(__name__)


# ── Git helpers ──────────────────────────────────────────────────────────────

def _find_git_root(base_path: Path) -> Optional[Path]:
    """Return the git repository root inside base_path, or None."""
    if (base_path / ".git").is_dir():
        return base_path
    try:
        for child in base_path.iterdir():
            if child.is_dir() and (child / ".git").is_dir():
                return child
    except Exception:
        pass
    return None


def _get_git_history(repo_path: str) -> Optional[Dict]:
    """Parse git commit history + per-commit stats from a local repo."""
    try:
        # One-shot log with numstat: COMMIT header lines + numstat lines
        result = subprocess.run(
            ["git", "log",
             "--pretty=format:COMMIT|%h|%s|%an|%ad",
             "--date=short", "--numstat", "-30"],
            cwd=repo_path, capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return None

        commits = []
        current: Optional[Dict] = None
        for raw in result.stdout.split("\n"):
            line = raw.rstrip()
            if line.startswith("COMMIT|"):
                parts = line.split("|", 4)
                current = {
                    "hash":         parts[1] if len(parts) > 1 else "",
                    "message":      parts[2] if len(parts) > 2 else "",
                    "author":       parts[3] if len(parts) > 3 else "",
                    "date":         parts[4] if len(parts) > 4 else "",
                    "insertions":   0,
                    "deletions":    0,
                    "files_changed": 0,
                }
                commits.append(current)
            elif current and "\t" in line:
                cols = line.split("\t")
                if len(cols) >= 2:
                    try:
                        current["insertions"]    += int(cols[0]) if cols[0].isdigit() else 0
                        current["deletions"]     += int(cols[1]) if cols[1].isdigit() else 0
                        current["files_changed"] += 1
                    except (ValueError, IndexError):
                        pass

        # Total commit count
        cnt = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=5,
        )
        total = int(cnt.stdout.strip()) if cnt.returncode == 0 and cnt.stdout.strip().isdigit() else len(commits)

        # Current branch
        br = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path, capture_output=True, text=True, timeout=5,
        )
        branch = br.stdout.strip() or "HEAD"

        # Churn = total lines touched per commit
        for commit in commits:
            commit["churn"] = commit["insertions"] + commit["deletions"]

        # Per-commit function-definition deltas (added / removed functions)
        fn_re_add = re.compile(r'^\+[^+].*\b(?:def |function |func |fn |class )\s+\w')
        fn_re_del = re.compile(r'^\-[^-].*\b(?:def |function |func |fn |class )\s+\w')

        for commit in commits[:20]:   # limit to 20 to avoid slow startup
            try:
                diff_r = subprocess.run(
                    ["git", "show", "--unified=0", "--no-color", commit["hash"],
                     "--", "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
                     "*.java", "*.go", "*.rs", "*.cs"],
                    cwd=repo_path, capture_output=True, text=True, timeout=8,
                )
                if diff_r.returncode == 0:
                    lines = diff_r.stdout.split("\n")
                    commit["fn_added"]   = sum(1 for l in lines if fn_re_add.match(l))
                    commit["fn_removed"] = sum(1 for l in lines if fn_re_del.match(l))
                else:
                    commit["fn_added"] = commit["fn_removed"] = 0
            except Exception:
                commit["fn_added"] = commit["fn_removed"] = 0

        return {"total_commits": total, "current_branch": branch, "commits": commits}
    except Exception as exc:
        logger.warning(f"Git history extraction failed: {exc}")
        return None

app = FastAPI()

# ========== SESSION MANAGEMENT ==========
# In-memory session storage
active_sessions: Dict[str, Dict[str, Any]] = {}
# {
#   "uuid-123": {
#       "created_at": datetime,
#       "last_active": datetime,
#       "files": ["file1.py", "file2.py"],
#       "upload_dir": "/path/to/uploads/uuid-123"
#   }
# }

UPLOADS_BASE_DIR = Path("./uploads")
# Dynamic-analysis tier's persisted Python source (see /upload) — deliberately
# outside Backend/ so `uvicorn --reload`'s file watcher never sees it change.
DYNAMIC_SOURCE_DIR = Path(__file__).resolve().parent.parent / "dynamic_analysis_sources"
SESSION_TIMEOUT = timedelta(hours=3)  # Sessions auto-cleanup after 3 hours of inactivity

# In-memory cache of last parsed upload (used when Neo4j is unavailable)
PARSED_CACHE: dict = {"functions": [], "tier1": None}

# Per-session cache
SESSION_CACHE: Dict[str, Dict[str, Any]] = {}
# {
#   "uuid-123": {
#       "functions": [...],
#       "tier1": {...},
#       "render_strategy": "..."
#   }
# }

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILE_SIZE = 2000 * 1024  # 2MB per source file
MAX_FILE_COUNT = 1000
MAX_DEPTH = 50

SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "uploads"
}

SKIP_DIRS_LOWER = {d.lower() for d in SKIP_DIRS}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".cs",
    ".zip",
}

# Extensions considered "source files" for size/count checks inside archives
SOURCE_EXTENSIONS = {e for e in SUPPORTED_EXTENSIONS if e != ".zip"}

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (or specify ["http://localhost:5173", "http://127.0.0.1:5173"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== SESSION UTILITIES ==========
def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session metadata or None if not found"""
    return active_sessions.get(session_id)


def create_session() -> str:
    """Create new session, return session_id"""
    session_id = str(uuid.uuid4())
    
    # Create session directory
    session_dir = UPLOADS_BASE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Track session
    active_sessions[session_id] = {
        "created_at": datetime.now(),
        "last_active": datetime.now(),
        "files": [],
        "upload_dir": str(session_dir)
    }
    
    logger.info(f"✅ Session created: {session_id}")
    return session_id


def update_session_activity(session_id: str) -> None:
    """Update session's last active timestamp"""
    if session_id in active_sessions:
        active_sessions[session_id]["last_active"] = datetime.now()


def end_session_cleanup(session_id: str) -> bool:
    """Clean up session: delete from Neo4j, disk, and RAM"""
    try:
        session_info = active_sessions.pop(session_id, None)
        
        if not session_info:
            logger.warning(f"⚠️ Session not found: {session_id}")
            return False
        
        # Delete from Neo4j
        try:
            delete_session_data(session_id)
            logger.info(f"✅ Cleaned Neo4j data for session: {session_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to clean Neo4j for {session_id}: {e}")
        
        # Delete from disk
        upload_dir = Path(session_info["upload_dir"])
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
            logger.info(f"✅ Deleted upload directory: {upload_dir}")

        dynamic_source_dir = DYNAMIC_SOURCE_DIR / session_id
        if dynamic_source_dir.exists():
            shutil.rmtree(dynamic_source_dir, ignore_errors=True)

        # Delete from session cache
        SESSION_CACHE.pop(session_id, None)
        
        logger.info(f"✅ Session fully cleaned: {session_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error cleaning session {session_id}: {e}")
        return False


async def cleanup_orphan_sessions() -> None:
    """Background task: periodically clean up inactive sessions"""
    while True:
        try:
            await asyncio.sleep(1800)  # Every 30 minutes
            
            now = datetime.now()
            orphan_sessions = []
            
            for session_id, session_data in list(active_sessions.items()):
                inactivity = now - session_data["last_active"]
                
                if inactivity > SESSION_TIMEOUT:
                    orphan_sessions.append(session_id)
                    logger.warning(f"⚠️ Session expired (3h inactive): {session_id}")
            
            for session_id in orphan_sessions:
                end_session_cleanup(session_id)
                logger.info(f"🧹 Orphan session cleaned: {session_id}")
            
            if orphan_sessions:
                logger.info(f"🧹 Cleaned {len(orphan_sessions)} orphan sessions")
                
        except Exception as e:
            logger.error(f"❌ Error in cleanup task: {e}")


@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on app startup"""
    logger.info("🚀 Backend startup - creating cleanup task")
    
    # Create uploads directory
    UPLOADS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # Idempotent Neo4j schema setup for the GoF pattern engine's Class nodes
    # (best-effort — logs and continues if the constraint can't be created)
    ensure_schema()

    # Start background cleanup
    asyncio.create_task(cleanup_orphan_sessions())


def validate_session(session_id: Optional[str]) -> str:
    """Validate session_id from request header"""
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing X-Session-ID header")
    
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    
    return session_id


@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "Backend is running",
        "active_sessions": len(active_sessions),
        "timestamp": datetime.now().isoformat()
    }


# ========== SESSION ENDPOINTS ==========
@app.post("/start-session")
async def start_session():
    """
    Create new session for a user
    Frontend calls this on first load or after page refresh
    Returns session_id to be stored in sessionStorage
    """
    try:
        session_id = create_session()
        return {
            "status": "success",
            "session_id": session_id,
            "message": "Session created",
            "expires_in_hours": SESSION_TIMEOUT.total_seconds() / 3600
        }
    except Exception as e:
        logger.error(f"❌ Error creating session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@app.delete("/end-session")
async def end_session(request: Request):
    """
    Clean up session when browser closes
    Frontend sends this via sendBeacon before closing
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing X-Session-ID header")
        
        success = end_session_cleanup(session_id)
        
        return {
            "status": "success" if success else "not_found",
            "session_id": session_id,
            "message": "Session cleaned" if success else "Session not found"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error ending session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to end session: {str(e)}")


@app.get("/sessions/info")
async def get_session_info(request: Request):
    """Get current session info (debugging/monitoring)"""
    try:
        session_id = request.headers.get("X-Session-ID")
        
        if not session_id or session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = active_sessions[session_id]
        
        return {
            "session_id": session_id,
            "created_at": session_data["created_at"].isoformat(),
            "last_active": session_data["last_active"].isoformat(),
            "inactivity_minutes": (datetime.now() - session_data["last_active"]).total_seconds() / 60,
            "files": session_data["files"],
            "upload_dir": session_data["upload_dir"],
            "last_upload_error": session_data.get("last_upload_error"),
            "last_upload_error_files": session_data.get("last_upload_error_files", [])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching session info: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/admin/sessions")
async def list_all_sessions():
    """
    Get all active sessions (admin endpoint)
    Shows current session count and details
    """
    try:
        sessions_info = []
        
        for sid, data in active_sessions.items():
            inactivity = datetime.now() - data["last_active"]
            sessions_info.append({
                "session_id": sid,
                "created_at": data["created_at"].isoformat(),
                "inactivity_minutes": inactivity.total_seconds() / 60,
                "files_count": len(data["files"])
            })
        
        return {
            "status": "success",
            "total_sessions": len(active_sessions),
            "sessions": sessions_info
        }
    except Exception as e:
        logger.error(f"❌ Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


def detect_language(ext: str) -> str:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
    }
    return mapping.get(ext, "unknown")


def validate_upload(file_name: str, size: int) -> None:
    if size > MAX_UPLOAD_SIZE:
        raise ValueError("File too large (max 50MB)")

    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file type")


def has_skipped_dir(path_parts: tuple[str, ...]) -> bool:
    return any(part.lower() in SKIP_DIRS_LOWER for part in path_parts)


# Filenames that mark a folder as an independently buildable/deployable unit.
# A top-level folder only counts as a monorepo "service" if it has one of these
# directly inside it — this is what tells a real microservice folder apart from
# an ordinary src/, test/, or docs/ directory in a single, non-monorepo project.
SERVICE_MANIFEST_FILES = {
    "package.json",       # node / js / ts
    "requirements.txt",   # python
    "pyproject.toml",     # python
    "setup.py",           # python
    "pom.xml",            # java (maven)
    "build.gradle",       # java (gradle)
    "build.gradle.kts",   # java (gradle, kotlin dsl)
    "go.mod",             # go
    "Cargo.toml",         # rust
    "Dockerfile",         # generic — independently deployable service
}


def _has_service_manifest(dir_path: str) -> bool:
    """Shallow (non-recursive) check for a manifest file directly inside dir_path."""
    try:
        with os.scandir(dir_path) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                if entry.name in SERVICE_MANIFEST_FILES or entry.name.lower().endswith(".csproj"):
                    return True
    except OSError:
        return False
    return False


# Common microservice folder-naming convention: book_service, auth-service,
# paymentService, notification-svc, service-billing, etc. A second, independent
# signal from _has_service_manifest() — many demo/course monorepos name each
# service suggestively without giving it its own package.json/go.mod/etc.
def _looks_like_service_name(name: str) -> bool:
    lname = name.lower()
    return lname.endswith("service") or lname.endswith("svc") or lname.startswith("service")


def _find_manifest_dirs(scan_root: str, rel_prefix: str = "") -> list[dict]:
    """Return one entry per non-SKIP_DIRS directory directly under scan_root
    that either carries its own manifest file or has a microservice-style name.

    `rel_path` is the path-from-upload-root prefix used to bucket `all_files`
    entries into this service later (differs from `service_id` when a wrapper
    folder was unwrapped — see detect_services()).
    """
    found: list[dict] = []
    try:
        with os.scandir(scan_root) as entries:
            for entry in entries:
                if not entry.is_dir() or entry.name.lower() in SKIP_DIRS_LOWER:
                    continue
                if _has_service_manifest(entry.path) or _looks_like_service_name(entry.name):
                    found.append({
                        "service_id": entry.name,
                        "rel_path": f"{rel_prefix}{entry.name}",
                        "path": entry.path,
                    })
    except OSError:
        pass
    return found


def detect_services(root_path: str) -> list[dict]:
    """Detect monorepo services: each top-level directory under root_path that
    isn't a SKIP_DIRS entry AND (a) carries its own manifest file (package.json,
    requirements.txt, pom.xml, go.mod, Cargo.toml, Dockerfile, etc.) directly
    inside it, OR (b) has a microservice-style name (book_service, auth-service,
    paymentSvc, ...), is treated as one independently-buildable service.

    Handles the common "wrapped zip" shape too: when a zip extracts to a
    single repo-name folder with the actual services nested one level inside
    it (e.g. RepoName/auth-service/package.json), that wrapper is transparently
    unwrapped so services are still detected — mirrors the root-stripping the
    frontend's tier1 view already does for the same wrapped-zip shape.

    Must be called while root_path still exists on disk (i.e. before the
    TemporaryDirectory it lives in is closed).
    """
    services = _find_manifest_dirs(root_path)
    if services:
        return services

    try:
        with os.scandir(root_path) as entries:
            subdirs = [e for e in entries if e.is_dir() and e.name.lower() not in SKIP_DIRS_LOWER]
    except OSError:
        subdirs = []

    if len(subdirs) == 1:
        wrapper = subdirs[0]
        return _find_manifest_dirs(wrapper.path, rel_prefix=f"{wrapper.name}/")

    return []


def handle_zip(zip_path: str, extract_to: str) -> str:
    extract_root = Path(extract_to).resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()

        # Count only source files for the MAX_FILE_COUNT limit
        source_file_count = 0
        for info in members:
            if info.is_dir():
                continue
            member = info.filename
            member_parts = Path(member).parts

            # Enforce path depth for all members
            if len(member_parts) > MAX_DEPTH:
                raise ValueError(f"Path too deep in ZIP: {member}")

            # Skip files located under ignored directories (e.g., node_modules)
            if has_skipped_dir(member_parts):
                continue

            ext = Path(member).suffix.lower()
            if ext in SOURCE_EXTENSIONS:
                source_file_count += 1
                if info.file_size > MAX_FILE_SIZE:
                    raise ValueError(f"Source file too large inside ZIP: {member}")

        if source_file_count > MAX_FILE_COUNT:
            raise ValueError("Too many source files in ZIP")

        # Safe to extract; non-source files will be ignored later by walk_folder
        zf.extractall(extract_root)

    return str(extract_root)


def walk_folder(root_path: str) -> list[dict]:
    return walk_folder(root_path, MAX_FILE_COUNT)


def walk_folder(root_path: str, max_files: int = MAX_FILE_COUNT) -> list[dict]:
    files: list[dict] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS_LOWER]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            ext = filepath.suffix.lower()

            if ext not in SUPPORTED_EXTENSIONS or ext == ".zip":
                continue

            size = filepath.stat().st_size
            if size > MAX_FILE_SIZE:
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            files.append(
                {
                    "path": filepath.relative_to(root_path).as_posix(),
                    "language": detect_language(ext),
                    "size": size,
                    "content": content,
                }
            )

            # SKIP_DIRS-filtered counting: truncate and return when limit reached
            if len(files) >= max_files:
                logger.warning(
                    f"⚠️ File limit reached: {max_files} files collected, remaining files skipped. (SKIP_DIRS-filtered count)"
                )
                return files

    return files


def sanitize_relative_path(raw_name: str) -> Path:
    rel_path = Path(raw_name)

    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"Unsafe upload path: {raw_name}")

    if len(rel_path.parts) > MAX_DEPTH:
        raise ValueError(f"Path too deep: {raw_name}")

    return rel_path


async def persist_folder_upload(files: list[UploadFile], destination_root: str) -> None:
    root_path = Path(destination_root)
    root_path.mkdir(parents=True, exist_ok=True)

    accepted_files = 0

    for uploaded in files:
        file_name = uploaded.filename or ""
        safe_rel_path = sanitize_relative_path(file_name.replace("\\", "/"))

        if has_skipped_dir(safe_rel_path.parts):
            continue

        ext = safe_rel_path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS or ext == ".zip":
            continue

        file_bytes = await uploaded.read()
        validate_upload(file_name, len(file_bytes))

        accepted_files += 1
        if accepted_files >= MAX_FILE_COUNT:
            logger.warning(
                f"⚠️ Folder upload file limit reached at {MAX_FILE_COUNT} source files (SKIP_DIRS already excluded). Truncating."
            )
            # stop accepting more files; proceed with what we've written
            break

        target = (root_path / safe_rel_path).resolve()
        if not str(target).startswith(str(root_path.resolve())):
            raise ValueError(f"Unsafe target path: {file_name}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_bytes)


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
):
    """
    Upload file(s) and analyze code
    Requires X-Session-ID header to track which user owns the data
    """
    try:
        # Validate session
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)
        
        # Get session's upload directory
        session_info = active_sessions[session_id]
        session_upload_dir = Path(session_info["upload_dir"])
        session_upload_dir.mkdir(parents=True, exist_ok=True)
        
        git_history: Optional[Dict] = None   # captured inside tmpdir before it closes
        services: list[dict] = []   # detected monorepo services — must be captured before tmpdir closes

        with tempfile.TemporaryDirectory() as tmpdir:
            if file is not None:
                file_name = file.filename or "upload.txt"
                file_bytes = await file.read()
                validate_upload(file_name, len(file_bytes))

                if file_name.lower().endswith(".zip"):
                    zip_path = Path(tmpdir) / "upload.zip"
                    zip_path.write_bytes(file_bytes)

                    extract_path = Path(tmpdir) / "extracted"
                    extract_path.mkdir(parents=True, exist_ok=True)
                    handle_zip(str(zip_path), str(extract_path))

                    # Git detection — must happen before tmpdir closes
                    git_root = _find_git_root(extract_path)
                    if git_root:
                        git_history = _get_git_history(str(git_root))

                    services = detect_services(str(extract_path))
                    all_files = walk_folder(str(extract_path))
                else:
                    single_path = Path(tmpdir) / file_name
                    single_path.parent.mkdir(parents=True, exist_ok=True)
                    single_path.write_bytes(file_bytes)
                    all_files = walk_folder(tmpdir)

            elif files:
                folder_root = Path(tmpdir) / "folder_upload"
                await persist_folder_upload(files, str(folder_root))
                services = detect_services(str(folder_root))
                all_files = walk_folder(str(folder_root))

            else:
                raise HTTPException(status_code=400, detail="No file(s) provided")

        # Remove any files that live under SKIP_DIRS (catch any missed cases)
        orig_count = len(all_files)
        filtered = []
        for f in all_files:
            try:
                parts = tuple(Path(f.get("path", "")).parts)
            except Exception:
                parts = tuple()
            if not has_skipped_dir(parts):
                filtered.append(f)
        filtered_out = orig_count - len(filtered)
        if filtered_out:
            logger.info(f"Filtered out {filtered_out} files under SKIP_DIRS before analysis")
        all_files = filtered

        # Persist Python source somewhere it survives past this request — needed by
        # the dynamic-analysis tier (sandbox execution, statement extraction) since
        # SESSION_CACHE strips file content to save memory. Deliberately NOT under
        # session_upload_dir (Backend/uploads/...): that's inside the tree `uvicorn
        # --reload` watches, so writing .py files there on every /upload triggered a
        # full server reload mid-request — wiping active_sessions/SESSION_CACHE and
        # breaking the session that was just created. dynamic_source_dir lives
        # outside Backend/ entirely so it's never watched.
        dynamic_source_dir = DYNAMIC_SOURCE_DIR / session_id
        # Clear any files persisted by a previous upload in this session first,
        # mirroring the Neo4j wipe below (delete_session_data) so stale sources don't linger.
        if dynamic_source_dir.exists():
            for stale in dynamic_source_dir.glob("**/*"):
                if stale.is_file():
                    try:
                        stale.unlink()
                    except OSError:
                        pass
        for f in all_files:
            if f.get("language") != "python":
                continue
            try:
                dest = dynamic_source_dir / f["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(f.get("content", ""), encoding="utf-8")
            except Exception:
                logger.exception(f"Failed to persist source for {f.get('path')} (session {session_id})")

        if len(all_files) >= MAX_FILE_COUNT:
            logger.warning(
                f"⚠️ File count at or above limit after SKIP_DIRS filtering: {len(all_files)} files (limit {MAX_FILE_COUNT}). Remaining files were skipped."
            )

        if not all_files:
            # Record error on session for easier debugging
            try:
                active_sessions[session_id]["last_upload_error"] = "No supported source files found"
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="No supported source files found")

        # A monorepo Service tier only activates with 2+ detected top-level service
        # folders — single-folder / flat uploads keep the exact single-project behavior.
        is_multi_service = len(services) > 1
        service_connections: list = []
        service_buckets: list = []  # [{"service_id":, "files":, "functions":}] — multi-service only

        if is_multi_service:
            functions = []
            classes = []
            unused_imports: dict = {}
            all_violations: list = []
            for svc in services:
                sid = svc["service_id"]
                # rel_path (path from the upload root) differs from service_id when a
                # wrapper folder was unwrapped in detect_services() — bucket by rel_path.
                prefix = svc.get("rel_path", sid) + "/"
                bucket_files = [f for f in all_files if f.get("path", "").startswith(prefix)]
                if not bucket_files:
                    continue
                bucket_functions, bucket_classes, bucket_unused, bucket_layer = analyze_files(bucket_files)
                for fn in bucket_functions:
                    fn["service"] = sid
                for c in bucket_classes:
                    c["service"] = sid
                for f in bucket_files:
                    f["service"] = sid
                functions.extend(bucket_functions)
                classes.extend(bucket_classes)
                unused_imports.update(bucket_unused)
                all_violations.extend(bucket_layer.get("all_violations", []))
                service_buckets.append({
                    "service_id": sid, "files": bucket_files,
                    "functions": bucket_functions, "classes": bucket_classes,
                })

            # Automatic inter-service call detection (HTTP/REST + message-queue
            # pub/sub) from source text — no manual service-map.json needed.
            try:
                service_connections = detect_service_connections(
                    [{"service_id": b["service_id"], "files": b["files"]} for b in service_buckets]
                )
            except Exception:
                logger.exception("Service call detection failed")
                service_connections = []

            layer_violations = {
                "by_module": {},
                "summary": {
                    "total": len(all_violations),
                    "high": sum(1 for v in all_violations if v.get("severity") == "high"),
                    "medium": sum(1 for v in all_violations if v.get("severity") == "medium"),
                },
                "all_violations": all_violations,
            }
        else:
            functions, classes, unused_imports, layer_violations = analyze_files(all_files)

        # Compute aggregate metrics (needs file content — do it before all_files is gc'd)
        try:
            metrics = compute_aggregate_metrics(functions, all_files)
        except Exception:
            logger.exception("Failed to compute aggregate metrics")
            metrics = {}

        # Update session's file list
        session_info["files"] = [f["path"] for f in all_files]

        # Go/Rust Singleton idiom scan (sync.Once, lazy_static!, OnceCell/
        # OnceLock) — must run here, while all_files still has `content`;
        # the cached all_files below strips it out to save memory.
        try:
            singleton_idiom_matches = scan_singleton_idioms(all_files)
        except Exception:
            logger.exception(f"Failed to scan language-idiom singletons for session {session_id}")
            singleton_idiom_matches = []

        # cache parsed functions and raw file list for this session
        try:
            tier1 = build_module_graph(functions)
            SESSION_CACHE[session_id] = {
                "functions": functions,
                "classes": classes,
                "tier1": tier1,
                "all_files": [{"path": f["path"], "language": f["language"], "service": f.get("service")} for f in all_files],
                "unused_imports": unused_imports,
                "layer_violations": layer_violations,
                "metrics": metrics,
                "git_history": git_history,
                "services": services if is_multi_service else [],
                "service_connections": service_connections,
                "singleton_idiom_matches": singleton_idiom_matches,
            }

            # Also update global cache for fallback
            PARSED_CACHE["functions"] = functions
            PARSED_CACHE["tier1"] = tier1
            PARSED_CACHE["unused_imports"] = unused_imports
            PARSED_CACHE["layer_violations"] = layer_violations
            PARSED_CACHE["metrics"] = metrics

        except Exception:
            logger.exception(f"Failed to cache parsed functions for session {session_id}")

        # Each /upload replaces this session's project — session_id persists in
        # the browser across uploads (sessionStorage, only cleared on tab
        # close/end-session), but Neo4j writes below are MERGE-based and would
        # otherwise just layer the new project's nodes on top of whatever a
        # previous upload in this same session already stored. Wipe the old
        # graph first so a second upload doesn't leave stale classes/functions
        # around for get_class_graph()/GoF pattern detection to pick up
        # alongside the new ones.
        try:
            delete_session_data(session_id)
            logger.info(f"✅ Cleared previous Neo4j data for session {session_id} before storing new upload")
        except Exception:
            logger.exception(f"⚠️ Failed to clear previous Neo4j data for session {session_id}")

        # Persist to Neo4j with session_id (best-effort)
        try:
            if is_multi_service:
                for bucket in service_buckets:
                    store_all(bucket["functions"], session_id, bucket["files"], service_id=bucket["service_id"])
            else:
                store_all(functions, session_id, all_files)
            logger.info(f"✅ Stored graph to Neo4j for session {session_id}")
        except Exception:
            logger.exception(f"⚠️ Failed to store graph to Neo4j for session {session_id}")

        # Persist the GoF pattern engine's class graph — a separate write from
        # store_all() above (see store_class_graph's docstring for why): a bug
        # here must only degrade the new GoF feature, not the Function/File/
        # Calls data store_all() already persisted successfully.
        try:
            if is_multi_service:
                for bucket in service_buckets:
                    store_class_graph(bucket["classes"], bucket["functions"], session_id, service_id=bucket["service_id"])
            else:
                store_class_graph(classes, functions, session_id)
            logger.info(f"✅ Stored class graph to Neo4j for session {session_id}")
        except Exception:
            logger.exception(f"⚠️ Failed to store class graph to Neo4j for session {session_id}")

        tier1 = SESSION_CACHE.get(session_id, {}).get("tier1") or PARSED_CACHE.get("tier1") or build_module_graph(functions)
        render = decide_render_strategy(len(tier1["nodes"]))

        response = {
            "message": "Graph generated",
            "status": "success",
            "session_id": session_id,
            "tier1_graph": tier1,
            "render_strategy": render,
            "total_functions": len(functions),
            "total_files": len(all_files),
        }

        if is_multi_service:
            response["is_multi_service"] = True
            response["service_graph"] = _build_service_graph(session_id)

        return response
    except ValueError as e:
        # Log and attach the validation error to the session for debugging
        logger.error(f"Validation error for session {session_id if 'session_id' in locals() else 'unknown'}: {str(e)}")
        try:
            if 'session_id' in locals() and session_id in active_sessions:
                active_sessions[session_id]["last_upload_error"] = str(e)
                # also record filenames if available
                fnames = []
                try:
                    if files:
                        fnames = [f.filename for f in files]
                    elif file:
                        fnames = [file.filename]
                except Exception:
                    fnames = []
                active_sessions[session_id]["last_upload_error_files"] = fnames
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/expand/{function_name}")
def expand(request: Request, function_name: str):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)
        try:
            neighbors = get_neighbors(function_name, session_id)
        except Exception as neo4j_err:
            logger.warning(f"Neo4j expand failed, using cache: {neo4j_err}")
            neighbors = _expand_from_cache(function_name, session_id)

        return {
            "nodes": [{"id": n} for n in neighbors],
            "edges": [
                {"source": function_name, "target": n}
                for n in neighbors
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Expand error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching graph: {str(e)}")


def _expand_from_cache(function_name: str, session_id: str) -> list[str]:
    """SESSION_CACHE থেকে function এর neighbors বের করো।
    function_name হয় plain name অথবা name:line_start format।
    """
    functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
    if not functions:
        return []

    # Duplicate name detection
    name_counts: Dict[str, int] = {}
    for fn in functions:
        n = fn["name"]
        name_counts[n] = name_counts.get(n, 0) + 1

    def _node_id(fn: Dict) -> str:
        name = fn["name"]
        if name_counts.get(name, 1) > 1:
            return f"{name}:{fn.get('line_start')}"
        return name

    fn_names = {fn["name"] for fn in functions}

    # name:line format হলে specific function খোঁজো
    if ":" in function_name:
        actual_name, line_str = function_name.rsplit(":", 1)
        try:
            target_line = int(line_str)
        except ValueError:
            target_line = None

        target_fn = next(
            (fn for fn in functions
             if fn["name"] == actual_name and fn.get("line_start") == target_line),
            None,
        )
        if not target_fn:
            return []

        neighbors = set()
        # এই function যাদের call করে
        for called in target_fn.get("calls", []):
            if called in fn_names:
                for fn in functions:
                    if fn["name"] == called:
                        neighbors.add(_node_id(fn))
        # অন্য functions যারা এই function কে call করে
        for fn in functions:
            if actual_name in fn.get("calls", []):
                neighbors.add(_node_id(fn))
        neighbors.discard(function_name)
        return list(neighbors)

    # Plain name (no duplicates)
    neighbors = set()
    for fn in functions:
        if fn["name"] == function_name:
            for called in fn.get("calls", []):
                if called in fn_names:
                    for other in functions:
                        if other["name"] == called:
                            neighbors.add(_node_id(other))
        else:
            if function_name in fn.get("calls", []):
                neighbors.add(_node_id(fn))
    neighbors.discard(function_name)
    return list(neighbors)


def _build_service_graph(session_id: str) -> dict:
    """Assemble the Tier-0 service graph from SESSION_CACHE (in-memory-first,
    mirrors how /graph/files derives its cache fallback)."""
    cache = SESSION_CACHE.get(session_id, {})
    functions = cache.get("functions", [])
    all_files = cache.get("all_files", [])
    services = cache.get("services", [])
    connections = cache.get("service_connections", [])

    modules_by_service: Dict[str, set] = {}
    files_by_service: Dict[str, set] = {}
    for fn in functions:
        sid = fn.get("service")
        if not sid:
            continue
        mod = (fn.get("module") or "").strip()
        if mod:
            modules_by_service.setdefault(sid, set()).add(mod)
    for f in all_files:
        sid = f.get("service")
        if not sid:
            continue
        files_by_service.setdefault(sid, set()).add(f.get("path"))

    service_list = [
        {
            "service_id": svc["service_id"],
            "module_count": len(modules_by_service.get(svc["service_id"], set())),
            "file_count": len(files_by_service.get(svc["service_id"], set())),
        }
        for svc in services
    ]
    return {"services": service_list, "connections": connections}


@app.get("/service-graph")
def api_service_graph(request: Request):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        return _build_service_graph(session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service graph error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching service graph: {str(e)}")


@app.get("/graph/tier1")
def api_tier1(request: Request, service_id: str | None = None):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        if service_id:
            # Prefer the in-memory build here — it's richer than the live Neo4j
            # query (it also infers edges from import/require statements, not
            # just direct function CALLS relationships), matching how the
            # initial non-service tier1 view already gets its edge set today.
            functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
            scoped = [fn for fn in functions if fn.get("service") == service_id]
            if scoped:
                return build_module_graph(scoped)

        return get_tier1(session_id, service_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier1 from DB for session {session_id}")
        # fallback to session cache
        if service_id:
            functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
            scoped = [fn for fn in functions if fn.get("service") == service_id]
            if scoped:
                return build_module_graph(scoped)
        tier = SESSION_CACHE.get(session_id, {}).get("tier1")
        if tier:
            return tier
        raise HTTPException(status_code=500, detail="Error fetching tier1 graph and no cache available")


@app.get("/graph/tier2/{module_name:path}")
def api_tier2(request: Request, module_name: str, service_id: str | None = None):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        return get_tier2(module_name, session_id, service_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier2 from DB for session {session_id}")
        # fallback: build from session cache
        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]
        if functions:
            from analyzer import build_file_graph
            return build_file_graph(module_name, functions)
        raise HTTPException(status_code=500, detail="Error fetching tier2 graph and no cache available")


@app.get("/graph/files")
def api_all_files(request: Request):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache = SESSION_CACHE.get(session_id, {})
        functions = cache.get("functions", [])
        raw_files = cache.get("all_files", [])

        if functions:
            graph = build_all_files_graph(functions)
            existing = {n["id"] for n in graph.get("nodes", [])}
            for f in raw_files:
                fp = f.get("path")
                if fp and fp not in existing:
                    graph["nodes"].append({
                        "id": fp,
                        "type": "file",
                        "language": f.get("language"),
                        "fn_count": 0,
                    })
            return graph

        return get_all_files_graph(session_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch file graph from DB for session {session_id}")
        # Fallback: build from session cache
        cache = SESSION_CACHE.get(session_id, {})
        functions = cache.get("functions", [])
        if functions:
            return build_all_files_graph(functions)
        # Last resort: raw file list with no edges
        raw_files = cache.get("all_files", [])
        if raw_files:
            return {
                "nodes": [{"id": f["path"], "type": "file", "language": f["language"], "fn_count": 0} for f in raw_files],
                "edges": [],
                "tier": "files",
            }
        raise HTTPException(status_code=500, detail="Error fetching file graph and no cache available")


@app.get("/graph/tier3")
def api_tier3(request: Request, file_path: str, service_id: str | None = None):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]
        if functions:
            from analyzer import build_function_graph
            graph = build_function_graph(file_path, functions)
            # An empty node list here isn't necessarily a cache miss — a file whose only
            # functions are inline anonymous callbacks (build_function_graph filters those
            # out as un-navigable) legitimately produces zero nodes. Falling through to the
            # DB path in that case used to leak those same anonymous_<line> callbacks back
            # in, since get_tier3's Cypher query has no such filter. Only fall back to DB
            # when this file truly has no cached functions at all.
            file_has_functions = any(
                fn.get("file") == file_path or fn.get("virtual_module") == file_path
                for fn in functions
            )
            if graph.get("nodes") or file_has_functions:
                return graph

        return get_tier3(file_path, session_id, service_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier3 from DB for session {session_id}")
        # fallback: build from session cache
        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]
        if functions:
            from analyzer import build_function_graph
            return build_function_graph(file_path, functions)
        raise HTTPException(status_code=500, detail="Error fetching tier3 graph and no cache available")


@app.get("/graph/chunk")
def api_chunk(request: Request, file_path: str, chunk_name: str):
    """Return function-level graph for a specific chunk (virtual module) inside a god file."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        # Fast path: build from session cache
        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if functions:
            from analyzer import build_function_graph
            # build_function_graph treats chunk_name as file_path → finds fns by virtual_module
            graph = build_function_graph(chunk_name, functions)
            # See /graph/tier3's identical check: an empty node list can legitimately mean
            # "this chunk's only functions are anonymous callbacks", not "not cached yet" —
            # only fall back to the (unfiltered) DB path when nothing at all matched.
            chunk_has_functions = any(fn.get("virtual_module") == chunk_name for fn in functions)
            if graph.get("nodes") or chunk_has_functions:
                return {**graph, "file": file_path, "chunk": chunk_name, "tier": 4, "chunked": False}

        # DB path
        return get_chunk_functions(file_path, chunk_name, session_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch chunk functions for {chunk_name}")
        raise HTTPException(status_code=500, detail="Error fetching chunk function graph")


@app.get("/risk-score")
def api_risk_score(request: Request):
    """Return all functions ranked by dependency risk (fan_in).
    Risk levels: high (>=10 callers), medium (>=3), low (>=1), none (0).
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        real_fns = [fn for fn in functions if fn.get("name") != "__file__"]

        summary = {"high": 0, "medium": 0, "low": 0, "none": 0}
        for fn in real_fns:
            lvl = fn.get("risk_level", "none")
            summary[lvl] = summary.get(lvl, 0) + 1

        # Only functions that are called by at least one other function, sorted by risk
        risky = sorted(
            [fn for fn in real_fns if fn.get("fan_in", 0) > 0],
            key=lambda f: f.get("fan_in", 0),
            reverse=True
        )

        result = [
            {
                "name": fn.get("name"),
                "file": fn.get("file"),
                "fan_in": fn.get("fan_in", 0),
                "fan_out": fn.get("fan_out", 0),
                "risk_level": fn.get("risk_level", "none"),
                "warning": f"Changing this will affect {fn.get('fan_in', 0)} caller(s)",
            }
            for fn in risky[:50]
        ]

        return {"functions": result, "summary": summary, "total": len(real_fns)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Risk score error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error computing risk scores: {str(e)}")


@app.get("/search")
def api_search(request: Request, q: str, limit: int = 20):
    """Search every parsed function and file in the session (not just the
    top-50 risky ones), ranked exact > prefix > substring. Each function hit
    carries what the UI needs to drill down to its node: the file, the node
    id used in that file's function graph, and the chunk (god files only)."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        needle = (q or "").strip().lower()
        if not needle:
            return {"results": []}
        limit = max(1, min(limit, 50))

        from analyzer.heuristics import _is_anonymous_callback

        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        real_fns = [
            fn for fn in functions
            if fn.get("name") and fn.get("name") != "__file__"
            and not _is_anonymous_callback(fn.get("name", ""))
        ]

        # Mirror build_function_graph's node-id rule (name, or name:line when the
        # name repeats within a file / chunk) so the UI can find the node directly.
        by_scope: Dict[Any, Dict[str, int]] = {}
        for fn in real_fns:
            scope = fn.get("virtual_module") if fn.get("virtual_module") != fn.get("file") else None
            counts = by_scope.setdefault((fn.get("file"), scope), {})
            counts[fn["name"]] = counts.get(fn["name"], 0) + 1
        file_counts: Dict[str, Dict[str, int]] = {}
        for fn in real_fns:
            counts = file_counts.setdefault(fn.get("file"), {})
            counts[fn["name"]] = counts.get(fn["name"], 0) + 1
        god_chunked_files = set()
        vms_per_file: Dict[str, set] = {}
        for fn in real_fns:
            vm = fn.get("virtual_module")
            if vm and vm != fn.get("file"):
                vms_per_file.setdefault(fn.get("file"), set()).add(vm)
        for f_path, vms in vms_per_file.items():
            if len(vms) > 1 and any(
                fn.get("is_god_file") for fn in real_fns if fn.get("file") == f_path
            ):
                god_chunked_files.add(f_path)

        def rank(text: str) -> int:
            t = text.lower()
            if t == needle:
                return 0
            if t.startswith(needle):
                return 1
            return 2 if needle in t else -1

        scored = []
        seen_files = set()
        for fn in real_fns:
            name, file_path = fn["name"], fn.get("file") or ""
            r = rank(name)
            if r < 0:
                continue
            chunk = None
            if file_path in god_chunked_files:
                chunk = fn.get("virtual_module")
                counts = by_scope.get((file_path, chunk), {})
            else:
                counts = file_counts.get(file_path, {})
            node_id = f"{name}:{fn.get('line_start')}" if counts.get(name, 1) > 1 else name
            scored.append((r, name.lower(), {
                "type": "function", "label": name, "node_id": node_id,
                "file": file_path, "chunk": chunk, "line_start": fn.get("line_start"),
                "risk_level": fn.get("risk_level", "none"), "service": fn.get("service"),
            }))
        for fn in real_fns:
            file_path = fn.get("file") or ""
            if not file_path or file_path in seen_files:
                continue
            seen_files.add(file_path)
            base = file_path.replace("\\", "/").rsplit("/", 1)[-1]
            r = rank(base)
            if r < 0 and needle in file_path.lower():
                r = 3
            if r < 0:
                continue
            scored.append((r, base.lower(), {
                "type": "file", "label": base, "node_id": file_path, "file": file_path,
                "chunk": None, "line_start": None, "risk_level": None,
                "service": fn.get("service"),
            }))

        scored.sort(key=lambda s: (s[0], s[1]))
        return {"results": [s[2] for s in scored[:limit]]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching: {str(e)}")


@app.get("/impact-analysis/{function_name}")
def api_impact_analysis(function_name: str, request: Request):
    """
    Reverse call graph: which functions/modules would be affected if
    `function_name` changes. Walks the caller chain transitively (BFS)
    over functions[].calls, the same data risk-score's fan_in is built from.
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        real_fns = [fn for fn in functions if fn.get("name") != "__file__"]

        if not any(fn.get("name") == function_name for fn in real_fns):
            raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found")

        # callee name -> list of caller function dicts
        callers_of: Dict[str, list] = {}
        for fn in real_fns:
            for callee in fn.get("calls", []):
                callers_of.setdefault(callee, []).append(fn)

        # BFS outward from function_name through the reverse-call edges
        visited = {function_name}
        depth_map: Dict[str, int] = {}
        queue = []
        for fn in callers_of.get(function_name, []):
            name = fn.get("name")
            if name not in visited:
                visited.add(name)
                depth_map[name] = 1
                queue.append(fn)

        affected = list(queue)
        i = 0
        while i < len(queue):
            fn = queue[i]
            i += 1
            depth = depth_map.get(fn.get("name"), 1)
            for caller in callers_of.get(fn.get("name"), []):
                cname = caller.get("name")
                if cname not in visited:
                    visited.add(cname)
                    depth_map[cname] = depth + 1
                    queue.append(caller)
                    affected.append(caller)

        affected.sort(key=lambda f: depth_map.get(f.get("name"), 1))
        direct_names = {fn.get("name") for fn in callers_of.get(function_name, [])}

        affected_files   = sorted({fn.get("file", "")   for fn in affected if fn.get("file")})
        affected_modules = sorted({fn.get("module", "") for fn in affected if fn.get("module")})

        result = [
            {
                "name":   fn.get("name"),
                "file":   fn.get("file"),
                "module": fn.get("module"),
                "depth":  depth_map.get(fn.get("name"), 1),
                "direct": fn.get("name") in direct_names,
            }
            for fn in affected[:100]
        ]

        return {
            "function":          function_name,
            "total_affected":    len(affected),
            "affected_functions": result,
            "affected_files":    affected_files,
            "affected_modules":  affected_modules,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Impact analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error computing impact analysis: {str(e)}")


@app.get("/dead-code")
def api_dead_code(request: Request, service_id: str | None = None):
    """Detect potentially unreachable functions and unused imports per file.

    Confidence levels:
    • high   — private function (name starts with _) with no detected callers.
               Very likely safe to remove.
    • medium — public function with no detected callers, OR a name pattern
               that suggests runtime invocation (callback, hook, listener…).
               May still be called via reflection, dynamic dispatch, external
               users, or polymorphism — review before removing.

    Cross-file calls within the uploaded codebase are already handled:
    fan_in counts callers across every parsed file, so a function called from
    another file in the project will have fan_in > 0 and is never flagged.
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache = SESSION_CACHE.get(session_id, {})
        functions = cache.get("functions", [])
        unused_imports: dict = cache.get("unused_imports", {})

        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]
            unused_imports = {k: v for k, v in unused_imports.items() if k.startswith(service_id + "/")}

        real_fns = [fn for fn in functions if fn.get("name") != "__file__"]

        def _suggestion(fn: dict) -> str:
            conf = fn.get("dead_confidence", "medium")
            if conf == "high":
                return (
                    f"'{fn['name']}' is a private function with no detected callers. "
                    "Safe to remove if not used via reflection or monkey-patching."
                )
            return (
                f"'{fn['name']}' has no detected callers within this codebase. "
                "Verify it is not called dynamically, via reflection, "
                "as a callback/event handler, or by external consumers before removing."
            )

        # Potentially unreachable functions, sorted: high confidence first
        dead_fns = sorted(
            [
                {
                    "name": fn["name"],
                    "file": fn["file"],
                    "language": fn.get("language"),
                    "line_start": fn.get("line_start"),
                    "line_end": fn.get("line_end"),
                    "dead_confidence": fn.get("dead_confidence", "medium"),
                    "suggestion": _suggestion(fn),
                }
                for fn in real_fns
                if fn.get("is_dead", False)
            ],
            key=lambda f: 0 if f["dead_confidence"] == "high" else 1,
        )

        high_count = sum(1 for f in dead_fns if f["dead_confidence"] == "high")
        medium_count = len(dead_fns) - high_count

        # Unused imports — only files that have at least one unused import
        unused_import_list = [
            {
                "file": file_path,
                "unused": names,
                "suggestion": f"Remove unused import(s): {', '.join(names)}",
            }
            for file_path, names in unused_imports.items()
            if names
        ]

        summary = {
            "high_confidence": high_count,
            "medium_confidence": medium_count,
            "total_unreachable": len(dead_fns),
            "files_with_unused_imports": len(unused_import_list),
            "total_unused_imports": sum(len(e["unused"]) for e in unused_import_list),
        }

        note = (
            "Static analysis only. Functions invoked via reflection, dynamic dispatch, "
            "polymorphism, or by external callers outside this upload cannot be detected "
            "and will appear here even if they are reachable at runtime."
        )

        return {
            "unreachable_functions": dead_fns,
            "unused_imports": unused_import_list,
            "summary": summary,
            "note": note,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dead code analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error running dead code analysis: {str(e)}")


@app.get("/layer-violations")
def api_layer_violations(request: Request, service_id: str | None = None):
    """Detect architectural layer violations in a multi-file project.

    Only meaningful for folder / ZIP uploads (single files are skipped).
    Returns per-module violation counts and a full violation list so the
    frontend can colour module nodes in the tier-1 graph.

    Rule: each layer may only call the layer DIRECTLY below it.
      Controller → Service → Repository → Model / DB
      Any layer  → Utility  (cross-cutting concern, always allowed)
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache = SESSION_CACHE.get(session_id, {})
        lv = cache.get("layer_violations", {})
        functions = cache.get("functions", [])

        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]

        # Build file → module_id map so we can group by tier-1 module
        file_module_map: dict = {}
        for fn in functions:
            fp = fn.get("file")
            mod = fn.get("module") or ""
            if fp and mod:
                file_module_map[fp] = mod

        raw_violations = lv.get("all_violations", [])
        if service_id:
            raw_violations = [v for v in raw_violations if v.get("source_file", "").startswith(service_id + "/")]
        by_module: dict = {}

        for v in raw_violations:
            src = v.get("source_file", "")
            mod_id = file_module_map.get(src) or str(Path(src).parent).replace("\\", "/")
            if mod_id not in by_module:
                by_module[mod_id] = {"count": 0, "severity": "medium", "items": []}
            by_module[mod_id]["count"] += 1
            by_module[mod_id]["items"].append(v)
            if v.get("severity") == "high":
                by_module[mod_id]["severity"] = "high"

        # Compact version for the frontend (no raw items, just count + severity)
        by_module_compact = {
            mod: {"count": data["count"], "severity": data["severity"]}
            for mod, data in by_module.items()
        }

        summary = lv.get("summary", {"total": 0, "high": 0, "medium": 0})
        if service_id:
            summary = {
                "total": len(raw_violations),
                "high": sum(1 for v in raw_violations if v.get("severity") == "high"),
                "medium": sum(1 for v in raw_violations if v.get("severity") == "medium"),
            }

        return {
            "by_module": by_module_compact,
            "violations": raw_violations,
            "summary": summary,
            "is_folder": len(cache.get("all_files", [])) > 1,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Layer violation analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error running layer violation analysis: {str(e)}")


@app.get("/metrics")
def api_metrics(request: Request):
    """Return Integrated Metrics Dashboard data for the current session."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        metrics = SESSION_CACHE.get(session_id, {}).get("metrics") or PARSED_CACHE.get("metrics") or {}
        return metrics if metrics else {"error": "Metrics not available — upload a project first."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/git-history")
def api_git_history(request: Request):
    """Return git commit history for the uploaded repository (ZIP with .git only)."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        git_history = SESSION_CACHE.get(session_id, {}).get("git_history")
        if not git_history:
            return {"available": False, "message": "No git repository detected in the upload."}
        return {"available": True, **git_history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Git history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Code Smell Analysis ──────────────────────────────────────────────────────

LAYER_DISPLAY_NAMES = {
    "function":     "Function Level",
    "module":       "Module / Class Level",
    "architecture": "Architecture Level",
}


def _group_smells_by_layer(smells: list) -> Dict[str, list]:
    """Feature 3: bucket smells by their SMELL_CAUSATION architecture layer."""
    grouped: Dict[str, list] = {name: [] for name in LAYER_DISPLAY_NAMES.values()}
    for s in smells:
        layer = SMELL_CAUSATION.get(s.type, {}).get("layer", "function")
        display = LAYER_DISPLAY_NAMES.get(layer, "Function Level")
        grouped[display].append(s.to_dict())
    return grouped


def _build_fix_tree(smells: list) -> list:
    """
    Feature 4: build upstream -> downstream smell trees (max depth 3).

    A smell type is a "root" if no other detected smell type lists it as
    downstream in SMELL_CAUSATION. A smell instance may appear under multiple
    root trees if it has multiple upstream parent types — that's expected.
    """
    by_type: Dict[str, list] = {}
    for s in smells:
        by_type.setdefault(s.type, []).append(s)

    detected_types = set(by_type.keys())
    downstream_types: set = set()
    for t in detected_types:
        for ds_type in SMELL_CAUSATION.get(t, {}).get("downstream", []):
            if ds_type in detected_types:
                downstream_types.add(ds_type)
    root_types = detected_types - downstream_types

    def build_node(smell, depth: int) -> Dict:
        node = {
            "smell_id":    smell.smell_id,
            "type":        smell.type,
            "target_name": smell.target_name,
            "severity":    smell.severity,
            "children":    [],
        }
        if depth >= 3:
            return node
        for ds_type in SMELL_CAUSATION.get(smell.type, {}).get("downstream", []):
            for child in by_type.get(ds_type, []):
                node["children"].append(build_node(child, depth + 1))
        return node

    return [build_node(s, 1) for s in smells if s.type in root_types]


@app.get("/smell-analysis")
async def api_smell_analysis(request: Request, service_id: str | None = None):
    """
    Run static-analysis code smell detection + build smell dependency graph.

    Pipeline (no LLM for detection — pure static analysis):
      1. SmellDetector.detect_all()     — metric-based smell instances
      2. build_smell_graph()            — dependency graph + BFS root-cause scoring
      3. graph.minimal_fix_plan()       — greedy set-cover, ranked by ROI (resolves/effort)
      4. LLM before/after code preview  — top-3 plan items only, fetched concurrently

    Call /llm-refactor-reason after this for full LLM architectural reasoning.
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache     = SESSION_CACHE.get(session_id, {})
        functions = cache.get("functions", [])
        metrics   = cache.get("metrics",   {})

        if service_id:
            functions = [fn for fn in functions if fn.get("service") == service_id]

        if not functions:
            return {"smells": [], "summary": {}, "graph_summary": {}, "plan": [],
                    "fn_smell_map": {}, "smells_by_layer": {}, "fix_tree": [],
                    "total_debt_score": 0, "estimated_dev_days": 0.0,
                    "message": "No functions found — upload a project first."}

        # ── Static analysis: detect smells ───────────────────────────────────
        detector = SmellDetector()
        cycles   = [
            c.split(" → ")
            for c in metrics.get("circular_dep_details", [])
            if c
        ]
        smells = detector.detect_all(functions, metrics, cycles)

        # ── Build smell dependency graph + score root causes ─────────────────
        graph = build_smell_graph(smells)

        # ── Greedy set-cover plan, ranked by ROI (Feature 1) ──────────────────
        plan = graph.minimal_fix_plan(max_steps=10)

        # ── Build severity summary ────────────────────────────────────────────
        summary: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": len(smells)}
        fn_smell_map: Dict[str, str] = {}   # function_name → worst severity
        for s in smells:
            summary[s.severity] = summary.get(s.severity, 0) + 1
            existing = fn_smell_map.get(s.target_name)
            if not existing or ["critical","high","medium","low"].index(s.severity) \
               < ["critical","high","medium","low"].index(existing):
                fn_smell_map[s.target_name] = s.severity

        graph_summary = graph.to_llm_summary()

        # ── Feature 1: total debt score + estimated dev days ──────────────────
        total_debt_score = sum(
            SEVERITY_WEIGHTS.get(s.severity, 1) * SMELL_CAUSATION.get(s.type, {}).get("effort", 2)
            for s in smells
        )
        estimated_dev_days = round(total_debt_score / 24, 1)

        # ── Feature 3: group smells by architecture layer ─────────────────────
        smells_by_layer = _group_smells_by_layer(smells)

        # ── Feature 4: dependency-aware fix tree ───────────────────────────────
        fix_tree = _build_fix_tree(smells)

        # ── Feature 2: before/after code preview for top-3 ROI plan items ─────
        smell_by_id = {s.smell_id: s for s in smells}
        top3 = plan[:3]
        schedulable = []   # (plan_item, coroutine)
        for item in top3:
            s = smell_by_id.get(item["smell_id"])
            if s and s.refactor_suggestions:
                schedulable.append((item, asyncio.to_thread(
                    llm_engine.get_code_preview,
                    s.type, s.target_name, s.metrics,
                    s.refactor_suggestions[0], s.language,
                )))
            else:
                item["code_preview"] = None
        if schedulable:
            previews = await asyncio.gather(
                *(coro for _, coro in schedulable), return_exceptions=True,
            )
            for (item, _), preview in zip(schedulable, previews):
                item["code_preview"] = preview if isinstance(preview, dict) else None
        for item in plan[3:]:
            item["code_preview"] = None

        # ── Cache for /llm-refactor-reason ───────────────────────────────────
        cache["_smells"]        = [s.to_dict() for s in smells]
        cache["_smell_plan"]    = plan
        cache["_smell_summary"] = graph_summary
        cache["_fn_smell_map"]  = fn_smell_map

        return {
            "smells":             [s.to_dict() for s in smells],
            "summary":            summary,
            "graph_summary":      graph_summary,
            "plan":               plan,
            "fn_smell_map":       fn_smell_map,
            "smells_by_layer":    smells_by_layer,
            "fix_tree":           fix_tree,
            "total_debt_score":   round(total_debt_score, 2),
            "estimated_dev_days": estimated_dev_days,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smell analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm-refactor-reason")
async def api_llm_refactor(request: Request):
    """
    Get LLM architectural reasoning for the smell analysis.
    Requires /smell-analysis to have been called first.

    The LLM receives ONLY structured smell data (not raw code).
    It reasons about: root cause, architectural patterns, refactor ordering, risk.
    """
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache         = SESSION_CACHE.get(session_id, {})
        graph_summary = cache.get("_smell_summary")
        plan          = cache.get("_smell_plan", [])
        metrics       = cache.get("metrics", {})

        if not graph_summary:
            raise HTTPException(
                status_code=400,
                detail="Run GET /smell-analysis first to generate smell data.",
            )

        project_context = {
            "total_files":            metrics.get("total_files", 0),
            "total_functions":        metrics.get("total_functions", 0),
            "avg_cyclomatic":         metrics.get("avg_cyclomatic", 0),
            "max_call_chain_depth":   metrics.get("max_call_chain_depth", 0),
        }

        llm_plan = llm_engine.get_refactor_plan(graph_summary, plan, project_context)

        return {
            "llm_plan":    llm_plan,
            "static_plan": plan,
            "source":      llm_plan.get("_source", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM refactor error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patterns/{session_id}")
async def api_detect_patterns(session_id: str, service_id: str | None = None):
    """
    Detect architecture patterns in a previously uploaded project.
    Rule-based, no LLM. Returns patterns with confidence >= 0.55.
    """
    try:
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache = SESSION_CACHE.get(session_id)
        if not cache:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found. Upload a project first.",
            )

        # Build flat file list from all_files
        raw_functions: list = cache.get("functions", [])
        all_files_cache: list = cache.get("all_files", [])
        if service_id:
            raw_functions = [fn for fn in raw_functions if fn.get("service") == service_id]
            all_files_cache = [f for f in all_files_cache if f.get("service") == service_id]
        files: list[str] = [f["path"] for f in all_files_cache]

        # Derive call_edges from functions[].calls
        fn_name_to_file: dict[str, str] = {
            fn["name"]: fn.get("file", "") for fn in raw_functions
        }
        call_edges: list[dict] = []
        for fn in raw_functions:
            for callee_name in fn.get("calls", []):
                call_edges.append({
                    "caller_file":     fn.get("file", ""),
                    "caller_function": fn.get("name", ""),
                    "callee_function": callee_name,
                    "callee_file":     fn_name_to_file.get(callee_name, ""),
                })

        session_data = {
            "files":      files,
            "functions":  raw_functions,
            "call_edges": call_edges,
        }

        detector = ArchitecturePatternDetector(session_data)
        patterns = detector.detect_all()

        return {
            "session_id":     session_id,
            "patterns_found": len(patterns),
            "patterns":       patterns,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pattern detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gof-patterns/{session_id}")
async def api_detect_gof_patterns(session_id: str):
    """
    Detect GoF design patterns in a previously uploaded project. Rule-based,
    no LLM — evaluates declarative rule specs (patterns/specs/*.yaml)
    against the class/interface graph in Neo4j (populated by
    store_class_graph() at upload time), not SESSION_CACHE.

    Singleton/Observer/Factory/Facade are structural specs here too (see
    patterns/specs/singleton.yaml etc.) — no naming/keyword heuristics
    anywhere in this endpoint. ArchitecturePatternDetector (MVC, Layered,
    Clean Architecture, Hexagonal, Repository) is a separate, untouched
    system exclusive to /api/patterns.

    Also merges in Go/Rust Singleton language-idiom matches (sync.Once,
    lazy_static!, OnceCell/OnceLock — computed at upload time and cached,
    see patterns/language_idioms/singleton_idioms.py) as a separate,
    explicitly `"heuristic": true`-flagged addition. These never blend into
    the structural rule engine's tier/confidence scoring — they're a
    genuinely different kind of evidence (a language keyword/macro match,
    not a graph shape) and the UI should render them distinctly.
    """
    try:
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        cache = SESSION_CACHE.get(session_id, {})
        idiom_patterns = [
            {
                "pattern":         "Singleton (language idiom)",
                "category":        "Creational",
                "tier":            "heuristic",
                "confidence":      None,
                "bindings":        {"file": m["file"]},
                "evidence":        [f"{m['idiom']} found in {m['file']}:{m['line']}"],
                "evidence_detail": [{
                    "predicate": "language_idiom", "label": "Language idiom",
                    "role": None, "strength": None,
                    "evidence": [f"{m['idiom']} found in {m['file']}:{m['line']}"],
                }],
                "heuristic":       True,
                **pattern_info("Singleton (language idiom)"),
            }
            for m in cache.get("singleton_idiom_matches", [])
        ]

        raw_graph = get_class_graph(session_id)
        structural_patterns = []
        if raw_graph.get("classes"):
            view = SessionGraphView.from_raw(raw_graph)
            matches = evaluate_all(view)
            structural_patterns = [
                {
                    "pattern":         m.pattern,
                    "category":        m.category,
                    "tier":            m.tier,
                    "confidence":      m.confidence,
                    "bindings":        m.bindings,
                    "evidence":        m.evidence,
                    "evidence_detail": m.evidence_detail,
                    "heuristic":       False,
                    **pattern_info(m.pattern),
                }
                for m in matches
            ]

        # evaluate_all() already returns structural_patterns sorted by
        # confidence, but re-assert it explicitly at the API boundary once
        # idiom_patterns (confidence: None, always heuristic) are merged in —
        # highest-confidence structural match first, heuristic entries last.
        patterns = sorted(
            structural_patterns + idiom_patterns,
            key=lambda p: p["confidence"] if p["confidence"] is not None else -1.0,
            reverse=True,
        )
        return {
            "session_id":     session_id,
            "patterns_found": len(patterns),
            "patterns":       patterns,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GoF pattern detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== DYNAMIC ANALYSIS (Python-only) ==========
# session_id comes from the X-Session-ID header like every other route above —
# not from the URL — so `function_node_id` alone identifies the target, encoded
# as "<file_path>::<function_name>" (function names can't contain "::", so
# splitting on the last occurrence is unambiguous even if a file_path did).

def _split_function_node_id(function_node_id: str) -> tuple[str, str]:
    if "::" not in function_node_id:
        raise HTTPException(status_code=400, detail="malformed function_node_id (expected '<file_path>::<function_name>')")
    file_path, function_name = function_node_id.rsplit("::", 1)
    return file_path, function_name


def _require_python_function(session_id: str, file_path: str, function_name: str) -> None:
    fn = get_function_node(session_id, file_path, function_name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"function '{function_name}' not found in {file_path}")
    if fn.get("language") != "python":
        raise HTTPException(status_code=400, detail="dynamic analysis is only supported for Python functions")


@app.post("/dynamic/functions/{function_node_id:path}/params")
def api_dynamic_params(request: Request, function_node_id: str):
    """Param names + type hints for the auto-generated input form (re-parses
    the function's persisted source — Python functions carry no params on
    their Function node; see dynamic_analysis/params.py)."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        file_path, function_name = _split_function_node_id(function_node_id)
        _require_python_function(session_id, file_path, function_name)

        upload_dir = str(DYNAMIC_SOURCE_DIR / session_id)
        return dynamic_runner.get_function_params(session_id, upload_dir, file_path, function_name)

    except HTTPException:
        raise
    except FunctionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Dynamic-analysis params error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dynamic/functions/{function_node_id:path}/run")
async def api_dynamic_run(request: Request, function_node_id: str):
    """Executes the target function in the sandbox with the given inputs and
    returns the traced execution (see dynamic_analysis/runner.py, sandbox.py)."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        file_path, function_name = _split_function_node_id(function_node_id)
        _require_python_function(session_id, file_path, function_name)

        body = await request.json()
        inputs = body.get("inputs", {})
        upload_dir = str(DYNAMIC_SOURCE_DIR / session_id)
        run_id = str(uuid.uuid4())

        return dynamic_runner.run_dynamic_function(session_id, upload_dir, file_path, function_name, inputs, run_id)

    except HTTPException:
        raise
    except (FunctionNotFoundError, UnsupportedFunctionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Dynamic-analysis run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dynamic/runs/{run_id}/slice")
async def api_dynamic_slice(request: Request, run_id: str):
    """Backward program slice for one (statement, variable) criterion within
    an already-completed run (see dynamic_analysis/slicer.py)."""
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        body = await request.json()
        statement_node_id = body.get("statement_node_id")
        variable_name = body.get("variable_name")
        if not statement_node_id or not variable_name:
            raise HTTPException(status_code=400, detail="statement_node_id and variable_name are required")

        return dynamic_runner.compute_slice_for_run(session_id, run_id, statement_node_id, variable_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Dynamic-analysis slice error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
