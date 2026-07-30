"""Architecture-layer detection and layer-violation rules.

Detects which architectural layer (router/controller/service/repository/
model/database/middleware/utility) a file or import reference belongs to
from naming conventions, then flags imports that skip layers, go against
the stack, or couple same-layer modules directly.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Layer Violation Detection ───────────────────────────────────────────────
#
# Architecture rule: each layer may only call the layer DIRECTLY below it.
# Allowed:  Controller → Service → Repository → Model/DB
# Allowed:  Any layer  → Utility (cross-cutting concern)
# Allowed:  Middleware → Service (auth/authz checks)
# Violation: skipping a layer, calling a higher layer, or cross-repo deps.
#
# Cross-file calls WITHIN the upload are detected via relative import paths.
# Only meaningful for multi-file uploads (folder / ZIP containing a folder).

_LAYER_KEYWORDS: Dict[str, frozenset] = {
    # ── Router: URL mapping only — calls controllers & applies middlewares ──
    "router": frozenset({
        "route", "routes", "router", "routers", "routing", "routings",
    }),
    # ── Controller: HTTP request/response handling ───────────────────────────
    "controller": frozenset({
        "controller", "controllers",
        "handler", "handlers",
        "api",
        "view", "views",
        "presenter", "presenters",
        "endpoint", "endpoints",
        "resource", "resources",
        "rest",
        "graphql", "resolver", "resolvers",
        "action", "actions",
        "command", "commands",
        "request", "requests", "response", "responses",
    }),
    # ── Service: business / application logic ───────────────────────────────
    "service": frozenset({
        "service", "services", "usecase", "usecases", "use_case", "use_cases",
        "business", "interactor", "interactors", "application",
        "manager", "managers", "facade", "facades", "processor", "processors",
        "workflow", "workflows", "orchestrator", "orchestrators",
    }),
    # ── Repository: data-access layer ───────────────────────────────────────
    "repository": frozenset({
        "repository", "repositories", "repo", "repos", "dao", "daos",
        "store", "stores", "storage", "gateway", "gateways", "finder", "finders",
    }),
    # ── Model: domain objects / schemas ─────────────────────────────────────
    "model": frozenset({
        "model", "models", "entity", "entities", "schema", "schemas",
        "dto", "dtos", "struct", "structs", "domain",
        "aggregate", "aggregates", "valueobject", "value_object",
    }),
    # ── Database: raw DB access, migrations, ORM config ─────────────────────
    "database": frozenset({
        "db", "database", "databases", "migration", "migrations",
        "seed", "seeds", "connection", "connections", "orm",
        "datasource", "data_source", "infrastructure", "infra",
        "persistence", "adapter", "adapters", "query", "queries",
    }),
    # ── Middleware: cross-cutting (auth, logging, validation, guards) ────────
    "middleware": frozenset({
        "middleware", "middlewares", "interceptor", "interceptors",
        "guard", "guards", "filter", "filters", "hook", "hooks",
        "plugin", "plugins", "decorator", "decorators",
    }),
    # ── Utility: shared helpers, config, constants ───────────────────────────
    "utility": frozenset({
        "util", "utils", "utility", "utilities", "helper", "helpers",
        "shared", "common", "lib", "libs", "constant", "constants",
        "config", "configs", "configuration", "logger", "logging",
        "log", "exception", "exceptions", "error", "errors",
        "validator", "validators", "validation", "formatter", "formatters",
        "converter", "converters", "mapper", "mappers", "types", "type",
    }),
}

# Lower number = higher in the architecture stack (closest to user)
_LAYER_ORDER: Dict[str, int] = {
    "router":     0,   # routes/  — URL mapping, topmost layer
    "controller": 1,   # controllers/
    "middleware": 2,   # middlewares/ — applied between router and service
    "service":    3,   # services/
    "repository": 4,   # repositories/
    "model":      5,   # models/
    "database":   5,   # db/
    "utility":    -1,  # cross-cutting: allowed from any layer
    "unknown":    -2,
}


def _detect_file_layer(file_path: str) -> str:
    """Return the architectural layer of a source file from its path."""
    parts = Path(file_path.replace("\\", "/")).parts
    stem = Path(file_path).stem.lower()

    # Check folder names from most-specific (deepest) to root
    for part in reversed(parts[:-1]):
        p = part.lower()
        for layer, kws in _LAYER_KEYWORDS.items():
            if p in kws:
                return layer

    # Fallback: check filename stem (e.g. userController.js, UserService.java)
    for layer, kws in _LAYER_KEYWORDS.items():
        for kw in kws:
            if stem.endswith(kw) or stem.startswith(kw):
                return layer

    return "unknown"


def _detect_import_layer(import_ref: str) -> str:
    """Return the architectural layer that an import reference points to."""
    ref = import_ref.lower().replace("\\", "/")
    # Strip common extensions
    for ext in (".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".rs", ".cs", ".cpp", ".c"):
        if ref.endswith(ext):
            ref = ref[: -len(ext)]
            break

    # Split on / and . to get individual name segments
    parts = [p for p in re.split(r"[/.]", ref) if p and p not in ("", "..")]

    for part in reversed(parts):   # most-specific segment first
        for layer, kws in _LAYER_KEYWORDS.items():
            if part in kws:
                return layer
            for kw in kws:
                if part.endswith(kw) or part.startswith(kw):
                    return layer

    return "unknown"


# Explicit allowed downward transitions — the only source of truth for what is OK.
# We use an explicit dict (not numeric gaps) so that valid long jumps like
# Controller → Service are never flagged just because a numeric gap > 1.
_ALLOWED_TRANSITIONS: Dict[str, frozenset] = {
    # Router maps URLs → calls Controllers and applies Middlewares
    "router":     frozenset({"controller", "middleware", "utility"}),
    # Controller handles HTTP → calls Services
    "controller": frozenset({"service", "utility"}),
    # Middleware (auth, logging, guards) → calls Services
    "middleware": frozenset({"service", "utility"}),
    # Service (business logic) → calls Repositories or Models
    "service":    frozenset({"repository", "model", "utility", "service"}),
    # Repository (data access) → Model definitions or raw DB
    "repository": frozenset({"model", "database", "utility"}),
    "model":      frozenset({"utility"}),
    "database":   frozenset({"utility"}),
    "utility":    frozenset({"utility"}),
}


def _check_layer_violation(src_layer: str, tgt_layer: str) -> Optional[Dict]:
    """Return a violation dict or None if the src→tgt import is acceptable.

    Uses an explicit allowed-transition table instead of numeric gaps so that
    Controller → Service (which is correct) is never flagged as a skip.
    """
    if src_layer in ("unknown", "utility") or tgt_layer in ("unknown", "utility", "router"):
        return None   # cross-cutting, indeterminate, or nobody imports router → skip

    # Explicitly allowed: no violation
    if tgt_layer in _ALLOWED_TRANSITIONS.get(src_layer, frozenset()):
        return None

    src_ord = _LAYER_ORDER[src_layer]
    tgt_ord = _LAYER_ORDER[tgt_layer]

    # Going UP the stack — reverse dependency
    if tgt_ord < src_ord:
        return {
            "type": "reverse_dependency",
            "severity": "high",
            "message": (
                f"{src_layer.title()} imports from {tgt_layer.title()} "
                f"— reverse dependency (going up the stack)"
            ),
        }

    # Same-level cross dependency (e.g. Repository → Repository)
    if tgt_ord == src_ord:
        return {
            "type": "cross_layer",
            "severity": "medium",
            "message": (
                f"{src_layer.title()} imports another {tgt_layer.title()} directly "
                f"— same-layer coupling"
            ),
        }

    # Going DOWN but not to an allowed layer — skipping layers
    return {
        "type": "layer_skip",
        "severity": "high",
        "message": (
            f"{src_layer.title()} skips directly to {tgt_layer.title()} "
            f"— intermediate layer(s) bypassed"
        ),
    }


def _compute_layer_violations(
    files: List[Dict],
    module_map: Dict[str, str],
    file_import_map: Dict[str, List[str]],
) -> Dict:
    """Compute layer violations for all files.

    Only meaningful for multi-file uploads (folder / ZIP with a folder).
    Returns {by_module: {module_id: {count, severity, items}}, summary, all_violations}.
    """
    if len(files) <= 1:
        return {"by_module": {}, "summary": {"total": 0, "high": 0, "medium": 0}, "all_violations": []}

    all_violations: List[Dict] = []

    for raw_path, imports in file_import_map.items():
        if not imports:
            continue
        norm_path = raw_path.replace("\\", "/")
        src_layer = _detect_file_layer(norm_path)
        if src_layer in ("unknown", "utility"):
            continue

        for imp in imports:
            tgt_layer = _detect_import_layer(imp)
            violation = _check_layer_violation(src_layer, tgt_layer)
            if violation:
                all_violations.append({
                    "source_file": norm_path,
                    "source_layer": src_layer,
                    "target_ref": imp,
                    "target_layer": tgt_layer,
                    **violation,
                })

    # Group by module_id (matches tier1 graph node IDs)
    by_module: Dict[str, Any] = {}
    for v in all_violations:
        raw_src = v["source_file"]
        mod_id = module_map.get(raw_src) or module_map.get(raw_src.replace("/", "\\")) or str(Path(raw_src).parent)
        if mod_id not in by_module:
            by_module[mod_id] = {"count": 0, "severity": "medium", "items": []}
        by_module[mod_id]["count"] += 1
        by_module[mod_id]["items"].append(v)
        if v["severity"] == "high":
            by_module[mod_id]["severity"] = "high"

    summary = {
        "total": len(all_violations),
        "high": sum(1 for v in all_violations if v["severity"] == "high"),
        "medium": sum(1 for v in all_violations if v["severity"] == "medium"),
    }

    return {"by_module": by_module, "summary": summary, "all_violations": all_violations}
