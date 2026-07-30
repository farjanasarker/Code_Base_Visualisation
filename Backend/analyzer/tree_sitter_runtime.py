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
