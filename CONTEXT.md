# CONTEXT.md - Technical Architecture & Context

## Database Schema (Neo4j)

### Node Types

#### Module Node
```cypher
CREATE (m:Module {
  id: string,           // Unique ID (usually folder name)
  name: string,         // Human-readable name
  path: string,         // Absolute path
  file_count: integer,  // Number of files
  function_count: integer,
  avg_complexity: float,
  created_at: timestamp
})
```

#### File Node
```cypher
CREATE (f:File {
  id: string,           // Unique ID (usually relative path)
  name: string,         // Filename
  path: string,         // Full path
  language: string,     // py, js, ts, java, go, rs
  size_bytes: integer,
  line_count: integer,
  function_count: integer,
  is_data_file: boolean,
  is_god_file: boolean,
  created_at: timestamp,
  checksum: string      // For caching
})
```

#### Function Node
```cypher
CREATE (fn:Function {
  id: string,           // Unique ID (file_path:function_name:line)
  name: string,         // Function/method name
  file_path: string,    // Full file path
  line_start: integer,
  line_end: integer,
  cyclomatic_complexity: integer,
  fan_in: integer,      // Count of callers
  fan_out: integer,     // Count of callees
  parameters: list,     // Parameter names (if available)
  return_type: string,  // Return type (if available)
  is_public: boolean,   // Public/private
  created_at: timestamp
})
```

#### Virtual Module Node (for God Files)
```cypher
CREATE (vm:VirtualModule {
  id: string,           // ChunkedFile_1, ChunkedFile_2, etc.
  name: string,         // AuthModule_1, DataProcessing_1
  source_file: string,  // Original God file path
  chunk_strategy: string, // "class_based", "complexity_based", "line_range"
  line_start: integer,
  line_end: integer,
  function_count: integer,
  created_at: timestamp
})
```

### Relationship Types

#### BELONGS_TO
```cypher
// File belongs to Module
(f:File)-[:BELONGS_TO]->(m:Module)

// Virtual Module belongs to File
(vm:VirtualModule)-[:BELONGS_TO]->(f:File)
```

#### DEFINED_IN
```cypher
// Function defined in File
(fn:Function)-[:DEFINED_IN]->(f:File)

// Or for God files with chunks:
(fn:Function)-[:DEFINED_IN]->(vm:VirtualModule)
```

#### CALLS (with frequency)
```cypher
// Function A calls Function B
(fnA:Function)-[:CALLS {
  frequency: integer,   // How many times called
  line: integer         // Line where call happens
}]->(fnB:Function)
```

### Indexes for Performance

```cypher
CREATE INDEX ON :Function(name)
CREATE INDEX ON :Function(file_path)
CREATE INDEX ON :Module(path)
CREATE INDEX ON :File(path)
CREATE INDEX ON :Function(cyclomatic_complexity)
```

---

## API Contract

### 1. POST /upload
**Request**:
```json
{
  "file": "<binary>",        // Single .py file
  // OR
  "zip": "<binary>",         // .zip file with multiple files
  // OR
  "files": [                 // Multipart array (folder)
    {"path": "src/a.py", "content": "..."},
    {"path": "src/b.js", "content": "..."}
  ]
}
```

**Response**:
```json
{
  "status": "success",
  "upload_id": "uuid",
  "session_id": "uuid",
  "tier1_graph": {
    "nodes": [
      {
        "id": "module-1",
        "type": "module",
        "label": "src",
        "data": {
          "files": 12,
          "functions": 145,
          "complexity_avg": 3.2
        }
      }
    ],
    "edges": [
      {
        "id": "e1",
        "source": "module-1",
        "target": "module-2",
        "label": "5 calls"
      }
    ]
  },
  "render_strategy": "show_all",  // or "make_group" or "search_only"
  "total_nodes": 45,
  "total_functions": 340,
  "processing_time_ms": 2340
}
```

### 2. GET /graph/tier2/{module_name}
**Response**:
```json
{
  "module_name": "src",
  "tier2_graph": {
    "nodes": [
      {
        "id": "file-1",
        "type": "file",
        "label": "parser.py",
        "data": {
          "language": "py",
          "functions": 12,
          "size_kb": 45,
          "complexity_avg": 4.1
        }
      }
    ],
    "edges": [
      {
        "source": "file-1",
        "target": "file-2",
        "label": "3 calls"
      }
    ]
  },
  "render_strategy": "show_all"
}
```

### 3. GET /graph/tier3?file_path=src/parser.py
**Response**:
```json
{
  "file_path": "src/parser.py",
  "tier3_graph": {
    "nodes": [
      {
        "id": "fn-1",
        "type": "function",
        "label": "parse_ast()",
        "data": {
          "line_start": 45,
          "line_end": 120,
          "complexity": 7,
          "fan_in": 3,
          "fan_out": 5
        }
      }
    ],
    "edges": [
      {
        "source": "fn-1",
        "target": "fn-2",
        "label": "1",
        "data": {"frequency": 1, "line": 67}
      }
    ]
  },
  "render_strategy": "show_all"
}
```

### 4. GET /search?q=function_name
**Response**:
```json
{
  "query": "function_name",
  "results": [
    {
      "type": "function",
      "name": "function_name",
      "file": "src/module.py",
      "line": 45,
      "complexity": 5,
      "fan_in": 2,
      "relevance_score": 0.95
    }
  ]
}
```

---

## Parsing Configuration (Tree-sitter)

### Python Function Query
```scheme
(function_definition
  name: (identifier) @function.name
  parameters: (parameters) @function.params) @function.def
```

### JavaScript/TypeScript Function Query
```scheme
[
  (function_declaration
    name: (identifier) @function.name)
  (arrow_function) @function.def
  (method_definition
    key: (property_identifier) @function.name)
] @function.def
```

### Call Detection (All Languages)
- Track internal calls only (functions defined in project)
- Skip stdlib/external imports
- De-duplicate calls (count only unique callers)
- Include method calls: `obj.method()`

---

## God File Chunking Strategies

### Strategy 1: Class-Based Grouping
```python
# For each class in file:
# Create virtual module "ClassName_1"
# Assign all class methods to that module
```

### Strategy 2: Complexity-Based Grouping
```python
# Group functions by complexity:
# - HIGH: cyclomatic_complexity >= 10
# - MEDIUM: 5-9
# - LOW: 1-4
# Then name: ComplexityLevel_1, ComplexityLevel_2, etc.
```

### Strategy 3: Line-Range Grouping
```python
# Chunk every 50 functions by line number:
# Lines 1-2000 → Range_1
# Lines 2001-4000 → Range_2
# Lines 4001+ → Range_3
```

### Selection Logic
```
IF file has classes:
  Use class-based grouping
ELSE IF file has significant complexity variance:
  Use complexity-based grouping
ELSE:
  Use line-range grouping (fallback)
```

---

## Render Strategy Decision Tree

```
total_nodes = number of nodes in response

IF total_nodes < 100:
  render_strategy = "show_all"
  ACTION: Display all nodes, all edges

ELSE IF total_nodes <= 500:
  render_strategy = "make_group"
  ACTION: Calculate importance for each node
          Group least-important 50%
          Show important nodes individually
          Provide expand/collapse grouping

ELSE:
  render_strategy = "search_only"
  ACTION: Sort by importance
          Show top 100 nodes
          Hide remaining nodes
          Provide search UI to find hidden nodes
```

### Importance Calculation
```python
importance_score = (
  (fan_in * 0.3) +              # Incoming calls weighted 30%
  (fan_out * 0.3) +             # Outgoing calls weighted 30%
  (cyclomatic_complexity * 0.4) # Complexity weighted 40%
)
```

---

## Performance Requirements

| Operation | Target | Notes |
|-----------|--------|-------|
| Parse 100 files | <2 sec | Cache parsed ASTs |
| Generate Tier-1 graph | <5 sec | Query module relationships |
| Generate Tier-2 graph | <1 sec | Cache file-level data |
| Generate Tier-3 graph | <500 ms | Small scope, direct query |
| Search 1000+ functions | <1 sec | Full-text index |
| God file chunking | <10 sec | Complexity-aware grouping |
| Zip extraction + validation | <3 sec | Security checks |

---

## Caching Strategy

### L1 Cache (In-Memory, 5 min TTL)
- Tier-1 graph for current session
- Recently accessed Tier-2 graphs
- Search results

### L2 Cache (Database, persistent)
- Parsed AST per file (checksum-based)
- Function signatures and metadata
- Call graph relationships

### Invalidation Triggers
- File re-upload with different checksum
- Explicit cache clear request
- Session timeout (30 min)

---

## Security Checklist

- ✅ Zip-slip prevention (validate all extracted paths)
- ✅ Max file size enforcement (10 MB per file)
- ✅ Max folder depth (10 levels)
- ✅ Filename sanitization (remove ../, absolute paths)
- ✅ Max upload size (50 MB total)
- ✅ Max file count (1000 files)
- ✅ File type validation (extension whitelist)
- ✅ Symlink prevention (reject symlinks)
- ✅ Permission checks (no code execution)
- ✅ Input rate limiting (per IP, per session)

---

## Testing Matrix

| Component | Test Type | Coverage |
|-----------|-----------|----------|
| Folder walker | Unit + Integration | 95%+ |
| Tree-sitter parsing | Unit + Language-specific | 90%+ |
| God file chunking | Unit + Edge cases | 90%+ |
| Neo4j queries | Integration | 85%+ |
| API endpoints | Integration + E2E | 85%+ |
| Security | Security scanning + Manual | 100% |

---

## Monitoring & Metrics

### Key Metrics to Track
- Parse success rate (should be >99%)
- Average processing time per file
- Cache hit ratio (target >60%)
- Query performance (p95 response time)
- God file detection rate
- Error rate by language
- False negatives in call detection

### Alerts to Set Up
- Parse failure spike (>5% in 5 min window)
- Response time > 5 sec
- Neo4j connection failures
- Disk space low (<10% free)
- Memory usage >85%
