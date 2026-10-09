"""Dead-code / entry-point / private-name heuristics used by UniversalParser
and chunking logic to judge whether a function is a real entry point, a
runtime-invoked callback, or a private helper — and to measure nesting depth
and magic-literal counts inside a function body.
"""

import re

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


_ANONYMOUS_NAME_RE = re.compile(r'^anonymous_\d+$')


def _is_anonymous_callback(name: str) -> bool:
    """True for the parser's `anonymous_<line>` fallback name (see
    UniversalParser._extract_functions), assigned only when a function
    expression has no name of its own — i.e. it sits inline as a call
    argument, object-literal callback, or IIFE. Such a literal's only
    appearance IS its invocation site, so it is always run by whatever
    received it; a missing fan_in edge here is the AST call-graph's blind
    spot for argument-passed callbacks, not evidence of dead code.
    """
    return bool(_ANONYMOUS_NAME_RE.match(name))


_HASH_COMMENT_LANGS = frozenset({"python", "ruby", "bash", "shell", "perl", "r"})


def _strip_comments(content: str, language: str) -> str:
    """Blank out line/block comments so name-reference counting ignores them.

    String literals are left intact (a `#` or `//` inside a string is not a
    comment, and `getattr(obj, "name")` is a genuine reference). Newlines are
    preserved. Python docstrings are strings to the tokenizer and are kept.
    """
    hash_style = language in _HASH_COMMENT_LANGS
    out = []
    i, n = 0, len(content)
    quote = None            # active string delimiter: ', ", `, or triple forms
    while i < n:
        ch = content[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n and len(quote) == 1:
                out.append(content[i + 1])
                i += 2
                continue
            if content.startswith(quote, i):
                out.append(content[i + 1:i + len(quote)])
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if ch in "'\"`":
            quote = ch * 3 if (language == "python" and content.startswith(ch * 3, i)) else ch
            out.append(quote)
            i += len(quote)
            continue
        if hash_style and ch == "#":
            while i < n and content[i] != "\n":
                i += 1
            continue
        if not hash_style and content.startswith("//", i):
            while i < n and content[i] != "\n":
                i += 1
            continue
        if not hash_style and content.startswith("/*", i):
            end = content.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.append("\n" * content.count("\n", i, end))
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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
        # "do..." was dropped: it also matched ordinary names like "document".
        return name.startswith("_")
    return name.startswith("_")
