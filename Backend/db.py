from neo4j import GraphDatabase
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

driver = GraphDatabase.driver(
    "neo4j+s://41ba1e28.databases.neo4j.io",
    auth=("41ba1e28", "PXi2zC7QElI7PCf-cuK6S0E-DhuVxukey8ysxwPfzJE")
)

# ========== SESSION MANAGEMENT ==========
def delete_session_data(session_id: str) -> None:
    """Delete all nodes and relationships for a specific session"""
    try:
        with driver.session() as db_session:
            db_session.run("""
                MATCH (n {session_id: $session_id})
                DETACH DELETE n
            """, session_id=session_id)
            logger.info(f"✅ Deleted Neo4j data for session: {session_id}")
    except Exception as e:
        logger.error(f"❌ Error deleting session data: {str(e)}")
        raise


def add_edge(caller, callee, session_id: str):
    try:
        with driver.session() as db_session:
            db_session.run("""
                MERGE (a:Function {name: $caller, session_id: $session_id})
                MERGE (b:Function {name: $callee, session_id: $session_id})
                MERGE (a)-[:CALLS]->(b)
            """, caller=caller, callee=callee, session_id=session_id)
    except Exception as e:
        logger.error(f"Error adding edge: {str(e)}")
        raise

def clear_graph(session_id: str):
    try:
        with driver.session() as db_session:
            db_session.run("""
                MATCH (n {session_id: $session_id})
                DETACH DELETE n
            """, session_id=session_id)
    except Exception as e:
        logger.error(f"Error clearing graph: {str(e)}")
        raise

def get_neighbors(function_name: str, session_id: str):
    try:
        with driver.session() as db_session:
            result = db_session.run("""
                MATCH (a:Function {name: $name, session_id: $session_id})-[:CALLS]->(b)
                RETURN b.name AS name
            """, name=function_name, session_id=session_id)
            return [r["name"] for r in result]
    except Exception as e:
        logger.error(f"Error getting neighbors: {str(e)}")
        raise


def get_full_graph(session_id: str):
    try:
        with driver.session() as db_session:
            node_result = db_session.run(
                """
                MATCH (n:Function {session_id: $session_id})
                RETURN n.name AS name
                ORDER BY n.name
                """,
                session_id=session_id
            )

            edge_result = db_session.run(
                """
                MATCH (a:Function {session_id: $session_id})-[:CALLS]->(b:Function {session_id: $session_id})
                RETURN a.name AS source, b.name AS target
                ORDER BY source, target
                """,
                session_id=session_id
            )

            nodes = [{"id": r["name"]} for r in node_result]
            edges = [
                {"source": r["source"], "target": r["target"]}
                for r in edge_result
            ]

            return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.error(f"Error fetching full graph: {str(e)}")
        raise


def store_all(functions, session_id: str, all_files: list = None):
    """Store modules, files, functions and CALLS edges from a list of function dicts.
    
    Args:
        functions: List of function dicts with parsed function info
        session_id: Session ID for scoping data
        all_files: Optional list of all files (even those with no functions)
                   Each file dict should have 'path' and 'language' keys
    """
    try:
        with driver.session() as db_session:
            # First, create File and Module nodes for all files (even those without functions)
            files_processed = set()
            if all_files:
                for file_info in all_files:
                    file_path = file_info.get("path")
                    language = file_info.get("language", "unknown")
                    module = Path(file_path).parts[0] if Path(file_path).parts else "root"
                    if module:
                        db_session.run("""
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
                        db_session.run("""
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
                    db_session.run("""
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
                    db_session.run("""
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
                    db_session.run("""
                        MATCH (caller:Function {name: $caller, file: $file, session_id: $session_id})
                        MATCH (callee:Function {name: $callee, session_id: $session_id})
                        MERGE (caller)-[:CALLS]->(callee)
                    """, caller=fn.get("name"), file=fn.get("file"), callee=called, session_id=session_id)
            
            # Persist chunk (virtual_module) nodes and relationships
            for fn in functions:
                vm = fn.get("virtual_module")
                fpath = fn.get("file")
                if vm and vm != fpath:
                    db_session.run("""
                        MATCH (fil:File {path: $file, session_id: $session_id})
                        MERGE (chunk:Chunk {name: $vm, session_id: $session_id})
                        MERGE (chunk)-[:IN_FILE]->(fil)
                        MATCH (func:Function {name: $name, file: $file, session_id: $session_id})
                        MERGE (func)-[:PART_OF]->(chunk)
                    """, file=fpath, vm=vm, name=fn.get("name"), session_id=session_id)
    except Exception as e:
        logger.error(f"Error storing functions: {str(e)}")
        raise


def get_tier1(session_id: str):
    """Return module-level graph (nodes + edges)."""
    try:
        with driver.session() as db_session:
            # Get edges (cross-module calls)
            result = db_session.run("""
                MATCH (m1:Module {session_id: $session_id})<-[:BELONGS_TO]-(:File {session_id: $session_id})<-[:DEFINED_IN]-(f1:Function {session_id: $session_id})
                      -[:CALLS]->(f2:Function {session_id: $session_id})-[:DEFINED_IN]->(:File {session_id: $session_id})-[:BELONGS_TO]->(m2:Module {session_id: $session_id})
                WHERE m1 <> m2
                RETURN m1.name AS source, m2.name AS target, count(*) AS call_count
            """, session_id=session_id)
            edges = [{"source": r["source"], "target": r["target"], "call_count": r["call_count"]} for r in result]

            # nodes: aggregate module stats (including isolated modules with no cross-module calls)
            node_res = db_session.run("""
                MATCH (m:Module {session_id: $session_id})<-[:BELONGS_TO]-(fil:File {session_id: $session_id})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(f:Function {session_id: $session_id})
                RETURN m.name AS module, sum(f.line_end - f.line_start) AS loc, count(distinct f.name) AS fn_count, collect(distinct fil.language) AS languages
            """, session_id=session_id)
            nodes = [{"id": r["module"], "type": "module", "loc": int(r["loc"] or 0), "fn_count": int(r["fn_count"]), "languages": r["languages"]} for r in node_res]

            return {"nodes": nodes, "edges": edges, "tier": 1}
    except Exception as e:
        logger.error(f"Error building tier1: {str(e)}")
        raise


def get_tier2(module_name: str, session_id: str):
    try:
        with driver.session() as db_session:
            # Get cross-file call edges within module
            result = db_session.run("""
                MATCH (fil:File {session_id: $session_id})-[:BELONGS_TO]->(mod:Module {name: $module, session_id: $session_id})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function {session_id: $session_id})-[:CALLS]->(fn2:Function {session_id: $session_id})
                              -[:DEFINED_IN]->(fil2:File {session_id: $session_id})-[:BELONGS_TO]->(mod)
                WHERE fil <> fil2
                RETURN fil.path AS source_file, fil2.path AS target_file,
                       fil.language AS language, count(fn) AS call_count
            """, module=module_name, session_id=session_id)
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
            fn_counts = db_session.run("""
                MATCH (fil:File {session_id: $session_id})-[:BELONGS_TO]->(mod:Module {name: $module, session_id: $session_id})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function {session_id: $session_id})
                RETURN fil.path AS file, count(fn) AS fn_count, fil.language AS language
            """, module=module_name, session_id=session_id)
            for r in fn_counts:
                f = r["file"]
                if f in nodes_map:
                    nodes_map[f]["fn_count"] = int(r["fn_count"])
                else:
                    nodes_map[f] = {"id": f, "type": "file", "language": r["language"], "fn_count": int(r["fn_count"])}

            return {"nodes": list(nodes_map.values()), "edges": edges, "tier": 2, "module": module_name}
    except Exception as e:
        logger.error(f"Error building tier2: {str(e)}")
        raise


def get_all_files_graph(session_id: str):
    """Return file-level graph across all files in the session (used when no module structure exists)."""
    try:
        with driver.session() as db_session:
            # Cross-file call edges
            result = db_session.run("""
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
            file_res = db_session.run("""
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
    except Exception as e:
        logger.error(f"Error building file graph: {str(e)}")
        raise


def get_tier3(file_path: str, session_id: str):
    try:
        normalized_file = file_path.replace("\\", "/")
        windows_file = file_path.replace("/", "\\")
        with driver.session() as db_session:
            # First check if chunk (virtual module) nodes exist for this file
            chunk_res = db_session.run("""
                MATCH (fil:File {session_id: $session_id})
                WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                OPTIONAL MATCH (chunk:Chunk {session_id: $session_id})-[:IN_FILE]->(fil)
                RETURN chunk.name AS chunk_name, count(*) AS cnt
            """, file=file_path, normalized_file=normalized_file, windows_file=windows_file, session_id=session_id)
            chunks = [r["chunk_name"] for r in chunk_res if r["chunk_name"]]

            if chunks and len(chunks) > 1:
                # return chunk-level graph
                nodes_q = db_session.run("""
                    MATCH (fil:File {session_id: $session_id})
                    WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                    MATCH (chunk:Chunk {session_id: $session_id})-[:IN_FILE]->(fil)
                    OPTIONAL MATCH (chunk)<-[:PART_OF]-(f:Function {session_id: $session_id})
                    RETURN chunk.name AS id, count(f) AS fn_count, collect(distinct f.language) AS languages
                """, file=file_path, normalized_file=normalized_file, windows_file=windows_file, session_id=session_id)
                nodes = [{"id": r["id"], "type": "chunk", "fn_count": int(r["fn_count"] or 0), "language": (r["languages"][0] if r["languages"] else None)} for r in nodes_q]

                edges_q = db_session.run("""
                    MATCH (fil:File {session_id: $session_id})
                    WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                    MATCH (c1:Chunk {session_id: $session_id})-[:IN_FILE]->(fil)
                    MATCH (c2:Chunk {session_id: $session_id})-[:IN_FILE]->(fil)
                    MATCH (f1:Function {session_id: $session_id})-[:PART_OF]->(c1)
                    MATCH (f1)-[:CALLS]->(f2:Function {session_id: $session_id})-[:PART_OF]->(c2)
                    WHERE c1 <> c2
                    RETURN c1.name AS source, c2.name AS target, count(*) AS call_count
                """, file=file_path, normalized_file=normalized_file, windows_file=windows_file, session_id=session_id)
                edges = [{"source": r["source"], "target": r["target"], "call_count": int(r["call_count"])} for r in edges_q]

                return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": True}

            # Fallback: return function-level graph for the file
            result = db_session.run("""
                MATCH (fn:Function {session_id: $session_id})-[:DEFINED_IN]->(fil:File {session_id: $session_id})
                WHERE fil.path = $file OR fil.path = $normalized_file OR fil.path = $windows_file
                OPTIONAL MATCH (fn)-[:CALLS]->(fn2:Function {session_id: $session_id})-[:DEFINED_IN]->(fil)
                RETURN fn.name AS source, fn2.name AS target,
                       fn.complexity AS complexity,
                       fn.fan_in AS fan_in, fn.fan_out AS fan_out,
                       fn.line_start AS line_start, fn.line_end AS line_end
            """, file=file_path, normalized_file=normalized_file, windows_file=windows_file, session_id=session_id)
            nodes = {}
            edges = []
            for r in result:
                src = r["source"]
                tgt = r.get("target")
                if src not in nodes:
                    nodes[src] = {"id": src, "type": "function", "line_start": int(r.get("line_start") or 0), "line_end": int(r.get("line_end") or 0), "complexity": int(r.get("complexity") or 0), "fan_in": int(r.get("fan_in") or 0), "fan_out": int(r.get("fan_out") or 0)}
                if tgt:
                    edges.append({"source": src, "target": tgt})

            return {"nodes": list(nodes.values()), "edges": edges, "tier": 3, "file": file_path, "chunked": False}
    except Exception as e:
        logger.error(f"Error building tier3: {str(e)}")
        raise