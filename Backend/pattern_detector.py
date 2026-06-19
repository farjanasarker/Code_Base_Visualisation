"""
pattern_detector.py — Rule-based Architecture Pattern Detection.

Uses file paths, function names, and call-edge graph only — no LLM.
Deterministic and fast.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PatternResult:
    pattern: str
    confidence: float
    evidence: list[str]
    components: dict[str, list[str]]
    violations: list[str]


class ArchitecturePatternDetector:
    def __init__(self, session_data: dict):
        self.files: list[str] = session_data.get("files", [])
        self.functions: list[dict] = session_data.get("functions", [])
        self.call_edges: list[dict] = session_data.get("call_edges", [])

        self.files_lower = [f.lower().replace("\\", "/") for f in self.files]

        # caller_file → {callee_files}  and  callee_file → {caller_files}
        self.caller_map: dict[str, set[str]] = {}
        self.callee_map: dict[str, set[str]] = {}
        for edge in self.call_edges:
            cf = edge.get("caller_file", "").lower().replace("\\", "/")
            tf = edge.get("callee_file", "").lower().replace("\\", "/")
            if cf and tf and cf != tf:
                self.caller_map.setdefault(cf, set()).add(tf)
                self.callee_map.setdefault(tf, set()).add(cf)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _files_matching(self, *keywords) -> list[str]:
        return [
            self.files[i]
            for i, f in enumerate(self.files_lower)
            if any(kw in f for kw in keywords)
        ]

    def _fns_matching(self, *keywords) -> list[dict]:
        return [
            fn for fn in self.functions
            if any(kw in fn.get("name", "").lower() for kw in keywords)
        ]

    def _confidence(self, matched: int, total: int) -> float:
        return round(min(matched / total, 1.0), 2) if total > 0 else 0.0

    # ── 1. MVC / MVP ──────────────────────────────────────────────────────────

    def detect_mvc_mvp(self) -> Optional[PatternResult]:
        models      = self._files_matching("model", "schema", "entity")
        views       = self._files_matching("view", "template", "page", "pages")
        controllers = self._files_matching("controller")
        presenters  = self._files_matching("presenter")

        # No dedicated model/ folder is common in service+repository backends —
        # service/repository files jointly play the Model role there.
        if not models:
            models = self._files_matching("service", "repository", "repo")

        is_mvp   = bool(presenters) and not bool(controllers)
        middle   = presenters if is_mvp else controllers
        name     = "MVP" if is_mvp else "MVC"

        if not (models and views and middle):
            return None

        evidence = [
            f"{len(models)} model/service file(s) found",
            f"{len(views)} view file(s) found",
            f"{len(middle)} {'presenter' if is_mvp else 'controller'} file(s) found",
        ]

        view_set  = {v.lower().replace("\\", "/") for v in views}
        model_set = {m.lower().replace("\\", "/") for m in models}
        violations = []
        for vf in view_set:
            bad = self.caller_map.get(vf, set()) & model_set
            for b in bad:
                violations.append(f"View '{vf}' calls Model '{b}' directly")

        confidence = self._confidence(3 - len(violations), 3)
        if confidence < 0.4:
            return None

        return PatternResult(
            pattern=name,
            confidence=confidence,
            evidence=evidence,
            components={"models": models, "views": views,
                        "controllers/presenters": middle},
            violations=violations,
        )

    # ── 2. Layered / N-Tier ───────────────────────────────────────────────────

    def detect_layered(self) -> Optional[PatternResult]:
        layer_keywords = {
            "presentation": ["controller", "route", "view", "api", "handler"],
            "business":     ["service", "usecase", "use_case", "logic", "manager"],
            "data":         ["repository", "repo", "dao", "database", "db", "store"],
        }
        layer_order = ["presentation", "business", "data"]

        file_layer: dict[str, str] = {}
        for i, f in enumerate(self.files_lower):
            for layer, kws in layer_keywords.items():
                if any(kw in f for kw in kws):
                    file_layer[self.files[i]] = layer
                    break

        if len(set(file_layer.values())) < 2:
            return None

        violations = []
        for edge in self.call_edges:
            cf = edge.get("caller_file", "")
            tf = edge.get("callee_file", "")
            cl = file_layer.get(cf)
            tl = file_layer.get(tf)
            if cl and tl and cl != tl:
                ci = layer_order.index(cl) if cl in layer_order else -1
                ti = layer_order.index(tl) if tl in layer_order else -1
                if ci > ti:
                    violations.append(
                        f"'{cl}' → '{tl}' (upward call): {cf} → {tf}"
                    )

        total_cross = sum(
            1 for e in self.call_edges
            if file_layer.get(e.get("caller_file")) and file_layer.get(e.get("callee_file"))
            and file_layer.get(e.get("caller_file")) != file_layer.get(e.get("callee_file"))
        )
        violation_ratio = len(violations) / total_cross if total_cross > 0 else 0
        confidence = round(max(0.4, 0.95 - violation_ratio * 0.5), 2)

        layers_found = set(file_layer.values())
        return PatternResult(
            pattern="Layered/N-Tier",
            confidence=confidence,
            evidence=[f"Layer '{l}' detected" for l in layers_found],
            components={l: [f for f, ly in file_layer.items() if ly == l]
                        for l in layer_order if l in layers_found},
            violations=violations[:10],
        )

    # ── 3. Clean Architecture ─────────────────────────────────────────────────

    def detect_clean_architecture(self) -> Optional[PatternResult]:
        layer_keywords = {
            "entities":   ["entity", "entities", "domain", "model"],
            "use_cases":  ["usecase", "use_case", "interactor", "application"],
            "interfaces": ["controller", "presenter", "gateway", "interface", "adapter"],
            "frameworks": ["framework", "infra", "infrastructure", "db", "web", "external"],
        }
        layer_order = ["entities", "use_cases", "interfaces", "frameworks"]

        file_layer: dict[str, str] = {}
        for i, f in enumerate(self.files_lower):
            for layer, kws in layer_keywords.items():
                if any(kw in f for kw in kws):
                    file_layer[self.files[i]] = layer
                    break

        if len(set(file_layer.values())) < 3:
            return None

        violations = []
        for edge in self.call_edges:
            cf = edge.get("caller_file", "")
            tf = edge.get("callee_file", "")
            cl = file_layer.get(cf)
            tl = file_layer.get(tf)
            if cl and tl and cl != tl:
                ci = layer_order.index(cl)
                ti = layer_order.index(tl)
                if ci < ti:  # inner calling outer = violation
                    violations.append(f"Inner '{cl}' → Outer '{tl}': {cf} → {tf}")

        total_cross = sum(
            1 for e in self.call_edges
            if file_layer.get(e.get("caller_file")) and file_layer.get(e.get("callee_file"))
            and file_layer.get(e.get("caller_file")) != file_layer.get(e.get("callee_file"))
        )
        vr = len(violations) / total_cross if total_cross > 0 else 0
        confidence = round(max(0.3, 0.95 - vr), 2)

        if confidence < 0.5:
            return None

        layers_found = set(file_layer.values())
        return PatternResult(
            pattern="Clean Architecture",
            confidence=confidence,
            evidence=[
                f"{len(layers_found)} distinct layers found",
                f"{len(violations)} inward-dependency violations",
            ],
            components={l: [f for f, ly in file_layer.items() if ly == l]
                        for l in layer_order if l in layers_found},
            violations=violations[:10],
        )

    # ── 4. Hexagonal Architecture ─────────────────────────────────────────────

    def detect_hexagonal(self) -> Optional[PatternResult]:
        domain   = self._files_matching("domain", "core")
        ports    = self._files_matching("port", "interface")
        adapters = self._files_matching("adapter", "infra", "infrastructure")

        if not (domain and (ports or adapters)):
            return None

        domain_set = {f.lower().replace("\\", "/") for f in domain}
        outer_set  = {f.lower().replace("\\", "/") for f in ports + adapters}
        violations = []
        for df in domain_set:
            bad = self.caller_map.get(df, set()) & outer_set
            for b in bad:
                violations.append(f"Domain '{df}' depends on outer '{b}'")

        confidence = 0.9 if not violations else round(0.9 - len(violations) * 0.1, 2)

        return PatternResult(
            pattern="Hexagonal Architecture",
            confidence=max(confidence, 0.4),
            evidence=[
                f"{len(domain)} domain/core file(s)",
                f"{len(ports)} port/interface file(s)",
                f"{len(adapters)} adapter file(s)",
            ],
            components={"domain": domain, "ports": ports, "adapters": adapters},
            violations=violations,
        )

    # ── 5. Repository Pattern ─────────────────────────────────────────────────

    def detect_repository(self) -> Optional[PatternResult]:
        repos    = self._files_matching("repository", "repo")
        services = self._files_matching("service")

        if not repos:
            return None

        db_keywords = {"find", "save", "update", "delete", "query",
                       "execute", "fetch", "insert", "get", "create",
                       "findall", "findbyid", "findbyemail"}

        # Match by basename, not full path — caller/callee paths in the call
        # graph and file list aren't always normalized the same way.
        def basename(path: str) -> str:
            return path.lower().replace("\\", "/").split("/")[-1]

        repo_basenames = {basename(r) for r in repos}

        repo_has_crud = any(
            any(kw in fn.get("name", "").lower() for kw in db_keywords)
            for fn in self.functions
            if basename(fn.get("file", "")) in repo_basenames
        )

        service_calls_repo = any(
            basename(edge.get("callee_file", "")) in repo_basenames
            for edge in self.call_edges
            if "service" in edge.get("caller_file", "").lower()
        )

        score = sum([bool(repos), repo_has_crud, service_calls_repo, bool(services)])
        confidence = self._confidence(score, 4)
        if confidence < 0.4:
            return None

        evidence = []
        if repos:               evidence.append(f"{len(repos)} repository file(s) found")
        if repo_has_crud:       evidence.append("CRUD methods detected in repositories")
        if service_calls_repo:  evidence.append("Service layer calls repositories")

        return PatternResult(
            pattern="Repository Pattern",
            confidence=confidence,
            evidence=evidence,
            components={"repositories": repos, "services": services},
            violations=[],
        )

    # ── 6. Singleton ──────────────────────────────────────────────────────────

    def detect_singleton(self) -> Optional[PatternResult]:
        singleton_fns   = self._fns_matching("getinstance", "get_instance", "createinstance")
        singleton_files = self._files_matching("singleton")
        instance_vars   = [
            fn for fn in self.functions
            if "_instance" in fn.get("name", "").lower()
        ]

        if not (singleton_fns or singleton_files or instance_vars):
            return None

        unique_files = list(
            {fn.get("file", "") for fn in singleton_fns + instance_vars}
            | set(singleton_files)
        )

        return PatternResult(
            pattern="Singleton",
            confidence=0.85 if singleton_fns else 0.65,
            evidence=[
                f"{len(singleton_fns)} getInstance-style function(s)",
                f"{len(instance_vars)} _instance variable(s)",
            ],
            components={"singleton_classes": unique_files},
            violations=[],
        )

    # ── 7. Observer ───────────────────────────────────────────────────────────

    def detect_observer(self) -> Optional[PatternResult]:
        emitter_kws    = {"notify", "emit", "dispatch", "publish", "trigger", "fire"}
        subscriber_kws = {"subscribe", "unsubscribe", "listen",
                          "register", "addlistener", "addobserver",
                          "usecontext", "usereducer", "addeventlistener"}

        emitters    = self._fns_matching(*emitter_kws)
        subscribers = self._fns_matching(*subscriber_kws)

        # React Context / pub-sub files are an Observer variant: state lives
        # in a Subject (createContext/EventEmitter) and consumers subscribe
        # to changes without explicit notify()/subscribe() function names.
        context_files = self._files_matching("context", "eventemitter", "pubsub", "event_bus", "eventbus")

        has_emitters    = bool(emitters) or bool(context_files)
        has_subscribers = bool(subscribers) or bool(context_files)

        if not (has_emitters and has_subscribers):
            return None

        score = self._confidence(
            int(has_emitters) + int(has_subscribers) +
            int(len(subscribers) >= 2 or bool(context_files)),
            3,
        )

        evidence = []
        if emitters:
            evidence.append(f"{len(emitters)} emitter function(s) (notify/emit/dispatch)")
        if subscribers:
            evidence.append(f"{len(subscribers)} subscriber function(s) (subscribe/listen/register)")
        if context_files:
            evidence.append(f"{len(context_files)} context/event file(s) (React Context Observer pattern)")

        return PatternResult(
            pattern="Observer",
            confidence=score,
            evidence=evidence,
            components={
                "emitters":    list({fn.get("file", "") for fn in emitters} | set(context_files)),
                "subscribers": list({fn.get("file", "") for fn in subscribers} | set(context_files)),
            },
            violations=[],
        )

    # ── 8. Factory ────────────────────────────────────────────────────────────

    def detect_factory(self) -> Optional[PatternResult]:
        factory_fns   = self._fns_matching("create", "build", "make", "produce", "generate")
        factory_files = self._files_matching("factory")

        if not factory_fns and not factory_files:
            return None

        unique_files = list({fn.get("file", "") for fn in factory_fns} | set(factory_files))

        return PatternResult(
            pattern="Factory",
            confidence=0.85 if factory_files else 0.65,
            evidence=[
                f"{len(factory_files)} factory file(s)" if factory_files else "No dedicated factory file",
                f"{len(factory_fns)} create/build/make function(s)",
            ],
            components={"factories": unique_files},
            violations=[],
        )

    # ── 9. Facade ─────────────────────────────────────────────────────────────

    def detect_facade(self) -> Optional[PatternResult]:
        facade_files = self._files_matching("facade")
        candidates   = []

        # Heuristic: a file that calls 5+ unique files but is called by few
        for f_lower, callees in self.caller_map.items():
            callers_of_f = self.callee_map.get(f_lower, set())
            if len(callees) >= 5 and len(callers_of_f) <= len(callees) * 0.4:
                orig = next(
                    (f for f in self.files if f.lower().replace("\\", "/") == f_lower),
                    f_lower,
                )
                candidates.append(orig)

        all_facades = list(set(facade_files + candidates))
        if not all_facades:
            return None

        return PatternResult(
            pattern="Facade",
            confidence=0.85 if facade_files else 0.70,
            evidence=[
                f"{len(facade_files)} file(s) named 'facade'",
                f"{len(candidates)} file(s) match Facade heuristic (5+ subsystems, few callers)",
            ],
            components={"facades": all_facades},
            violations=[],
        )

    # ── Run All ───────────────────────────────────────────────────────────────

    def detect_all(self, min_confidence: float = 0.55) -> list[dict]:
        detectors = [
            self.detect_mvc_mvp,
            self.detect_layered,
            self.detect_clean_architecture,
            self.detect_hexagonal,
            self.detect_repository,
            self.detect_singleton,
            self.detect_observer,
            self.detect_factory,
            self.detect_facade,
        ]

        results = []
        for detector in detectors:
            try:
                result = detector()
                if result and result.confidence >= min_confidence:
                    results.append({
                        "pattern":    result.pattern,
                        "confidence": result.confidence,
                        "evidence":   result.evidence,
                        "components": result.components,
                        "violations": result.violations,
                    })
            except Exception:
                continue

        return sorted(results, key=lambda x: x["confidence"], reverse=True)
