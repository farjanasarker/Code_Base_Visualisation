import os
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
from db import clear_graph, get_full_graph, get_neighbors, store_all, get_tier1, get_tier2, get_tier3, get_all_files_graph, delete_session_data
from analyzer import analyze_files, build_module_graph, decide_render_strategy, build_all_files_graph
import logging

logger = logging.getLogger(__name__)

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
                    all_files = walk_folder(str(extract_path))
                else:
                    single_path = Path(tmpdir) / file_name
                    single_path.parent.mkdir(parents=True, exist_ok=True)
                    single_path.write_bytes(file_bytes)
                    all_files = walk_folder(tmpdir)

            elif files:
                folder_root = Path(tmpdir) / "folder_upload"
                await persist_folder_upload(files, str(folder_root))
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

        functions = analyze_files(all_files)

        # Update session's file list
        session_info["files"] = [f["path"] for f in all_files]

        # cache parsed functions and raw file list for this session
        try:
            tier1 = build_module_graph(functions)
            SESSION_CACHE[session_id] = {
                "functions": functions,
                "tier1": tier1,
                # store raw file info (without content) for fallback file graph
                "all_files": [{"path": f["path"], "language": f["language"]} for f in all_files],
            }
            
            # Also update global cache for fallback
            PARSED_CACHE["functions"] = functions
            PARSED_CACHE["tier1"] = tier1
            
        except Exception:
            logger.exception(f"Failed to cache parsed functions for session {session_id}")

        # Persist to Neo4j with session_id (best-effort)
        try:
            store_all(functions, session_id, all_files)
            logger.info(f"✅ Stored graph to Neo4j for session {session_id}")
        except Exception:
            logger.exception(f"⚠️ Failed to store graph to Neo4j for session {session_id}")

        tier1 = SESSION_CACHE.get(session_id, {}).get("tier1") or PARSED_CACHE.get("tier1") or build_module_graph(functions)
        render = decide_render_strategy(len(tier1["nodes"]))

        return {
            "message": "Graph generated",
            "status": "success",
            "session_id": session_id,
            "tier1_graph": tier1,
            "render_strategy": render,
            "total_functions": len(functions),
            "total_files": len(all_files),
        }
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


@app.get("/graph/tier1")
def api_tier1(request: Request):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)
        
        return get_tier1(session_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier1 from DB for session {session_id}")
        # fallback to session cache
        tier = SESSION_CACHE.get(session_id, {}).get("tier1")
        if tier:
            return tier
        raise HTTPException(status_code=500, detail="Error fetching tier1 graph and no cache available")


@app.get("/graph/tier2/{module_name:path}")
def api_tier2(request: Request, module_name: str):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)
        
        return get_tier2(module_name, session_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier2 from DB for session {session_id}")
        # fallback: build from session cache
        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
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
def api_tier3(request: Request, file_path: str):
    try:
        session_id = request.headers.get("X-Session-ID")
        session_id = validate_session(session_id)
        update_session_activity(session_id)

        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if functions:
            from analyzer import build_function_graph
            graph = build_function_graph(file_path, functions)
            if graph.get("nodes"):
                return graph

        return get_tier3(file_path, session_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to fetch tier3 from DB for session {session_id}")
        # fallback: build from session cache
        functions = SESSION_CACHE.get(session_id, {}).get("functions", [])
        if functions:
            from analyzer import build_function_graph
            return build_function_graph(file_path, functions)
        raise HTTPException(status_code=500, detail="Error fetching tier3 graph and no cache available")


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