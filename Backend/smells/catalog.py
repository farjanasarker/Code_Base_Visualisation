"""
catalog.py — Static data for smell detection: thresholds, severity weights,
refactoring catalog and the smell causation model.
"""

from typing import Any, Dict, List


# ── Detection Thresholds ──────────────────────────────────────────────────────
THRESHOLDS: Dict[str, Any] = {
    # --- function-level ---
    "long_method_lines":        50,    # LoC in one function body
    "long_method_cc":           10,    # cyclomatic complexity
    "too_many_params":           5,    # parameter count
    "dead_code_high_only":    True,    # only high-confidence (private, uncalled) dead code
    "feature_envy_min_fan_out":  5,    # minimum fan_out to consider
    "feature_envy_ratio":        3.0,  # fan_out / fan_in
    "deep_nesting_depth":        4,    # max block-nesting depth to flag
    "deep_nesting_cc_heur":      0.18, # CC/LOC ratio fallback when no depth metric
    "switch_smell_min_cc":       6,    # minimum CC to suspect switch/if chains
    "switch_smell_max_loc":      40,   # only flag compact-but-complex methods
    "magic_number_min":          5,    # minimum non-trivial literal count
    # --- class / module-level ---
    "god_module_fn_count":      20,    # functions per module/file
    "god_module_avg_cc":         7.0,  # average CC in that module
    "god_class_fn_count":        7,    # methods per class (lower bar than module)
    "god_class_avg_cc":          4.0,  # average CC for class-level detection
    "large_module_loc":        400,    # lines of code per module/file
    "lazy_class_max_fns":        2,    # max methods for a class to be "lazy"
    "duplicate_loc_delta":       5,    # ±LOC for metric-similarity duplicate check
    "duplicate_cc_delta":        2,    # ±CC  for metric-similarity duplicate check
    "duplicate_min_loc":         8,    # minimum LOC to consider a function for duplication
    "data_clump_param_min":      4,    # per-function param_count threshold
    "data_clump_fn_count":       3,    # how many high-param functions to flag
    # --- architecture ---
    "shotgun_surgery_files":     8,    # distinct files that call a function
    "shotgun_surgery_utility_fan_in": 30,  # fan_in above this → shared utility, not a smell
    "long_chain_depth":          7,    # max call chain depth
}

SEVERITY_WEIGHTS: Dict[str, int] = {
    "critical": 4,
    "high":     3,
    "medium":   2,
    "low":      1,
}

# ── Refactoring Catalog ───────────────────────────────────────────────────────
REFACTOR_CATALOG: Dict[str, List[str]] = {
    "god_module":             ["Extract Class", "Apply Single Responsibility Principle",
                               "Split Module into Sub-packages"],
    "god_class":              ["Extract Class", "Apply Single Responsibility Principle",
                               "Decompose Class into Focused Components"],
    "large_module":           ["Move Functions by Responsibility", "Extract Class",
                               "Split into Submodules"],
    "long_method":            ["Extract Method", "Decompose Conditional",
                               "Replace Conditional with Polymorphism"],
    "too_many_params":        ["Introduce Parameter Object", "Preserve Whole Object",
                               "Remove Flag Argument"],
    "feature_envy":           ["Move Method", "Move Field", "Extract Class"],
    "shotgun_surgery":        ["Move Method", "Extract Service / Facade",
                               "Introduce Indirection"],
    "dead_code":              ["Delete Function",
                               "Add Test Coverage to Confirm Unreachability"],
    "circular_dependency":    ["Dependency Inversion Principle",
                               "Extract Interface / Abstract Class",
                               "Break Cycle with Event Bus or Mediator"],
    "long_call_chain":        ["Hide Delegate", "Introduce Facade",
                               "Apply Law of Demeter"],
    "inappropriate_intimacy": ["Move Method", "Change Bidirectional to Unidirectional",
                               "Hide Delegate"],
    "divergent_change":       ["Extract Class by Cohesion",
                               "Separate by Change Axis (SRP)"],
    "deep_nesting":           ["Extract Method", "Replace Nested Conditional with Guard Clauses",
                               "Decompose Conditional"],
    "switch_smell":           ["Replace Conditional with Polymorphism",
                               "Replace Type Code with Strategy Pattern",
                               "Extract Method per Branch"],
    "lazy_class":             ["Inline Class", "Collapse Hierarchy",
                               "Move to Utility Module"],
    "duplicate_code":         ["Extract Method", "Pull Up Method",
                               "Form Template Method"],
    "data_clumps":            ["Introduce Parameter Object", "Extract Class",
                               "Preserve Whole Object"],
    "primitive_obsession":    ["Replace Data Value with Object",
                               "Introduce Parameter Object", "Extract Class"],
    "magic_numbers":          ["Replace Magic Number with Named Constant",
                               "Extract Configuration / Constants Class",
                               "Use Enum for Related Constants"],
}

# ── Smell Causation Model ─────────────────────────────────────────────────────
# Defines which smell types are DOWNSTREAM (caused/worsened) by each upstream type.
# Fixing an upstream smell typically cascades to reduce/resolve downstream ones.
SMELL_CAUSATION: Dict[str, Dict] = {
    # ── Root-level architectural smells ───────────────────────────────────────
    "god_class": {
        "downstream": ["long_method", "too_many_params", "feature_envy",
                       "dead_code", "divergent_change", "deep_nesting",
                       "duplicate_code", "switch_smell", "data_clumps",
                       "magic_numbers"],
        "effort":     5,
        "layer":      "module",
        "note":       ("God Class violates SRP — one class absorbs too many responsibilities, "
                       "creating a cascade of function-level and architectural downstream smells. "
                       "Extract Class is the primary refactoring."),
    },
    "god_module": {
        "downstream": ["long_method", "too_many_params", "feature_envy",
                       "dead_code", "large_module", "divergent_change",
                       "deep_nesting", "duplicate_code", "switch_smell",
                       "data_clumps"],
        "effort":     5,
        "layer":      "module",
        "note":       ("God Module is the primary SRP violation — extracting classes "
                       "eliminates the root of multiple downstream smells."),
    },
    "circular_dependency": {
        "downstream": ["feature_envy", "inappropriate_intimacy", "divergent_change"],
        "effort":     4,
        "layer":      "architecture",
        "note":       ("Cycles lock modules together, making it impossible to cleanly "
                       "separate responsibilities or remove feature envy."),
    },
    "large_module": {
        "downstream": ["long_method", "dead_code", "divergent_change", "duplicate_code"],
        "effort":     3,
        "layer":      "module",
        "note":       ("Large modules accumulate mixed responsibilities over time."),
    },
    "long_call_chain": {
        "downstream": ["feature_envy", "inappropriate_intimacy"],
        "effort":     3,
        "layer":      "architecture",
        "note":       ("Deep chains indicate hidden coupling and misplaced logic."),
    },
    "shotgun_surgery": {
        "downstream": ["feature_envy"],
        "effort":     3,
        "layer":      "module",
        "note":       ("Widely-called functions develop envy as callers grow."),
    },
    # ── Mid-level smells ──────────────────────────────────────────────────────
    "long_method": {
        "downstream": ["too_many_params", "deep_nesting", "switch_smell"],
        "effort":     2,
        "layer":      "function",
        "note":       ("Long methods accumulate parameters, nesting, and branching over time."),
    },
    "divergent_change": {
        "downstream": ["feature_envy"],
        "effort":     2,
        "layer":      "module",
        "note":       ("Modules that change for many reasons develop envy."),
    },
    "data_clumps": {
        "downstream": ["too_many_params"],
        "effort":     2,
        "layer":      "function",
        "note":       ("Data clumps should be encapsulated into Parameter Objects or domain entities."),
    },
    "deep_nesting": {
        "downstream": ["too_many_params"],
        "effort":     2,
        "layer":      "function",
        "note":       ("Deep nesting hides logic and forces extra parameters to thread state."),
    },
    "duplicate_code": {
        "downstream": [],
        "effort":     2,
        "layer":      "function",
        "note":       ("Duplicate code is a maintainability tax — changes must be made in multiple places."),
    },
    "switch_smell": {
        "downstream": [],
        "effort":     2,
        "layer":      "function",
        "note":       ("Switch/if-chains should be replaced with polymorphism or the Strategy pattern."),
    },
    # ── Leaf smells (no downstream) ───────────────────────────────────────────
    "feature_envy": {
        "downstream": [],
        "effort":     2,
        "layer":      "function",
        "note":       "Leaf smell — directly fixed by moving the envious method.",
    },
    "too_many_params": {
        "downstream": [],
        "effort":     1,
        "layer":      "function",
        "note":       "Leaf smell — solved with Parameter Object.",
    },
    "dead_code": {
        "downstream": [],
        "effort":     0.5,
        "layer":      "function",
        "note":       "Leaf smell — safe to delete after confirming unreachability.",
    },
    "inappropriate_intimacy": {
        "downstream": [],
        "effort":     2,
        "layer":      "module",
        "note":       "Leaf smell — solved by hiding delegates or moving methods.",
    },
    "lazy_class": {
        "downstream": [],
        "effort":     1,
        "layer":      "module",
        "note":       "Lazy classes add cognitive overhead without providing sufficient value.",
    },
    "magic_numbers": {
        "downstream": [],
        "effort":     1,
        "layer":      "function",
        "note":       "Raw numeric literals obscure intent — use named constants.",
    },
    "primitive_obsession": {
        "downstream": ["too_many_params", "data_clumps"],
        "effort":     2,
        "layer":      "function",
        "note":       "Using primitives instead of rich objects hides domain concepts.",
    },
}
