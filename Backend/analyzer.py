from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import importlib
import ast
import logging
import math
import re

from db import add_edge

logger = logging.getLogger(__name__)


# ── Unreachable-code detection helpers ─────────────────────────────────────
#
# A function with fan_in == 0 is NOT necessarily dead.  It may be:
#   • An OS / framework entry point  (main, __init__, …)
#   • A callback / event handler     (onClick, on_message, …)
#   • A runtime-reflected call       (getattr, importlib, …)   ← can't detect
#   • A library public API           (called by external users) ← can't detect
#   • A virtual/override method      (called via polymorphism)  ← hard to detect
#   • Called from a file we did NOT analyse (cross-project)
#
# Cross-file calls WITHIN the uploaded codebase ARE already handled:
# compute_fan_in() aggregates calls across every parsed file, so a function
# called from another file will have fan_in > 0 and will never appear here.
#
# What we CAN do statically is flag functions that have none of the above
# characteristics as "potentially unreachable" with a confidence level.

# 1. Known entry-point names — definitively not dead
_ENTRY_POINT_NAMES: frozenset = frozenset({
    "main", "init", "run", "start", "stop", "shutdown", "close",
    # Python dunder / magic methods (all __x__ are handled separately)
    "__init__", "__new__", "__del__", "__repr__", "__str__", "__bytes__",
    "__format__", "__hash__", "__bool__", "__len__", "__iter__", "__next__",
    "__call__", "__enter__", "__exit__", "__getitem__", "__setitem__",
    "__delitem__", "__contains__", "__missing__", "__reversed__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
    "__add__", "__radd__", "__iadd__", "__mul__", "__rmul__", "__imul__",
    "__sub__", "__rsub__", "__isub__", "__truediv__", "__floordiv__",
    "__mod__", "__pow__", "__lshift__", "__rshift__", "__and__", "__or__",
    "__xor__", "__int__", "__float__", "__complex__", "__index__",
    "__abs__", "__neg__", "__pos__", "__invert__", "__round__",
    "__trunc__", "__floor__", "__ceil__",
    "__aiter__", "__anext__", "__aenter__", "__aexit__",
    "__await__", "__get__", "__set__", "__delete__", "__set_name__",
    "__class_getitem__", "__init_subclass__", "__subclasshook__",
    "__sizeof__", "__reduce__", "__reduce_ex__", "__copy__", "__deepcopy__",
    "__getstate__", "__setstate__",
    # Test-framework lifecycle
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "setUpModule", "tearDownModule", "runTest",
    # Web / serverless entry points
    "handler", "lambda_handler", "application", "wsgi_app",
    "create_app", "make_app", "configure", "bootstrap", "app_factory",
    # OOP override candidates (common interface methods)
    "toString", "hashCode", "equals", "compareTo", "compare",
    "clone", "finalize", "run", "execute", "call",
    # React / Vue / Angular lifecycle
    "render", "componentDidMount", "componentWillUnmount",
    "componentDidUpdate", "shouldComponentUpdate",
    "getDerivedStateFromProps", "getSnapshotBeforeUpdate",
    "mounted", "created", "destroyed", "updated",
    "beforeMount", "beforeCreate", "beforeDestroy", "beforeUpdate",
    "ngOnInit", "ngOnDestroy", "ngOnChanges", "ngAfterViewInit",
    "ngAfterContentInit", "ngDoCheck",
    # Django / Flask / FastAPI views
    "get", "post", "put", "patch", "delete", "head", "options",
    # Go
    "init", "main", "ServeHTTP", "String", "Error",
    # Rust
    "new", "default", "fmt", "from", "into", "drop",
})

# 2. Prefix / suffix patterns that strongly suggest runtime invocation
_ENTRY_POINT_PREFIXES: tuple = (
    "test_", "Test", "spec_", "it_", "should_", "given_", "when_", "then_",
    "on_", "On", "handle_", "Handle",
    "before_", "after_", "pre_", "post_",
    "middleware_", "fixture_", "plugin_",
    "register_", "setup_", "init_",
    "dispatch_", "emit_", "notify_", "receive_",
    "visit_",       # Visitor pattern
)

# 3. Name patterns that suggest the function is invoked at runtime (callback, hook, etc.)
#    These lower the confidence to "medium" rather than "high".
_RUNTIME_INVOKE_SUFFIXES: tuple = (
    "Handler", "handler", "Callback", "callback",
    "Listener", "listener", "Hook", "hook",
    "Action", "action", "Event", "event",
    "Trigger", "trigger", "Observer", "observer",
    "Middleware", "middleware", "Interceptor", "interceptor",
    "Decorator", "decorator", "Wrapper", "wrapper",
    "Resolver", "resolver", "Plugin", "plugin",
)
_RUNTIME_INVOKE_KEYWORDS: tuple = (
    "onClick", "onChange", "onSubmit", "onLoad", "onError",
    "onSuccess", "onFailure", "onComplete", "onDone", "onReady",
    "onKeyUp", "onKeyDown", "onMouseOver", "onMouseOut",
    "onFocus", "onBlur", "onScroll", "onResize",
)


def _is_entry_point(name: str) -> bool:
    """Return True when a function is a known entry point and must not be flagged."""
    if name in _ENTRY_POINT_NAMES:
        return True
    if name.startswith("__") and name.endswith("__"):   # any dunder
        return True
    for prefix in _ENTRY_POINT_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _is_likely_runtime_invoked(name: str) -> bool:
    """Return True when the name pattern suggests the function is called at runtime
    (callback, event handler, hook, etc.) even if fan_in == 0 statically.
    These are flagged with 'medium' confidence instead of 'high'.
    """
    if name in _RUNTIME_INVOKE_KEYWORDS:
        return True
    for suffix in _RUNTIME_INVOKE_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def _compute_nesting_depth(body: str) -> int:
    """Compute max brace-nesting depth inside a function body string.

    Subtracts 1 for the method's own opening brace so the result represents
    the deepest *inner* nesting level (depth 0 = no inner nesting).
    """
    depth = max_depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch == "}":
            depth -= 1
    return max(0, max_depth - 1)


# Numeric literal values that are universally understood and NOT magic numbers
_COMMON_LITERALS: frozenset = frozenset({"0", "1", "2", "3", "-1", "10", "100", "1000"})


def _count_magic_literals(body: str) -> int:
    """Count numeric literals in *body* that are likely 'magic' (unexplained constants).

    Excludes 0, 1, 2, 3, -1, 10, 100, 1000 which are nearly universally understood.
    """
    found = re.findall(r'(?<!\w)(\d+\.?\d*)(?!\w)', body)
    return sum(1 for f in found if f not in _COMMON_LITERALS)


def _is_private_name(name: str, language: str) -> bool:
    """Heuristic: is this function considered 'private' in its language?
    Private → higher confidence it's not a public API entry point.
    """
    if language == "python":
        return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))
    if language in ("javascript", "typescript"):
        return name.startswith("_") or name.startswith("#")
    if language in ("java", "csharp"):
        return name[0].islower() and name.startswith(("_", "do", "helper", "util"))
    return name.startswith("_")


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


# Supported language mapping (file extension -> language name)
SUPPORTED_EXTENSIONS = {
    '.py': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.java': 'java',
    '.go': 'go',
    '.rs': 'rust',
    '.cpp': 'cpp',
    '.c': 'c',
    '.cs': 'csharp',
}


# Try importing tree-sitter language bindings; if unavailable, we degrade gracefully.
def _load_tree_sitter_runtime():
    try:
        tree_sitter_module = importlib.import_module("tree_sitter")
        tspython = importlib.import_module("tree_sitter_python")
        tsjavascript = importlib.import_module("tree_sitter_javascript")
        tsjava = importlib.import_module("tree_sitter_java")
        tsgo = importlib.import_module("tree_sitter_go")
        tsrust = importlib.import_module("tree_sitter_rust")

        Language = tree_sitter_module.Language
        Parser = tree_sitter_module.Parser

        tree_sitter_languages = {
            "python":     Language(tspython.language()),
            "javascript": Language(tsjavascript.language()),
            "typescript": Language(tsjavascript.language()),
            "java":       Language(tsjava.language()),
            "go":         Language(tsgo.language()),
            "rust":       Language(tsrust.language()),
        }

        def get_parser(language: str):
            lang = tree_sitter_languages[language]
            # tree-sitter ≥0.22: Parser(language) — set_language নেই
            try:
                parser = Parser(lang)
            except TypeError:
                # পুরনো API fallback: Parser() তারপর set_language()
                parser = Parser()
                parser.set_language(lang)
            return parser

        return tree_sitter_languages, get_parser
    except Exception:
        return {}, None


TREE_SITTER_LANGUAGES, get_parser = _load_tree_sitter_runtime()

if get_parser is None:
    def get_parser(language: str):
        raise RuntimeError("tree-sitter is not available in this environment")


# Tree-sitter queries for function and call extraction (language specific)
FUNCTION_QUERIES = {
    "python": """
        (function_definition
          name: (identifier) @fn_name) @fn_def

        (class_definition
          name: (identifier) @class_name
          body: (block
            (function_definition
              name: (identifier) @method_name) @fn_def))
    """,

    "javascript": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_definition
          name: (property_identifier) @fn_name) @fn_def

        (arrow_function) @fn_def

        (variable_declarator
          name: (identifier) @fn_name
          value: (arrow_function) @fn_def)
    """,

    "typescript": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_definition
          name: (property_identifier) @fn_name) @fn_def

        (arrow_function) @fn_def
    """,

    "java": """
        (method_declaration
          name: (identifier) @fn_name) @fn_def

        (constructor_declaration
          name: (identifier) @fn_name) @fn_def
    """,

    "go": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_declaration
          name: (field_identifier) @fn_name) @fn_def
    """,

    "rust": """
        (function_item
          name: (identifier) @fn_name) @fn_def

        (impl_item
          body: (declaration_list
            (function_item
              name: (identifier) @fn_name) @fn_def))
    """,
}

CALL_QUERIES = {
    "python": """
        (call (identifier) @called_fn)
        (call (attribute attribute: (identifier) @called_fn))
    """,
    "javascript": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (member_expression
          property: (property_identifier) @called_fn))
    """,
    "typescript": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (member_expression
          property: (property_identifier) @called_fn))
    """,
    "java": """
        (method_invocation name: (identifier) @called_fn)
    """,
    "go": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (selector_expression
          field: (field_identifier) @called_fn))
    """,
    "rust": """
        (call_expression function: (identifier) @called_fn)
        (call_expression function: (field_expression
          field: (field_identifier) @called_fn))
    """,
}


@dataclass
class ParsedFunction:
    name: str
    file: str
    language: str
    module: str
    virtual_module: str
    line_start: int
    line_end: int
    complexity: int = 1
    calls: List[str] = field(default_factory=list)
    fan_in: int = 0
    fan_out: int = 0
    risk_level: str = "none"      # none | low | medium | high
    is_dead: bool = False          # True → potentially unreachable
    dead_confidence: str = "none"  # none | medium | high
    max_nesting_depth: int = 0     # max block-nesting depth inside the function
    literal_count: int = 0         # count of non-trivial numeric literals (magic numbers)


class UniversalParser:
    def parse_file(self, filepath: str, content: str, language: str) -> List[ParsedFunction]:
        if language == "python":
            parsed = self._parse_python_ast(filepath, content)
            if parsed:
                return parsed

        try:
            parser = get_parser(language)
        except Exception:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)
            if language in ("javascript", "typescript"):
                return self._parse_js_ts_regex(filepath, content, language)
            if language == "go":
                return self._parse_go_regex(filepath, content)
            if language == "rust":
                return self._parse_rust_regex(filepath, content)
            return []

        try:
            tree = parser.parse(bytes(content, "utf8"))
        except Exception:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)
            if language in ("javascript", "typescript"):
                return self._parse_js_ts_regex(filepath, content, language)
            if language == "go":
                return self._parse_go_regex(filepath, content)
            if language == "rust":
                return self._parse_rust_regex(filepath, content)
            return []

        try:
            functions = self._extract_functions(tree, content, filepath, language)
        except Exception:
            functions = []

        if not functions:
            if language == "python":
                return self._parse_python_ast(filepath, content)
            if language == "java":
                return self._parse_java_regex(filepath, content)
            if language in ("javascript", "typescript"):
                return self._parse_js_ts_regex(filepath, content, language)
            if language == "go":
                return self._parse_go_regex(filepath, content)
            if language == "rust":
                return self._parse_rust_regex(filepath, content)

        for fn in functions:
            fn.calls = self._extract_calls(tree, content, language, fn.name)
            fn.fan_out = len(fn.calls)
        return functions

    def _parse_java_regex(self, filepath: str, content: str) -> List[ParsedFunction]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        class_name = class_match.group(1) if class_match else None

        # Match Java methods and constructors with bodies.
        method_pattern = re.compile(
            r"(?ms)^\s*(?:@[\w.]+\s*)*(?:public|protected|private|static|final|native|synchronized|abstract|strictfp|\s)+"
            r"(?:[\w<>\[\],.?]+\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{"
        )

        functions: List[ParsedFunction] = []
        seen = set()
        keywords = {
            "if", "for", "while", "switch", "catch", "return", "new", "throw", "super", "this",
            "try", "else", "case", "do", "synchronized",
        }

        for match in method_pattern.finditer(content):
            fn_name = match.group(1)
            key = (fn_name, match.start())
            if key in seen:
                continue
            seen.add(key)

            start_line = content.count("\n", 0, match.start()) + 1

            # Find body range by brace matching.
            brace_start = content.find("{", match.end() - 1)
            if brace_start < 0:
                continue
            depth = 0
            end_idx = brace_start
            for i in range(brace_start, len(content)):
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break

            method_body = content[brace_start:end_idx + 1]
            end_line = content.count("\n", 0, end_idx) + 1

            calls = []
            for call_match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", method_body):
                callee = call_match.group(1)
                if callee not in keywords and callee != fn_name:
                    calls.append(callee)

            complexity = 1
            for kw in ["if", "for", "while", "case", "catch", "&&", "||"]:
                complexity += method_body.count(kw)

            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language="java",
                module=module,
                virtual_module=class_name or module,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=sorted(set(calls)),
                fan_out=len(set(calls)),
                max_nesting_depth=_compute_nesting_depth(method_body),
                literal_count=_count_magic_literals(method_body),
            ))

        return functions

    def _parse_js_ts_regex(self, filepath: str, content: str, language: str) -> List[ParsedFunction]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"

        fn_patterns = [
            # function foo(...) { ... }
            re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.MULTILINE),
            # const foo = function(...) { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*function\s*\([^)]*\)\s*\{", re.MULTILINE),
            # const foo = (...) => { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\([^)]*\)\s*=>\s*\{", re.MULTILINE),
        ]

        # class Foo { bar(...) { ... } }
        class_pattern = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)\s*\{", re.MULTILINE)
        method_pattern = re.compile(r"\n\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.MULTILINE)

        functions: List[ParsedFunction] = []
        seen = set()
        keywords = {
            "if", "for", "while", "switch", "catch", "return", "new", "throw",
            "try", "else", "case", "do", "typeof", "instanceof", "await", "yield",
        }

        def _extract_body(start_idx: int) -> Tuple[int, int, str]:
            brace_start = content.find("{", start_idx)
            if brace_start < 0:
                return -1, -1, ""
            depth = 0
            end_idx = brace_start
            for i in range(brace_start, len(content)):
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            return brace_start, end_idx, content[brace_start:end_idx + 1]

        # top-level and assigned functions
        for pattern in fn_patterns:
            for match in pattern.finditer(content):
                fn_name = match.group(1)
                key = (fn_name, match.start())
                if key in seen:
                    continue
                seen.add(key)

                brace_start, end_idx, body = _extract_body(match.end() - 1)
                if brace_start < 0:
                    continue

                start_line = content.count("\n", 0, match.start()) + 1
                end_line = content.count("\n", 0, end_idx) + 1

                calls = []
                for call_match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", body):
                    callee = call_match.group(1)
                    if callee not in keywords and callee != fn_name:
                        calls.append(callee)

                complexity = 1
                for kw in ["if", "for", "while", "case", "catch", "&&", "||", "?", "?:"]:
                    complexity += body.count(kw)

                functions.append(ParsedFunction(
                    name=fn_name,
                    file=filepath,
                    language=language,
                    module=module,
                    virtual_module=module,
                    line_start=start_line,
                    line_end=end_line,
                    complexity=complexity,
                    calls=sorted(set(calls)),
                    fan_out=len(set(calls)),
                    max_nesting_depth=_compute_nesting_depth(body),
                    literal_count=_count_magic_literals(body),
                ))

        # class methods (best-effort)
        for class_match in class_pattern.finditer(content):
            class_name = class_match.group(1)
            brace_start, end_idx, body = _extract_body(class_match.end() - 1)
            if brace_start < 0:
                continue
            for method_match in method_pattern.finditer(body):
                method_name = method_match.group(1)
                if method_name in ("constructor",) or method_name in keywords:
                    continue
                key = (f"{class_name}.{method_name}", brace_start + method_match.start())
                if key in seen:
                    continue
                seen.add(key)

                method_brace_start = body.find("{", method_match.end() - 1)
                if method_brace_start < 0:
                    continue
                depth = 0
                method_end = method_brace_start
                for i in range(method_brace_start, len(body)):
                    ch = body[i]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            method_end = i
                            break

                full_start = brace_start + method_match.start()
                full_end = brace_start + method_end
                start_line = content.count("\n", 0, full_start) + 1
                end_line = content.count("\n", 0, full_end) + 1
                method_body = body[method_brace_start:method_end + 1]

                calls = []
                for call_match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", method_body):
                    callee = call_match.group(1)
                    if callee not in keywords and callee != method_name:
                        calls.append(callee)

                complexity = 1
                for kw in ["if", "for", "while", "case", "catch", "&&", "||", "?", "?:"]:
                    complexity += method_body.count(kw)

                functions.append(ParsedFunction(
                    name=method_name,
                    file=filepath,
                    language=language,
                    module=module,
                    virtual_module=class_name or module,
                    line_start=start_line,
                    line_end=end_line,
                    complexity=complexity,
                    calls=sorted(set(calls)),
                    fan_out=len(set(calls)),
                    max_nesting_depth=_compute_nesting_depth(method_body),
                    literal_count=_count_magic_literals(method_body),
                ))

        return functions

    def _parse_go_regex(self, filepath: str, content: str) -> List[ParsedFunction]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"

        # group(1) = receiver contents (optional), group(2) = function name
        fn_pattern = re.compile(
            r"\bfunc\s+(?:\(([^)]+)\)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            re.MULTILINE,
        )

        functions: List[ParsedFunction] = []
        seen = set()
        keywords = {"if", "for", "switch", "select", "return", "go", "defer",
                    "range", "make", "new", "len", "cap", "append", "copy",
                    "delete", "close", "panic", "recover", "print", "println"}

        for match in fn_pattern.finditer(content):
            receiver_raw = match.group(1)   # e.g. "m *CounterVec" | "r SomeType" | None
            fn_name_raw  = match.group(2)   # e.g. "Reset"
            if fn_name_raw in keywords:
                continue

            # Prefix method name with receiver type for uniqueness
            if receiver_raw:
                rec_type = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*$', receiver_raw.strip())
                fn_name = f"{rec_type.group(1)}.{fn_name_raw}" if rec_type else fn_name_raw
            else:
                fn_name = fn_name_raw

            key = (fn_name, match.start())
            if key in seen:
                continue
            seen.add(key)

            # { খোঁজো — কিন্তু ; আগে এলে declaration, skip করো
            search_from = match.end()
            next_brace = content.find('{', search_from)
            if next_brace < 0:
                continue

            # Only skip if ';' appears before '{' on the SAME logical line
            # (i.e. between the signature and the opening brace, not in comments/later code)
            # Look for ';' only up to the opening brace (not the whole file)
            snippet = content[search_from:next_brace]
            next_semi_local = snippet.find(';')
            if next_semi_local >= 0:
                # ';' is between signature end and '{' — this is a declaration, skip
                continue

            # brace matching
            depth = 0
            end_idx = next_brace
            for i in range(next_brace, len(content)):
                ch = content[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break

            start_line = content.count("\n", 0, match.start()) + 1
            end_line = content.count("\n", 0, end_idx) + 1
            body = content[next_brace:end_idx + 1]

            calls = []
            for call_match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", body):
                callee = call_match.group(1)
                if callee not in keywords and callee != fn_name_raw:
                    calls.append(callee)

            complexity = 1
            for kw in ["if ", "for ", "switch ", "case ", "select ", "&&", "||"]:
                complexity += body.count(kw)

            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language="go",
                module=module,
                virtual_module=module,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=sorted(set(calls)),
                fan_out=len(set(calls)),
                max_nesting_depth=_compute_nesting_depth(body),
                literal_count=_count_magic_literals(body),
            ))

        return functions

    def _parse_rust_regex(self, filepath: str, content: str) -> List[ParsedFunction]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        
        # impl block থেকে struct name বের করো (virtual_module-এর জন্য)
        impl_pattern = re.compile(r'\bimpl(?:<[^>]*>)?\s+([A-Za-z_][A-Za-z0-9_]*)')
        current_impl = None
        impl_match = impl_pattern.search(content)
        if impl_match:
            current_impl = impl_match.group(1)

        fn_pattern = re.compile(
            r'(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+"[^"]*"\s+)?'
            r'fn\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:<[^>]*>)?\s*\('
        )

        keywords = {
            'if', 'while', 'for', 'match', 'loop', 'where', 'let',
            'return', 'impl', 'trait', 'struct', 'enum', 'type', 'use',
            'mod', 'pub', 'crate', 'super', 'self', 'Self', 'move',
        }

        functions: List[ParsedFunction] = []
        seen = set()

        for match in fn_pattern.finditer(content):
            fn_name = match.group(1)
            if fn_name in keywords:
                continue

            start_line = content.count('\n', 0, match.start()) + 1
            key = (fn_name, start_line)
            if key in seen:
                continue
            seen.add(key)

            # brace matching দিয়ে body range বের করো
            brace_pos = content.find('{', match.end())
            semi_pos = content.find(';', match.end())

            # semicolon আগে থাকলে এটা declaration (trait/extern), body নেই
            if semi_pos >= 0 and (brace_pos < 0 or semi_pos < brace_pos):
                continue

            if brace_pos < 0:
                continue

            depth = 0
            end_idx = brace_pos
            for i in range(brace_pos, len(content)):
                ch = content[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break

            end_line = content.count('\n', 0, end_idx) + 1
            body = content[brace_pos:end_idx + 1]

            # calls extract করো
            call_pat = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:::<[^>]*>)?\s*\(')
            call_keywords = keywords | {
                'println', 'eprintln', 'print', 'eprint', 'format', 'write',
                'writeln', 'assert', 'assert_eq', 'assert_ne', 'panic', 'todo',
                'unimplemented', 'unreachable', 'dbg', 'vec', 'Some', 'None',
                'Ok', 'Err', 'Box', 'Vec', 'String', 'HashMap',
            }
            calls = list({
                m.group(1) for m in call_pat.finditer(body)
                if m.group(1) not in call_keywords and m.group(1) != fn_name
            })

            complexity = 1 + sum(body.count(kw) for kw in [
                'if ', 'else if', 'for ', 'while ', 'match ', '&&', '||', '?', 'unwrap()'
            ])

            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language='rust',
                module=module,
                virtual_module=current_impl or module,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=calls,
                fan_out=len(calls),
                max_nesting_depth=_compute_nesting_depth(body),
                literal_count=_count_magic_literals(body),
            ))

        return functions

    def _parse_python_ast(self, filepath: str, content: str) -> List[ParsedFunction]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        functions: List[ParsedFunction] = []
        seen = set()

        class PythonVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_class = None

            def visit_ClassDef(self, node):
                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def visit_FunctionDef(self, node):
                key = (node.name, node.lineno)
                if key in seen:
                    return
                seen.add(key)
                line_end = getattr(node, "end_lineno", node.lineno)
                functions.append(ParsedFunction(
                    name=node.name,
                    file=filepath,
                    language="python",
                    module=module,
                    virtual_module=self.current_class or module,
                    line_start=node.lineno,
                    line_end=line_end,
                    complexity=self._estimate_python_complexity(node),
                    calls=self._extract_python_calls(node),
                    max_nesting_depth=self._estimate_python_nesting(node),
                    literal_count=self._estimate_python_literals(node),
                ))

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

            def _estimate_python_complexity(self, node):
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Try, ast.BoolOp, ast.Match)):
                        complexity += 1
                return complexity

            def _estimate_python_nesting(self, node):
                _NESTING_NODES = (ast.If, ast.For, ast.While, ast.With,
                                  ast.Try, ast.AsyncWith, ast.AsyncFor)
                max_d = [0]
                def _walk(n, d):
                    if isinstance(n, _NESTING_NODES):
                        d += 1
                        if d > max_d[0]:
                            max_d[0] = d
                    for child in ast.iter_child_nodes(n):
                        _walk(child, d)
                _walk(node, 0)
                return max_d[0]

            def _estimate_python_literals(self, node):
                _COMMON = {0, 1, 2, 3, -1, 10, 100, 1000}
                count = 0
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
                        if child.value not in _COMMON:
                            count += 1
                return count

            def _extract_python_calls(self, node):
                calls = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = None
                        if isinstance(child.func, ast.Name):
                            callee = child.func.id
                        elif isinstance(child.func, ast.Attribute):
                            callee = child.func.attr
                        if callee:
                            calls.add(callee)
                return list(calls)

        visitor = PythonVisitor()
        visitor.visit(tree)
        for fn in functions:
            fn.fan_out = len(fn.calls)
        return functions

    def _extract_functions(self, tree, content: str, filepath: str, language: str) -> List[ParsedFunction]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []

        query = lang_obj.query(FUNCTION_QUERIES[language])
        raw_captures = query.captures(tree.root_node)

        # tree-sitter >= 0.22 returns dict[str, list[Node]]; older returns list[tuple[Node, str]]
        if isinstance(raw_captures, dict):
            capture_pairs = [
                (node, name)
                for name, nodes in raw_captures.items()
                for node in nodes
            ]
        else:
            capture_pairs = raw_captures

        functions: List[ParsedFunction] = []
        seen = set()

        for node, capture_name in capture_pairs:
            if "fn_def" not in capture_name:
                continue
            # attempt to get the name child
            name_node = node.child_by_field_name("name")
            fn_name = (
                content[name_node.start_byte:name_node.end_byte]
                if name_node is not None
                else f"anonymous_{node.start_point[0]}"
            )

            # For Go method_declarations, prefix with receiver type for uniqueness
            if language == "go":
                recv_node = node.child_by_field_name("receiver")
                if recv_node:
                    recv_text = content[recv_node.start_byte:recv_node.end_byte]
                    rec_match = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\)', recv_text)
                    if rec_match:
                        fn_name = f"{rec_match.group(1)}.{fn_name}"

            key = (fn_name, node.start_point[0])
            if key in seen:
                continue
            seen.add(key)

            module = Path(filepath).parts[0] if Path(filepath).parts else "root"
            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language=language,
                module=module,
                virtual_module=module,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                complexity=self._estimate_complexity(node, content),
            ))
        return functions

    def _extract_calls(self, tree, content: str, language: str, current_fn_name: str) -> List[str]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []
        query = lang_obj.query(CALL_QUERIES[language])
        raw_captures = query.captures(tree.root_node)

        calls = set()
        if isinstance(raw_captures, dict):
            for nodes in raw_captures.values():
                for node in nodes:
                    called = content[node.start_byte:node.end_byte]
                    if called and called != current_fn_name:
                        calls.add(called)
        else:
            for node, _ in raw_captures:
                called = content[node.start_byte:node.end_byte]
                if called and called != current_fn_name:
                    calls.add(called)
        return list(calls)

    def _estimate_complexity(self, node, content: str) -> int:
        body_text = content[node.start_byte:node.end_byte]
        keywords = ["if ", "elif ", "else:", "for ", "while ",
                    "case ", "catch", "except", "&&", "||"]
        return 1 + sum(body_text.count(kw) for kw in keywords)

    def compute_fan_in(self, all_functions: List[ParsedFunction]) -> List[ParsedFunction]:
        call_counts: Dict[str, int] = {}
        for fn in all_functions:
            for called in fn.calls:
                call_counts[called] = call_counts.get(called, 0) + 1
        for fn in all_functions:
            fn.fan_in = call_counts.get(fn.name, 0)
        return all_functions

    def compute_risk_scores(self, all_functions: List[ParsedFunction]) -> List[ParsedFunction]:
        for fn in all_functions:
            if fn.fan_in >= 10:
                fn.risk_level = "high"
            elif fn.fan_in >= 3:
                fn.risk_level = "medium"
            elif fn.fan_in >= 1:
                fn.risk_level = "low"
            else:
                fn.risk_level = "none"
        return all_functions

    def compute_dead_code(self, all_functions: List[ParsedFunction]) -> List[ParsedFunction]:
        for fn in all_functions:
            # fan_in counts calls from ALL parsed files — cross-file calls are
            # already included, so fan_in > 0 means definitely reachable.
            if fn.fan_in > 0:
                fn.is_dead = False
                fn.dead_confidence = "none"
                continue

            # Definitive entry points — OS / framework calls these
            if _is_entry_point(fn.name):
                fn.is_dead = False
                fn.dead_confidence = "none"
                continue

            # Patterns that suggest runtime invocation (callbacks, hooks, …)
            # We still flag these as potentially unreachable but with only
            # "medium" confidence because we cannot rule out dynamic dispatch.
            if _is_likely_runtime_invoked(fn.name):
                fn.is_dead = True
                fn.dead_confidence = "medium"
                continue

            # Private helper — high confidence it's truly unused
            if _is_private_name(fn.name, fn.language):
                fn.is_dead = True
                fn.dead_confidence = "high"
                continue

            # Public function with no detected callers — could still be:
            #   • a public library API called by external code
            #   • invoked via reflection / getattr / importlib
            #   • a virtual/override method called polymorphically
            # → medium confidence only
            fn.is_dead = True
            fn.dead_confidence = "medium"

        return all_functions


def count_functions_ast(filepath: str, content: str) -> int:
    ext = Path(filepath).suffix.lower()
    language_name = SUPPORTED_EXTENSIONS.get(ext)
    if language_name == "python":
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                count += 1
        return count

    if not language_name or language_name not in TREE_SITTER_LANGUAGES:
        # ── tree-sitter নেই, regex fallback ──
        if language_name == "go":
            return len(re.findall(
                r'\bfunc\s+(?:\([^)]*\)\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(',
                content
            ))
        if language_name == "rust":
            return len(re.findall(r'\bfn\s+[a-zA-Z_][a-zA-Z0-9_]*\s*[<(]', content))
        if language_name in ("javascript", "typescript"):
            return len(re.findall(r'\bfunction\s+[A-Za-z_$]', content))
        return 0

    try:
        parser = get_parser(language_name)
        tree = parser.parse(bytes(content, "utf8"))
        query = TREE_SITTER_LANGUAGES[language_name].query(FUNCTION_QUERIES[language_name])
        captures = query.captures(tree.root_node)
        return sum(1 for _, name in captures if "fn_def" in name)
    except Exception:
        # tree-sitter আছে কিন্তু parse fail → regex fallback
        if language_name == "go":
            return len(re.findall(
                r'\bfunc\s+(?:\([^)]*\)\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(',
                content
            ))
        return 0


def detect_file_strategy(filepath: str, content: str) -> str:
    """
    Returns one of: "data_file", "large_normal", "god_file", "normal"
    """
    filename = Path(filepath).name.lower()
    generated_patterns = ['.pb.go', '.pb.gw.go', '_grpc.pb.go', '.gen.go',
                          '.generated.go', '_generated.go']
    if any(filename.endswith(p) for p in generated_patterns):
        lines = content.split('\n')
        # অনেক বড় generated file (100k lines ≈ 6MB+) skip করো
        if len(lines) > 100_000:
            return "data_file"
        # generated files সবসময় god_file হিসেবে chunk করো
        # "normal" return করলে module graph-এ fn_count=0 দেখায়
        return "god_file"

    lines = content.split("\n")
    line_count = len(lines)
    if line_count <= 10_000:
        return "normal"

    fn_count = count_functions_ast(filepath, content)

    if fn_count < 3:      # 10 থেকে 3: tree-sitter ছাড়া undercount হলেও safe
        return "data_file"
    elif fn_count <= 100:
        return "large_normal"
    else:
        return "god_file"


def chunk_god_file(filepath: str, content: str, language: str, functions: List[Dict]) -> List[Dict]:
    # Strategy 1: class-based chunking
    try:
        classes = []
        if language == "python":
            # lightweight class extractor using AST to avoid extra dependencies
            import ast as _ast
            tree = _ast.parse(content)
            for node in [n for n in tree.body if isinstance(n, _ast.ClassDef)]:
                start = node.lineno
                end = max(getattr(n, 'end_lineno', start) for n in node.body) if node.body else start
                classes.append({"name": node.name, "line_start": start, "line_end": end})
        # For other languages, attempt tree-sitter class extraction
        if not classes and language in TREE_SITTER_LANGUAGES:
            try:
                parser = get_parser(language)
                tree = parser.parse(bytes(content, "utf8"))
                q = TREE_SITTER_LANGUAGES[language].query(
                    "(class_definition name: (identifier) @class_name) @class_def"
                )
                raw = q.captures(tree.root_node)
                pairs = (
                    [(n, name) for name, nodes in raw.items() for n in nodes]
                    if isinstance(raw, dict) else raw
                )
                for node, capture_name in pairs:
                    if "class_def" in capture_name:
                        classes.append({
                            "name": content[node.start_byte:node.end_byte],
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                        })
            except Exception:
                pass  # class chunking ব্যর্থ হলে complexity/line-range fallback এ যাবে

        if classes:
            chunks = []
            for cls in classes:
                methods = [f for f in functions if cls["line_start"] <= f["line_start"] <= cls["line_end"]]
                chunks.append({
                    "virtual_module": cls["name"],
                    "functions": methods,
                    "line_range": (cls["line_start"], cls["line_end"]),
                    "chunk_strategy": "class",
                })
            return chunks
    except Exception:
        logger.exception("class-based chunking failed")

    # Strategy 2: complexity-based clustering
    high = [f for f in functions if f.get("complexity", 0) > 15]
    medium = [f for f in functions if 5 < f.get("complexity", 0) <= 15]
    low = [f for f in functions if f.get("complexity", 0) <= 5]
    if high or medium:
        return [
            {"virtual_module": "High Complexity", "functions": high, "chunk_strategy": "complexity"},
            {"virtual_module": "Medium Complexity", "functions": medium, "chunk_strategy": "complexity"},
            {"virtual_module": "Low Complexity", "functions": low, "chunk_strategy": "complexity"},
        ]

    # Strategy 3: Line range chunking (fallback)
    CHUNK_SIZE = 50
    sorted_fns = sorted(functions, key=lambda f: f["line_start"])
    chunks = []
    for i in range(0, len(sorted_fns), CHUNK_SIZE):
        batch = sorted_fns[i:i+CHUNK_SIZE]
        if not batch:
            continue
        chunks.append({
            "virtual_module": f"Group {i//CHUNK_SIZE+1} (lines {batch[0]['line_start']}–{batch[-1]['line_end']})",
            "functions": batch,
            "chunk_strategy": "line_range",
        })
    return chunks


def decide_render_strategy(node_count: int) -> Dict:
    if node_count < 100:
        return {"strategy": "show_all", "description": "Render all nodes, no clustering", "max_nodes": node_count}
    elif node_count <= 500:
        return {"strategy": "make_group", "description": "Collapse low-fan nodes into group summary nodes", "max_nodes": 100, "collapse_threshold": 2}
    else:
        return {"strategy": "search_only", "description": "Show top 100 by importance only. User must search to find others.", "max_nodes": 100}


def filter_top_nodes(functions: List[Dict], max_n: int = 100) -> List[Dict]:
    return sorted(functions, key=lambda f: f.get("fan_in", 0) + f.get("fan_out", 0), reverse=True)[:max_n]


def _detect_module_structure(files: List[Dict]) -> Dict[str, str]:
    """
    Detect module assignments from the uploaded folder hierarchy.

    Rules:
    1. Prefer the path that starts at the uploaded root folder.
     2. If a file lives directly under src/, it has no module and should be
         rendered as a file node.
     3. If a file lives under src/<subdir>/..., its module is the subdir path
         relative to src.
     4. If a file is not under src/, its module is its parent directory.

    Examples:
    - lab6/src/Builder.java -> lab6/src
    - lab6/src/lab6b/Image.java -> lab6/src/lab6b
    - lab6/README.md -> lab6

    Returns a mapping of file path -> module name.
    """
    module_map = {}

    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/")

    def _as_module_path(path: str) -> str:
        normalized = _normalize_path(path)
        parts = Path(normalized).parts
        if not parts:
            return "root"

        try:
            src_index = parts.index("src")
        except ValueError:
            src_index = -1

        if src_index >= 0:
            remaining = parts[src_index + 1:]
            if len(remaining) <= 1:
                return ""

            module_parts = list(remaining[:-1])
            return Path(*module_parts).as_posix() if module_parts else ""

        if len(parts) > 1:
            return Path(*parts[:-1]).as_posix()

        return ""

    for file_info in files:
        path = file_info.get("path", "")
        if path:
            module_map[path] = _as_module_path(path)

    return module_map


def _module_basename(module_path: str) -> str:
    """
    Extract a usable stem from a module specifier string.

    Examples
    --------
    './utils/helpers'  → 'helpers'
    '../db'            → 'db'
    'lodash'           → 'lodash'
    'pkg/name'         → 'name'
    """
    # take the last path component's stem (handles multi-level paths too)
    stem = Path(module_path.rstrip("/")).stem if module_path else ""
    return stem


def _build_stem_to_files(all_functions: List[Dict]) -> Dict[str, List[str]]:
    """Build a mapping of file stem -> list of file paths (handles duplicate stems)."""
    from collections import defaultdict
    stem_map: Dict[str, List[str]] = defaultdict(list)
    seen: set = set()
    for fn in all_functions:
        fp = fn.get("file")
        if fp and fp not in seen:
            seen.add(fp)
            stem = Path(fp).stem
            stem_map[stem].append(fp)
            # Also index without extension in case require() includes '.js'
            # e.g. require('../controllers/ticketController.js') -> stem already correct
    return stem_map


def _resolve_import(raw_import: str, stem_to_files: Dict[str, List[str]], importing_file: str = "") -> str | None:
    """
    Resolve a raw import/require path to an actual file path.

    When multiple files share the same stem (e.g. controllers/auth.js and
    routes/auth.js both have stem 'auth'), use the directory hint embedded
    in the import specifier to pick the best match.

    Examples
    --------
    '../controllers/auth'  → 'controllers/auth.js'   (not routes/auth.js)
    '../utils/sendMail'    → 'utils/sendMail.js'
    """
    stem = Path(raw_import.rstrip("/")).stem
    candidates = stem_to_files.get(stem, [])

    if not candidates:
        return None

    # Filter out self-reference (a file importing itself makes no sense)
    if importing_file:
        candidates = [c for c in candidates if c != importing_file]
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Use directory segments from the import specifier as hints
    # e.g. '../controllers/auth' -> parts after stripping leading dots: ['controllers', 'auth']
    hint_parts = [p for p in Path(raw_import).parts if p not in (".", "..")]
    # Walk hint parts from most-specific to least-specific (excluding the final filename)
    dir_hints = [h.lower() for h in hint_parts[:-1]]

    for hint in reversed(dir_hints):
        for candidate in candidates:
            cand_dirs = [p.lower() for p in Path(candidate).parts[:-1]]
            if hint in cand_dirs:
                return candidate

    # Fallback: first candidate
    return candidates[0]


def _extract_file_imports(content: str, language: str) -> List[str]:
    imports = []

    if language == "java":
        # import com.example.Foo; → "Foo"
        for match in re.finditer(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[-1])
        # new ClassName(  /  extends X  /  implements X, Y
        for match in re.finditer(r"\bnew\s+([A-Z][A-Za-z0-9_]*)\s*\(", content):
            imports.append(match.group(1))
        for match in re.finditer(r"\bextends\s+([A-Z][A-Za-z0-9_]*)\b", content):
            imports.append(match.group(1))
        for match in re.finditer(r"\bimplements\s+([A-Z][A-Za-z0-9_\s,]*)\b", content):
            names = [p.strip() for p in match.group(1).split(",") if p.strip()]
            imports.extend(names)

    elif language in ("javascript", "typescript"):
        # ES module:  import X from './foo'   /  import { X } from './foo'
        # require():  require('./foo')
        # Store the raw specifier so callers can do directory-hint resolution.
        # External packages (no leading dot) are stored as their stem only.
        for match in re.finditer(
            r"""import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""", content
        ):
            raw = match.group(1)
            imports.append(raw if raw.startswith(".") else _module_basename(raw))
        for match in re.finditer(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", content):
            raw = match.group(1)
            imports.append(raw if raw.startswith(".") else _module_basename(raw))

    elif language == "python":
        # import foo.bar  /  from foo.bar import baz
        for match in re.finditer(r"^\s*import\s+([\w.]+)", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[0])
        for match in re.finditer(r"^\s*from\s+([\w.]+)\s+import", content, re.MULTILINE):
            raw = match.group(1)
            # relative imports like "from . import x" are skipped (no useful file target)
            if raw.startswith("."):
                continue
            imports.append(raw.split(".")[0])

    elif language == "go":
        # import "pkg/name"  /  import ( "pkg/name" \n "other" )
        for match in re.finditer(r'"([\w./\-]+)"', content):
            imports.append(_module_basename(match.group(1)))

    elif language == "rust":
        # use crate::foo::bar;  /  use foo::{Bar, Baz};
        for match in re.finditer(r"^\s*use\s+([\w:]+)", content, re.MULTILINE):
            first = match.group(1).split("::")[0]
            if first not in ("crate", "super", "self", "std", "core", "alloc"):
                imports.append(first)
            else:
                # intra-crate: take second segment as the local module name
                parts = match.group(1).split("::")
                if len(parts) >= 2 and parts[1]:
                    imports.append(parts[1])

    elif language in ("cpp", "c"):
        # #include "localfile.h"  — angle-bracket system headers are intentionally skipped
        for match in re.finditer(r'#include\s+"([^"]+)"', content):
            imports.append(Path(match.group(1)).stem)

    elif language == "csharp":
        # using Foo.Bar;  /  using static Foo.Bar;
        for match in re.finditer(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE):
            imports.append(match.group(1).split(".")[-1])

    # De-duplicate while preserving order
    seen: set = set()
    deduped: List[str] = []
    for name in imports:
        if name and name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def detect_unused_imports(content: str, language: str, imports: List[str]) -> List[str]:
    """Return import names from `imports` that never appear in the non-import body of `content`."""
    # Strip import statement lines so we don't count the declaration itself as usage
    lines = content.split("\n")
    body_lines: List[str] = []
    in_import_block = False  # for Go multi-line import blocks

    for line in lines:
        s = line.strip()
        if language == "python":
            if s.startswith("import ") or s.startswith("from "):
                continue
        elif language in ("javascript", "typescript"):
            if s.startswith("import ") or ("require(" in s and "=" in s):
                continue
        elif language == "java":
            if s.startswith("import "):
                continue
        elif language == "go":
            if s.startswith("import ("):
                in_import_block = True
                continue
            if in_import_block:
                if s == ")":
                    in_import_block = False
                continue
            if s.startswith("import "):
                continue
        elif language == "rust":
            if s.startswith("use "):
                continue
        elif language in ("c", "cpp"):
            if s.startswith("#include"):
                continue
        elif language == "csharp":
            if s.startswith("using "):
                continue
        body_lines.append(line)

    body = "\n".join(body_lines)
    unused: List[str] = []
    for imp in imports:
        if not re.search(r"\b" + re.escape(imp) + r"\b", body):
            unused.append(imp)
    return unused


def _fn_param_count(fn: "ParsedFunction", content_map: Dict[str, str]) -> int:
    """Extract parameter count for a function from its signature line."""
    content = content_map.get(fn.file, "")
    ls = fn.line_start
    if not content or ls <= 0:
        return 0
    lines = content.split("\n")
    if ls > len(lines):
        return 0
    sig = lines[ls - 1]
    ps, pe = sig.find("("), sig.rfind(")")
    if ps == -1 or pe <= ps:
        return 0
    pstr = sig[ps + 1:pe].strip()
    if not pstr:
        return 0
    pl = [p.strip() for p in pstr.split(",") if p.strip()]
    if fn.language == "python" and pl and pl[0] in ("self", "cls"):
        pl = pl[1:]
    return len(pl)


def analyze_files(files: List[Dict]) -> Tuple[List[Dict], Dict[str, List[str]], Dict]:
    """Parse all supported files, apply file strategies, chunk god files and store edges via `add_edge`.

    Returns (functions_list, unused_import_map, layer_violations) where:
    • unused_import_map  → {file_path: [unused_import_names]}
    • layer_violations   → {by_module, summary, all_violations}
    """
    parser = UniversalParser()
    all_functions: List[ParsedFunction] = []
    
    # Detect module structure
    module_map = _detect_module_structure(files)
    file_import_map = {}

    file_unused_import_map: Dict[str, List[str]] = {}
    file_content_map: Dict[str, str] = {}   # needed for param_count extraction
    for file_info in files:
        file_path = file_info.get("path", "<in-memory>")
        lang = file_info.get("language", "")
        content = file_info.get("content", "")
        file_content_map[file_path] = content
        imports = _extract_file_imports(content, lang)
        file_import_map[file_path] = imports
        if imports:
            file_unused_import_map[file_path] = detect_unused_imports(content, lang, imports)

    # First pass: parse files and decide strategies
    for file_info in files:
        lang = file_info.get("language")
        if not lang or lang == "unknown":
            continue

        content = file_info.get("content", "")
        if not content.strip():
            continue

        file_path = file_info.get("path", "<in-memory>").replace("\\", "/")
        strategy = detect_file_strategy(file_path, content)
        if strategy == "data_file":
            continue

        parsed = parser.parse_file(file_path, content, lang)
        
        # Override module based on detected structure
        detected_module = module_map.get(file_info.get("path", ""), "root")
        for p in parsed:
            p.module = detected_module

        # convert ParsedFunction objects to dicts for chunking convenience
        parsed_dicts = [p.__dict__ for p in parsed]

        if strategy == "god_file":
            chunks = chunk_god_file(file_path, content, lang, parsed_dicts)
            # assign virtual modules
            for chunk in chunks:
                names_in_chunk = {f["name"] for f in chunk["functions"]}
                for p in parsed:
                    if p.name in names_in_chunk:
                        p.virtual_module = chunk["virtual_module"]

        all_functions.extend(parsed)

    # compute fan-in, risk scores, dead code
    all_functions = parser.compute_fan_in(all_functions)

    # Supplementary cross-file text search for functions still at fan_in == 0.
    # The parsed call graph misses callbacks passed as arguments, variable-stored
    # functions, and dynamic dispatch patterns.  A regex scan across every other
    # file's raw content catches the common case of `fn_name(` appearing somewhere.
    if len(file_content_map) > 1:
        norm_content_map: Dict[str, str] = {
            k.replace("\\", "/"): v for k, v in file_content_map.items()
        }
        for fn in all_functions:
            if fn.fan_in > 0:
                continue
            # Match direct calls `fn(` AND reference passing `, fn)` / `= fn`
            pattern = re.compile(r'\b' + re.escape(fn.name) + r'\b')
            for fp, content in norm_content_map.items():
                if fp != fn.file and pattern.search(content):
                    fn.fan_in = 1
                    break

    all_functions = parser.compute_risk_scores(all_functions)
    all_functions = parser.compute_dead_code(all_functions)

    # CALLS edges are persisted later in store_all() with proper session scoping.

    # Build set of files that already have at least one parsed function
    files_with_functions = {fn.file for fn in all_functions}

    # For files that produced 0 functions (e.g. JS without tree-sitter), inject a
    # lightweight sentinel dict so their imports still flow into the graph builders.
    file_sentinels: List[Dict] = []
    for file_info in files:
        lang = file_info.get("language")
        if not lang or lang == "unknown":
            continue
        raw_path = file_info.get("path", "<in-memory>")
        norm_path = raw_path.replace("\\", "/")
        if norm_path in files_with_functions:
            continue  # already covered by real function dicts
        detected_module = module_map.get(raw_path, "")
        file_sentinels.append({
            "name": "__file__",
            "file": norm_path,
            "language": lang,
            "module": detected_module,
            "virtual_module": detected_module or norm_path,
            "line_start": 0,
            "line_end": 0,
            "complexity": 0,
            "calls": [],
            "fan_in": 0,
            "fan_out": 0,
            "imports": file_import_map.get(raw_path, []),
        })

    # return serializable list of dicts
    return [
        {
            "name": fn.name,
            "file": fn.file,
            "language": fn.language,
            "module": fn.module,
            "virtual_module": fn.virtual_module,
            "line_start": fn.line_start,
            "line_end": fn.line_end,
            "complexity": fn.complexity,
            "calls": fn.calls,
            "fan_in": fn.fan_in,
            "fan_out": fn.fan_out,
            "risk_level": fn.risk_level,
            "is_dead": fn.is_dead,
            "dead_confidence": fn.dead_confidence,
            "param_count":       _fn_param_count(fn, file_content_map),
            "max_nesting_depth": fn.max_nesting_depth,
            "literal_count":     fn.literal_count,
            "imports": file_import_map.get(fn.file, []),
        }
        for fn in all_functions
    ] + file_sentinels, file_unused_import_map, _compute_layer_violations(files, module_map, file_import_map)


def build_module_graph(all_functions: List[Dict]) -> Dict:
    group_stats = {}
    fn_to_group = {}

    file_to_imports = {}

    for fn in all_functions:
        is_sentinel = fn.get("name") == "__file__"
        module_name = (fn.get("module") or "").strip()
        if module_name:
            group_id = module_name
            group_type = "module"
            label = module_name
        else:
            group_id = fn.get("file")
            group_type = "file"
            label = fn.get("file")

        if not is_sentinel:
            fn_to_group[fn.get("name")] = group_id

        if group_id not in group_stats:
            group_stats[group_id] = {
                "id": group_id,
                "type": group_type,
                "label": label,
                "loc": 0,
                "fn_count": 0,
                "languages": set(),
            }

        if not is_sentinel:
            group_stats[group_id]["loc"] += (fn.get("line_end", 0) - fn.get("line_start", 0))
            group_stats[group_id]["fn_count"] += 1
        group_stats[group_id]["languages"].add(fn.get("language"))
        if fn.get("imports"):
            file_to_imports.setdefault(fn.get("file"), set()).update(fn.get("imports", []))

    file_to_group = {}
    for fn in all_functions:
        file_path = fn.get("file")
        if not file_path:
            continue
        module_name = (fn.get("module") or "").strip()
        file_to_group[file_path] = module_name if module_name else file_path

    file_name_to_group = {}
    for fn in all_functions:
        file_path = fn.get("file")
        if not file_path:
            continue
        file_key = Path(file_path).stem
        file_name_to_group.setdefault(file_key, file_to_group.get(file_path, file_path))

    # Build stem->files map for directory-hint resolution
    stem_to_files_global = _build_stem_to_files(all_functions)

    group_calls = {}
    for fn in all_functions:
        src_group = fn_to_group.get(fn.get("name"))
        for called in fn.get("calls", []):
            tgt_group = fn_to_group.get(called)
            if tgt_group and tgt_group != src_group:
                key = (src_group, tgt_group)
                group_calls[key] = group_calls.get(key, 0) + 1

    for file_path, imported_names in file_to_imports.items():
        src_group = file_to_group.get(file_path)
        for imported_name in imported_names:
            # Try directory-hint resolution first, fall back to stem lookup
            resolved_file = _resolve_import(imported_name, stem_to_files_global, file_path)
            if resolved_file:
                tgt_group = file_to_group.get(resolved_file)
            else:
                tgt_group = file_name_to_group.get(_module_basename(imported_name))
            if tgt_group and tgt_group != src_group:
                key = (src_group, tgt_group)
                group_calls[key] = group_calls.get(key, 0) + 1

    nodes = [
        {
            "id": s["id"],
            "type": s["type"],
            "label": s["label"],
            "loc": s["loc"],
            "fn_count": s["fn_count"],
            "languages": list(s["languages"]),
        }
        for s in group_stats.values()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in group_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": 1}


def build_all_files_graph(all_functions: List[Dict]) -> Dict:
    """Build a flat file-relations graph across all files (no module grouping)."""
    files_map: Dict[str, Dict] = {}
    file_imports: Dict[str, set] = {}
    for fn in all_functions:
        f = fn.get("file")
        if not f:
            continue
        is_sentinel = fn.get("name") == "__file__"
        if f not in files_map:
            files_map[f] = {"language": fn.get("language"), "fn_count": 0}
        if not is_sentinel:
            files_map[f]["fn_count"] += 1
        if fn.get("imports"):
            file_imports.setdefault(f, set()).update(fn.get("imports", []))

    fn_to_file = {fn.get("name"): fn.get("file") for fn in all_functions}
    stem_to_files = _build_stem_to_files(all_functions)
    file_calls: Dict[tuple, int] = {}
    for fn in all_functions:
        for called in fn.get("calls", []):
            src_f = fn.get("file")
            tgt_f = fn_to_file.get(called)
            if src_f and tgt_f and tgt_f != src_f:
                key = (src_f, tgt_f)
                file_calls[key] = file_calls.get(key, 0) + 1

    for src_file, imported_names in file_imports.items():
        for imported_name in imported_names:
            tgt_f = _resolve_import(imported_name, stem_to_files, src_file)
            if tgt_f and tgt_f != src_file:
                key = (src_file, tgt_f)
                file_calls[key] = file_calls.get(key, 0) + 1

    nodes = [
        {"id": f, "type": "file", "language": info["language"], "fn_count": info["fn_count"]}
        for f, info in files_map.items()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in file_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": "files"}


def build_file_graph(module_name: str, all_functions: List[Dict]) -> Dict:
    files_in_module = {}
    for fn in all_functions:
        if fn.get("module") != module_name:
            continue
        f = fn.get("file")
        if f not in files_in_module:
            files_in_module[f] = {"language": fn.get("language"), "functions": []}
        files_in_module[f]["functions"].append(fn.get("name"))

    fn_to_file = {fn.get("name"): fn.get("file") for fn in all_functions if fn.get("module") == module_name}
    file_calls = {}
    file_imports = {}
    for fn in all_functions:
        if fn.get("module") != module_name:
            continue
        if fn.get("imports"):
            file_imports.setdefault(fn.get("file"), set()).update(fn.get("imports", []))
        for called in fn.get("calls", []):
            target_file = fn_to_file.get(called)
            if target_file and target_file != fn.get("file"):
                key = (fn.get("file"), target_file)
                file_calls[key] = file_calls.get(key, 0) + 1

    # Build stem->files restricted to this module for resolution
    module_fns = [fn for fn in all_functions if fn.get("module") == module_name]
    stem_to_files_module = _build_stem_to_files(module_fns)

    for src_file, imported_names in file_imports.items():
        for imported_name in imported_names:
            target_file = _resolve_import(imported_name, stem_to_files_module, src_file)
            if target_file and target_file != src_file:
                key = (src_file, target_file)
                file_calls[key] = file_calls.get(key, 0) + 1

    nodes = [
        {"id": f, "type": "file", "language": info["language"], "fn_count": len(info["functions"])}
        for f, info in files_in_module.items()
    ]
    edges = [
        {"source": src, "target": tgt, "call_count": cnt}
        for (src, tgt), cnt in file_calls.items()
    ]
    return {"nodes": nodes, "edges": edges, "tier": 2, "module": module_name}


def build_function_graph(file_path: str, all_functions: List[Dict]) -> Dict:
    # শুধু file path দিয়ে match করো
    file_fns = [fn for fn in all_functions if fn.get("file") == file_path]
    
    if not file_fns:
        # God file chunk case: virtual_module id দিয়ে call হয়েছে
        file_fns = [fn for fn in all_functions if fn.get("virtual_module") == file_path]

    fn_names = {fn.get("name") for fn in file_fns}

    # Chunking check
    virtual_modules = {}
    for fn in file_fns:
        vm = fn.get("virtual_module") or file_path
        virtual_modules.setdefault(vm, []).append(fn)

    # God file: same file has multiple virtual_modules → show chunk-level graph
    files_in_result = {fn.get("file") for fn in file_fns}
    # Only chunk when all fns are from one file (same god file) AND there are multiple chunk groups
    non_default_vms = {vm for vm in virtual_modules if vm != file_path}

    if len(non_default_vms) > 1 and len(files_in_result) == 1:
        # এটা god file chunk view — file_path আসলে একটা virtual_module id
        nodes = []
        for vm_name, fns in virtual_modules.items():
            if vm_name == file_path:
                continue  # skip the default (unchunked) bucket
            nodes.append({
                "id": vm_name,
                "type": "chunk",
                "fn_count": len(fns),
                "language": fns[0].get("language"),
            })
        fn_to_vm = {fn.get("name"): (fn.get("virtual_module") or file_path) for fn in file_fns}
        chunk_calls = {}
        for fn in file_fns:
            src_vm = fn_to_vm.get(fn.get("name"))
            if src_vm == file_path:
                continue  # skip unchunked functions
            for called in fn.get("calls", []):
                tgt_vm = fn_to_vm.get(called)
                if tgt_vm and tgt_vm != src_vm and tgt_vm != file_path:
                    key = (src_vm, tgt_vm)
                    chunk_calls[key] = chunk_calls.get(key, 0) + 1
        edges = [{"source": src, "target": tgt, "call_count": cnt} for (src, tgt), cnt in chunk_calls.items()]
        return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": True}

    # Normal case: সরাসরি function graph (class split হলেও)
    name_counts: Dict[str, int] = {}
    for fn in file_fns:
        name = fn.get("name", "")
        name_counts[name] = name_counts.get(name, 0) + 1
    has_duplicates = any(v > 1 for v in name_counts.values())

    def _node_id(fn: Dict) -> str:
        name = fn.get("name", "")
        if has_duplicates and name_counts.get(name, 1) > 1:
            return f"{name}:{fn.get('line_start')}"
        return name

    nodes = [
        {
            "id": _node_id(fn),
            "label": fn.get("name"),
            "type": "function",
            "line_start": fn.get("line_start"),
            "line_end": fn.get("line_end"),
            "complexity": fn.get("complexity"),
            "fan_in": fn.get("fan_in"),
            "fan_out": fn.get("fan_out"),
            "risk_level": fn.get("risk_level", "none"),
            "is_dead": fn.get("is_dead", False),
            "dead_confidence": fn.get("dead_confidence", "none"),
            "language": fn.get("language"),
        }
        for fn in file_fns
    ]

    # called name → list of node ids (for duplicate targets)
    name_to_ids: Dict[str, list] = {}
    for fn in file_fns:
        name_to_ids.setdefault(fn.get("name", ""), []).append(_node_id(fn))

    seen_edges: set = set()
    edges = []
    for fn in file_fns:
        src_id = _node_id(fn)
        for called in fn.get("calls", []):
            if called not in fn_names:
                continue
            for tgt_id in name_to_ids.get(called, []):
                key = (src_id, tgt_id)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": src_id, "target": tgt_id})

    return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": False}


# ── Integrated Metrics Computation ─────────────────────────────────────────

def _detect_cycles(functions: List[Dict]) -> List[List[str]]:
    """DFS-based cycle detection on the call graph. Returns up to 10 short cycles."""
    fn_set = {fn["name"] for fn in functions if fn.get("name") != "__file__"}
    adj: Dict[str, List[str]] = {}
    for fn in functions:
        n = fn.get("name", "")
        if n == "__file__":
            continue
        adj[n] = [c for c in fn.get("calls", []) if c in fn_set]

    found: List[List[str]] = []
    visited: set = set()
    stack: List[str] = []
    on_stack: Dict[str, int] = {}

    def _dfs(node: str) -> None:
        if len(found) >= 10:
            return
        visited.add(node)
        on_stack[node] = len(stack)
        stack.append(node)
        for nxt in adj.get(node, []):
            if nxt not in visited:
                _dfs(nxt)
            elif nxt in on_stack and (len(stack) - on_stack[nxt]) <= 6:
                found.append(stack[on_stack[nxt]:] + [nxt])
        stack.pop()
        del on_stack[node]

    for node in list(adj):
        if node not in visited:
            _dfs(node)

    seen_keys: set = set()
    unique: List[List[str]] = []
    for c in found:
        k = frozenset(c)
        if k not in seen_keys:
            seen_keys.add(k)
            unique.append(c)
    return unique[:10]


def _max_call_chain_depth(functions: List[Dict]) -> int:
    """BFS from root functions to find the longest call chain."""
    fn_set = {fn["name"] for fn in functions if fn.get("name") != "__file__"}
    adj: Dict[str, List[str]] = {}
    in_deg: Dict[str, int] = {}
    for fn in functions:
        n = fn.get("name", "")
        if n == "__file__":
            continue
        calls = [c for c in fn.get("calls", []) if c in fn_set]
        adj[n] = calls
        in_deg.setdefault(n, 0)
        for c in calls:
            in_deg[c] = in_deg.get(c, 0) + 1

    roots = [n for n, d in in_deg.items() if d == 0] or list(adj)[:5]
    max_d = 0
    for root in roots[:8]:
        q: deque = deque([(root, 0, frozenset([root]))])
        while q:
            node, d, vis = q.popleft()
            if d > max_d:
                max_d = d
            if d >= 40:
                continue
            for nxt in adj.get(node, []):
                if nxt not in vis:
                    q.append((nxt, d + 1, vis | {nxt}))
    return max_d


def _halstead_metrics(files: List[Dict]) -> Dict:
    """Compute simplified Halstead program metrics across all source files."""
    op_re = re.compile(
        r'\b(?:if|elif|else|while|for|switch|case|default|do|'
        r'return|break|continue|throw|raise|yield|'
        r'new|delete|typeof|instanceof|'
        r'class|function|def|lambda|'
        r'try|catch|except|finally|'
        r'async|await|import|from|'
        r'and|or|not|in|is|with|'
        r'var|let|const|pub|fn|impl|use|match|struct|enum)\b|'
        r'(?:<<=?|>>=?|>>>|<<|>>'
        r'|\*\*|//|->|=>|::'
        r'|[+\-*/%&|^~]=?|[<>!=]=?|&&|\|\||[?:,;])'
    )
    id_re = re.compile(r'\b[A-Za-z_]\w*\b')
    noise_re = re.compile(
        r'(""".*?"""|\'\'\'.*?\'\'\'|"[^"\\]*"|\'[^\'\\]*\'|`[^`]*`'
        r'|//[^\n]*|/\*.*?\*/|#[^\n]*)',
        re.DOTALL,
    )

    all_ops: List[str] = []
    all_ids: List[str] = []
    op_kw_cache: Optional[set] = None

    for f in files:
        raw = f.get("content", "")
        cleaned = noise_re.sub(" ", raw)
        ops = op_re.findall(cleaned)
        if op_kw_cache is None:
            op_kw_cache = set(ops)
        else:
            op_kw_cache.update(ops)
        all_ops.extend(ops)
        all_ids.extend(i for i in id_re.findall(cleaned) if i not in (op_kw_cache or set()))

    n1 = len(set(all_ops))
    n2 = len(set(all_ids))
    N1, N2 = len(all_ops), len(all_ids)
    vocab = n1 + n2
    length = N1 + N2
    volume = length * math.log2(max(vocab, 2))
    difficulty = (n1 / 2) * (N2 / max(n2, 1))
    return {
        "volume": round(volume, 1),
        "difficulty": round(difficulty, 1),
        "effort": round(difficulty * volume, 0),
        "vocab": vocab,
    }


def _maintainability_index(hv: float, avg_cc: float, avg_loc: float) -> float:
    """Microsoft Maintainability Index (0–100, higher = more maintainable)."""
    try:
        raw = (171 - 5.2 * math.log(max(hv, 1))
               - 0.23 * avg_cc
               - 16.2 * math.log(max(avg_loc, 1)))
        return round(max(0.0, min(100.0, raw * 100 / 171)), 1)
    except Exception:
        return 50.0


def compute_aggregate_metrics(all_functions: List[Dict], files: List[Dict]) -> Dict:
    """Compute comprehensive Integrated Metrics Dashboard data."""
    real = [fn for fn in all_functions if fn.get("name") != "__file__"]

    # Build content map for parameter extraction
    content_map: Dict[str, str] = {f.get("path", ""): f.get("content", "") for f in files}

    # ── LOC / SLOC ──────────────────────────────────────────────────────────
    total_loc = total_sloc = 0
    for f in files:
        lines = f.get("content", "").split("\n")
        total_loc += len(lines)
        total_sloc += sum(
            1 for ln in lines
            if ln.strip() and not ln.strip().startswith(("#", "//", "/*", "*", "'''", '"""'))
        )

    n_files = len(files)
    n_fns = len(real)
    total_calls = sum(fn.get("fan_out", 0) for fn in real)

    # ── Cyclomatic Complexity ────────────────────────────────────────────────
    ccs = [fn.get("complexity", 1) for fn in real]
    avg_cc = round(sum(ccs) / max(len(ccs), 1), 2)
    max_cc = max(ccs, default=1)
    total_decision = sum(max(0, c - 1) for c in ccs)

    # ── Cognitive Complexity (approximation) ────────────────────────────────
    # Full cognitive CC requires a complete AST nesting walk; this is an
    # approximation that weights avg cyclomatic CC by a base factor and adds a
    # nesting penalty derived from the per-function max_nesting_depth values we
    # already have.  Reported in the UI as an approximation.
    nesting_penalty = sum(fn.get("max_nesting_depth", 0) for fn in real)
    cognitive_cc = round(avg_cc * 1.2 + (nesting_penalty / max(n_fns, 1)) * 0.5, 2)

    # ── Parameters ──────────────────────────────────────────────────────────
    param_counts: List[int] = []
    for fn in real:
        content = content_map.get(fn.get("file", ""), "")
        ls = fn.get("line_start", 0)
        if content and 0 < ls <= content.count("\n") + 1:
            fn_lines = content.split("\n")
            # Join up to 10 lines from line_start so multi-line signatures are handled.
            sig_lines: List[str] = []
            for line in fn_lines[ls - 1: ls + 10]:
                sig_lines.append(line)
                if ")" in line:
                    break
            sig = " ".join(sig_lines)
            ps, pe = sig.find("("), sig.rfind(")")
            if ps != -1 and pe > ps:
                pstr = sig[ps + 1:pe].strip()
                if pstr:
                    pl = [p.strip() for p in pstr.split(",") if p.strip()]
                    if fn.get("language") == "python" and pl and pl[0] in ("self", "cls"):
                        pl = pl[1:]
                    param_counts.append(len(pl))
                else:
                    param_counts.append(0)

    avg_params = round(sum(param_counts) / max(len(param_counts), 1), 1)
    max_params = max(param_counts, default=0)

    # ── Orphan Nodes ────────────────────────────────────────────────────────
    orphans = sum(
        1 for fn in real
        if fn.get("fan_in", 0) == 0
        and fn.get("fan_out", 0) == 0
        and not _is_entry_point(fn.get("name", ""))
    )

    # ── Structural Analysis ─────────────────────────────────────────────────
    cycles = _detect_cycles(real)
    max_depth = _max_call_chain_depth(real)

    # ── Halstead ────────────────────────────────────────────────────────────
    hs = _halstead_metrics(files)

    # ── Maintainability Index ────────────────────────────────────────────────
    # Microsoft MI formula uses average LOC *per function*, not per file.
    # Using per-file LOC artificially deflates MI for large codebases.
    avg_loc_per_fn = total_sloc / max(n_fns, 1)
    mi = _maintainability_index(hs["volume"], avg_cc, avg_loc_per_fn)
    mi_label = (
        "Highly Maintainable" if mi >= 85 else
        "Maintainable"        if mi >= 65 else
        "Needs Attention"     if mi >= 40 else
        "Hard to Maintain"
    )

    return {
        "loc": total_loc,
        "sloc": total_sloc,
        "total_files": n_files,
        "total_functions": n_fns,
        "total_calls": total_calls,
        "avg_cyclomatic": avg_cc,
        "max_cyclomatic": max_cc,
        "decision_points": total_decision,
        "cognitive_complexity": cognitive_cc,
        "avg_parameters": avg_params,
        "max_parameters": max_params,
        "orphan_nodes": orphans,
        "circular_deps": len(cycles),
        "circular_dep_details": [" → ".join(c) for c in cycles[:5]],
        "max_call_chain_depth": max_depth,
        "halstead_volume": hs["volume"],
        "halstead_difficulty": hs["difficulty"],
        "maintainability_index": mi,
        "maintainability_label": mi_label,
    }