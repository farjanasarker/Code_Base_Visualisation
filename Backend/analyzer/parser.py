"""Per-language function/call parsing.

`UniversalParser.parse_file()` tries tree-sitter first (accurate AST-based
extraction) and falls back to a regex/AST parser per language whenever
tree-sitter isn't available, fails to parse, or yields zero functions —
which also covers environments where a language grammar package is missing.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .heuristics import (
    _compute_nesting_depth,
    _count_magic_literals,
    _is_anonymous_callback,
    _is_entry_point,
    _is_likely_runtime_invoked,
    _is_private_name,
)
from .tree_sitter_runtime import (
    CALL_QUERIES,
    CLASS_QUERIES,
    FUNCTION_QUERIES,
    INSTANTIATION_QUERIES,
    TREE_SITTER_LANGUAGES,
    get_parser,
    run_query,
    run_query_matches,
)


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
    # bare call-name -> owning class name, only populated when the call can be traced back to
    # a `self.<attr> = <ClassName>(...)` assignment — used to disambiguate same-named methods
    # across classes in the same file (e.g. self.cell.forward() vs self.forward()) when
    # rendering the flat function graph.
    call_targets: Dict[str, str] = field(default_factory=dict)
    fan_in: int = 0
    fan_out: int = 0
    # Dependency risk = how fragile this function is because of what it DEPENDS ON
    # (outgoing calls). Deliberately the opposite direction to impact analysis,
    # which walks callers (fan_in) to find what a change would break.
    risk_level: str = "none"      # none | low | medium | high
    risk_score: int = 0
    dep_direct: int = 0            # distinct project functions it calls directly
    dep_transitive: int = 0        # distinct project functions reachable via calls
    dep_cross_file: int = 0        # direct deps that live only in other files
    in_dep_cycle: bool = False     # part of a circular call chain
    is_dead: bool = False          # True → potentially unreachable
    dead_confidence: str = "none"  # none | medium | high
    max_nesting_depth: int = 0     # max block-nesting depth inside the function
    literal_count: int = 0         # count of non-trivial numeric literals (magic numbers)
    is_god_file: bool = False      # True → file classified as god_file and actually chunked
    # class this function is a method of, independent of `virtual_module` (which is also
    # reused as a god-file chunk id and shouldn't be overloaded further) — None for free functions
    class_name: Optional[str] = None
    is_method: bool = False
    # True only for Python's @abstractmethod (the one case where an abstract
    # declaration still gets a real ParsedFunction — see visit_FunctionDef).
    # Always False elsewhere; those languages' bodyless signatures never
    # produce a ParsedFunction at all, so there's nothing to flag.
    is_abstract: bool = False
    # Class names this function constructs an instance of (`new Foo()`,
    # `Foo{}`, `Foo::new()`, ...) — a genuinely different AST shape from a
    # call in every language but Python, see INSTANTIATION_QUERIES.
    instantiates: List[str] = field(default_factory=list)


@dataclass
class ParsedField:
    name: str
    type: str = ""
    is_collection: bool = False


@dataclass
class ParsedClass:
    name: str
    file: str
    language: str
    module: str
    kind: str  # class | abstract_class | interface | struct | trait
    bases: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    fields: List[ParsedField] = field(default_factory=list)
    # Every method *declared* on this class/interface/trait, by name —
    # deliberately independent of whether a Function/METHOD_OF node exists
    # for it: interface method signatures and abstract-method declarations
    # have no body, so they're never emitted as a ParsedFunction (nothing to
    # parse a call graph out of), but predicates like Strategy's
    # "interface with a single method" still need to count them.
    method_names: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


# Which class/struct-body child node types represent a field declaration, per
# language — bodies mix fields and methods (JS/TS class_body, Java class_body),
# so this filters the walk. Go/Rust struct bodies (field_declaration_list)
# contain nothing but fields, so no filter is needed for those (absent here).
_FIELD_NODE_TYPES = {
    "javascript": {"field_definition"},
    "typescript": {"public_field_definition"},
    "java": {"field_declaration"},
}

_COLLECTION_TYPE_HINTS = ("list<", "vec<", "array<", "set<", "hashset<",
                           "hashmap<", "map<", "dict<", "dict[",
                           # Python's typing module uses square brackets, not
                           # angle brackets, for generics (`List[Component]`).
                           "list[", "set[", "frozenset[", "sequence[")

_METHOD_NODE_TYPES = {
    "javascript": {"method_definition"},
    "typescript": {"method_signature", "method_definition", "abstract_method_signature"},
    "java": {"method_declaration"},
    "go": {"method_elem"},
    "rust": {"function_signature_item", "function_item"},
}


def _is_collection_type(type_text: str) -> bool:
    t = type_text.lower().strip()
    if t.endswith("[]"):
        return True
    return any(hint in t for hint in _COLLECTION_TYPE_HINTS)


def _field_name_node(child):
    """A field's name is under `name:` (Rust/Go/TS) or `property:` (plain JS)
    directly, or nested one level under `declarator:` (Java's
    `field_declaration -> variable_declarator -> name`).
    """
    for fname in ("name", "property"):
        n = child.child_by_field_name(fname)
        if n is not None:
            return n
    declarator = child.child_by_field_name("declarator")
    if declarator is not None:
        return declarator.child_by_field_name("name")
    return None


def _walk_fields(body_node, content: str, language: str) -> List[ParsedField]:
    if body_node is None:
        return []
    allowed_types = _FIELD_NODE_TYPES.get(language)
    fields: List[ParsedField] = []
    for child in body_node.named_children:
        if allowed_types is not None and child.type not in allowed_types:
            continue
        name_node = _field_name_node(child)
        if name_node is None:
            continue
        name = content[name_node.start_byte:name_node.end_byte]
        type_node = child.child_by_field_name("type")
        type_text = content[type_node.start_byte:type_node.end_byte].lstrip(":").strip() if type_node else ""
        fields.append(ParsedField(name=name, type=type_text, is_collection=_is_collection_type(type_text)))
    return fields


def _walk_method_names(body_node, content: str, language: str) -> List[str]:
    if body_node is None:
        return []
    allowed_types = _METHOD_NODE_TYPES.get(language)
    if not allowed_types:
        return []
    names: List[str] = []
    for child in body_node.named_children:
        if child.type not in allowed_types:
            continue
        name_node = _field_name_node(child)
        if name_node is None:
            continue
        names.append(content[name_node.start_byte:name_node.end_byte])
    return names


def _walk_type_names(container_node, content: str) -> List[str]:
    """Extract every listed type name out of a heterogeneous container node
    (Java `super_interfaces`/`extends_interfaces` — wraps a `type_list`; TS
    `implements_clause`/`extends_type_clause` — lists `type_identifier`s
    directly) by descending into any non-identifier wrapper children.
    """
    if container_node is None:
        return []
    names: List[str] = []

    def _walk(node):
        for child in node.named_children:
            if child.type.endswith("identifier"):
                names.append(content[child.start_byte:child.end_byte])
            elif child.named_child_count > 0:
                _walk(child)

    _walk(container_node)
    return names


def _parse_class_heritage(heritage_node, content: str, language: str) -> Tuple[List[str], List[str]]:
    """Extract (bases, interfaces) from a TS/JS `class_heritage` node's own
    children in Python, rather than via nested query captures — see the
    `(class_heritage)? @heritage` comment in tree_sitter_runtime.py for why.

    Plain JS `class_heritage` wraps a bare `(identifier)` superclass directly
    (JS has no `implements`). TS `class_heritage` wraps an optional
    `extends_clause` (`value:` field) and/or `implements_clause`.
    """
    bases: List[str] = []
    interfaces: List[str] = []
    if heritage_node is None:
        return bases, interfaces
    if language == "javascript":
        for child in heritage_node.named_children:
            if child.type == "identifier":
                bases.append(content[child.start_byte:child.end_byte])
        return bases, interfaces
    for child in heritage_node.named_children:
        if child.type == "extends_clause":
            value_node = child.child_by_field_name("value")
            if value_node is not None:
                bases.append(content[value_node.start_byte:value_node.end_byte])
        elif child.type == "implements_clause":
            interfaces.extend(_walk_type_names(child, content))
    return bases, interfaces


def _find_enclosing_class(
    class_ranges: List[Tuple[int, int, str]], start_byte: int, end_byte: int
) -> Optional[str]:
    """Smallest range fully containing [start_byte, end_byte) — smallest, not
    first, in case ranges ever nest (they don't for any language handled
    today, but this keeps the lookup correct if that changes).
    """
    best_name = None
    best_size = None
    for r_start, r_end, name in class_ranges:
        if r_start <= start_byte and end_byte <= r_end:
            size = r_end - r_start
            if best_size is None or size < best_size:
                best_name = name
                best_size = size
    return best_name


class UniversalParser:
    def parse_file(
        self, filepath: str, content: str, language: str
    ) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
        if language == "python":
            parsed = self._parse_python_ast(filepath, content)
            if parsed[0]:
                return parsed

        try:
            parser = get_parser(language)
        except Exception:
            return self._fallback_parse(filepath, content, language)

        try:
            tree = parser.parse(bytes(content, "utf8"))
        except Exception:
            return self._fallback_parse(filepath, content, language)

        try:
            classes, class_ranges = self._extract_classes(tree, content, filepath, language)
            functions = self._extract_functions(tree, content, filepath, language, class_ranges)
        except Exception:
            functions, classes = [], []

        # An interface/trait-only file legitimately produces zero
        # ParsedFunctions (method *signatures* have no body to extract a
        # function from) while still having real ParsedClasses — falling
        # back to regex here would discard those correctly-extracted
        # classes. Only fall back when tree-sitter found nothing at all.
        if not functions and not classes:
            return self._fallback_parse(filepath, content, language)

        return functions, classes

    def _fallback_parse(
        self, filepath: str, content: str, language: str
    ) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
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
        return [], []

    def _parse_java_regex(self, filepath: str, content: str) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"

        # Multi-class scoping: find EVERY class/interface header and brace-match
        # its body, then attribute each method only to the (smallest) range that
        # contains it. A single `re.search` for the first `class` keyword (the
        # previous behavior) silently collapsed every method in a multi-class
        # file onto whichever class happened to appear first in the file.
        type_header_pattern = re.compile(
            r"(?P<mods>(?:public|protected|private|abstract|final|static|strictfp|\s)*)"
            r"\b(?P<decl_kind>class|interface)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\s+extends\s+(?P<extends>[A-Za-z_][\w.<>,\s]*?))?"
            r"(?:\s+implements\s+(?P<implements>[A-Za-z_][\w.<>,\s]*?))?"
            r"\s*\{"
        )

        classes: List[ParsedClass] = []
        class_ranges: List[Tuple[int, int, str]] = []
        for header in type_header_pattern.finditer(content):
            name = header.group("name")
            brace_start = header.end() - 1
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

            kind = "interface" if header.group("decl_kind") == "interface" else (
                "abstract_class" if "abstract" in header.group("mods") else "class")
            extends_raw = header.group("extends")
            implements_raw = header.group("implements")
            bases = [extends_raw.strip()] if extends_raw else []
            interfaces = [s.strip() for s in implements_raw.split(",")] if implements_raw else []

            classes.append(ParsedClass(
                name=name, file=filepath, language="java", module=module, kind=kind,
                bases=bases, interfaces=interfaces, fields=[],
                line_start=content.count("\n", 0, header.start()) + 1,
                line_end=content.count("\n", 0, end_idx) + 1,
            ))
            class_ranges.append((header.start(), end_idx, name))

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

            class_name = _find_enclosing_class(class_ranges, match.start(), end_idx)
            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language="java",
                module=module,
                virtual_module=class_name or filepath,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=sorted(set(calls)),
                fan_out=len(set(calls)),
                max_nesting_depth=_compute_nesting_depth(method_body),
                literal_count=_count_magic_literals(method_body),
                class_name=class_name,
                is_method=class_name is not None,
            ))

        return functions, classes

    def _parse_js_ts_regex(
        self, filepath: str, content: str, language: str
    ) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"

        fn_patterns = [
            # function foo(...) { ... }
            re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.MULTILINE),
            # const foo = function(...) { ... } / const foo = async function(...) { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\s*\([^)]*\)\s*\{", re.MULTILINE),
            # const foo = (...) => { ... } / const foo = async (...) => { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", re.MULTILINE),
            # exports.foo = (...) / module.exports.foo = (...), function or arrow, optionally async
            re.compile(r"\b(?:module\.exports|exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\s*\([^)]*\)\s*\{", re.MULTILINE),
            re.compile(r"\b(?:module\.exports|exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", re.MULTILINE),
        ]

        # class Foo extends Bar implements Baz, Qux { ... }
        class_pattern = re.compile(
            r"\bclass\s+([A-Za-z_$][\w$]*)"
            r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?"
            r"(?:\s+implements\s+([A-Za-z_$][\w$.,\s]*?))?"
            r"\s*\{",
            re.MULTILINE,
        )
        method_pattern = re.compile(r"\n\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.MULTILINE)
        # TS typed field: `name: Type;` / `name: Type = ...;` at the top of a class body.
        typed_field_pattern = re.compile(
            r"^\s*(?:public|private|protected|readonly|static)*\s*"
            r"([A-Za-z_$][\w$]*)\s*:\s*([\w<>\[\].,\s]+?)\s*[=;]",
            re.MULTILINE,
        )
        # Untyped JS field: `this.name = ...` anywhere in the class body (constructor
        # or otherwise) — best-effort, may pick up a method-local `this.x =` write.
        this_field_pattern = re.compile(r"\bthis\.([A-Za-z_$][\w$]*)\s*=\s*(\[|\{|new\s+Map|new\s+Set)?")

        def _scan_class_fields(body: str) -> List[ParsedField]:
            field_map: Dict[str, ParsedField] = {}
            for m in typed_field_pattern.finditer(body):
                name, type_text = m.group(1), m.group(2).strip()
                if name in keywords or name == "constructor":
                    continue
                field_map[name] = ParsedField(name=name, type=type_text, is_collection=_is_collection_type(type_text))
            for m in this_field_pattern.finditer(body):
                name = m.group(1)
                if name in field_map:
                    continue
                hint = m.group(2) or ""
                field_map[name] = ParsedField(
                    name=name, type="", is_collection=hint.startswith("[") or "Map" in hint or "Set" in hint)
            return list(field_map.values())

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
                    virtual_module=filepath,
                    line_start=start_line,
                    line_end=end_line,
                    complexity=complexity,
                    calls=sorted(set(calls)),
                    fan_out=len(set(calls)),
                    max_nesting_depth=_compute_nesting_depth(body),
                    literal_count=_count_magic_literals(body),
                ))

        # class methods (best-effort)
        classes: List[ParsedClass] = []
        for class_match in class_pattern.finditer(content):
            class_name = class_match.group(1)
            extends_raw = class_match.group(2)
            implements_raw = class_match.group(3)
            brace_start, end_idx, body = _extract_body(class_match.end() - 1)
            if brace_start < 0:
                continue

            classes.append(ParsedClass(
                name=class_name, file=filepath, language=language, module=module,
                kind="class",
                bases=[extends_raw] if extends_raw else [],
                interfaces=[s.strip() for s in implements_raw.split(",")] if implements_raw else [],
                fields=_scan_class_fields(body),
                line_start=content.count("\n", 0, class_match.start()) + 1,
                line_end=content.count("\n", 0, end_idx) + 1,
            ))

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
                    virtual_module=class_name or filepath,
                    line_start=start_line,
                    line_end=end_line,
                    complexity=complexity,
                    calls=sorted(set(calls)),
                    fan_out=len(set(calls)),
                    max_nesting_depth=_compute_nesting_depth(method_body),
                    literal_count=_count_magic_literals(method_body),
                    class_name=class_name,
                    is_method=True,
                ))

        return functions, classes

    def _parse_go_regex(self, filepath: str, content: str) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
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

            # Prefix method name with receiver type for uniqueness, and use the
            # receiver type as this method's class_name — Go methods live outside
            # any type declaration, so the receiver is the only source of linkage.
            class_name = None
            if receiver_raw:
                rec_type = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*$', receiver_raw.strip())
                if rec_type:
                    class_name = rec_type.group(1)
                    fn_name = f"{class_name}.{fn_name_raw}"
                else:
                    fn_name = fn_name_raw
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
                virtual_module=class_name or filepath,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=sorted(set(calls)),
                fan_out=len(set(calls)),
                max_nesting_depth=_compute_nesting_depth(body),
                literal_count=_count_magic_literals(body),
                class_name=class_name,
                is_method=class_name is not None,
            ))

        classes = self._scan_go_types(filepath, content, module)
        return functions, classes

    def _scan_go_types(self, filepath: str, content: str, module: str) -> List[ParsedClass]:
        """Best-effort `type X struct {...}` / `type X interface {...}` regex
        scan, used only when tree-sitter's Go grammar isn't available — the
        common case (grammar installed) goes through `_extract_classes` instead.
        """
        classes: List[ParsedClass] = []
        type_header = re.compile(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s+(struct|interface)\s*\{")
        for header in type_header.finditer(content):
            name, decl_kind = header.group(1), header.group(2)
            brace_start = header.end() - 1
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
            body = content[brace_start + 1:end_idx]

            fields = []
            if decl_kind == "struct":
                for line in body.splitlines():
                    field_match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+([\[\]*\w.]+)", line)
                    if field_match:
                        f_name, f_type = field_match.group(1), field_match.group(2)
                        fields.append(ParsedField(name=f_name, type=f_type, is_collection=f_type.startswith("[]")))

            classes.append(ParsedClass(
                name=name, file=filepath, language="go", module=module,
                kind="interface" if decl_kind == "interface" else "struct",
                bases=[], interfaces=[], fields=fields,
                line_start=content.count("\n", 0, header.start()) + 1,
                line_end=content.count("\n", 0, end_idx) + 1,
            ))
        return classes

    def _parse_rust_regex(self, filepath: str, content: str) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
        module = Path(filepath).parts[0] if Path(filepath).parts else "root"

        # Every `impl (Trait for)? Type { ... }` block, brace-matched, so methods
        # are attributed to the impl block that actually contains them — a
        # single `.search()` for the first `impl` in the file (the previous
        # behavior) collapsed every function in a multi-impl file onto whichever
        # impl happened to appear first, and additionally mislabeled `impl Trait
        # for Type` blocks with the trait's name instead of the type's.
        impl_pattern = re.compile(
            r'\bimpl(?:<[^>]*>)?\s+(?:([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]*>)?\s+for\s+)?'
            r'([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]*>)?[^{;]*\{'
        )
        impl_ranges: List[Tuple[int, int, str]] = []
        for impl_match in impl_pattern.finditer(content):
            type_name = impl_match.group(2)
            brace_start = impl_match.end() - 1
            depth = 0
            end_idx = brace_start
            for i in range(brace_start, len(content)):
                ch = content[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            impl_ranges.append((impl_match.start(), end_idx, type_name))

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

            class_name = _find_enclosing_class(impl_ranges, match.start(), end_idx)
            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language='rust',
                module=module,
                virtual_module=class_name or filepath,
                line_start=start_line,
                line_end=end_line,
                complexity=complexity,
                calls=calls,
                fan_out=len(calls),
                max_nesting_depth=_compute_nesting_depth(body),
                literal_count=_count_magic_literals(body),
                class_name=class_name,
                is_method=class_name is not None,
            ))

        classes = self._scan_rust_types(filepath, content, module)
        return functions, classes

    def _scan_rust_types(self, filepath: str, content: str, module: str) -> List[ParsedClass]:
        """Best-effort `struct X {...}` / `trait X {...}` regex scan, used only
        when tree-sitter's Rust grammar isn't available — the common case
        (grammar installed) goes through `_extract_classes` instead.
        """
        classes: List[ParsedClass] = []
        type_header = re.compile(
            r'\b(struct|trait)\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^>]*>)?[^{;]*\{'
        )
        for header in type_header.finditer(content):
            decl_kind, name = header.group(1), header.group(2)
            brace_start = header.end() - 1
            depth = 0
            end_idx = brace_start
            for i in range(brace_start, len(content)):
                ch = content[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            body = content[brace_start + 1:end_idx]

            fields = []
            if decl_kind == "struct":
                for field_match in re.finditer(
                    r'(?:pub(?:\([^)]*\))?\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([\w<>\[\]:, ]+?)\s*[,\n]',
                    body,
                ):
                    f_name, f_type = field_match.group(1), field_match.group(2).strip()
                    fields.append(ParsedField(name=f_name, type=f_type, is_collection=_is_collection_type(f_type)))

            classes.append(ParsedClass(
                name=name, file=filepath, language="rust", module=module,
                kind="trait" if decl_kind == "trait" else "struct",
                bases=[], interfaces=[], fields=fields,
                line_start=content.count("\n", 0, header.start()) + 1,
                line_end=content.count("\n", 0, end_idx) + 1,
            ))
        return classes

    def _parse_python_ast(
        self, filepath: str, content: str
    ) -> Tuple[List[ParsedFunction], List[ParsedClass]]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return [], []

        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        functions: List[ParsedFunction] = []
        seen = set()

        # class_name -> {attr_name -> target_class_name}, from `self.<attr> = <ClassName>(...)`
        # assignments — lets call extraction tell `self.cell.forward()` (LSTMCell.forward)
        # apart from `self.forward()` (own class) when two classes share a method name.
        class_defs = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        class_names = {n.name for n in class_defs}
        self_attr_map: Dict[str, Dict[str, str]] = {}
        for cls_node in class_defs:
            attr_map: Dict[str, str] = {}
            for child in ast.walk(cls_node):
                if not (isinstance(child, ast.Assign) and isinstance(child.value, ast.Call)):
                    continue
                callee = child.value.func
                target_class = callee.id if isinstance(callee, ast.Name) else None
                if target_class not in class_names:
                    continue
                for tgt in child.targets:
                    if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"):
                        attr_map[tgt.attr] = target_class
            self_attr_map[cls_node.name] = attr_map

        classes = [self._build_parsed_class(cls_node, filepath, module, class_names)
                   for cls_node in class_defs]

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
                calls, call_targets, instantiates = self._extract_python_calls(node)
                # `@abstractmethod` methods still have a syntactic body
                # (`...`/`pass`), so they get a real ParsedFunction here
                # unlike TS/Java/Go/Rust's genuinely bodyless interface
                # signatures — is_abstract lets predicates that need
                # "concrete methods only" (e.g. Template Method's
                # abstract_method_called_from_concrete_sibling_method)
                # exclude them despite that.
                is_abstract = any(
                    (d.id if isinstance(d, ast.Name) else
                     d.attr if isinstance(d, ast.Attribute) else "") == "abstractmethod"
                    for d in node.decorator_list
                )
                functions.append(ParsedFunction(
                    name=node.name,
                    file=filepath,
                    language="python",
                    module=module,
                    virtual_module=self.current_class or filepath,
                    line_start=node.lineno,
                    line_end=line_end,
                    complexity=self._estimate_python_complexity(node),
                    calls=calls,
                    call_targets=call_targets,
                    max_nesting_depth=self._estimate_python_nesting(node),
                    literal_count=self._estimate_python_literals(node),
                    class_name=self.current_class,
                    is_method=self.current_class is not None,
                    is_abstract=is_abstract,
                    instantiates=instantiates,
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
                call_targets: Dict[str, str] = {}
                instantiates = set()
                attr_map = self_attr_map.get(self.current_class, {})
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = None
                        if isinstance(child.func, ast.Name):
                            callee = child.func.id
                            # Python has no separate `new` syntax — a
                            # constructor call is syntactically identical to
                            # a plain function call, so instantiation is
                            # just "a call whose bare name is a known class".
                            if callee in class_names:
                                instantiates.add(callee)
                        elif isinstance(child.func, ast.Attribute):
                            callee = child.func.attr
                            value = child.func.value
                            if isinstance(value, ast.Name) and value.id == "self" and self.current_class:
                                # self.<callee>() → definitely this class's own method
                                call_targets[callee] = self.current_class
                            elif (isinstance(value, ast.Attribute)
                                    and isinstance(value.value, ast.Name)
                                    and value.value.id == "self"):
                                # self.<attr>.<callee>() → resolve <attr>'s class if known
                                target_class = attr_map.get(value.attr)
                                if target_class:
                                    call_targets[callee] = target_class
                            elif (isinstance(value, ast.Call)
                                    and isinstance(value.func, ast.Name)
                                    and value.func.id == "super"):
                                # super().<callee>() → a real edge, but when
                                # <callee> matches the enclosing function's own
                                # name (the common super().__init__() case)
                                # it must not read as a same-node self-loop in
                                # the call-cycle detector.
                                call_targets[callee] = "__super__"
                        if callee:
                            calls.add(callee)
                return list(calls), call_targets, list(instantiates)

        visitor = PythonVisitor()
        visitor.visit(tree)
        for fn in functions:
            fn.fan_out = len(fn.calls)
        return functions, classes

    def _build_parsed_class(
        self, cls_node: ast.ClassDef, filepath: str, module: str, class_names: set,
    ) -> ParsedClass:
        def _base_name(node) -> str:
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return node.attr
            try:
                return ast.unparse(node)
            except Exception:
                return "?"

        def _annotation_text(node) -> str:
            try:
                return ast.unparse(node)
            except Exception:
                return ""

        def _value_is_collection(value) -> bool:
            if isinstance(value, (ast.List, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp)):
                return True
            if isinstance(value, ast.Call):
                callee = value.func
                name = (callee.id if isinstance(callee, ast.Name)
                        else callee.attr if isinstance(callee, ast.Attribute) else None)
                return name in ("list", "set", "dict", "List", "Set", "Dict", "defaultdict", "OrderedDict")
            return False

        bases = [_base_name(b) for b in cls_node.bases]
        kind = "class"
        if "Protocol" in bases:
            kind = "interface"
        elif "ABC" in bases:
            kind = "abstract_class"
        else:
            for kw in cls_node.keywords:
                if kw.arg == "metaclass" and _base_name(kw.value) == "ABCMeta":
                    kind = "abstract_class"
            if kind == "class":
                for stmt in cls_node.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                        (_base_name(d) if not isinstance(d, ast.Name) else d.id) == "abstractmethod"
                        for d in stmt.decorator_list
                    ):
                        kind = "abstract_class"
                        break

        field_map: Dict[str, ParsedField] = {}

        # Class-level attributes: direct statements in the class body only
        # (not nested in a method) — the common dataclass/attrs-style shape.
        for stmt in cls_node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                type_text = _annotation_text(stmt.annotation)
                field_map[stmt.target.id] = ParsedField(
                    name=stmt.target.id, type=type_text, is_collection=_is_collection_type(type_text))
            elif isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name):
                        field_map.setdefault(tgt.id, ParsedField(
                            name=tgt.id, type="", is_collection=_value_is_collection(stmt.value)))

        # Constructor-injection is the idiomatic Python shape for holding a
        # collaborator (`def __init__(self, strategy: PaymentStrategy):
        # self.strategy = strategy`) — the assignment's RHS is a bare Name,
        # not a `ClassName(...)` call, so its type has to come from the
        # parameter's own annotation. Collect every method's parameter
        # annotations up front so the self.attr walk below can resolve it.
        param_annotations: Dict[str, str] = {}
        for stmt in cls_node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in stmt.args.args:
                    if arg.annotation is not None:
                        param_annotations.setdefault(arg.arg, _annotation_text(arg.annotation))

        # Instance attributes: `self.<attr>` assignments anywhere in the class
        # (typically __init__), which is where most fields actually live.
        for child in ast.walk(cls_node):
            if isinstance(child, ast.AnnAssign):
                target = child.target
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    type_text = _annotation_text(child.annotation)
                    is_coll = _is_collection_type(type_text) or (
                        child.value is not None and _value_is_collection(child.value))
                    field_map[target.attr] = ParsedField(name=target.attr, type=type_text, is_collection=is_coll)
            elif isinstance(child, ast.Assign):
                for tgt in child.targets:
                    if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                        if tgt.attr in field_map and field_map[tgt.attr].type:
                            continue  # keep the richer (annotated) version already found
                        type_text = ""
                        if (isinstance(child.value, ast.Call) and isinstance(child.value.func, ast.Name)
                                and child.value.func.id in class_names):
                            type_text = child.value.func.id
                        elif isinstance(child.value, ast.Name):
                            type_text = param_annotations.get(child.value.id, "")
                        field_map[tgt.attr] = ParsedField(
                            name=tgt.attr, type=type_text, is_collection=_value_is_collection(child.value))

        method_names = [
            stmt.name for stmt in cls_node.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        return ParsedClass(
            name=cls_node.name, file=filepath, language="python", module=module, kind=kind,
            bases=bases, interfaces=[], fields=list(field_map.values()), method_names=method_names,
            line_start=cls_node.lineno, line_end=getattr(cls_node, "end_lineno", cls_node.lineno),
        )

    def _extract_classes(
        self, tree, content: str, filepath: str, language: str
    ) -> Tuple[List[ParsedClass], List[Tuple[int, int, str]]]:
        """Returns (classes, class_ranges).

        `class_ranges` is [(start_byte, end_byte, class_name)] for every
        class/interface/struct/trait body AND every Rust impl-block body —
        used by `_extract_functions` to link a method back to its containing
        class via byte-span containment. Impl blocks contribute a range but
        no `ParsedClass` of their own (the struct/trait they extend already
        has one, possibly parsed from a different match in the same file).
        """
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        query = CLASS_QUERIES.get(language)
        if not lang_obj or not query:
            return [], []

        try:
            matches = run_query_matches(lang_obj, query, tree.root_node)
        except Exception:
            return [], []

        def _first(v):
            return v[0] if isinstance(v, list) else v

        module = Path(filepath).parts[0] if Path(filepath).parts else "root"
        classes: List[ParsedClass] = []
        class_ranges: List[Tuple[int, int, str]] = []
        seen_spans = set()
        # Rust `impl Trait for Type` blocks: (type_name, trait_name) pairs to
        # merge into the matching struct's `interfaces` list after the main
        # loop, since impl and struct/trait declarations can appear in any
        # order and aren't guaranteed to share a single query match.
        rust_trait_impls: List[Tuple[str, str]] = []

        for _, cap in matches:
            decl = None
            kind = None
            for cap_key, resolved_kind in (
                ("class_decl", "class"),
                ("abstract_class_decl", "abstract_class"),
                ("interface_decl", "interface"),
                ("struct_decl", "struct"),
                ("trait_decl", "trait"),
                ("impl_decl", None),
            ):
                if cap_key in cap:
                    decl = _first(cap[cap_key])
                    kind = resolved_kind
                    break
            if decl is None:
                continue

            span = (decl.start_byte, decl.end_byte)
            if span in seen_spans:
                continue
            seen_spans.add(span)

            if kind is None:
                # Rust impl block: method->class linkage only, no ParsedClass of its own.
                impl_type_cap = cap.get("impl_type")
                if impl_type_cap is not None:
                    type_node = _first(impl_type_cap)
                    type_name = content[type_node.start_byte:type_node.end_byte]
                    class_ranges.append((decl.start_byte, decl.end_byte, type_name))

                    impl_trait_cap = cap.get("impl_trait")
                    if impl_trait_cap is not None:
                        trait_node = _first(impl_trait_cap)
                        trait_name = content[trait_node.start_byte:trait_node.end_byte]
                        rust_trait_impls.append((type_name, trait_name))
                continue

            name_cap = (cap.get("class_name") or cap.get("interface_name")
                        or cap.get("struct_name") or cap.get("trait_name"))
            if name_cap is None:
                continue
            name_node = _first(name_cap)
            name = content[name_node.start_byte:name_node.end_byte]

            if kind == "class" and language == "java":
                modifiers_cap = cap.get("modifiers")
                if modifiers_cap is not None:
                    mod_node = _first(modifiers_cap)
                    if "abstract" in content[mod_node.start_byte:mod_node.end_byte]:
                        kind = "abstract_class"

            if language in ("javascript", "typescript") and kind != "interface":
                heritage_cap = cap.get("heritage")
                heritage_node = _first(heritage_cap) if heritage_cap is not None else None
                bases, interfaces = _parse_class_heritage(heritage_node, content, language)
            else:
                superclass_cap = cap.get("superclass")
                bases = []
                if superclass_cap is not None:
                    sc_node = _first(superclass_cap)
                    bases.append(content[sc_node.start_byte:sc_node.end_byte])

                implements_container = cap.get("implements_list") or cap.get("interface_extends_list")
                interfaces = (
                    _walk_type_names(_first(implements_container), content)
                    if implements_container is not None else []
                )

            body_cap = (cap.get("class_body") or cap.get("struct_body")
                        or cap.get("trait_body") or cap.get("interface_body"))
            body_node = _first(body_cap) if body_cap is not None else None
            fields = _walk_fields(body_node, content, language)
            method_names = _walk_method_names(body_node, content, language)

            classes.append(ParsedClass(
                name=name, file=filepath, language=language, module=module, kind=kind,
                bases=bases, interfaces=interfaces, fields=fields, method_names=method_names,
                line_start=decl.start_point[0] + 1, line_end=decl.end_point[0] + 1,
            ))
            class_ranges.append((decl.start_byte, decl.end_byte, name))

        if rust_trait_impls:
            by_name = {c.name: c for c in classes}
            for type_name, trait_name in rust_trait_impls:
                c = by_name.get(type_name)
                if c is not None and trait_name not in c.interfaces:
                    c.interfaces.append(trait_name)

        return classes, class_ranges

    def _extract_functions(
        self, tree, content: str, filepath: str, language: str,
        class_ranges: List[Tuple[int, int, str]] = (),
    ) -> List[ParsedFunction]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []

        matches = run_query_matches(lang_obj, FUNCTION_QUERIES[language], tree.root_node)

        def _first(v):
            return v[0] if isinstance(v, list) else v

        # A given function node (e.g. an arrow_function) can be captured by
        # more than one pattern in the query — once generically as @fn_def
        # with no name, and again by a naming pattern (variable/property/
        # exports assignment) that pairs @fn_name with the same node in one
        # match. Collect any such name per node span before building results,
        # since arrow/function expressions have no "name" AST field of
        # their own to fall back on.
        name_by_span: Dict[Tuple[int, int], str] = {}
        ordered_defs = []
        seen_spans = set()

        for _, cap in matches:
            fn_def = cap.get("fn_def")
            if fn_def is None:
                continue
            fn_def = _first(fn_def)
            span = (fn_def.start_byte, fn_def.end_byte)
            fn_name_cap = cap.get("fn_name")
            if fn_name_cap is not None:
                name_node = _first(fn_name_cap)
                name_by_span[span] = content[name_node.start_byte:name_node.end_byte]
            if span not in seen_spans:
                seen_spans.add(span)
                ordered_defs.append(fn_def)

        functions: List[ParsedFunction] = []
        seen = set()

        # Every function's own span, used below to keep a call attributed to
        # only its *innermost* enclosing function — without this, a call sitting
        # inside a nested closure (e.g. a db.query callback) gets re-collected
        # by every ancestor function's own scoped query too, since a child
        # node's byte range is entirely inside its parent's range. That
        # phantom fan-out/fan-in inflation is what let a callback like
        # `anonymous_129` show up as a second "caller" of a function alongside
        # the outer named function that actually contains it.
        all_spans = [(n.start_byte, n.end_byte) for n in ordered_defs]

        # node -> (start_byte, end_byte) of the ParsedFunction built for it,
        # used by the anonymous-callback merge pass below.
        node_span_by_fn: Dict[int, Tuple[int, int]] = {}

        for node in ordered_defs:
            span = (node.start_byte, node.end_byte)
            # attempt to get the name child, else a name paired via the query, else anonymous
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                fn_name = content[name_node.start_byte:name_node.end_byte]
            elif span in name_by_span:
                fn_name = name_by_span[span]
            else:
                fn_name = f"anonymous_{node.start_point[0]}"

            # For Go method_declarations, prefix with receiver type for uniqueness.
            # Go methods live outside any type declaration (no enclosing struct
            # body span to match against class_ranges), so the receiver is the
            # only source of class linkage for this language.
            class_name = None
            if language == "go":
                recv_node = node.child_by_field_name("receiver")
                if recv_node:
                    recv_text = content[recv_node.start_byte:recv_node.end_byte]
                    rec_match = re.search(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\)', recv_text)
                    if rec_match:
                        class_name = rec_match.group(1)
                        fn_name = f"{class_name}.{fn_name}"
            else:
                class_name = _find_enclosing_class(class_ranges, node.start_byte, node.end_byte)

            key = (fn_name, node.start_point[0])
            if key in seen:
                continue
            seen.add(key)

            # Scope the call query to this function's own node — querying
            # tree.root_node instead would collect every call in the whole
            # file for every function. Also exclude any nested function's
            # span so a call made inside a closure is attributed only to
            # that innermost function, not to every ancestor whose range
            # happens to contain it too (see all_spans comment above).
            nested_spans = [
                s for s in all_spans
                if s != span and span[0] <= s[0] and s[1] <= span[1]
            ]
            calls = self._extract_calls(node, content, language, fn_name, exclude_spans=nested_spans)
            instantiates = self._extract_instantiations(node, content, language)

            # Java's method_declaration is the SAME node type for both a
            # concrete method and a bodyless abstract-method declaration
            # (`abstract void step();`) — unlike TS/Rust, which use distinct
            # node types for their bodyless forms (abstract_method_signature/
            # method_signature, function_signature_item) and so never reach
            # this path at all. Without this, an abstract Java method got a
            # real ParsedFunction with is_abstract defaulting to False,
            # making it indistinguishable from a concrete sibling method —
            # see abstract_method_called_from_concrete_sibling_method in
            # predicates.py, which relies on this flag to find Template
            # Method's abstract "step" methods.
            is_abstract = node.child_by_field_name("body") is None

            module = Path(filepath).parts[0] if Path(filepath).parts else "root"
            parsed_fn = ParsedFunction(
                name=fn_name,
                file=filepath,
                language=language,
                module=module,
                virtual_module=class_name or filepath,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                complexity=self._estimate_complexity(node, content),
                calls=calls,
                fan_out=len(calls),
                class_name=class_name,
                is_method=class_name is not None,
                is_abstract=is_abstract,
                instantiates=instantiates,
            )
            functions.append(parsed_fn)
            node_span_by_fn[id(parsed_fn)] = span

        # Anonymous callback scopes (`anonymous_<line>` — see _is_anonymous_
        # callback) are already excluded from the rendered function graph and
        # from dead-code flagging, because they have no name a user could
        # click through to. A call made directly inside one should read the
        # same way everywhere else: as coming from the nearest NAMED function
        # that actually contains it, not from the anonymous scope itself —
        # otherwise it either vanishes from that named function's fan_out
        # (now that nested_spans excludes the callback body above) or, worse,
        # surfaces in impact analysis as a confusing extra "anonymous_129"
        # caller with nothing to navigate to.
        for fn in functions:
            if not _is_anonymous_callback(fn.name) or not fn.calls:
                continue
            fn_span = node_span_by_fn[id(fn)]
            best_ancestor = None
            best_ancestor_span = None
            for other in functions:
                if other is fn or _is_anonymous_callback(other.name):
                    continue
                other_span = node_span_by_fn[id(other)]
                if other_span[0] <= fn_span[0] and fn_span[1] <= other_span[1]:
                    if best_ancestor_span is None or (
                        other_span[1] - other_span[0] < best_ancestor_span[1] - best_ancestor_span[0]
                    ):
                        best_ancestor = other
                        best_ancestor_span = other_span
            if best_ancestor is not None:
                best_ancestor.calls = sorted(set(best_ancestor.calls) | set(fn.calls))
                best_ancestor.fan_out = len(best_ancestor.calls)
                fn.calls = []
                fn.fan_out = 0

        return functions

    def _extract_calls(
        self, scope_node, content: str, language: str, current_fn_name: str,
        exclude_spans: List[Tuple[int, int]] = (),
    ) -> List[str]:
        """`current_fn_name` is unused for filtering — kept in the signature
        since callers already pass it and other extractors in this file take
        the same parameter shape. It USED to exclude any call whose bare
        name matched the enclosing method's own name, on the assumption that
        meant self-recursion. That's wrong for the single most common
        Decorator/Proxy/Chain of Responsibility shape there is: a wrapping
        method delegating to a SAME-NAMED method on a *different* object
        (`cost()` calling `wrapped.cost()`) — bare-name call extraction has
        no receiver info to tell that apart from true recursion, so the old
        filter silently dropped the delegation call entirely, not just
        mis-resolved it. Discarding the call was strictly worse than keeping
        it: genuine recursion is legitimate call-graph data too, and the
        class-aware resolution downstream (graph_view._resolve_callee_class)
        is the right layer to disambiguate same-name calls, not a blunt
        string-equality filter here that has no receiver context at all.
        """
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []
        raw_captures = run_query(lang_obj, CALL_QUERIES[language], scope_node)

        def _excluded(node) -> bool:
            return any(s <= node.start_byte and node.end_byte <= e for s, e in exclude_spans)

        calls = set()
        if isinstance(raw_captures, dict):
            for nodes in raw_captures.values():
                for node in nodes:
                    if _excluded(node):
                        continue
                    called = content[node.start_byte:node.end_byte]
                    if called:
                        calls.add(called)
        else:
            for node, _ in raw_captures:
                if _excluded(node):
                    continue
                called = content[node.start_byte:node.end_byte]
                if called:
                    calls.add(called)
        return list(calls)

    def _extract_instantiations(self, scope_node, content: str, language: str) -> List[str]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        query = INSTANTIATION_QUERIES.get(language)
        if not lang_obj or not query:
            return []
        try:
            raw_captures = run_query(lang_obj, query, scope_node)
        except Exception:
            return []

        instantiated = set()
        if isinstance(raw_captures, dict):
            for nodes in raw_captures.values():
                for node in nodes:
                    instantiated.add(content[node.start_byte:node.end_byte])
        else:
            for node, _ in raw_captures:
                instantiated.add(content[node.start_byte:node.end_byte])
        return list(instantiated)

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

    # Dependency-risk weights/thresholds (see compute_risk_scores).
    RISK_CYCLE_PENALTY = 6
    RISK_HIGH_SCORE = 25
    RISK_MEDIUM_SCORE = 10

    def compute_risk_scores(self, all_functions: List[ParsedFunction]) -> List[ParsedFunction]:
        """Dependency risk: how exposed a function is to breakage in the code it
        *calls* (forward edges). Impact analysis is the reverse question — who
        calls it (fan_in) and would break if it changed — so fan_in is not used here.

        score = 2*direct + (transitive - direct) + 2*cross_file + cycle penalty
        Only calls that resolve to a function defined in the project count;
        library / builtin calls are outside our control and ignored.
        """
        defs_by_name: Dict[str, set] = {}
        for fn in all_functions:
            defs_by_name.setdefault(fn.name, set()).add(fn.file)

        # name-level forward call graph restricted to project functions
        graph: Dict[str, set] = {name: set() for name in defs_by_name}
        for fn in all_functions:
            for callee in fn.calls:
                if callee in defs_by_name and callee != fn.name:
                    graph[fn.name].add(callee)

        # Tarjan SCC (iterative). Components are emitted sinks-first, so each
        # component's reachable set can be built from its already-finished children.
        index_of: Dict[str, int] = {}
        low: Dict[str, int] = {}
        on_stack: set = set()
        stack: List[str] = []
        comp_of: Dict[str, int] = {}
        comps: List[List[str]] = []
        counter = 0
        for root in graph:
            if root in index_of:
                continue
            work = [(root, iter(graph[root]))]
            index_of[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack.add(root)
            while work:
                node, it = work[-1]
                advanced = False
                for nxt in it:
                    if nxt not in index_of:
                        index_of[nxt] = low[nxt] = counter
                        counter += 1
                        stack.append(nxt)
                        on_stack.add(nxt)
                        work.append((nxt, iter(graph[nxt])))
                        advanced = True
                        break
                    if nxt in on_stack:
                        low[node] = min(low[node], index_of[nxt])
                if advanced:
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index_of[node]:
                    members = []
                    while True:
                        m = stack.pop()
                        on_stack.discard(m)
                        comp_of[m] = len(comps)
                        members.append(m)
                        if m == node:
                            break
                    comps.append(members)

        # reachable-set bitmask per component (bit i = name_bit[i] reachable)
        name_bit = {name: 1 << i for i, name in enumerate(graph)}
        reach: List[int] = [0] * len(comps)
        for cid, members in enumerate(comps):
            mask = 0
            for m in members:
                mask |= name_bit[m]
                for callee in graph[m]:
                    if comp_of[callee] != cid:
                        mask |= reach[comp_of[callee]]
            reach[cid] = mask

        for fn in all_functions:
            direct = graph[fn.name]
            cid = comp_of[fn.name]
            fn.dep_direct = len(direct)
            fn.dep_transitive = max(bin(reach[cid]).count("1") - 1, 0)
            fn.in_dep_cycle = len(comps[cid]) > 1
            fn.dep_cross_file = sum(1 for c in direct if fn.file not in defs_by_name[c])

            score = (
                2 * fn.dep_direct
                + (fn.dep_transitive - fn.dep_direct)
                + 2 * fn.dep_cross_file
                + (self.RISK_CYCLE_PENALTY if fn.in_dep_cycle else 0)
            )
            fn.risk_score = score
            if score >= self.RISK_HIGH_SCORE:
                fn.risk_level = "high"
            elif score >= self.RISK_MEDIUM_SCORE:
                fn.risk_level = "medium"
            elif score >= 1:
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

            # Inline anonymous function expressions (callback arguments,
            # object-literal handlers, IIFEs) — the call-graph has no name
            # to link a fan_in edge to, but the literal is always invoked
            # at its definition site by whatever received it.
            if _is_anonymous_callback(fn.name):
                fn.is_dead = False
                fn.dead_confidence = "none"
                continue

            # Callback / hook / handler-style names are invoked by a runtime we
            # can't see — never flag them.
            if _is_likely_runtime_invoked(fn.name):
                fn.is_dead = False
                fn.dead_confidence = "none"
                continue

            # Abstract declarations and methods are dispatched polymorphically,
            # so a missing static caller proves nothing.
            if fn.is_abstract or fn.is_method and not _is_private_name(fn.name, fn.language):
                fn.is_dead = False
                fn.dead_confidence = "none"
                continue

            # Only a private helper with no callers is flagged. A public
            # function with no callers is just as likely a library API, a
            # script's top-level function or a demo — reporting it would be a
            # false positive, so it is left unflagged.
            if _is_private_name(fn.name, fn.language):
                fn.is_dead = True
                fn.dead_confidence = "high"
            else:
                fn.is_dead = False
                fn.dead_confidence = "none"

        return all_functions
