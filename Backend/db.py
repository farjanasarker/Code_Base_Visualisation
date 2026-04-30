from neo4j import GraphDatabase
import logging

logger = logging.getLogger(__name__)

driver = GraphDatabase.driver(
    "neo4j+s://41ba1e28.databases.neo4j.io",
    auth=("41ba1e28", "PXi2zC7QElI7PCf-cuK6S0E-DhuVxukey8ysxwPfzJE")
)

def add_edge(caller, callee):
    try:
        with driver.session() as session:
            session.run("""
                MERGE (a:Function {name: $caller})
                MERGE (b:Function {name: $callee})
                MERGE (a)-[:CALLS]->(b)
            """, caller=caller, callee=callee)
    except Exception as e:
        logger.error(f"Error adding edge: {str(e)}")
        raise

def clear_graph():
    try:
        with driver.session() as session:
            session.run("""
                MATCH (n)
                DETACH DELETE n
            """)
    except Exception as e:
        logger.error(f"Error clearing graph: {str(e)}")
        raise

def get_neighbors(function_name):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (a:Function {name: $name})-[:CALLS]->(b)
                RETURN b.name AS name
            """, name=function_name)
            return [r["name"] for r in result]
    except Exception as e:
        logger.error(f"Error getting neighbors: {str(e)}")
        raise


def get_full_graph():
    try:
        with driver.session() as session:
            node_result = session.run(
                """
                MATCH (n:Function)
                RETURN n.name AS name
                ORDER BY n.name
                """
            )

            edge_result = session.run(
                """
                MATCH (a:Function)-[:CALLS]->(b:Function)
                RETURN a.name AS source, b.name AS target
                ORDER BY source, target
                """
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


def store_all(functions):
    """Store modules, files, functions and CALLS edges from a list of function dicts."""
    try:
        with driver.session() as session:
            for fn in functions:
                session.run("""
                    MERGE (mod:Module {name: $module})
                    MERGE (fil:File {path: $file, language: $language})
                    MERGE (fil)-[:BELONGS_TO]->(mod)
                    MERGE (func:Function {name: $name, file: $file})
                    SET func.line_start   = $line_start,
                        func.line_end     = $line_end,
                        func.complexity   = $complexity,
                        func.language     = $language,
                        func.fan_in       = $fan_in,
                        func.fan_out      = $fan_out,
                        func.virtual_module = $virtual_module
                    MERGE (func)-[:DEFINED_IN]->(fil)
                """, **{
                    "module": fn.get("module"),
                    "file": fn.get("file"),
                    "language": fn.get("language"),
                    "name": fn.get("name"),
                    "line_start": fn.get("line_start"),
                    "line_end": fn.get("line_end"),
                    "complexity": fn.get("complexity"),
                    "fan_in": fn.get("fan_in"),
                    "fan_out": fn.get("fan_out"),
                    "virtual_module": fn.get("virtual_module"),
                })

            # Create CALLS edges
            for fn in functions:
                for called in fn.get("calls", []):
                    session.run("""
                        MATCH (caller:Function {name: $caller, file: $file})
                        MATCH (callee:Function {name: $callee})
                        MERGE (caller)-[:CALLS]->(callee)
                    """, caller=fn.get("name"), file=fn.get("file"), callee=called)
            # Persist chunk (virtual_module) nodes and relationships
            for fn in functions:
                vm = fn.get("virtual_module")
                fpath = fn.get("file")
                if vm and vm != fpath:
                    session.run("""
                        MATCH (fil:File {path: $file})
                        MERGE (chunk:Chunk {name: $vm})
                        MERGE (chunk)-[:IN_FILE]->(fil)
                        MATCH (func:Function {name: $name, file: $file})
                        MERGE (func)-[:PART_OF]->(chunk)
                    """, file=fpath, vm=vm, name=fn.get("name"))
    except Exception as e:
        logger.error(f"Error storing functions: {str(e)}")
        raise


def get_tier1():
    """Return module-level graph (nodes + edges)."""
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (m1:Module)<-[:BELONGS_TO]-(:File)<-[:DEFINED_IN]-(f1:Function)
                      -[:CALLS]->(f2:Function)-[:DEFINED_IN]->(:File)-[:BELONGS_TO]->(m2:Module)
                WHERE m1 <> m2
                RETURN m1.name AS source, m2.name AS target, count(*) AS call_count
            """)
            edges = [{"source": r["source"], "target": r["target"], "call_count": r["call_count"]} for r in result]

            # nodes: aggregate module stats
            node_res = session.run("""
                MATCH (m:Module)<-[:BELONGS_TO]-(fil:File)<-[:DEFINED_IN]-(f:Function)
                RETURN m.name AS module, sum(f.line_end - f.line_start) AS loc, count(distinct f.name) AS fn_count, collect(distinct fil.language) AS languages
            """)
            nodes = [{"id": r["module"], "type": "module", "loc": int(r["loc"] or 0), "fn_count": int(r["fn_count"]), "languages": r["languages"]} for r in node_res]

            return {"nodes": nodes, "edges": edges, "tier": 1}
    except Exception as e:
        logger.error(f"Error building tier1: {str(e)}")
        raise


def get_tier2(module_name: str):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (fil:File)-[:BELONGS_TO]->(mod:Module {name: $module})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function)-[:CALLS]->(fn2:Function)
                              -[:DEFINED_IN]->(fil2:File)-[:BELONGS_TO]->(mod)
                WHERE fil <> fil2
                RETURN fil.path AS source_file, fil2.path AS target_file,
                       fil.language AS language, count(fn) AS call_count
            """, module=module_name)
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

            # count functions per file
            fn_counts = session.run("""
                MATCH (fil:File)-[:BELONGS_TO]->(mod:Module {name: $module})
                OPTIONAL MATCH (fil)<-[:DEFINED_IN]-(fn:Function)
                RETURN fil.path AS file, count(fn) AS fn_count, fil.language AS language
            """, module=module_name)
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


def get_tier3(file_path: str):
    try:
        with driver.session() as session:
            # First check if chunk (virtual module) nodes exist for this file
            chunk_res = session.run("""
                MATCH (fil:File {path: $file})
                OPTIONAL MATCH (chunk:Chunk)-[:IN_FILE]->(fil)
                RETURN chunk.name AS chunk_name, count(*) AS cnt
            """, file=file_path)
            chunks = [r["chunk_name"] for r in chunk_res if r["chunk_name"]]

            if chunks and len(chunks) > 1:
                # return chunk-level graph
                nodes_q = session.run("""
                    MATCH (fil:File {path: $file})
                    MATCH (chunk:Chunk)-[:IN_FILE]->(fil)
                    OPTIONAL MATCH (chunk)<-[:PART_OF]-(f:Function)
                    RETURN chunk.name AS id, count(f) AS fn_count, collect(distinct f.language) AS languages
                """, file=file_path)
                nodes = [{"id": r["id"], "type": "chunk", "fn_count": int(r["fn_count"] or 0), "language": (r["languages"][0] if r["languages"] else None)} for r in nodes_q]

                edges_q = session.run("""
                    MATCH (fil:File {path: $file})
                    MATCH (c1:Chunk)-[:IN_FILE]->(fil)
                    MATCH (c2:Chunk)-[:IN_FILE]->(fil)
                    MATCH (f1:Function)-[:PART_OF]->(c1)
                    MATCH (f1)-[:CALLS]->(f2:Function)-[:PART_OF]->(c2)
                    WHERE c1 <> c2
                    RETURN c1.name AS source, c2.name AS target, count(*) AS call_count
                """, file=file_path)
                edges = [{"source": r["source"], "target": r["target"], "call_count": int(r["call_count"])} for r in edges_q]

                return {"nodes": nodes, "edges": edges, "tier": 3, "file": file_path, "chunked": True}

            # Fallback: return function-level graph for the file
            result = session.run("""
                MATCH (fn:Function)-[:DEFINED_IN]->(fil:File {path: $file})
                OPTIONAL MATCH (fn)-[:CALLS]->(fn2:Function)-[:DEFINED_IN]->(fil)
                RETURN fn.name AS source, fn2.name AS target,
                       fn.complexity AS complexity,
                       fn.fan_in AS fan_in, fn.fan_out AS fan_out,
                       fn.line_start AS line_start, fn.line_end AS line_end
            """, file=file_path)
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