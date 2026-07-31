"""Graph builders for the frontend's tiered visualization: module-level
(tier 1), file-level within a module (tier 2), and function-level within a
file or god-file chunk (tier 3), plus a flat all-files graph.
"""

from pathlib import Path
from typing import Dict, List

from .heuristics import _is_anonymous_callback
from .imports_resolution import _build_stem_to_files, _module_basename, _resolve_import


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

    # Inline anonymous callbacks (db.query/.then/.addEventListener arguments, IIFEs,
    # multer option handlers, ...) are still tracked upstream for accurate fan_in/
    # dead-code/complexity — this only trims them from the rendered function graph,
    # where dozens of un-clickable "anonymous_<line>" boxes add noise without a
    # meaningful name to navigate to.
    file_fns = [fn for fn in file_fns if not _is_anonymous_callback(fn.get("name", ""))]

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
    # Only files that were actually classified as god_file at ingest time should get the
    # chunk-drill-down view — a normal small file with 2+ classes should show a flat function
    # graph instead, otherwise its top-level (non-class) functions get silently dropped below.
    is_actual_god_file = any(fn.get("is_god_file") for fn in file_fns)

    if len(non_default_vms) > 1 and len(files_in_result) == 1 and is_actual_god_file:
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
            # owning class, when this function is a method — lets same-named methods on
            # different classes (e.g. LSTMCell.forward vs LSTMModel.forward) be told apart
            "class_name": fn.get("virtual_module") if fn.get("virtual_module") != file_path else None,
        }
        for fn in file_fns
    ]

    # called name → list of node ids (for duplicate targets)
    name_to_ids: Dict[str, list] = {}
    id_to_vm: Dict[str, str] = {}
    for fn in file_fns:
        node_id = _node_id(fn)
        name_to_ids.setdefault(fn.get("name", ""), []).append(node_id)
        id_to_vm[node_id] = fn.get("virtual_module") or file_path

    seen_edges: set = set()
    edges = []
    for fn in file_fns:
        src_id = _node_id(fn)
        call_targets = fn.get("call_targets") or {}
        for called in fn.get("calls", []):
            if called not in fn_names:
                continue
            candidates = name_to_ids.get(called, [])
            # when the same method name exists on 2+ classes in this file, narrow to the
            # one actually being called (resolved from self.<attr> tracking at parse time)
            hinted_class = call_targets.get(called)
            if len(candidates) > 1 and hinted_class:
                narrowed = [c for c in candidates if id_to_vm.get(c) == hinted_class]
                if narrowed:
                    candidates = narrowed
            for tgt_id in candidates:
                key = (src_id, tgt_id)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"source": src_id, "target": tgt_id})

    return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": False}
