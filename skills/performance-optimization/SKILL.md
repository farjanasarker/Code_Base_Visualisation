# Performance Optimization Skill

## Overview
Expertise in profiling bottlenecks, identifying optimization opportunities, and implementing performance improvements across backend, database, and frontend.

## When to Use This Skill
- Analyzing slow operations
- Identifying bottlenecks
- Recommending optimizations
- Profiling database queries
- Optimizing rendering performance
- Implementing caching strategies
- Load testing and benchmarking

## Performance Metrics

### Backend Targets
| Operation | Target | Current | Status |
|-----------|--------|---------|--------|
| Parse 100 files | <2 sec | TBD | ⏳ |
| Generate Tier-1 | <5 sec | TBD | ⏳ |
| Generate Tier-2 | <1 sec | TBD | ⏳ |
| Generate Tier-3 | <500 ms | TBD | ⏳ |
| Search 1000+ | <1 sec | TBD | ⏳ |
| God file chunk | <10 sec | TBD | ⏳ |

### Frontend Targets
| Operation | Target | Current | Status |
|-----------|--------|---------|--------|
| Render Tier-1 (<100 nodes) | <1 sec | TBD | ⏳ |
| Render Tier-2 (50 files) | <500 ms | TBD | ⏳ |
| Render Tier-3 (100 functions) | <300 ms | TBD | ⏳ |
| Search results display | <100 ms | TBD | ⏳ |
| Node grouping | <200 ms | TBD | ⏳ |

## Profiling Framework

### Step 1: Measure Current State
```python
import time
import memory_profiler

@memory_profiler.profile
def operation_to_profile():
    start = time.perf_counter()
    # ... operation ...
    elapsed = time.perf_counter() - start
    return elapsed

# Result: 2.34 seconds, 245 MB memory
```

### Step 2: Identify Bottleneck
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# ... operation ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 functions
```

**Output Example**:
```
function_name    ncalls  tottime  cumtime
tree_sitter_parse  100    1.2      1.8      ← Main bottleneck
format_results     100    0.4      0.6
store_in_neo4j     100    0.3      0.5
```

### Step 3: Calculate Impact
```python
# If tree_sitter_parse is 60% of time:
# - 50% improvement = 0.36 sec saved (18% total)
# - 80% improvement = 0.58 sec saved (29% total)
# - 100% improvement = 0.90 sec saved (45% total)
```

## Common Optimization Techniques

### 1. Caching (Easy, High Impact)
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_calculation(param):
    # Only runs once per unique param
    return result

# Cache hit ratio target: >60%
# Invalidation: On data change
```

**Impact**: 50-90% improvement for repeated operations

### 2. Batch Processing (Medium, High Impact)
```python
# Instead of:
for file in files:
    process_single(file)  # N database calls

# Do:
process_batch(files)  # 1 database call
```

**Impact**: 10x improvement for database operations

### 3. Async Operations (Medium, Medium Impact)
```python
import asyncio

async def process_files(files):
    tasks = [parse_file_async(f) for f in files]
    results = await asyncio.gather(*tasks)
    return results

# Parallelizes I/O, not CPU
```

**Impact**: 2-5x for I/O-bound operations

### 4. Indexing (Easy, High Impact - DB)
```cypher
CREATE INDEX ON :Function(file_path)
CREATE INDEX ON :Function(name)
CREATE INDEX ON :Module(path)
```

**Impact**: 100x for indexed queries

### 5. Query Optimization (Hard, Very High Impact)
```cypher
# Before: 3 seconds
MATCH (m:Module)--(f:File)--(fn:Function)
MATCH (fn)-[:CALLS]->(:Function)
RETURN ...

# After: 200ms
MATCH (m:Module {name: $module})
MATCH (fn:Function)-[:DEFINED_IN]->(:File)-[:BELONGS_TO]->(m)
RETURN ...
```

**Impact**: 5-50x for complex queries

### 6. Lazy Loading (Medium, Medium Impact)
```javascript
// Load data only when needed
const [nodes, setNodes] = useState([])

const handleNodeExpand = async (nodeId) => {
  const childNodes = await fetchChildren(nodeId)
  setNodes(prev => [...prev, ...childNodes])
}
```

**Impact**: 10x for large datasets

### 7. Compression (Easy, Low Impact - Network)
```python
# gzip responses
response.headers['Content-Encoding'] = 'gzip'
```

**Impact**: 5-10x for network transfer

## Decision Framework

```
bottleneck found: operation X = N seconds

Option A: Cache (cost=easy, impact=50%)
  → 0.5N seconds
  
Option B: Optimize query (cost=hard, impact=80%)
  → 0.2N seconds
  
Option C: Batch process (cost=medium, impact=70%)
  → 0.3N seconds

PICK: Highest impact / cost ratio
```

## Optimization Priority

### Priority 1: Show Immediate Value
- Caching (quick win)
- Simple indexing
- Low-hanging query optimizations
- **Target**: 20-30% improvement

### Priority 2: Solve Known Issues
- Database optimization
- Algorithm improvements
- Batch processing
- **Target**: 50-70% improvement

### Priority 3: Scale for Growth
- Async processing
- Lazy loading
- Distributed caching
- **Target**: Final polish

## Testing Performance

### Load Testing
```python
# Test with increasing load
for num_files in [10, 50, 100, 500, 1000]:
    start = time.time()
    result = parse_files(generate_test_files(num_files))
    elapsed = time.time() - start
    print(f"{num_files} files: {elapsed:.2f}s")
```

### Regression Testing
```python
# Ensure no performance degradation
baseline = 2.5  # seconds (previous version)
current = measure_performance()

if current > baseline * 1.1:  # 10% slower
    raise PerformanceRegression()
```

## Monitoring in Production

### Key Metrics
- Operation completion time (p50, p95, p99)
- Cache hit ratio
- Memory usage
- CPU usage
- Database query time
- Network latency

### Alerts
```
Alert if:
- Operation time > 1.5x target
- Cache hit ratio < 40%
- Memory usage > 80%
- Error rate spike > 5%
```

## Files in This Skill
- `SKILL.md` - This documentation
- `profilers/` - Profiling tools
- `benchmarks/` - Benchmark data
- `optimization_checklist.md` - Step-by-step guide

## Reference
- Python cProfile: https://docs.python.org/3/library/profile.html
- Async/await: https://docs.python.org/3/library/asyncio.html
- Neo4j Performance: https://neo4j.com/docs/operations-manual/current/performance/
- React Performance: https://react.dev/learn/render-and-commit
