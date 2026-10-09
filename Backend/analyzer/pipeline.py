"""Top-level orchestration: parse every uploaded file, apply file-size
strategies (including god-file chunking), aggregate cross-file fan-in, flag
dead code, resolve imports, and compute architecture-layer violations —
producing the flat function-dict list the rest of the app (graph builders,
metrics, smell detection) consumes.
"""

import re
from typing import Dict, List, Tuple

from .chunking import chunk_god_file, detect_file_strategy
from .imports_resolution import (
    _detect_module_structure,
    _extract_file_imports,
    _fn_param_count,
    detect_unused_imports,
)
from .heuristics import _strip_comments
from .layers import _compute_layer_violations
from .parser import ParsedClass, ParsedFunction, UniversalParser


def analyze_files(files: List[Dict]) -> Tuple[List[Dict], List[Dict], Dict[str, List[str]], Dict]:
    """Parse all supported files, apply file strategies, and chunk god files.

    Returns (functions_list, classes_list, unused_import_map, layer_violations) where:
    • classes_list        → flat list of class/interface/struct/trait dicts (GoF pattern engine)
    • unused_import_map   → {file_path: [unused_import_names]}
    • layer_violations    → {by_module, summary, all_violations}
    """
    parser = UniversalParser()
    all_functions: List[ParsedFunction] = []
    all_classes: List[ParsedClass] = []

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

        parsed, file_classes = parser.parse_file(file_path, content, lang)

        # Override module based on detected structure
        detected_module = module_map.get(file_info.get("path", ""), "root")
        for p in parsed:
            p.module = detected_module
        for c in file_classes:
            c.module = detected_module

        # convert ParsedFunction objects to dicts for chunking convenience
        parsed_dicts = [p.__dict__ for p in parsed]

        if strategy == "god_file":
            chunks = chunk_god_file(file_path, content, lang, parsed_dicts)
            # assign virtual modules directly on the dicts already grouped per chunk —
            # these are the same dict objects backing each ParsedFunction (p.__dict__),
            # so mutating them here mutates `parsed` in place. Matching by name instead
            # (the old approach) mis-assigns every function sharing a common name
            # (__init__, forward, run, ...) to whichever chunk processes that name last.
            for chunk in chunks:
                for f in chunk["functions"]:
                    f["virtual_module"] = chunk["virtual_module"]
                    f["is_god_file"] = True

        all_functions.extend(parsed)
        all_classes.extend(file_classes)

    # compute fan-in, risk scores, dead code
    all_functions = parser.compute_fan_in(all_functions)

    # Supplementary cross-file text search for functions still at fan_in == 0.
    # The parsed call graph misses callbacks passed as arguments, variable-stored
    # functions, and dynamic dispatch patterns.  A regex scan across every other
    # file's raw content catches the common case of `fn_name(` appearing somewhere.
    # Comments are stripped so a name merely mentioned in one doesn't count as a use.
    lang_by_path = {
        f.get("path", "").replace("\\", "/"): f.get("language", "") for f in files
    }
    norm_content_map: Dict[str, str] = {
        k.replace("\\", "/"): _strip_comments(v, lang_by_path.get(k.replace("\\", "/"), ""))
        for k, v in file_content_map.items()
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
        else:
            # Same-file reference, e.g. `map(_helper, xs)` or `handlers = [_helper]`:
            # the name appears more than once (the definition is one occurrence),
            # so something other than the `def` mentions it.
            own = norm_content_map.get(fn.file, "")
            if len(pattern.findall(own)) > 1:
                fn.fan_in = 1

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
            "call_targets": fn.call_targets,
            "fan_in": fn.fan_in,
            "fan_out": fn.fan_out,
            "risk_level": fn.risk_level,
            "risk_score": fn.risk_score,
            "dep_direct": fn.dep_direct,
            "dep_transitive": fn.dep_transitive,
            "dep_cross_file": fn.dep_cross_file,
            "in_dep_cycle": fn.in_dep_cycle,
            "is_dead": fn.is_dead,
            "dead_confidence": fn.dead_confidence,
            "is_god_file": fn.is_god_file,
            "param_count":       _fn_param_count(fn, file_content_map),
            "max_nesting_depth": fn.max_nesting_depth,
            "literal_count":     fn.literal_count,
            "imports": file_import_map.get(fn.file, []),
            "class_name": fn.class_name,
            "is_method": fn.is_method,
            "is_abstract": fn.is_abstract,
            "instantiates": fn.instantiates,
        }
        for fn in all_functions
    ] + file_sentinels, [
        {
            "name": cls.name,
            "file": cls.file,
            "language": cls.language,
            "module": cls.module,
            "kind": cls.kind,
            "bases": cls.bases,
            "interfaces": cls.interfaces,
            "fields": [
                {"name": f.name, "type": f.type, "is_collection": f.is_collection}
                for f in cls.fields
            ],
            "method_names": cls.method_names,
            "line_start": cls.line_start,
            "line_end": cls.line_end,
        }
        for cls in all_classes
    ], file_unused_import_map, _compute_layer_violations(files, module_map, file_import_map)
