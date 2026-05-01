# Neo4j Query Optimization Skill

## Overview
Expertise in writing, optimizing, and debugging Neo4j Cypher queries for the 3-tier call graph system.

## When to Use This Skill
- Building Tier-1, Tier-2, Tier-3 queries
- Optimizing slow queries
- Designing indexes for performance
- Implementing full-text search
- Calculating importance metrics
- Handling large graph traversals

## Core Queries

### Tier-1: Module-Level Call Graph
Returns all modules and inter-module call relationships
```cypher
MATCH (m1:Module)
OPTIONAL MATCH (f1:File)-[:BELONGS_TO]->(m1)
OPTIONAL MATCH (fn1:Function)-[:DEFINED_IN]->(f1)
OPTIONAL MATCH (fn1)-[:CALLS]->(fn2:Function)
OPTIONAL MATCH (fn2)-[:DEFINED_IN]->(f2:File)
OPTIONAL MATCH (f2)-[:BELONGS_TO]->(m2:Module)
WHERE m1 <> m2
WITH m1, m2, COUNT(DISTINCT fn1) as call_count
RETURN COLLECT({source: m1, target: m2, calls: call_count}) as edges
```

### Tier-2: File-Level Call Graph
Returns all files in a module and inter-file calls
```cypher
MATCH (m:Module {name: $module_name})
MATCH (f1:File)-[:BELONGS_TO]->(m)
OPTIONAL MATCH (fn1:Function)-[:DEFINED_IN]->(f1)
OPTIONAL MATCH (fn1)-[:CALLS]->(fn2:Function)
OPTIONAL MATCH (fn2)-[:DEFINED_IN]->(f2:File)
WHERE f1 <> f2 AND (f2)-[:BELONGS_TO]->(m)
WITH f1, f2, COUNT(DISTINCT fn1) as call_count
RETURN {files: COLLECT(f1), edges: COLLECT({source: f1, target: f2, calls: call_count})} as result
```

### Tier-3: Function-Level Call Graph
Returns all functions in a file and their call relationships
```cypher
MATCH (f:File {path: $file_path})
MATCH (fn:Function)-[:DEFINED_IN]->(f)
OPTIONAL MATCH (fn)-[:CALLS]->(callee:Function)
WITH fn, COLLECT(callee) as callees
RETURN {functions: COLLECT(fn), calls: COLLECT({caller: fn, callees: callees})} as result
```

## Performance Optimization Techniques

### Indexing Strategy
```cypher
CREATE INDEX ON :Function(file_path)
CREATE INDEX ON :Function(name)
CREATE INDEX ON :Module(path)
CREATE INDEX ON :File(path)
CREATE INDEX ON :Function(cyclomatic_complexity)
```

### Query Profiling
```cypher
PROFILE MATCH (m1:Module) RETURN count(m1)
EXPLAIN MATCH (m1:Module) RETURN count(m1)
```

### Caching Hints
- Short-term (5 min): Session-specific results
- Long-term (1 hour): Global statistics
- Invalidate on: File re-upload, data changes

## Common Patterns

### Importance Calculation
```cypher
MATCH (fn:Function)
WITH fn,
  size((fn)<-[:CALLS]-()) as fan_in,
  size((fn)-[:CALLS]->()) as fan_out,
  fn.cyclomatic_complexity as complexity
RETURN fn,
  (fan_in * 0.3 + fan_out * 0.3 + complexity * 0.4) as importance_score
ORDER BY importance_score DESC
```

### Call Frequency Analysis
```cypher
MATCH (fn1:Function)-[call:CALLS]->(fn2:Function)
RETURN fn1.name, fn2.name, call.frequency
ORDER BY call.frequency DESC
```

### Circular Dependency Detection
```cypher
MATCH path = (fn:Function)-[:CALLS*]->(:Function)
WHERE fn IN nodes(path)
RETURN EXTRACT(n IN nodes(path) | n.name) as cycle
```

## Best Practices
- Always use indexes for WHERE clauses
- Avoid expensive operations (cartesian products)
- Use LIMIT for pagination
- Profile queries before optimization
- Cache results appropriately
- Return only necessary fields

## Common Issues & Solutions

**Issue**: Query takes >5 seconds  
**Solution**: Add indexes, restructure query, use aggregations

**Issue**: Out of memory on large graphs  
**Solution**: Add LIMIT, use pagination, break into smaller queries

**Issue**: Incorrect results  
**Solution**: Check relationship directions, validate filters, trace logic

**Issue**: N+1 query problem  
**Solution**: Use COLLECT to aggregate, use WITH to pipeline

## Files in This Skill
- `SKILL.md` - This documentation
- `queries/` - Template Cypher queries
- `benchmarks/` - Performance test data
- `examples/` - Real usage examples

## Reference
- Neo4j Docs: https://neo4j.com/docs/
- Cypher Manual: https://neo4j.com/docs/cypher-manual/
- APOC Library: https://neo4j.com/labs/apoc/
