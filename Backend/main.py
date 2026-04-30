import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from analyzer import analyze_files, build_module_graph, decide_render_strategy
from db import clear_graph, get_full_graph, get_neighbors, store_all, get_tier1, get_tier2, get_tier3
import logging

logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory cache of last parsed upload (used when Neo4j is unavailable)
PARSED_CACHE: dict = {"functions": [], "tier1": None}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILE_SIZE = 500 * 1024  # 500KB per source file
MAX_FILE_COUNT = 1000
MAX_DEPTH = 10

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
}

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

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (or specify ["http://localhost:5173", "http://127.0.0.1:5173"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "Backend is running"}


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


def handle_zip(zip_path: str, extract_to: str) -> str:
    extract_root = Path(extract_to).resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        if len(members) > MAX_FILE_COUNT:
            raise ValueError("Too many files in ZIP")

        for info in members:
            member = info.filename
            member_parts = Path(member).parts

            if len(member_parts) > MAX_DEPTH:
                raise ValueError(f"Path too deep in ZIP: {member}")

            member_path = (extract_root / member).resolve()
            if not str(member_path).startswith(str(extract_root)):
                raise ValueError(f"Zip slip detected: {member}")

            if not member.endswith("/") and info.file_size > MAX_FILE_SIZE:
                raise ValueError(f"File too large inside ZIP: {member}")

        zf.extractall(extract_root)

    return str(extract_root)


def walk_folder(root_path: str) -> list[dict]:
    files = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

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
                    "path": str(filepath.relative_to(root_path)),
                    "language": detect_language(ext),
                    "size": size,
                    "content": content,
                }
            )

            if len(files) > MAX_FILE_COUNT:
                raise ValueError("Too many source files")

    return files


def sanitize_relative_path(raw_name: str) -> Path:
    rel_path = Path(raw_name)

    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"Unsafe upload path: {raw_name}")

    if len(rel_path.parts) > MAX_DEPTH:
        raise ValueError(f"Path too deep: {raw_name}")

    return rel_path


async def persist_folder_upload(files: list[UploadFile], destination_root: str) -> None:
    if len(files) > MAX_FILE_COUNT:
        raise ValueError("Too many uploaded files")

    root_path = Path(destination_root)
    root_path.mkdir(parents=True, exist_ok=True)

    for uploaded in files:
        file_name = uploaded.filename or ""
        safe_rel_path = sanitize_relative_path(file_name)
        ext = safe_rel_path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS or ext == ".zip":
            continue

        file_bytes = await uploaded.read()
        validate_upload(file_name, len(file_bytes))

        target = (root_path / safe_rel_path).resolve()
        if not str(target).startswith(str(root_path.resolve())):
            raise ValueError(f"Unsafe target path: {file_name}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_bytes)


@app.post("/upload")
async def upload(
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            clear_graph()

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

        if not all_files:
            raise HTTPException(status_code=400, detail="No supported source files found")

        functions = analyze_files(all_files)

        # cache parsed functions for fallback
        try:
            PARSED_CACHE["functions"] = functions
            PARSED_CACHE["tier1"] = build_module_graph(functions)
        except Exception:
            logger.exception("Failed to cache parsed functions")

        # Persist richer graph to Neo4j (best-effort)
        try:
            store_all(functions)
        except Exception:
            # non-fatal: log and continue
            logger.exception("Failed to store full graph to Neo4j")

        tier1 = PARSED_CACHE.get("tier1") or build_module_graph(functions)
        render = decide_render_strategy(len(tier1["nodes"]))

        return {
            "message": "Graph generated",
            "status": "success",
            "tier1_graph": tier1,
            "render_strategy": render,
            "total_functions": len(functions),
            "total_files": len(all_files),
        }
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/expand/{function_name}")
def expand(function_name: str):
    try:
        neighbors = get_neighbors(function_name)
        return {
            "nodes": [{"id": n} for n in neighbors],
            "edges": [
                {"source": function_name, "target": n}
                for n in neighbors
            ]
        }
    except Exception as e:
        logger.error(f"Expand error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching graph: {str(e)}")


@app.get("/graph/tier1")
def api_tier1():
    try:
        return get_tier1()
    except Exception:
        logger.exception("Failed to fetch tier1 from DB, falling back to cache")
        # fallback to cached parsed functions
        tier = PARSED_CACHE.get("tier1")
        if tier:
            return tier
        raise HTTPException(status_code=500, detail="Error fetching tier1 graph and no cache available")


@app.get("/graph/tier2/{module_name}")
def api_tier2(module_name: str):
    try:
        return get_tier2(module_name)
    except Exception:
        logger.exception("Failed to fetch tier2 from DB, falling back to cache")
        # fallback: build from cached parsed functions
        functions = PARSED_CACHE.get("functions", [])
        if functions:
            from analyzer import build_file_graph
            return build_file_graph(module_name, functions)
        raise HTTPException(status_code=500, detail="Error fetching tier2 graph and no cache available")


@app.get("/graph/tier3")
def api_tier3(file_path: str):
    try:
        return get_tier3(file_path)
    except Exception:
        logger.exception("Failed to fetch tier3 from DB, falling back to cache")
        functions = PARSED_CACHE.get("functions", [])
        if functions:
            from analyzer import build_function_graph
            return build_function_graph(file_path, functions)
        raise HTTPException(status_code=500, detail="Error fetching tier3 graph and no cache available")