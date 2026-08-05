"""tree-sitter runtime setup: language grammars, parser factory, query
execution helpers, and the per-language function/call queries. Degrades
gracefully (returns no-op stubs that raise on use) when tree-sitter or a
language grammar package isn't installed — callers fall back to regex/AST
parsing in that case.
"""

import importlib
from typing import Dict

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
        Query = getattr(tree_sitter_module, "Query", None)
        QueryCursor = getattr(tree_sitter_module, "QueryCursor", None)

        # Dedicated TypeScript/TSX grammars (type annotations, generics, JSX
        # in .tsx). Falls back to the plain JS grammar — which chokes on
        # `: Type` annotations — only if the package truly isn't installed.
        try:
            tstypescript = importlib.import_module("tree_sitter_typescript")
            # the tsx grammar is a superset of the plain typescript one (adds
            # JSX), so it's used for both .ts and .tsx to keep one language key
            typescript_language = Language(tstypescript.language_tsx())
        except Exception:
            typescript_language = Language(tsjavascript.language())

        tree_sitter_languages = {
            "python":     Language(tspython.language()),
            "javascript": Language(tsjavascript.language()),
            "typescript": typescript_language,
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

        def run_query(lang, query_string: str, node) -> Dict[str, list]:
            """Execute a tree-sitter query and return {capture_name: [nodes]}.

            tree-sitter >= 0.22 moved capture execution off Query onto a
            separate QueryCursor object (Query.captures() was removed); older
            versions returned captures directly from Query and sometimes as a
            list of (node, name) tuples instead of a dict. Normalize both.
            """
            if Query is not None and QueryCursor is not None:
                query = Query(lang, query_string)
                return QueryCursor(query).captures(node)
            query = lang.query(query_string)
            raw = query.captures(node)
            if isinstance(raw, dict):
                return raw
            result: Dict[str, list] = {}
            for n, name in raw:
                result.setdefault(name, []).append(n)
            return result

        def run_query_matches(lang, query_string: str, node):
            """Execute a query and return [(pattern_index, {capture_name: node|[nodes]})].

            Unlike run_query()/captures(), this keeps captures grouped by the
            pattern match they came from — needed to pair an @fn_name capture
            with its sibling @fn_def when they're only related by appearing in
            the same query pattern (e.g. naming an arrow function from the
            property it's assigned to), not by AST field structure.
            """
            if Query is not None and QueryCursor is not None:
                query = Query(lang, query_string)
                return QueryCursor(query).matches(node)
            return lang.query(query_string).matches(node)

        return tree_sitter_languages, get_parser, run_query, run_query_matches
    except Exception:
        return {}, None, None, None


TREE_SITTER_LANGUAGES, get_parser, run_query, run_query_matches = _load_tree_sitter_runtime()

if get_parser is None:
    def get_parser(language: str):
        raise RuntimeError("tree-sitter is not available in this environment")

if run_query is None:
    def run_query(lang, query_string: str, node) -> Dict[str, list]:
        raise RuntimeError("tree-sitter is not available in this environment")

if run_query_matches is None:
    def run_query_matches(lang, query_string: str, node):
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

        (function_expression) @fn_def

        (variable_declarator
          name: (identifier) @fn_name
          value: (arrow_function) @fn_def)

        (variable_declarator
          name: (identifier) @fn_name
          value: (function_expression) @fn_def)

        (assignment_expression
          left: (member_expression
            property: (property_identifier) @fn_name)
          right: (arrow_function) @fn_def)

        (assignment_expression
          left: (member_expression
            property: (property_identifier) @fn_name)
          right: (function_expression) @fn_def)

        (pair
          key: (property_identifier) @fn_name
          value: (arrow_function) @fn_def)

        (pair
          key: (property_identifier) @fn_name
          value: (function_expression) @fn_def)
    """,

    "typescript": """
        (function_declaration
          name: (identifier) @fn_name) @fn_def

        (method_definition
          name: (property_identifier) @fn_name) @fn_def

        (arrow_function) @fn_def

        (function_expression) @fn_def

        (variable_declarator
          name: (identifier) @fn_name
          value: (arrow_function) @fn_def)

        (variable_declarator
          name: (identifier) @fn_name
          value: (function_expression) @fn_def)

        (assignment_expression
          left: (member_expression
            property: (property_identifier) @fn_name)
          right: (arrow_function) @fn_def)

        (assignment_expression
          left: (member_expression
            property: (property_identifier) @fn_name)
          right: (function_expression) @fn_def)

        (pair
          key: (property_identifier) @fn_name
          value: (arrow_function) @fn_def)

        (pair
          key: (property_identifier) @fn_name
          value: (function_expression) @fn_def)
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


# Tree-sitter queries for class/interface/struct/trait extraction. Each query
# captures the declaration node as a whole (@*_decl) plus its name, an optional
# single superclass, an optional container node for one-or-more implemented
# interfaces, and the body node — field/method lists are then read by walking
# the body node's children directly in Python (see UniversalParser._extract_classes)
# rather than trying to capture repeated children in the query itself: tree-sitter's
# `*`-quantified captures were found (via probing against the installed grammars)
# to unreliably return only the first repetition through matches(), so every
# multi-item list (fields, multiple implemented interfaces) is walked in Python
# instead of captured in Cypher-query-style S-expressions.
#
# JS and TS are NOT interchangeable here despite similar syntax: they're
# different grammar packages with different node type names for the same
# concept (JS: `class_heritage (identifier)` / `field_definition` / `property`
# field; TS: `class_heritage (extends_clause value: ...)` / `implements_clause`
# / `public_field_definition` / `name` field). Plain JS has no interfaces or
# abstract classes at all — a query referencing `interface_declaration` or
# `extends_clause` against the plain JS grammar fails to even compile.
CLASS_QUERIES = {
    # NOTE on `(class_heritage)? @heritage`: capturing the whole heritage node
    # and walking its children in Python (see `_parse_class_heritage` in
    # parser.py) rather than decomposing extends_clause/implements_clause
    # directly in the query is deliberate — capturing an entire *optional*
    # child node (e.g. `(implements_clause) @implements_list`) was observed to
    # silently drop a sibling optional capture (`@superclass`) on this grammar
    # whenever the captured-whole-node child is itself absent (e.g. a class
    # with `extends` but no `implements`). Capturing the parent node whole
    # sidesteps that quirk entirely.
    "javascript": """
        (class_declaration
          name: (identifier) @class_name
          (class_heritage)? @heritage
          body: (class_body) @class_body) @class_decl
    """,

    "typescript": """
        (class_declaration
          name: (type_identifier) @class_name
          (class_heritage)? @heritage
          body: (class_body) @class_body) @class_decl

        (abstract_class_declaration
          name: (type_identifier) @class_name
          (class_heritage)? @heritage
          body: (class_body) @class_body) @abstract_class_decl

        (interface_declaration
          name: (type_identifier) @interface_name
          (extends_type_clause)? @interface_extends_list
          body: (interface_body) @interface_body) @interface_decl
    """,

    "java": """
        (class_declaration
          (modifiers)? @modifiers
          name: (identifier) @class_name
          superclass: (superclass (type_identifier) @superclass)?
          interfaces: (super_interfaces)? @implements_list
          body: (class_body) @class_body) @class_decl

        (interface_declaration
          name: (identifier) @interface_name
          (extends_interfaces)? @interface_extends_list
          body: (interface_body) @interface_body) @interface_decl
    """,

    "go": """
        (type_declaration
          (type_spec
            name: (type_identifier) @struct_name
            type: (struct_type
              (field_declaration_list) @struct_body))) @struct_decl

        (type_declaration
          (type_spec
            name: (type_identifier) @interface_name
            type: (interface_type) @interface_body)) @interface_decl
    """,

    "rust": """
        (struct_item
          name: (type_identifier) @struct_name
          body: (field_declaration_list) @struct_body) @struct_decl

        (trait_item
          name: (type_identifier) @trait_name
          body: (declaration_list) @trait_body) @trait_decl

        (impl_item
          trait: (type_identifier)? @impl_trait
          type: (type_identifier) @impl_type
          body: (declaration_list) @impl_body) @impl_decl
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

# Instantiation ("does this method construct class X") is a genuinely
# different AST shape from a call in every language except Python — `new
# Foo()` (TS/JS), `new Foo()` (Java's object_creation_expression), and
# `Foo{}`/`&Foo{}` (Go's composite_literal) are none of them a
# call_expression at all, so CALL_QUERIES above never captures them. Needed
# for Factory Method/Abstract Factory/Builder/Prototype, which are
# fundamentally about "this method creates and returns an instance".
#
# No Python entry: `ClassName(...)` is syntactically identical to a plain
# function call in Python (`ast.Call`), so it already flows through the
# existing call-extraction path — see parser.py's Python instantiation
# handling, which filters `calls` down to names matching a known class.
INSTANTIATION_QUERIES = {
    "javascript": """
        (new_expression constructor: (identifier) @instantiated)
    """,
    "typescript": """
        (new_expression constructor: (identifier) @instantiated)
    """,
    "java": """
        (object_creation_expression type: (type_identifier) @instantiated)
    """,
    "go": """
        (composite_literal type: (type_identifier) @instantiated)
    """,
    "rust": """
        (call_expression function: (scoped_identifier path: (identifier) @instantiated))
    """,
}
