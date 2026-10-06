"""
smell_graph.py — Smell Dependency Graph + Root Cause Analysis Engine.

Architecture:
  1. SmellDependencyGraph  — directed graph: node = smell instance, edge = causation
  2. Root Cause Scoring    — BFS downstream impact: score(A) = Σ severity_weight(descendants)
  3. Gain Ratio            — score / effort  (higher = better ROI for refactoring)
  4. Minimal-Fix Planner   — Greedy Set-Cover: pick highest gain_ratio, mark cascades resolved

Research notes:
  The causation graph encodes SMELL TYPE relationships (from SMELL_CAUSATION catalog).
  Instance-level edges are derived by linking each detected instance of type X to all
  detected instances of type Y where Y ∈ SMELL_CAUSATION[X]["downstream"].
  This models the real-world pattern: fixing a God Module instance typically
  reduces the Long Method instances that live inside it.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque
from .catalog import SMELL_CAUSATION, SEVERITY_WEIGHTS, REFACTOR_CATALOG
from .detector import Smell


# ── Graph Nodes and Edges ─────────────────────────────────────────────────────

@dataclass
class SmellNode:
    smell: Smell
    downstream_ids: List[str] = field(default_factory=list)   # caused-by edges (outgoing)
    upstream_ids:   List[str] = field(default_factory=list)   # caused-by edges (incoming)
    root_cause_score: float = 0.0
    gain_ratio:       float = 0.0

    @property
    def id(self) -> str:
        return self.smell.smell_id


# ── Smell Dependency Graph ────────────────────────────────────────────────────

class SmellDependencyGraph:
    """
    Directed graph where:
      node  = a detected smell instance (Smell object)
      edge  = causation: fixing upstream smell often resolves/reduces downstream

    Algorithms:
      build_edges_from_type_rules()  — derive instance edges from type-level catalog
      compute_root_cause_scores()    — BFS from each node, accumulate severity scores
      minimal_fix_plan()             — Greedy set-cover for maximum-gain ordering
    """

    def __init__(self):
        self.nodes: Dict[str, SmellNode] = {}    # smell_id → SmellNode
        self._edges: Set[Tuple[str,str]] = set() # (upstream_id, downstream_id)

    # ── Graph Construction ────────────────────────────────────────────────────

    def add_smell(self, smell: Smell) -> None:
        self.nodes[smell.smell_id] = SmellNode(smell=smell)

    def add_edge(self, upstream_id: str, downstream_id: str) -> None:
        if (upstream_id, downstream_id) in self._edges:
            return
        if upstream_id not in self.nodes or downstream_id not in self.nodes:
            return
        self._edges.add((upstream_id, downstream_id))
        self.nodes[upstream_id].downstream_ids.append(downstream_id)
        self.nodes[downstream_id].upstream_ids.append(upstream_id)

    def build_edges_from_type_rules(self) -> None:
        """
        For each smell instance of type X, create edges to all instances of
        type Y where Y ∈ SMELL_CAUSATION[X]["downstream"].

        Complexity: O(|smells|²) worst case — acceptable for ≤ 500 smell instances.
        For larger graphs, group-level edges (type→type instead of instance→instance)
        should be used with lazy expansion.
        """
        by_type: Dict[str, List[str]] = defaultdict(list)
        for sid, node in self.nodes.items():
            by_type[node.smell.type].append(sid)

        for sid, node in self.nodes.items():
            src_type     = node.smell.type
            ds_types     = SMELL_CAUSATION.get(src_type, {}).get("downstream", [])
            for ds_type in ds_types:
                for ds_id in by_type.get(ds_type, []):
                    if ds_id != sid:
                        self.add_edge(sid, ds_id)

    # ── Root Cause Scoring ────────────────────────────────────────────────────

    def compute_root_cause_scores(self) -> None:
        """
        BFS from every node → accumulate severity weights of all reachable descendants.

        score(A) = severity_weight(A) + Σ severity_weight(D) for D reachable from A

        This captures: "if I fix A, how much total smell severity is eliminated downstream?"
        """
        for start_id, start_node in self.nodes.items():
            visited: Set[str] = set()
            queue = deque(start_node.downstream_ids)
            score = SEVERITY_WEIGHTS.get(start_node.smell.severity, 1)

            while queue:
                cur_id = queue.popleft()
                if cur_id in visited:
                    continue
                visited.add(cur_id)
                cur = self.nodes.get(cur_id)
                if cur:
                    score += SEVERITY_WEIGHTS.get(cur.smell.severity, 1)
                    queue.extend(cur.downstream_ids)

            effort = SMELL_CAUSATION.get(start_node.smell.type, {}).get("effort", 2)

            start_node.root_cause_score       = score
            start_node.gain_ratio             = score / max(effort, 0.5)
            start_node.smell.root_cause_score = score
            start_node.smell.downstream_count = len(visited)

    # ── Minimal-Fix Planner ───────────────────────────────────────────────────

    def minimal_fix_plan(self, max_steps: int = 8) -> List[Dict]:
        """
        Greedy Set-Cover algorithm:
          1. Rank unresolved smell nodes by gain_ratio (score / effort).
          2. Pick the best candidate; mark it and all its BFS-reachable
             downstream smells as "resolved".
          3. Repeat until max_steps or no unresolved smells remain.

        This produces a MINIMAL refactoring sequence with MAXIMUM smell coverage,
        prioritising root-cause smells that eliminate cascades of downstream issues.
        """
        resolved:   Set[str] = set()
        plan:       List[Dict] = []

        for step in range(1, max_steps + 1):
            # Filter candidates that are not yet resolved
            candidates = [
                n for sid, n in self.nodes.items()
                if sid not in resolved
            ]
            if not candidates:
                break

            # Greedy: highest gain_ratio
            best = max(candidates, key=lambda n: n.gain_ratio)

            # BFS: collect all smells that will be resolved as cascade
            cascade: List[str] = []
            q  = deque(best.downstream_ids)
            seen: Set[str] = set()
            while q:
                sid = q.popleft()
                if sid in seen:
                    continue
                seen.add(sid)
                cascade.append(sid)
                child = self.nodes.get(sid)
                if child:
                    q.extend(child.downstream_ids)

            cascade_types = list({
                self.nodes[sid].smell.type
                for sid in cascade
                if sid in self.nodes
            })

            effort_val     = SMELL_CAUSATION.get(best.smell.type, {}).get("effort", 2)
            effort         = max(1, min(5, round(effort_val)))
            # Fixing a smell resolves the smell itself plus any downstream smells
            # not already counted by an earlier step. Without the "1 +", every
            # leaf smell (feature_envy, dead_code, ...) scored resolves=0 and
            # roi=0, so the ROI ranking collapsed into a severity-only tie-break.
            newly_resolved = [sid for sid in cascade if sid not in resolved]
            resolves_count = 1 + len(newly_resolved)
            roi_score      = resolves_count / effort

            plan.append({
                "smell_id":             best.smell.smell_id,
                "type":                 best.smell.type,
                "severity":             best.smell.severity,
                "target_name":          best.smell.target_name,
                "target_file":          best.smell.target_file,
                "description":          best.smell.description,
                "refactor_suggestions": best.smell.refactor_suggestions,
                "resolves_count":       resolves_count,
                "effort":               effort,
                "roi_score":            round(roi_score, 3),
                "root_cause_score":     round(best.root_cause_score, 2),
                "gain_ratio":           round(best.gain_ratio, 2),
                "cascades_types":       cascade_types,
                "cascade_count":        len(newly_resolved),
                "upstream_note":        SMELL_CAUSATION.get(best.smell.type, {}).get("note", ""),
            })

            resolved.add(best.smell.smell_id)
            resolved.update(cascade)

        # Re-rank by ROI (resolves_count / effort); ties broken by severity weight.
        plan.sort(
            key=lambda item: (item["roi_score"], SEVERITY_WEIGHTS.get(item["severity"], 1)),
            reverse=True,
        )
        for i, item in enumerate(plan, start=1):
            item["step"] = i

        return plan

    # ── Summary for LLM Prompt ────────────────────────────────────────────────

    def to_llm_summary(self, top_n: int = 6) -> Dict:
        """
        Compact, structured representation sent to the LLM.
        Contains only the data the LLM needs to reason about architecture —
        not raw code, not full metrics.
        """
        counts: Dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            counts[node.smell.type] += 1

        top_roots = sorted(
            self.nodes.values(),
            key=lambda n: n.root_cause_score,
            reverse=True,
        )[:top_n]

        return {
            "total_smells":      len(self.nodes),
            "smell_type_counts": dict(counts),
            "causation_edges":   len(self._edges),
            "top_root_causes": [
                {
                    "type":                 n.smell.type,
                    "severity":             n.smell.severity,
                    "target":               n.smell.target_name,
                    "metrics":              n.smell.metrics,
                    "root_cause_score":     round(n.root_cause_score, 2),
                    "downstream_resolves":  n.smell.downstream_count,
                    "gain_ratio":           round(n.gain_ratio, 2),
                    "causation_note":       SMELL_CAUSATION.get(n.smell.type, {}).get("note", ""),
                }
                for n in top_roots
            ],
        }

    def get_root_causes(self, top_n: int = 10) -> List[SmellNode]:
        return sorted(
            self.nodes.values(),
            key=lambda n: n.root_cause_score,
            reverse=True,
        )[:top_n]


# ── Factory ───────────────────────────────────────────────────────────────────

def build_smell_graph(smells: List[Smell]) -> SmellDependencyGraph:
    """Build, link and fully score the smell dependency graph from a smell list."""
    graph = SmellDependencyGraph()
    for smell in smells:
        graph.add_smell(smell)
    graph.build_edges_from_type_rules()
    graph.compute_root_cause_scores()
    return graph
