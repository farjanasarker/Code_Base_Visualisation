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
from typing import Dict, List, Tuple

from .heuristics import (
    _compute_nesting_depth,
    _count_magic_literals,
    _is_entry_point,
    _is_likely_runtime_invoked,
    _is_private_name,
)
from .tree_sitter_runtime import (
    CALL_QUERIES,
    FUNCTION_QUERIES,
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
    risk_level: str = "none"      # none | low | medium | high
    is_dead: bool = False          # True → potentially unreachable
    dead_confidence: str = "none"  # none | medium | high
    max_nesting_depth: int = 0     # max block-nesting depth inside the function
    literal_count: int = 0         # count of non-trivial numeric literals (magic numbers)
    is_god_file: bool = False      # True → file classified as god_file and actually chunked


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
                virtual_module=class_name or filepath,
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
            # const foo = function(...) { ... } / const foo = async function(...) { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\s*\([^)]*\)\s*\{", re.MULTILINE),
            # const foo = (...) => { ... } / const foo = async (...) => { ... }
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", re.MULTILINE),
            # exports.foo = (...) / module.exports.foo = (...), function or arrow, optionally async
            re.compile(r"\b(?:module\.exports|exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\s*\([^)]*\)\s*\{", re.MULTILINE),
            re.compile(r"\b(?:module\.exports|exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", re.MULTILINE),
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
                    virtual_module=class_name or filepath,
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
                virtual_module=filepath,
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
                virtual_module=current_impl or filepath,
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
                calls, call_targets = self._extract_python_calls(node)
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
                attr_map = self_attr_map.get(self.current_class, {})
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = None
                        if isinstance(child.func, ast.Name):
                            callee = child.func.id
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
                        if callee:
                            calls.add(callee)
                return list(calls), call_targets

        visitor = PythonVisitor()
        visitor.visit(tree)
        for fn in functions:
            fn.fan_out = len(fn.calls)
        return functions

    def _extract_functions(self, tree, content: str, filepath: str, language: str) -> List[ParsedFunction]:
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

            # Scope the call query to this function's own node — querying
            # tree.root_node instead would collect every call in the whole
            # file for every function.
            calls = self._extract_calls(node, content, language, fn_name)

            module = Path(filepath).parts[0] if Path(filepath).parts else "root"
            functions.append(ParsedFunction(
                name=fn_name,
                file=filepath,
                language=language,
                module=module,
                virtual_module=filepath,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                complexity=self._estimate_complexity(node, content),
                calls=calls,
                fan_out=len(calls),
            ))
        return functions

    def _extract_calls(self, scope_node, content: str, language: str, current_fn_name: str) -> List[str]:
        lang_obj = TREE_SITTER_LANGUAGES.get(language)
        if not lang_obj:
            return []
        raw_captures = run_query(lang_obj, CALL_QUERIES[language], scope_node)

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
