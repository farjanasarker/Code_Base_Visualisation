from neo4j import GraphDatabase
from pathlib import Path
import logging
import re

from patterns.normalization import is_abstract_like, is_interface_like, infer_go_structural_implements
from analyzer.heuristics import _is_anonymous_callback

logger = logging.getLogger(__name__)

driver = GraphDatabase.driver(
    "neo4j+s://41ba1e28.databases.neo4j.io",
    auth=("41ba1e28", "PXi2zC7QElI7PCf-cuK6S0E-DhuVxukey8ysxwPfzJE"),
    # Aura silently closes connections that sit idle for a while. Without this,
    # the pool can hand out an already-dead connection and the first write on
    # it fails with SSLEOFError/SessionExpired instead of just reconnecting.
    # This makes the pool test (and transparently replace) a connection that's
    # been idle longer than 30s before reusing it.
    liveness_check_timeout=30,
)

# ========== SESSION MANAGEMENT ==========
def delete_session_data(session_id: str) -> None:
    """Delete all nodes and relationships for a specific session"""
    def _tx(tx):
        tx.run("""
            MATCH (n {session_id: $session_id})
            DETACH DELETE n
        """, session_id=session_id)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
            logger.info(f"✅ Deleted Neo4j data for session: {session_id}")
    except Exception as e:
        logger.error(f"❌ Error deleting session data: {str(e)}")
        raise


def add_edge(caller, callee, session_id: str):
    def _tx(tx):
        tx.run("""
            MERGE (a:Function {name: $caller, session_id: $session_id})
            MERGE (b:Function {name: $callee, session_id: $session_id})
            MERGE (a)-[:CALLS]->(b)
        """, caller=caller, callee=callee, session_id=session_id)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
    except Exception as e:
        logger.error(f"Error adding edge: {str(e)}")
        raise

def clear_graph(session_id: str):
    def _tx(tx):
        tx.run("""
            MATCH (n {session_id: $session_id})
            DETACH DELETE n
        """, session_id=session_id)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
    except Exception as e:
        logger.error(f"Error clearing graph: {str(e)}")
        raise

def get_neighbors(function_name: str, session_id: str):
    def _tx(tx):
        result = tx.run("""
            MATCH (a:Function {name: $name, session_id: $session_id})-[:CALLS]->(b)
            RETURN b.name AS name
        """, name=function_name, session_id=session_id)
        return [r["name"] for r in result]

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error getting neighbors: {str(e)}")
        raise


def get_full_graph(session_id: str):
    def _tx(tx):
        node_result = tx.run(
            """
            MATCH (n:Function {session_id: $session_id})
            RETURN n.name AS name
            ORDER BY n.name
            """,
            session_id=session_id
        )
        nodes = [{"id": r["name"]} for r in node_result]

        edge_result = tx.run(
            """
            MATCH (a:Function {session_id: $session_id})-[:CALLS]->(b:Function {session_id: $session_id})
            RETURN a.name AS source, b.name AS target
            ORDER BY source, target
            """,
            session_id=session_id
        )
        edges = [
            {"source": r["source"], "target": r["target"]}
            for r in edge_result
        ]

        return {"nodes": nodes, "edges": edges}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error fetching full graph: {str(e)}")
        raise


def store_all(functions, session_id: str, all_files: list = None, service_id: str = None):
    """Store modules, files, functions and CALLS edges from a list of function dicts.

    Args:
        functions: List of function dicts with parsed function info
        session_id: Session ID for scoping data
        all_files: Optional list of all files (even those with no functions)
                   Each file dict should have 'path' and 'language' keys
        service_id: Optional service tier tag (monorepo microservice folder name).
                    When None, behaves exactly as before (no `service` property written).
    """
    def _tx(tx):
        # First, create File and Module nodes for all files (even those without functions)
        files_processed = set()
        if all_files:
            for file_info in all_files:
                file_path = file_info.get("path")
                language = file_info.get("language", "unknown")

                if service_id:
                    # Per-service calls: don't derive a Module here from
                    # Path(file_path).parts[0] — that's the file's full
                    # path (e.g. the monorepo's outer wrapper folder), not
                    # a module scoped to this service, and it would create
                    # a spurious Module that's a prefix of every real
                    # submodule in this service. The per-function pass
                    # below (which covers every file via a real function or
                    # a sentinel) already links each File to its correct,
                    # service-scoped Module — this pass just needs the bare
                    # File node to exist.
                    tx.run("""
                        MERGE (fil:File {path: $file, language: $language, session_id: $session_id, service: $service_id})
                    """, **{
                        "file": file_path,
                        "language": language,
                        "session_id": session_id,
                        "service_id": service_id,
                    })
                else:
                    module = Path(file_path).parts[0] if Path(file_path).parts else "root"
                    if module:
                        tx.run("""
                            MERGE (mod:Module {name: $module, session_id: $session_id})
                            MERGE (fil:File {path: $file, language: $language, session_id: $session_id})
                            MERGE (fil)-[:BELONGS_TO]->(mod)
                        """, **{
                            "module": module,
                            "file": file_path,
                            "language": language,
                            "session_id": session_id,
                        })
                    else:
                        tx.run("""
                            MERGE (fil:File {path: $file, language: $language, session_id: $session_id})
                        """, **{
                            "file": file_path,
                            "language": language,
                            "session_id": session_id,
                        })
                files_processed.add(file_path)

        # Then, process functions and create Function nodes
        for fn in functions:
            file_path = fn.get("file")
            files_processed.add(file_path)
            module = (fn.get("module") or "").strip()

            if module:
                if service_id:
                    tx.run("""
                        MERGE (mod:Module {name: $module, session_id: $session_id, service: $service_id})
                        MERGE (fil:File {path: $file, language: $language, session_id: $session_id, service: $service_id})
                        MERGE (fil)-[:BELONGS_TO]->(mod)
                        MERGE (func:Function {name: $name, file: $file, session_id: $session_id})
                        SET func.line_start   = $line_start,
                            func.line_end     = $line_end,
                            func.complexity   = $complexity,
                            func.language     = $language,
                            func.fan_in       = $fan_in,
                            func.fan_out      = $fan_out,
                            func.virtual_module = $virtual_module
                        MERGE (func)-[:DEFINED_IN]->(fil)
                    """, **{
                        "module": module,
                        "file": fn.get("file"),
                        "language": fn.get("language"),
                        "name": fn.get("name"),
                        "line_start": fn.get("line_start"),
                        "line_end": fn.get("line_end"),
                        "complexity": fn.get("complexity"),
                        "fan_in": fn.get("fan_in"),
                        "fan_out": fn.get("fan_out"),
                        "virtual_module": fn.get("virtual_module"),
                        "session_id": session_id,
                        "service_id": service_id,
                    })
                else:
                    tx.run("""
                        MERGE (mod:Module {name: $module, session_id: $session_id})
                        MERGE (fil:File {path: $file, language: $language, session_id: $session_id})
                        MERGE (fil)-[:BELONGS_TO]->(mod)
                        MERGE (func:Function {name: $name, file: $file, session_id: $session_id})
                        SET func.line_start   = $line_start,
                            func.line_end     = $line_end,
                            func.complexity   = $complexity,
                            func.language     = $language,
                            func.fan_in       = $fan_in,
                            func.fan_out      = $fan_out,
                            func.virtual_module = $virtual_module
                        MERGE (func)-[:DEFINED_IN]->(fil)
                    """, **{
                        "module": module,
                        "file": fn.get("file"),
                        "language": fn.get("language"),
                        "name": fn.get("name"),
                        "line_start": fn.get("line_start"),
                        "line_end": fn.get("line_end"),
                        "complexity": fn.get("complexity"),
                        "fan_in": fn.get("fan_in"),
                        "fan_out": fn.get("fan_out"),
                        "virtual_module": fn.get("virtual_module"),
                        "session_id": session_id,
                    })
            else:
                tx.run("""
                    MERGE (fil:File {path: $file, language: $language, session_id: $session_id})
                MERGE (func:Function {name: $name, file: $file, session_id: $session_id})
                SET func.line_start   = $line_start,
                    func.line_end     = $line_end,
                    func.complexity   = $complexity,
                    func.language     = $language,
                    func.fan_in       = $fan_in,
                    func.fan_out      = $fan_out,
                    func.virtual_module = $virtual_module
                MERGE (func)-[:DEFINED_IN]->(fil)
                """, **{
                    "file": fn.get("file"),
                    "language": fn.get("language"),
                    "name": fn.get("name"),
                    "line_start": fn.get("line_start"),
                    "line_end": fn.get("line_end"),
                    "complexity": fn.get("complexity"),
                    "fan_in": fn.get("fan_in"),
                    "fan_out": fn.get("fan_out"),
                    "virtual_module": fn.get("virtual_module"),
                    "session_id": session_id,
                })

        # Create CALLS edges
        for fn in functions:
            for called in fn.get("calls", []):
                tx.run("""
                    MATCH (caller:Function {name: $caller, file: $file, session_id: $session_id})
                    MATCH (callee:Function {name: $callee, session_id: $session_id})
                    MERGE (caller)-[:CALLS]->(callee)
                """, caller=fn.get("name"), file=fn.get("file"), callee=called, session_id=session_id)

        # Persist chunk (virtual_module) nodes and relationships
        for fn in functions:
            vm = fn.get("virtual_module")
            fpath = fn.get("file")
            if vm and vm != fpath:
                tx.run("""
                    MATCH (fil:File {path: $file, session_id: $session_id})
                    MERGE (chunk:Chunk {name: $vm, session_id: $session_id})
                    MERGE (chunk)-[:IN_FILE]->(fil)
                    MATCH (func:Function {name: $name, file: $file, session_id: $session_id})
                    MERGE (func)-[:PART_OF]->(chunk)
                """, file=fpath, vm=vm, name=fn.get("name"), session_id=session_id)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
    except Exception as e:
        logger.error(f"Error storing functions: {str(e)}")
        raise


# ========== GoF PATTERN ENGINE: CLASS GRAPH (additive) ==========
#
# Everything below is new schema for the GoF pattern-detection engine
# (Class/interface/struct/trait nodes and INHERITS_FROM/IMPLEMENTS/HAS_FIELD/
# METHOD_OF edges). It is deliberately kept as separate functions with their
# own transactions rather than folded into store_all() above: store_all() is
# one big transaction today, and a bug in this newer, less-battle-tested code
# must not be able to roll back the pre-existing Function/File/Calls data
# that store_all() already persisted successfully for the same upload.


def ensure_schema() -> None:
    """Idempotent constraint setup for Class nodes. Call once at app startup.

    Best-effort like everything else here: composite node-key constraints
    aren't guaranteed to be available on every Neo4j/Aura tier, and no other
    code path depends on the constraint actually existing (MERGE works fine
    without it) — a failure here is logged and swallowed, not raised.
    """
    def _tx(tx):
        tx.run("""
            CREATE CONSTRAINT class_unique_key IF NOT EXISTS
            FOR (c:Class) REQUIRE (c.name, c.file, c.session_id) IS NODE KEY
        """)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
        logger.info("Neo4j schema ensured (Class node key constraint)")
    except Exception as e:
        logger.warning(f"Could not create Class constraint (non-fatal): {e}")


def _core_type_name(type_text: str) -> str:
    """Strip generic wrappers/array brackets to resolve a field's declared
    type down to the underlying class name a HAS_FIELD edge should point at,
    e.g. `List<Foo>` -> `Foo`, `Foo[]` -> `Foo`, `pkg.Foo` -> `Foo`,
    `Box<dyn Foo>` -> `Foo` (Rust's idiomatic way to hold a trait object —
    `dyn` isn't a `\\w` character so the generic-arg regex needs to allow it
    explicitly, both wrapped and bare), `List[Foo]` -> `Foo` (Python's
    typing module uses square brackets, not angle brackets, for generics —
    only single-argument square-bracket generics resolve; `Dict[K, V]`'s
    two-argument form is left alone, nothing needs it yet), `'Foo'` -> `Foo`
    (Python's quoted forward-reference style for self-referencing type
    hints, e.g. `_instance: "Foo" = None` inside `class Foo:` — ast.unparse
    renders the annotation's string-literal node back with its quotes
    included, since that's what valid re-parseable Python source looks like).
    """
    t = (type_text or "").strip()
    if not t:
        return ""
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        t = t[1:-1].strip()
    if t.endswith("[]"):
        t = t[:-2].strip()
    if t.startswith("dyn "):
        t = t[4:].strip()
    generic_match = re.match(r'^[\w.]+<\s*(?:dyn\s+)?([\w.:]+)\s*>$', t)
    if generic_match:
        t = generic_match.group(1)
    else:
        square_generic_match = re.match(r'^[\w.]+\[\s*([\w.:]+)\s*\]$', t)
        if square_generic_match:
            t = square_generic_match.group(1)
    return t.split(".")[-1].split("::")[-1].strip()


def store_class_graph(
    classes: list, functions: list, session_id: str, service_id: str = None
) -> None:
    """Store Class nodes and INHERITS_FROM/IMPLEMENTS/HAS_FIELD/METHOD_OF
    edges for a session, from the `classes`/`functions` dicts produced by
    `analyzer.pipeline.analyze_files()`.

    Bases/interfaces/field-types are resolved to other Class nodes by name
    within the session only (no file path is known at declaration site) —
    the same tradeoff store_all() already makes for CALLS-edge callee
    resolution. Names that don't resolve to a known class in this session
    are kept as `unresolved_bases`/`unresolved_interfaces` string properties
    instead of a dangling edge.
    """
    if not classes:
        return

    known_names = {c["name"] for c in classes}

    class_rows = []
    inherits_rows = []
    implements_rows = []
    field_rows = []

    for c in classes:
        class_rows.append({
            "name": c["name"], "file": c["file"], "kind": c["kind"],
            "language": c["language"], "module": c.get("module") or "",
            "line_start": c.get("line_start", 0), "line_end": c.get("line_end", 0),
            "field_names": [f["name"] for f in c.get("fields", [])],
            "method_names": c.get("method_names", []),
            "unresolved_bases": [b for b in c.get("bases", []) if b not in known_names],
            "unresolved_interfaces": [i for i in c.get("interfaces", []) if i not in known_names],
            "service": service_id,
        })
        for base in c.get("bases", []):
            if base in known_names:
                inherits_rows.append({"child": c["name"], "file": c["file"], "parent": base})
        for iface in c.get("interfaces", []):
            if iface in known_names:
                implements_rows.append({"child": c["name"], "file": c["file"], "parent": iface})
        for f in c.get("fields", []):
            target = _core_type_name(f.get("type", ""))
            # Literal self-type fields (target == c["name"], e.g. Singleton's
            # `_instance: "Config"` inside `class Config`) are a real,
            # intentional shape, not excluded — a HAS_FIELD self-loop is
            # exactly what singleton_candidates (patterns/predicates.py)
            # looks for. Every prior use of self-referential fields in this
            # codebase (Composite, Decorator, ...) happened to go through an
            # inherited interface name instead of the class's own literal
            # name, so this exclusion went untested until Singleton needed it.
            if target and target in known_names:
                field_rows.append({
                    "owner": c["name"], "file": c["file"], "type": target,
                    "field_name": f["name"], "is_collection": bool(f.get("is_collection", False)),
                })

    # Carries each method's raw (bare) call names directly, rather than
    # relying on store_all()'s pre-existing :CALLS edges between Function
    # nodes: those are matched by exact `name` equality, but some languages
    # (Go) give methods compound names ("ReceiverType.MethodName") while a
    # call site only ever captures the bare method name ("MethodName") — so
    # a Go method calling another Go method never resolves to a :CALLS edge
    # at all (a pre-existing gap in store_all(), not something introduced
    # here — left alone since store_all() is shared with the graph
    # visualization feature and out of scope to change). Storing the raw
    # names here and resolving them in SessionGraphView.from_raw (see
    # graph_view.py) makes the GoF engine's method-call visibility
    # independent of that edge-matching quirk entirely.
    method_rows = [
        {"fn_name": f["name"], "file": f["file"], "class_name": f["class_name"],
         "raw_calls": f.get("calls", []), "is_abstract": bool(f.get("is_abstract", False)),
         "raw_instantiates": f.get("instantiates", [])}
        for f in functions if f.get("class_name") and f.get("class_name") in known_names
    ]

    # Go has no `implements` keyword — see infer_go_structural_implements's
    # docstring. A no-op for every other language (only fires when both a
    # Go interface and a Go struct exist in this batch).
    implements_rows.extend(infer_go_structural_implements(classes, functions))

    # Normalization layer: collapse per-language `kind` (Python ABC/Protocol,
    # Go interface, Rust trait, TS/Java interface/abstract class, ...) down to
    # two graph-queryable labels every pattern predicate can rely on without
    # a per-language `kind` check of its own. See patterns/normalization.py.
    interface_like_rows = [
        {"name": c["name"], "file": c["file"]}
        for c in classes if is_interface_like(c["kind"])
    ]
    abstract_like_rows = [
        {"name": c["name"], "file": c["file"]}
        for c in classes if is_abstract_like(c["kind"])
    ]

    def _tx(tx):
        tx.run("""
            UNWIND $rows AS c
            MERGE (cls:Class {name: c.name, file: c.file, session_id: $session_id})
            SET cls.kind = c.kind, cls.language = c.language, cls.module = c.module,
                cls.line_start = c.line_start, cls.line_end = c.line_end,
                cls.field_names = c.field_names, cls.method_names = c.method_names,
                cls.unresolved_bases = c.unresolved_bases,
                cls.unresolved_interfaces = c.unresolved_interfaces,
                cls.service = c.service
        """, rows=class_rows, session_id=session_id)

        if inherits_rows:
            tx.run("""
                UNWIND $rows AS r
                MATCH (child:Class {name: r.child, file: r.file, session_id: $session_id})
                MATCH (parent:Class {name: r.parent, session_id: $session_id})
                MERGE (child)-[:INHERITS_FROM]->(parent)
            """, rows=inherits_rows, session_id=session_id)

        if implements_rows:
            tx.run("""
                UNWIND $rows AS r
                MATCH (child:Class {name: r.child, file: r.file, session_id: $session_id})
                MATCH (parent:Class {name: r.parent, session_id: $session_id})
                MERGE (child)-[:IMPLEMENTS]->(parent)
            """, rows=implements_rows, session_id=session_id)

        if field_rows:
            tx.run("""
                UNWIND $rows AS r
                MATCH (owner:Class {name: r.owner, file: r.file, session_id: $session_id})
                MATCH (target:Class {name: r.type, session_id: $session_id})
                MERGE (owner)-[rel:HAS_FIELD {field_name: r.field_name}]->(target)
                SET rel.is_collection = r.is_collection
            """, rows=field_rows, session_id=session_id)

        if method_rows:
            # raw_calls/is_abstract are set on the METHOD_OF *relationship*,
            # not the Function node: store_all()'s Function identity is only
            # {name, file, session_id} — no class/virtual_module — so two
            # different classes' same-named methods in one file (e.g.
            # Tea.brew / Coffee.brew / CaffeineBeverage.brew) share a single
            # Function node. Properties on that node would silently
            # overwrite each other across classes; the (fn)-[:METHOD_OF]->
            # (cls) relationship is still correctly scoped per class even
            # when its `fn` endpoint is shared.
            tx.run("""
                UNWIND $rows AS r
                MATCH (fn:Function {name: r.fn_name, file: r.file, session_id: $session_id})
                MATCH (cls:Class {name: r.class_name, file: r.file, session_id: $session_id})
                MERGE (fn)-[rel:METHOD_OF]->(cls)
                SET rel.raw_calls = r.raw_calls, rel.is_abstract = r.is_abstract,
                    rel.raw_instantiates = r.raw_instantiates
            """, rows=method_rows, session_id=session_id)

        if interface_like_rows:
            tx.run("""
                UNWIND $rows AS r
                MATCH (cls:Class {name: r.name, file: r.file, session_id: $session_id})
                SET cls:INTERFACE_LIKE
            """, rows=interface_like_rows, session_id=session_id)

        if abstract_like_rows:
            tx.run("""
                UNWIND $rows AS r
                MATCH (cls:Class {name: r.name, file: r.file, session_id: $session_id})
                SET cls:ABSTRACT_LIKE
            """, rows=abstract_like_rows, session_id=session_id)

    try:
        with driver.session() as db_session:
            db_session.execute_write(_tx)
        logger.info(f"✅ Stored class graph to Neo4j for session {session_id} ({len(classes)} classes)")
    except Exception as e:
        logger.error(f"Error storing class graph: {str(e)}")
        raise


def get_class_graph(session_id: str) -> dict:
    """Return the full normalized class graph for a session in one batched
    round trip (a handful of queries, not one per class/predicate) — the rule
    engine builds its in-memory SessionGraphView from this once per scan.
    """
    def _tx(tx):
        classes = [dict(r) for r in tx.run("""
            MATCH (c:Class {session_id: $session_id})
            RETURN c.name AS name, c.file AS file, c.kind AS kind, c.language AS language,
                   c.module AS module, c.line_start AS line_start, c.line_end AS line_end,
                   c.field_names AS field_names, c.method_names AS method_names,
                   c.unresolved_bases AS unresolved_bases,
                   c.unresolved_interfaces AS unresolved_interfaces, labels(c) AS labels
        """, session_id=session_id)]

        inherits = [dict(r) for r in tx.run("""
            MATCH (child:Class {session_id: $session_id})-[:INHERITS_FROM]->(parent:Class {session_id: $session_id})
            RETURN child.name AS child, child.file AS child_file, parent.name AS parent
        """, session_id=session_id)]

        implements = [dict(r) for r in tx.run("""
            MATCH (child:Class {session_id: $session_id})-[:IMPLEMENTS]->(parent:Class {session_id: $session_id})
            RETURN child.name AS child, child.file AS child_file, parent.name AS parent
        """, session_id=session_id)]

        has_field = [dict(r) for r in tx.run("""
            MATCH (owner:Class {session_id: $session_id})-[r:HAS_FIELD]->(target:Class {session_id: $session_id})
            RETURN owner.name AS owner, owner.file AS owner_file, target.name AS target,
                   r.field_name AS field_name, r.is_collection AS is_collection
        """, session_id=session_id)]

        # `raw_calls` are bare call names as the parser captured them at the
        # call site — resolving them to a callee class (where possible) is
        # done in SessionGraphView.from_raw, not here, since it needs the
        # same class/method-name index the predicates already build.
        methods = [dict(r) for r in tx.run("""
            MATCH (fn:Function {session_id: $session_id})-[rel:METHOD_OF]->(cls:Class {session_id: $session_id})
            RETURN fn.name AS fn_name, fn.file AS file, cls.name AS class_name,
                   coalesce(rel.raw_calls, []) AS raw_calls,
                   coalesce(rel.is_abstract, false) AS is_abstract,
                   coalesce(rel.raw_instantiates, []) AS raw_instantiates
        """, session_id=session_id)]

        return {
            "classes": classes, "inherits": inherits, "implements": implements,
            "has_field": has_field, "methods": methods,
        }

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building class graph: {str(e)}")
        raise


def get_tier1(session_id: str, service_id: str = None):
    """Return module-level graph (nodes + edges), optionally scoped to one service."""
    def _tx(tx):
        if service_id:
            edges_q = """
                MATCH (m1:Module {session_id: $session_id, service: $service_id})<-[:BELONGS_TO]-(:File {session_id: $session_id, service: $service_id})<-[:DEFINED_IN]-(f1:Function {session_id: $session_id})
                      -[:CALLS]->(f2:Function {session_id: $session_id})-[:DEFINED_IN]->(:File {session_id: $session_id, service: $service_id})-[:BELONGS_TO]->(m2:Module {session_id: $session_id, service: $service_id})
                WHERE m1 <> m2
                RETURN m1.name AS source, m2.name AS target, count(*) AS call_count
            """
            nodes_q = """
                MATCH (m:Module {session_id: $session_id, service: $service_id})<-[:BELONGS_TO]-(fil:File {session_id: $session_id, service: $service_id})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(f:Function {session_id: $session_id})
                RETURN m.name AS module, sum(f.line_end - f.line_start) AS loc, count(distinct f.name) AS fn_count, collect(distinct fil.language) AS languages
            """
        else:
            edges_q = """
                MATCH (m1:Module {session_id: $session_id})<-[:BELONGS_TO]-(:File {session_id: $session_id})<-[:DEFINED_IN]-(f1:Function {session_id: $session_id})
                      -[:CALLS]->(f2:Function {session_id: $session_id})-[:DEFINED_IN]->(:File {session_id: $session_id})-[:BELONGS_TO]->(m2:Module {session_id: $session_id})
                WHERE m1 <> m2
                RETURN m1.name AS source, m2.name AS target, count(*) AS call_count
            """
            nodes_q = """
                MATCH (m:Module {session_id: $session_id})<-[:BELONGS_TO]-(fil:File {session_id: $session_id})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(f:Function {session_id: $session_id})
                RETURN m.name AS module, sum(f.line_end - f.line_start) AS loc, count(distinct f.name) AS fn_count, collect(distinct fil.language) AS languages
            """

        params = {"session_id": session_id}
        if service_id:
            params["service_id"] = service_id

        result = tx.run(edges_q, **params)
        edges = [{"source": r["source"], "target": r["target"], "call_count": r["call_count"]} for r in result]

        node_res = tx.run(nodes_q, **params)
        nodes = [{"id": r["module"], "type": "module", "loc": int(r["loc"] or 0), "fn_count": int(r["fn_count"]), "languages": r["languages"]} for r in node_res]

        return {"nodes": nodes, "edges": edges, "tier": 1}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building tier1: {str(e)}")
        raise


def get_tier2(module_name: str, session_id: str, service_id: str = None):
    def _tx(tx):
        params = {"module": module_name, "session_id": session_id}
        svc_clause = ""
        if service_id:
            svc_clause = ", service: $service_id"
            params["service_id"] = service_id

        # Get cross-file call edges within module
        result = tx.run(f"""
            MATCH (fil:File {{session_id: $session_id{svc_clause}}})-[:BELONGS_TO]->(mod:Module {{name: $module, session_id: $session_id{svc_clause}}})
            OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function {{session_id: $session_id}})-[:CALLS]->(fn2:Function {{session_id: $session_id}})
                          -[:DEFINED_IN]->(fil2:File {{session_id: $session_id{svc_clause}}})-[:BELONGS_TO]->(mod)
            WHERE fil <> fil2
            RETURN fil.path AS source_file, fil2.path AS target_file,
                   fil.language AS language, count(fn) AS call_count
        """, **params)
        edges = []
        nodes_map = {}
        for r in result:
            src = r["source_file"]
            tgt = r["target_file"]
            if src not in nodes_map:
                nodes_map[src] = {"id": src, "type": "file", "language": r["language"], "fn_count": 0}
            if tgt and tgt not in nodes_map:
                nodes_map[tgt] = {"id": tgt, "type": "file", "language": r["language"], "fn_count": 0}
            if tgt:
                edges.append({"source": src, "target": tgt, "call_count": r["call_count"]})

        # Get ALL files in module (including those without cross-file calls)
        fn_counts = tx.run(f"""
            MATCH (fil:File {{session_id: $session_id{svc_clause}}})-[:BELONGS_TO]->(mod:Module {{name: $module, session_id: $session_id{svc_clause}}})
            OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function {{session_id: $session_id}})
            RETURN fil.path AS file, count(fn) AS fn_count, fil.language AS language
        """, **params)
        for r in fn_counts:
            f = r["file"]
            if f in nodes_map:
                nodes_map[f]["fn_count"] = int(r["fn_count"])
            else:
                nodes_map[f] = {"id": f, "type": "file", "language": r["language"], "fn_count": int(r["fn_count"])}

        return {"nodes": list(nodes_map.values()), "edges": edges, "tier": 2, "module": module_name}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building tier2: {str(e)}")
        raise


def get_all_files_graph(session_id: str):
    """Return file-level graph across all files in the session (used when no module structure exists)."""
    def _tx(tx):
        # Cross-file call edges
        result = tx.run("""
            MATCH (fn:Function {session_id: $session_id})-[:DEFINED_IN]->(fil:File {session_id: $session_id})
            MATCH (fn)-[:CALLS]->(fn2:Function {session_id: $session_id})-[:DEFINED_IN]->(fil2:File {session_id: $session_id})
            WHERE fil <> fil2
            RETURN fil.path AS source_file, fil2.path AS target_file,
                   fil.language AS language, count(fn) AS call_count
        """, session_id=session_id)
        edges = []
        nodes_map = {}
        for r in result:
            src = r["source_file"]
            tgt = r["target_file"]
            if src and src not in nodes_map:
                nodes_map[src] = {"id": src, "type": "file", "language": r["language"], "fn_count": 0}
            if tgt and tgt not in nodes_map:
                nodes_map[tgt] = {"id": tgt, "type": "file", "language": r["language"], "fn_count": 0}
            if src and tgt:
                edges.append({"source": src, "target": tgt, "call_count": int(r["call_count"])})

        # All files (including isolated ones with no cross-file calls)
        file_res = tx.run("""
            MATCH (fil:File {session_id: $session_id})
            OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function {session_id: $session_id})
            RETURN fil.path AS file, fil.language AS language, count(fn) AS fn_count
        """, session_id=session_id)
        for r in file_res:
            f = r["file"]
            if f and f not in nodes_map:
                nodes_map[f] = {"id": f, "type": "file", "language": r["language"], "fn_count": int(r["fn_count"] or 0)}
            elif f:
                nodes_map[f]["fn_count"] = int(r["fn_count"] or 0)

        return {"nodes": list(nodes_map.values()), "edges": edges, "tier": "files"}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building file graph: {str(e)}")
        raise


def get_tier3(file_path: str, session_id: str, service_id: str = None):
    normalized_file = file_path.replace("\\", "/")
    windows_file = file_path.replace("/", "\\")
    base_params = {
        "file": file_path,
        "normalized_file": normalized_file,
        "windows_file": windows_file,
        "session_id": session_id,
    }
    svc_clause = ""
    if service_id:
        svc_clause = ", service: $service_id"
        base_params["service_id"] = service_id

    def _tx(tx):
        # First check if chunk (virtual module) nodes exist for this file
        chunk_res = tx.run(f"""
            MATCH (fil:File {{session_id: $session_id{svc_clause}}})
            WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
            OPTIONAL MATCH (chunk:Chunk {{session_id: $session_id}})-[:IN_FILE]->(fil)
            RETURN chunk.name AS chunk_name, count(*) AS cnt
        """, **base_params)
        chunks = [r["chunk_name"] for r in chunk_res if r["chunk_name"]]

        if chunks and len(chunks) > 1:
            # return chunk-level graph
            nodes_q = tx.run(f"""
                MATCH (fil:File {{session_id: $session_id{svc_clause}}})
                WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                MATCH (chunk:Chunk {{session_id: $session_id}})-[:IN_FILE]->(fil)
                OPTIONAL MATCH (chunk)<-[:PART_OF]-(f:Function {{session_id: $session_id}})
                RETURN chunk.name AS id, count(f) AS fn_count, collect(distinct f.language) AS languages
            """, **base_params)
            nodes = [{"id": r["id"], "type": "chunk", "fn_count": int(r["fn_count"] or 0), "language": (r["languages"][0] if r["languages"] else None)} for r in nodes_q]

            edges_q = tx.run(f"""
                MATCH (fil:File {{session_id: $session_id{svc_clause}}})
                WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                MATCH (c1:Chunk {{session_id: $session_id}})-[:IN_FILE]->(fil)
                MATCH (c2:Chunk {{session_id: $session_id}})-[:IN_FILE]->(fil)
                MATCH (f1:Function {{session_id: $session_id}})-[:PART_OF]->(c1)
                MATCH (f1)-[:CALLS]->(f2:Function {{session_id: $session_id}})-[:PART_OF]->(c2)
                WHERE c1 <> c2
                RETURN c1.name AS source, c2.name AS target, count(*) AS call_count
            """, **base_params)
            edges = [{"source": r["source"], "target": r["target"], "call_count": int(r["call_count"])} for r in edges_q]

            return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": True}

        # Fallback: return function-level graph for the file
        result = tx.run(f"""
            MATCH (fn:Function {{session_id: $session_id}})-[:DEFINED_IN]->(fil:File {{session_id: $session_id{svc_clause}}})
            WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
            OPTIONAL MATCH (fn)-[:CALLS]->(fn2:Function {{session_id: $session_id}})-[:DEFINED_IN]->(fil)
            RETURN fn.name AS source, fn2.name AS target,
                   fn.complexity AS complexity,
                   fn.fan_in AS fan_in, fn.fan_out AS fan_out,
                   fn.line_start AS line_start, fn.line_end AS line_end
        """, **base_params)
        nodes = {}
        edges = []
        for r in result:
            src = r["source"]
            tgt = r.get("target")
            # Un-clickable `anonymous_<line>` callbacks (db.query/.then/addEventListener
            # arguments, IIFEs, ...) are filtered out of the in-memory function graph by
            # build_function_graph — mirror that here so this DB-backed path (hit whenever
            # a file's real functions are all anonymous, making build_function_graph's own
            # result legitimately empty) doesn't leak them back in as un-navigable nodes.
            if _is_anonymous_callback(src):
                continue
            if src not in nodes:
                nodes[src] = {"id": src, "type": "function", "line_start": int(r.get("line_start") or 0), "line_end": int(r.get("line_end") or 0), "complexity": int(r.get("complexity") or 0), "fan_in": int(r.get("fan_in") or 0), "fan_out": int(r.get("fan_out") or 0)}
            if tgt and not _is_anonymous_callback(tgt):
                edges.append({"source": src, "target": tgt})

        return {"nodes": list(nodes.values()), "edges": edges, "tier": 3, "file": file_path, "chunked": False}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building tier3: {str(e)}")
        raise


def get_chunk_functions(file_path: str, chunk_name: str, session_id: str):
    """Return function-level graph for a specific chunk inside a god file."""
    normalized_file = file_path.replace("\\", "/")
    windows_file = file_path.replace("/", "\\")

    def _tx(tx):
        result = tx.run("""
            MATCH (fil:File {session_id: $session_id})
            WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
            MATCH (chunk:Chunk {name: $chunk_name, session_id: $session_id})-[:IN_FILE]->(fil)
            MATCH (fn:Function {session_id: $session_id})-[:PART_OF]->(chunk)
            OPTIONAL MATCH (fn)-[:CALLS]->(fn2:Function {session_id: $session_id})-[:PART_OF]->(chunk)
            RETURN fn.name AS source, fn2.name AS target,
                   fn.complexity AS complexity, fn.fan_in AS fan_in, fn.fan_out AS fan_out,
                   fn.line_start AS line_start, fn.line_end AS line_end,
                   fn.language AS language
        """, file=file_path, normalized_file=normalized_file, windows_file=windows_file,
             chunk_name=chunk_name, session_id=session_id)

        nodes = {}
        edges = []
        for r in result:
            src = r["source"]
            tgt = r.get("target")
            # Keep this in sync with get_tier3's anonymous-callback filtering above —
            # chunk views hit the same DB fallback path when a chunk's real functions
            # are all anonymous.
            if src and _is_anonymous_callback(src):
                continue
            if src and src not in nodes:
                nodes[src] = {
                    "id": src, "label": src, "type": "function",
                    "line_start": int(r.get("line_start") or 0),
                    "line_end": int(r.get("line_end") or 0),
                    "complexity": int(r.get("complexity") or 0),
                    "fan_in": int(r.get("fan_in") or 0),
                    "fan_out": int(r.get("fan_out") or 0),
                    "language": r.get("language"),
                }
            if tgt and src and tgt != src and not _is_anonymous_callback(tgt):
                edges.append({"source": src, "target": tgt})

        return {"nodes": list(nodes.values()), "edges": edges,
                "tier": 4, "file": file_path, "chunk": chunk_name, "chunked": False}

    try:
        with driver.session() as db_session:
            return db_session.execute_read(_tx)
    except Exception as e:
        logger.error(f"Error building chunk functions: {str(e)}")
        raise
