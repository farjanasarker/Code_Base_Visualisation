# SKILLS.md - Reusable Skills for CodeFlow

## Overview
Reusable skills are task-specific knowledge modules that can be invoked by agents to handle specialized work efficiently. Each skill is self-contained with clear input/output contracts.

---

## Skill 1: Tree-Sitter Multi-Language Parsing

**Skill ID**: `tree-sitter-parsing`  
**Owner**: @backend-dev, @architect  
**Category**: Code Analysis  

### Purpose
Parse code files in 6 languages and extract functions, calls, and complexity metrics.

### Supported Languages
- Python (.py)
- JavaScript (.js)
- TypeScript (.ts, .tsx)
- Java (.java)
- Go (.go)
- Rust (.rs)

### Input
```json
{
  "file_path": "string",
  "language": "py|js|ts|java|go|rs",
  "content": "string (file content)",
  "include_docstrings": boolean,
  "calculate_complexity": boolean
}
```

### Output
```json
{
  "functions": [
    {
      "id": "file:function_name:line_start",
      "name": "function_name",
      "line_start": 10,
      "line_end": 45,
      "parameters": ["param1", "param2"],
      "return_type": "string",
      "is_public": true,
      "cyclomatic_complexity": 3,
      "calls": ["called_function_1", "called_function_2"],
      "called_by": ["caller_1"],
      "docstring": "..."
    }
  ],
  "imports": ["import1", "import2"],
  "classes": ["Class1", "Class2"],
  "statistics": {
    "total_functions": 5,
    "avg_complexity": 3.2,
    "max_complexity": 7
  }
}
```

### Key Implementation Notes
- Use Tree-sitter for accurate AST parsing
- Extract only internal calls (filter stdlib/external)
- De-duplicate calls per function
- Calculate McCabe's cyclomatic complexity
- Handle async/await (JS/TS) and decorators (Python)

### Example Usage
```
@backend-dev: Use the tree-sitter-parsing skill to analyze src/parser.py
Extract all functions and their call relationships
```

---

## Skill 2: Neo4j Query Optimization

**Skill ID**: `neo4j-queries`  
**Owner**: @architect, @backend-dev  
**Category**: Database  

### Purpose
Build and optimize Neo4j queries for the 3-tier graph system.

### Input
```json
{
  "query_type": "tier1|tier2|tier3|search",
  "parameters": {
    "module_name": "string",
    "file_path": "string",
    "search_query": "string",
    "limit": integer
  }
}
```

### Output
```json
{
  "cypher_query": "string",
  "expected_performance": "ms",
  "index_requirements": ["string"],
  "caching_hint": "none|short|long"
}
```

### Tier-Specific Queries

#### Tier 1: Module-Level Call Graph
```cypher
MATCH (m1:Module)-[:BELONGS_TO*]->(m2:Module)
WHERE m1 <> m2
RETURN m1, count(DISTINCT relationships) as call_count
```

#### Tier 2: File-Level Call Graph
```cypher
MATCH (f1:File)-[:BELONGS_TO]->(m:Module {name: $module_name})
MATCH (f2:File)-[:BELONGS_TO]->(m)
OPTIONAL MATCH (fn1:Function)-[:DEFINED_IN]->(f1)
OPTIONAL MATCH (fn2:Function)-[:DEFINED_IN]->(f2)
OPTIONAL MATCH (fn1)-[:CALLS]->(fn2)
RETURN f1, f2, count(DISTINCT fn1) as calls
```

#### Tier 3: Function-Level Call Graph
```cypher
MATCH (f:File {path: $file_path})
MATCH (fn:Function)-[:DEFINED_IN]->(f)
OPTIONAL MATCH (fn)-[:CALLS]->(callee:Function)
RETURN fn, callee
```

### Key Implementation Notes
- Use APOC for complex queries
- Add indexes before production queries
- Implement query caching for common patterns
- Monitor slow queries (>1 sec)
- Batch operations for bulk inserts

### Example Usage
```
@backend-dev: Use the neo4j-queries skill to build Tier-2 query
Parameter: module_name = "src"
Include caching hints
```

---

## Skill 3: God File Chunking Algorithm

**Skill ID**: `god-file-chunking`  
**Owner**: @architect, @backend-dev  
**Category**: Code Analysis  

### Purpose
Intelligently split God Files (>100 functions) into manageable chunks.

### Input
```json
{
  "file_path": "string",
  "functions": [
    {
      "name": "string",
      "line_start": integer,
      "line_end": integer,
      "class": "string (if applicable)",
      "complexity": integer
    }
  ],
  "strategy_preference": "auto|class_based|complexity_based|line_range"
}
```

### Output
```json
{
  "chunks": [
    {
      "chunk_id": "AuthModule_1",
      "functions": ["login", "logout", "validate_token"],
      "line_start": 1,
      "line_end": 200,
      "strategy_used": "class_based",
      "estimated_importance": "HIGH"
    }
  ],
  "total_chunks": 3,
  "strategy_rationale": "string"
}
```

### Chunking Strategies

**1. Class-Based (Priority 1)**
```
FOR each class in file:
  CREATE chunk named after class
  ASSIGN all methods of that class to chunk
```

**2. Complexity-Based (Priority 2)**
```
GROUP functions by complexity level:
  HIGH (complexity >= 10): ComplexityHigh_1, _2, ...
  MEDIUM (5-9): ComplexityMed_1, _2, ...
  LOW (1-4): ComplexityLow_1, _2, ...
```

**3. Line-Range (Priority 3)**
```
CHUNK every 50 functions by line range:
  Range_1: lines 1-2000
  Range_2: lines 2001-4000
  Range_3: lines 4001+
```

### Selection Logic
```python
IF classes_found > 0:
    return class_based_chunks()
ELIF max_complexity - min_complexity > 8:
    return complexity_based_chunks()
ELSE:
    return line_range_chunks()
```

### Example Usage
```
@architect: Use god-file-chunking skill to design chunks for large_file.py
It has 250 functions with 5 classes
Give me the chunk layout and virtual module names
```

---

## Skill 4: Security Validation for File Uploads

**Skill ID**: `upload-security`  
**Owner**: @security, @backend-dev  
**Category**: Security  

### Purpose
Validate uploaded files and folders for security threats.

### Input
```json
{
  "upload_type": "file|zip|folder",
  "file_paths": ["string"],
  "total_size_bytes": integer,
  "file_count": integer,
  "max_depth": integer
}
```

### Output
```json
{
  "is_valid": boolean,
  "violations": [
    {
      "type": "zip_slip|size_violation|depth_violation|invalid_extension",
      "severity": "error|warning",
      "details": "string",
      "remediation": "string"
    }
  ],
  "cleaned_paths": ["string"],
  "security_score": 0.95
}
```

### Security Checks

| Check | Rules | Impact |
|-------|-------|--------|
| Zip-Slip | No `../` in extracted paths | BLOCK |
| File Size | <10 MB per file | BLOCK |
| Total Size | <50 MB total | BLOCK |
| File Count | <1000 files | BLOCK |
| Depth | <10 levels | BLOCK |
| Extension | Whitelist only | BLOCK |
| Symlinks | Reject symlinks | BLOCK |
| Absolute Paths | Convert to relative | WARN |

### Example Usage
```
@security: Use upload-security skill to validate this zip file
Check for all known vulnerabilities
Return cleaned paths ready for processing
```

---

## Skill 5: React Flow Visualization Mapping

**Skill ID**: `react-flow-mapping`  
**Owner**: @frontend-dev  
**Category**: UI/UX  

### Purpose
Convert graph data to React Flow node/edge format with optimization hints.

### Input
```json
{
  "graph_data": {
    "nodes": [...],
    "edges": [...]
  },
  "render_strategy": "show_all|make_group|search_only",
  "tier": 1|2|3,
  "viewport_size": {"width": integer, "height": integer}
}
```

### Output
```json
{
  "nodes": [
    {
      "id": "node-1",
      "data": {"label": "...", "details": "..."},
      "position": {"x": 0, "y": 0},
      "style": {"background": "#...", "borderColor": "#..."},
      "type": "default|group|module",
      "parent": "group-1"
    }
  ],
  "edges": [
    {
      "id": "edge-1",
      "source": "node-1",
      "target": "node-2",
      "animated": boolean,
      "style": {"stroke": "#..."}
    }
  ],
  "layout_hints": {
    "algorithm": "dagre|force|hierarchical",
    "group_threshold": integer
  }
}
```

### Render Strategy Handling

**show_all**: Display all nodes individually with full styling
**make_group**: Group low-importance nodes, highlight critical paths
**search_only**: Show top 100 with search UI for others

### Example Usage
```
@frontend-dev: Use react-flow-mapping skill to convert Tier-2 graph
Render strategy is "make_group"
Provide layout hints for hierarchical positioning
```

---

## Skill 6: Performance Profiling & Optimization

**Skill ID**: `performance-optimization`  
**Owner**: @architect, @backend-dev, @frontend-dev  
**Category**: Performance  

### Purpose
Profile and optimize slow operations.

### Input
```json
{
  "operation": "parsing|querying|rendering|upload",
  "current_metrics": {
    "time_ms": number,
    "memory_mb": number,
    "items_processed": integer
  },
  "target_metrics": {
    "time_ms": number,
    "memory_mb": number
  },
  "constraints": ["string"]
}
```

### Output
```json
{
  "bottleneck": "string",
  "optimization_recommendations": [
    {
      "technique": "string",
      "impact": "high|medium|low",
      "effort": "easy|medium|hard",
      "expected_improvement_percent": number
    }
  ],
  "implementation_priority": ["string"]
}
```

### Common Optimizations
- Caching (in-memory, Redis, DB)
- Batch processing
- Async operations
- Index optimization
- Query optimization
- Memory pooling
- Lazy loading

### Example Usage
```
@architect: Use performance-optimization skill
Operation: Tier-2 query taking 3 seconds
Target: <1 second
Current: parsing 50 files, 200 functions
```

---

## Skill 7: Testing Strategy & Test Case Generation

**Skill ID**: `test-strategy`  
**Owner**: @qa-engineer  
**Category**: Quality Assurance  

### Purpose
Design comprehensive test strategies and generate test cases.

### Input
```json
{
  "component": "folder_walker|parser|chunking|queries|api|ui",
  "complexity": "low|medium|high",
  "coverage_target": 85|90|95
}
```

### Output
```json
{
  "test_categories": [
    {
      "category": "unit|integration|e2e",
      "test_cases": [
        {
          "name": "string",
          "description": "string",
          "inputs": "...",
          "expected_output": "...",
          "edge_case": boolean
        }
      ]
    }
  ],
  "test_data": ["..."],
  "coverage_estimate": number,
  "estimated_effort_hours": number
}
```

### Example Usage
```
@qa-engineer: Use test-strategy skill
Component: god-file-chunking
Complexity: high
Coverage target: 95%
Generate comprehensive test strategy with edge cases
```

---

## Skill 8: Documentation Generation

**Skill ID**: `doc-generation`  
**Owner**: @skills-engineer  
**Category**: Documentation  

### Purpose
Generate API docs, architecture diagrams, and user guides.

### Input
```json
{
  "doc_type": "api|architecture|user_guide|troubleshooting",
  "component": "string",
  "audience": "developer|architect|user|devops",
  "format": "markdown|html|pdf"
}
```

### Output
```json
{
  "document": "string (markdown/html content)",
  "diagrams": ["mermaid_syntax"],
  "code_examples": ["string"],
  "metadata": {
    "generated_at": "timestamp",
    "version": "string"
  }
}
```

### Example Usage
```
@skills-engineer: Use doc-generation skill
Generate API documentation for /upload endpoint
Audience: backend developers
Include code examples for all languages
```

---

## How to Invoke Skills

### Syntax
```
@agent-name: Use the [skill-id] skill to [specific task]
[Additional context and parameters]
```

### Examples

**Example 1: Parsing**
```
@backend-dev: Use the tree-sitter-parsing skill to analyze all Python files in src/
Extract functions, calls, and complexity metrics
De-duplicate calls and filter external imports
```

**Example 2: Optimization**
```
@architect: Use the performance-optimization skill
Operation: God file chunking
Current performance: 15 seconds for 500-function file
Target: <5 seconds
```

**Example 3: Testing**
```
@qa-engineer: Use the test-strategy skill
Component: Neo4j queries
Complexity: high
Generate test cases for all 3 tiers
Include edge cases for circular call patterns
```

---

## Skill Library Structure

```
skills/
├── tree-sitter-parsing/
│   ├── SKILL.md (documentation)
│   ├── examples/ (code examples)
│   └── templates/ (language-specific)
├── neo4j-queries/
│   ├── SKILL.md
│   ├── queries/ (Cypher templates)
│   └── tests/
├── god-file-chunking/
│   ├── SKILL.md
│   ├── algorithms/
│   └── test_data/
├── upload-security/
│   ├── SKILL.md
│   ├── validators/
│   └── security_tests/
├── react-flow-mapping/
│   ├── SKILL.md
│   ├── templates/
│   └── examples/
├── performance-optimization/
│   ├── SKILL.md
│   ├── profilers/
│   └── benchmarks/
├── test-strategy/
│   ├── SKILL.md
│   ├── templates/
│   └── test_data/
└── doc-generation/
    ├── SKILL.md
    ├── templates/
    └── examples/
```

---

## Best Practices for Skills

✅ **DO**:
- Keep skills focused and single-purpose
- Provide clear input/output contracts
- Include error handling
- Document assumptions and constraints
- Provide examples and templates
- Version skills explicitly
- Cache results when applicable

❌ **DON'T**:
- Mix multiple concerns in one skill
- Leave error cases undefined
- Assume specific tool versions
- Skip documentation
- Hardcode paths or values
- Forget to handle edge cases
- Skip testing

---

## Skill Versioning

Skills follow semantic versioning: `major.minor.patch`

- **major**: Breaking changes to input/output contract
- **minor**: New features, backward compatible
- **patch**: Bug fixes

Example: `tree-sitter-parsing@1.2.3`

Reference specific versions: `@backend-dev: Use tree-sitter-parsing@1.2.0 skill...`
