"""
smell_detector.py — Pure static-analysis code smell detection.

Architecture:
  Static analysis detects smells from metrics (fan_in, fan_out, complexity, LOC, etc.)
  LLM does NOT run here — all rules are metric/pattern-based.
  LLM only receives the structured output of this module to reason about architecture.

Smell taxonomy:
  Function-level  : long_method, too_many_params, dead_code, feature_envy,
                    deep_nesting, switch_smell, magic_numbers
  Module-level    : god_module, god_class, large_module, shotgun_surgery,
                    divergent_change, lazy_class, duplicate_code, data_clumps
  Architecture    : circular_dependency, long_call_chain, inappropriate_intimacy
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any
import uuid

from .catalog import (
    THRESHOLDS, SEVERITY_WEIGHTS, REFACTOR_CATALOG, SMELL_CAUSATION,
)


# ── Smell Dataclass ───────────────────────────────────────────────────────────
@dataclass
class Smell:
    smell_id:            str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type:                str   = ""
    severity:            str   = "medium"   # critical | high | medium | low
    target_file:         str   = ""
    target_name:         str   = ""
    language:            str   = ""
    metrics:             Dict  = field(default_factory=dict)
    description:         str   = ""
    refactor_suggestions: List[str] = field(default_factory=list)
    # set by SmellGraph after graph analysis:
    root_cause_score:    float = 0.0
    downstream_count:    int   = 0

    def to_dict(self) -> Dict:
        return {
            "smell_id":            self.smell_id,
            "type":                self.type,
            "severity":            self.severity,
            "target_file":         self.target_file,
            "target_name":         self.target_name,
            "language":            self.language,
            "metrics":             self.metrics,
            "description":         self.description,
            "refactor_suggestions": self.refactor_suggestions,
            "root_cause_score":    self.root_cause_score,
            "downstream_count":    self.downstream_count,
        }


# ── Smell Detector ────────────────────────────────────────────────────────────
class SmellDetector:
    """
    Detects all code smells using only static metrics.
    No LLM, no code reading — pure numerical + structural analysis.
    """

    def __init__(self, thresholds: Optional[Dict] = None):
        self.t = {**THRESHOLDS, **(thresholds or {})}

    # ── Long Method ───────────────────────────────────────────────────────────
    def _long_methods(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            lines = (fn.get("line_end") or 0) - (fn.get("line_start") or 0)
            cc    = fn.get("complexity", 1)
            if lines <= self.t["long_method_lines"] and cc <= self.t["long_method_cc"]:
                continue
            sev = (
                "critical" if lines > 200 or cc > 25 else
                "high"     if lines > 80  or cc > 15 else
                "medium"
            )
            out.append(Smell(
                type="long_method",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={"lines": lines, "cyclomatic_complexity": cc},
                description=(
                    f"'{fn['name']}' spans {lines} lines with CC={cc} — "
                    f"hard to test, maintain and understand"
                ),
                refactor_suggestions=REFACTOR_CATALOG["long_method"],
            ))
        return out

    # ── God Module / God Class ────────────────────────────────────────────────
    def _god_modules(self, functions: List[Dict]) -> List[Smell]:
        """Detect God Module (folder/file level) and God Class (class level).

        When all functions in a bucket share the same virtual_module (class name),
        the smell is emitted as 'god_class' with the class name as target.
        Otherwise it's 'god_module'.
        """
        buckets: Dict[str, List[Dict]] = {}
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            key = fn.get("module") or fn.get("file") or "unknown"
            buckets.setdefault(key, []).append(fn)

        # Module names are flat directory-parent strings (e.g. "Backend",
        # "Backend/analyzer") with no built-in parent/child relationship, so a
        # folder that has both loose files and a subpackage ends up as two
        # sibling buckets. Flag which ones have a nested sibling so the
        # displayed name can make that relationship explicit instead of
        # reading like an unrelated duplicate module.
        module_keys = set(buckets.keys())

        out = []
        for mod, fns in buckets.items():
            n      = len(fns)
            avg_cc = sum(f.get("complexity", 1) for f in fns) / n

            # Detect whether this bucket maps to a single class (God Class)
            # or to a file/package (God Module).
            virtual_modules = {f.get("virtual_module", "") for f in fns}
            is_class_level  = (
                len(virtual_modules) == 1 and
                list(virtual_modules)[0] and
                list(virtual_modules)[0] != mod
            )

            if is_class_level:
                threshold_n  = self.t["god_class_fn_count"]
                threshold_cc = self.t["god_class_avg_cc"]
                smell_type   = "god_class"
                target_name  = list(virtual_modules)[0]
            else:
                threshold_n  = self.t["god_module_fn_count"]
                threshold_cc = self.t["god_module_avg_cc"]
                smell_type   = "god_module"
                target_name  = mod

            if n < threshold_n and avg_cc < threshold_cc:
                continue

            total_fo = sum(f.get("fan_out", 0) for f in fns)
            sev = (
                "critical" if n > 60 or avg_cc > 15 else
                "high"     if n > 20 or avg_cc > 10 else
                "medium"
            )
            entity = "Class" if is_class_level else "Module"

            has_child_modules = not is_class_level and any(
                other != mod and other.startswith(mod + "/") for other in module_keys
            )
            display_name = f"{target_name} (root files)" if has_child_modules else target_name

            out.append(Smell(
                type=smell_type,
                severity=sev,
                target_file=fns[0].get("file", "") if fns else mod,
                target_name=display_name,
                language=fns[0].get("language", "") if fns else "",
                metrics={
                    "function_count":  n,
                    "avg_cyclomatic":  round(avg_cc, 2),
                    "total_fan_out":   total_fo,
                },
                description=(
                    f"{entity} '{display_name}' has {n} methods (avg CC={avg_cc:.1f}) — "
                    f"Single Responsibility Principle violated"
                ),
                refactor_suggestions=REFACTOR_CATALOG[smell_type],
            ))
        return out

    # ── Feature Envy ─────────────────────────────────────────────────────────
    def _feature_envy(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            fo    = fn.get("fan_out", 0)
            fi    = fn.get("fan_in",  0)
            if fo < self.t["feature_envy_min_fan_out"]:
                continue
            ratio = fo / max(fi, 1)
            if ratio < self.t["feature_envy_ratio"]:
                continue
            sev = "high" if ratio >= 6 or fo >= 12 else "medium"
            out.append(Smell(
                type="feature_envy",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={"fan_out": fo, "fan_in": fi, "envy_ratio": round(ratio, 2)},
                description=(
                    f"'{fn['name']}' calls {fo} functions but is called by only {fi} "
                    f"(envy ratio {ratio:.1f}x) — likely misplaced responsibility"
                ),
                refactor_suggestions=REFACTOR_CATALOG["feature_envy"],
            ))
        return out

    # ── Shotgun Surgery ───────────────────────────────────────────────────────
    def _shotgun_surgery(self, functions: List[Dict]) -> List[Smell]:
        file_callers: Dict[str, Set[str]] = {}
        for fn in functions:
            src_file = fn.get("file", "")
            for called in fn.get("calls", []):
                file_callers.setdefault(called, set()).add(src_file)

        fn_map = {fn["name"]: fn for fn in functions if fn.get("name") != "__file__"}

        utility_fan_in = self.t["shotgun_surgery_utility_fan_in"]
        out = []
        for fn_name, callers in file_callers.items():
            if len(callers) < self.t["shotgun_surgery_files"]:
                continue
            fn = fn_map.get(fn_name)
            if not fn:
                continue
            # High fan_in means this is a purposefully shared utility (e.g. get_logger,
            # parse_config) — called widely by design, not a shotgun surgery victim.
            if fn.get("fan_in", 0) > utility_fan_in:
                continue
            sev = "critical" if len(callers) >= 20 else "high"
            out.append(Smell(
                type="shotgun_surgery",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn_name,
                language=fn.get("language", ""),
                metrics={"distinct_calling_files": len(callers)},
                description=(
                    f"'{fn_name}' is called from {len(callers)} different files — "
                    f"any change requires shotgun-wide updates"
                ),
                refactor_suggestions=REFACTOR_CATALOG["shotgun_surgery"],
            ))
        return out

    # ── Dead Code ─────────────────────────────────────────────────────────────
    def _dead_code(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            if not fn.get("is_dead", False):
                continue
            confidence = fn.get("dead_confidence", "none")
            if self.t["dead_code_high_only"] and confidence != "high":
                continue
            if confidence == "none":
                continue
            sev = "high" if confidence == "high" else "medium"
            out.append(Smell(
                type="dead_code",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={
                    "fan_in":     fn.get("fan_in",  0),
                    "fan_out":    fn.get("fan_out", 0),
                    "confidence": confidence,
                },
                description=(
                    f"'{fn['name']}' has no detected callers "
                    f"(confidence: {confidence}) — potential dead code"
                ),
                refactor_suggestions=REFACTOR_CATALOG["dead_code"],
            ))
        return out

    # ── Too Many Parameters ───────────────────────────────────────────────────
    def _too_many_params(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            p = fn.get("param_count", 0)
            if p <= self.t["too_many_params"]:
                continue
            sev = "high" if p >= 9 else "medium"
            out.append(Smell(
                type="too_many_params",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={"parameter_count": p},
                description=(
                    f"'{fn['name']}' has {p} parameters — "
                    f"difficult to call correctly and test in isolation"
                ),
                refactor_suggestions=REFACTOR_CATALOG["too_many_params"],
            ))
        return out

    # ── Deep Nesting ──────────────────────────────────────────────────────────
    def _deep_nesting(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            depth = fn.get("max_nesting_depth", 0)
            lines = max(1, (fn.get("line_end") or 0) - (fn.get("line_start") or 0))
            cc    = fn.get("complexity", 1)

            # Primary: explicit nesting depth metric
            if depth >= self.t["deep_nesting_depth"]:
                sev = "critical" if depth >= 7 else "high" if depth >= 5 else "medium"
                out.append(Smell(
                    type="deep_nesting",
                    severity=sev,
                    target_file=fn.get("file", ""),
                    target_name=fn.get("name", ""),
                    language=fn.get("language", ""),
                    metrics={"max_nesting_depth": depth, "lines": lines},
                    description=(
                        f"'{fn['name']}' reaches nesting depth {depth} — "
                        f"deeply nested code is hard to read and unit-test"
                    ),
                    refactor_suggestions=REFACTOR_CATALOG["deep_nesting"],
                ))
            # Fallback: CC/LOC heuristic when nesting depth = 0 (parser didn't extract it)
            elif depth == 0 and lines > 5 and cc > 6 and (cc / lines) >= self.t["deep_nesting_cc_heur"]:
                sev = "high" if (cc / lines) >= 0.30 else "medium"
                out.append(Smell(
                    type="deep_nesting",
                    severity=sev,
                    target_file=fn.get("file", ""),
                    target_name=fn.get("name", ""),
                    language=fn.get("language", ""),
                    metrics={"cyclomatic_complexity": cc, "lines": lines,
                             "cc_per_line": round(cc / lines, 2)},
                    description=(
                        f"'{fn['name']}' has CC={cc} across {lines} lines "
                        f"(ratio {cc/lines:.2f}) — dense branching suggests deep nesting"
                    ),
                    refactor_suggestions=REFACTOR_CATALOG["deep_nesting"],
                ))
        return out

    # ── Switch Smell ─────────────────────────────────────────────────────────
    def _switch_smell(self, functions: List[Dict]) -> List[Smell]:
        """Flag compact methods with high cyclomatic complexity (switch/if-chain smell)."""
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            cc    = fn.get("complexity", 1)
            lines = max(1, (fn.get("line_end") or 0) - (fn.get("line_start") or 0))
            if cc < self.t["switch_smell_min_cc"]:
                continue
            if lines > self.t["switch_smell_max_loc"]:
                continue  # long methods handled by long_method detector
            sev = "high" if cc >= 12 else "medium"
            out.append(Smell(
                type="switch_smell",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={"cyclomatic_complexity": cc, "lines": lines},
                description=(
                    f"'{fn['name']}' has CC={cc} in only {lines} lines — "
                    f"dense switch/if-chain; use polymorphism or Strategy pattern"
                ),
                refactor_suggestions=REFACTOR_CATALOG["switch_smell"],
            ))
        return out

    # ── Lazy Class ───────────────────────────────────────────────────────────
    def _lazy_class(self, functions: List[Dict]) -> List[Smell]:
        """Detect classes with very few meaningful methods (Lazy Class smell)."""
        buckets: Dict[str, List[Dict]] = {}
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            vm  = fn.get("virtual_module", "")
            mod = fn.get("module", "") or fn.get("file", "")
            # Only consider class-level groupings (virtual_module ≠ module)
            if vm and vm != mod and vm != fn.get("file", ""):
                buckets.setdefault(vm, []).append(fn)

        out = []
        for class_name, fns in buckets.items():
            n = len(fns)
            if n > self.t["lazy_class_max_fns"]:
                continue
            # Only flag if the methods are non-trivial (> 3 lines each)
            non_trivial = [
                f for f in fns
                if (f.get("line_end", 0) - f.get("line_start", 0)) > 3
            ]
            if not non_trivial:
                continue
            out.append(Smell(
                type="lazy_class",
                severity="low",
                target_file=fns[0].get("file", ""),
                target_name=class_name,
                language=fns[0].get("language", ""),
                metrics={"method_count": n},
                description=(
                    f"Class '{class_name}' has only {n} method(s) — "
                    f"consider inlining into a caller or merging with a related class"
                ),
                refactor_suggestions=REFACTOR_CATALOG["lazy_class"],
            ))
        return out

    # ── Duplicate Code ───────────────────────────────────────────────────────
    def _duplicate_code(self, _functions: List[Dict]) -> List[Smell]:
        """Duplicate detection is deferred to LLM analysis.

        Metric-similarity heuristics (same LOC + CC) produce too many false positives:
        two unrelated validation or mapping functions can have identical size/complexity
        without sharing any logic.  The LLM receives the full function list and can
        detect semantic duplicates that pure metrics cannot distinguish.
        """
        return []

    # ── Data Clumps ──────────────────────────────────────────────────────────
    def _data_clumps(self, functions: List[Dict]) -> List[Smell]:
        """Flag modules where ≥N functions all have high parameter counts."""
        mod_fns: Dict[str, List[Dict]] = {}
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            key = fn.get("module") or fn.get("file") or "unknown"
            mod_fns.setdefault(key, []).append(fn)

        out = []
        param_min   = self.t["data_clump_param_min"]
        clump_count = self.t["data_clump_fn_count"]

        for mod, fns in mod_fns.items():
            high_param = [f for f in fns if f.get("param_count", 0) >= param_min]
            if len(high_param) < clump_count:
                continue
            avg_params = sum(f.get("param_count", 0) for f in high_param) / len(high_param)
            sev    = "high" if avg_params >= 7 or len(high_param) >= 5 else "medium"
            worst  = max(high_param, key=lambda f: f.get("param_count", 0))
            out.append(Smell(
                type="data_clumps",
                severity=sev,
                target_file=worst.get("file", ""),
                target_name=f"{mod} ({len(high_param)} functions)",
                language=worst.get("language", ""),
                metrics={
                    "functions_with_high_params": len(high_param),
                    "avg_param_count": round(avg_params, 1),
                    "module": mod,
                },
                description=(
                    f"{len(high_param)} functions in '{mod}' all have "
                    f"{int(avg_params)}+ parameters — "
                    f"these likely form data clumps that should be encapsulated"
                ),
                refactor_suggestions=REFACTOR_CATALOG["data_clumps"],
            ))
        return out

    # ── Magic Numbers ─────────────────────────────────────────────────────────
    def _magic_numbers(self, functions: List[Dict]) -> List[Smell]:
        out = []
        for fn in functions:
            if fn.get("name") == "__file__":
                continue
            count = fn.get("literal_count", 0)
            if count < self.t["magic_number_min"]:
                continue
            sev = "high" if count >= 10 else "medium"
            out.append(Smell(
                type="magic_numbers",
                severity=sev,
                target_file=fn.get("file", ""),
                target_name=fn.get("name", ""),
                language=fn.get("language", ""),
                metrics={"magic_literal_count": count},
                description=(
                    f"'{fn['name']}' contains {count} unexplained numeric literals — "
                    f"use named constants for readability and maintainability"
                ),
                refactor_suggestions=REFACTOR_CATALOG["magic_numbers"],
            ))
        return out

    # ── Circular Dependency ───────────────────────────────────────────────────
    def _circular_deps(self, cycles: List[List[str]], name_to_file: Optional[Dict[str, str]] = None) -> List[Smell]:
        out = []
        name_to_file = name_to_file or {}
        for cycle in cycles:
            if len(cycle) < 2:
                continue
            chain = " → ".join(cycle)
            sev   = "critical" if len(cycle) <= 3 else "high"
            # cycle can span multiple files — anchor the smell on the first
            # function's file so it still shows up under a real file in the
            # Ranked Files view instead of falling into an "(unknown)" bucket.
            cycle_file = next((name_to_file[n] for n in cycle if name_to_file.get(n)), "")
            out.append(Smell(
                type="circular_dependency",
                severity=sev,
                target_file=cycle_file,
                target_name=chain[:70],
                language="",
                metrics={"cycle_length": len(cycle), "functions": cycle[:8]},
                description=(
                    f"Circular call chain ({len(cycle)} nodes): {chain[:100]}"
                ),
                refactor_suggestions=REFACTOR_CATALOG["circular_dependency"],
            ))
        return out

    # ── Long Call Chain ───────────────────────────────────────────────────────
    def _long_chain(self, max_depth: int) -> List[Smell]:
        if max_depth < self.t["long_chain_depth"]:
            return []
        sev = "critical" if max_depth >= 15 else "high" if max_depth >= 10 else "medium"
        return [Smell(
            type="long_call_chain",
            severity=sev,
            target_file="",
            target_name=f"depth={max_depth}",
            language="",
            metrics={"max_call_chain_depth": max_depth},
            description=(
                f"Call chain reaches depth {max_depth} — "
                f"indicates poor layering and hidden coupling between modules"
            ),
            refactor_suggestions=REFACTOR_CATALOG["long_call_chain"],
        )]

    # ── Orchestration ─────────────────────────────────────────────────────────
    def detect_all(
        self,
        functions:  List[Dict],
        metrics:    Dict,
        cycles:     Optional[List[List[str]]] = None,
    ) -> List["Smell"]:
        smells: List[Smell] = []
        smells += self._long_methods(functions)
        smells += self._god_modules(functions)       # emits god_class or god_module
        smells += self._feature_envy(functions)
        smells += self._shotgun_surgery(functions)
        smells += self._dead_code(functions)
        smells += self._too_many_params(functions)
        smells += self._deep_nesting(functions)
        smells += self._switch_smell(functions)
        smells += self._lazy_class(functions)
        smells += self._duplicate_code(functions)
        smells += self._data_clumps(functions)
        smells += self._magic_numbers(functions)
        if cycles:
            name_to_file = {
                fn.get("name"): fn.get("file", "")
                for fn in functions
                if fn.get("name") != "__file__"
            }
            smells += self._circular_deps(cycles, name_to_file)
        depth = metrics.get("max_call_chain_depth", 0)
        if depth:
            smells += self._long_chain(depth)
        return smells
