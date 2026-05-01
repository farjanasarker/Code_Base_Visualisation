# PHASES.md - Implementation Roadmap & Phases

## Project Phases Overview

This BMAD project is broken into 5 phases, each with clear deliverables, dependencies, and success criteria.

---

## Phase 1: Foundation & Security (Weeks 1-2)
**Status**: 🔵 Not Started  
**Lead**: @backend-dev (with @security, @architecture)

### Objectives
- Set up base project structure
- Implement secure file upload handling
- Set up Neo4j database
- Create basic Tree-sitter parser for Python

### Tasks

#### Phase 1.1: Project Setup
- [ ] Initialize FastAPI project structure
- [ ] Set up environment (.env, requirements.txt)
- [ ] Create database configuration files
- [ ] Set up Vue.js Frontend basic structure
- [ ] Initialize git with proper .gitignore

**Skills Used**: None (standard setup)  
**Est. Time**: 4 hours

#### Phase 1.2: Security & File Upload
- [ ] Implement zip-slip prevention
- [ ] Add file size/count validation
- [ ] Create file extension whitelist
- [ ] Implement path sanitization
- [ ] Add rate limiting

**Skills Used**: `upload-security`  
**Est. Time**: 8 hours  
**Output**: Secure upload endpoint with full validation

#### Phase 1.3: Folder Walker Implementation
- [ ] Implement recursive folder traversal
- [ ] Add language detection (.py, .js, .ts, .java, .go, .rs)
- [ ] Add file filtering (skip node_modules, .git, etc.)
- [ ] Test with sample projects

**Skills Used**: None (custom implementation)  
**Est. Time**: 8 hours  
**Output**: Working folder walker

#### Phase 1.4: Neo4j Setup
- [ ] Set up Neo4j instance (local/Docker)
- [ ] Create database schema (Module, File, Function nodes)
- [ ] Create initial indexes
- [ ] Set up connection pooling

**Skills Used**: None (infrastructure)  
**Est. Time**: 4 hours  
**Output**: Running Neo4j with proper schema

#### Phase 1.5: Python Parser (Tree-sitter)
- [ ] Install tree-sitter library
- [ ] Create Python language parser
- [ ] Extract function signatures
- [ ] Extract function calls (internal only)
- [ ] Calculate basic metrics (lines, parameters)

**Skills Used**: `tree-sitter-parsing`  
**Est. Time**: 12 hours  
**Output**: Working Python parser with tests

### Phase 1 Deliverables
✅ Secure upload endpoint  
✅ Folder walker  
✅ Neo4j database running  
✅ Python parser working  

### Success Criteria
- Zip file upload works without zip-slip vulnerabilities
- Folder walker correctly identifies all .py files
- Python parser extracts 100% of functions in test files
- Neo4j can store and query parsed data

---

## Phase 2: Large File Handling (Weeks 3-4)
**Status**: 🔵 Not Started  
**Lead**: @architect (with @backend-dev)  
**Depends On**: Phase 1 ✅

### Objectives
- Implement large file detection
- Build God file chunking strategies
- Handle complex codebases

### Tasks

#### Phase 2.1: Large File Detection
- [ ] Add line count detection
- [ ] Identify God Files (>100 functions)
- [ ] Categorize files (Data/Normal/God)
- [ ] Add detection to upload flow

**Skills Used**: None (custom logic)  
**Est. Time**: 6 hours

#### Phase 2.2: Chunking Algorithm Design
- [ ] Analyze AST for class grouping
- [ ] Calculate complexity distribution
- [ ] Design chunking strategies

**Skills Used**: `god-file-chunking`  
**Est. Time**: 10 hours

#### Phase 2.3: Chunking Implementation
- [ ] Implement class-based chunking
- [ ] Implement complexity-based chunking
- [ ] Implement line-range chunking
- [ ] Create virtual module nodes
- [ ] Store in Neo4j

**Skills Used**: `god-file-chunking`  
**Est. Time**: 16 hours

#### Phase 2.4: Chunking Testing
- [ ] Create test God files (200+ functions)
- [ ] Test each chunking strategy
- [ ] Validate Neo4j storage
- [ ] Performance testing

**Skills Used**: `test-strategy`  
**Est. Time**: 10 hours

### Phase 2 Deliverables
✅ Large file detection working  
✅ God file chunking algorithm complete  
✅ Virtual modules in Neo4j  
✅ Comprehensive test suite

### Success Criteria
- Detects God Files correctly (>95% accuracy)
- Chunks are logical and meaningful
- <10 seconds to chunk 500-function file
- All chunks store correctly in Neo4j

---

## Phase 3: Multi-Language Parsing (Weeks 5-6)
**Status**: 🔵 Not Started  
**Lead**: @backend-dev (with @architect)  
**Depends On**: Phase 1 ✅, Phase 2 ✅

### Objectives
- Add parsers for 5 more languages
- Implement complexity metrics
- Handle language-specific patterns

### Tasks

#### Phase 3.1: JavaScript/TypeScript Parser
- [ ] Set up Tree-sitter JS/TS
- [ ] Extract functions (regular, arrow, async)
- [ ] Extract class methods
- [ ] Handle imports correctly
- [ ] Calculate complexity

**Skills Used**: `tree-sitter-parsing`  
**Est. Time**: 8 hours

#### Phase 3.2: Java Parser
- [ ] Set up Tree-sitter Java
- [ ] Extract class methods
- [ ] Extract interfaces
- [ ] Calculate complexity

**Skills Used**: `tree-sitter-parsing`  
**Est. Time**: 8 hours

#### Phase 3.3: Go, Rust, C++ Parsers
- [ ] Set up Tree-sitter for Go
- [ ] Set up Tree-sitter for Rust
- [ ] Set up Tree-sitter for C++
- [ ] Extract functions/methods
- [ ] Handle language-specific patterns

**Skills Used**: `tree-sitter-parsing`  
**Est. Time**: 12 hours each

#### Phase 3.4: Complexity Metrics
- [ ] Implement McCabe's complexity calculation
- [ ] Handle nested structures
- [ ] Calculate per all languages
- [ ] Validate against benchmarks

**Skills Used**: `tree-sitter-parsing`  
**Est. Time**: 8 hours

#### Phase 3.5: Call Graph Deduplication
- [ ] Track already-parsed functions
- [ ] Deduplicate calls across files
- [ ] Calculate fan-in and fan-out
- [ ] Store metrics in Neo4j

**Skills Used**: None (data processing)  
**Est. Time**: 10 hours

### Phase 3 Deliverables
✅ 6-language parser support  
✅ Complexity metrics calculated  
✅ Call graph deduplication working  
✅ All metrics in Neo4j

### Success Criteria
- All 6 languages parse correctly
- >90% function detection accuracy per language
- Complexity metrics within 5% of benchmarks
- <5 seconds to parse 100 diverse language files

---

## Phase 4: API & Query Optimization (Weeks 7-8)
**Status**: 🔵 Not Started  
**Lead**: @architect (with @backend-dev)  
**Depends On**: Phase 3 ✅

### Objectives
- Build all FastAPI endpoints
- Optimize Neo4j queries
- Implement render strategies
- Add caching

### Tasks

#### Phase 4.1: Tier-1 Endpoint & Query
- [ ] Design Tier-1 query (module view)
- [ ] Implement `/upload` endpoint
- [ ] Calculate inter-module calls
- [ ] Optimize for <5 sec response

**Skills Used**: `neo4j-queries`  
**Est. Time**: 8 hours

#### Phase 4.2: Tier-2 Endpoint & Query
- [ ] Design Tier-2 query (file view)
- [ ] Implement `/graph/tier2/{module}` endpoint
- [ ] Calculate inter-file calls within module
- [ ] Optimize for <1 sec response

**Skills Used**: `neo4j-queries`  
**Est. Time**: 6 hours

#### Phase 4.3: Tier-3 Endpoint & Query
- [ ] Design Tier-3 query (function view)
- [ ] Implement `/graph/tier3?file_path=...` endpoint
- [ ] Get all functions and calls in file
- [ ] Optimize for <500 ms response

**Skills Used**: `neo4j-queries`  
**Est. Time**: 6 hours

#### Phase 4.4: Search Endpoint
- [ ] Implement `/search?q=...` endpoint
- [ ] Add full-text indexes
- [ ] Rank results by relevance
- [ ] Optimize for <1 sec search

**Skills Used**: `neo4j-queries`  
**Est. Time**: 6 hours

#### Phase 4.5: Render Strategy Logic
- [ ] Implement node counting
- [ ] Implement importance calculation
- [ ] Generate render strategy hints
- [ ] Test on various datasets

**Skills Used**: None (business logic)  
**Est. Time**: 8 hours

#### Phase 4.6: Caching Strategy
- [ ] Implement in-memory cache (session data)
- [ ] Implement Redis/persistent cache
- [ ] Add cache invalidation logic
- [ ] Measure cache hit ratio

**Skills Used**: `performance-optimization`  
**Est. Time**: 10 hours

### Phase 4 Deliverables
✅ All FastAPI endpoints working  
✅ Optimized Neo4j queries  
✅ Render strategies calculated  
✅ Caching layer implemented

### Success Criteria
- All endpoints return <5 sec
- Tier-2 <1 sec, Tier-3 <500 ms
- Search <1 sec for 1000+ functions
- Cache hit ratio >60%

---

## Phase 5: Frontend Integration & Optimization (Weeks 9-10)
**Status**: 🔵 Not Started  
**Lead**: @frontend-dev (with @architect)  
**Depends On**: Phase 4 ✅

### Objectives
- Build React Flow visualization
- Implement tier-based navigation
- Optimize rendering performance
- Add search and filtering

### Tasks

#### Phase 5.1: React Flow Component Setup
- [ ] Install React Flow
- [ ] Create component structure
- [ ] Set up state management (Pinia)
- [ ] Create node/edge types

**Skills Used**: `react-flow-mapping`  
**Est. Time**: 8 hours

#### Phase 5.2: Tier-1 Visualization
- [ ] Map Tier-1 data to React Flow format
- [ ] Position nodes hierarchically
- [ ] Style module nodes
- [ ] Add click handlers for Tier-2

**Skills Used**: `react-flow-mapping`  
**Est. Time**: 8 hours

#### Phase 5.3: Tier-2 & Tier-3 Navigation
- [ ] Implement Tier-2 view
- [ ] Implement Tier-3 view
- [ ] Add back navigation
- [ ] Implement breadcrumb trail

**Skills Used**: `react-flow-mapping`  
**Est. Time**: 12 hours

#### Phase 5.4: Render Strategy UI
- [ ] Implement "Show All" rendering
- [ ] Implement "Make Group" grouping UI
- [ ] Implement "Search Only" search UI
- [ ] Add expand/collapse toggles

**Skills Used**: `react-flow-mapping`  
**Est. Time**: 10 hours

#### Phase 5.5: Performance Optimization
- [ ] Profile rendering performance
- [ ] Implement virtual scrolling
- [ ] Optimize re-renders
- [ ] Add loading indicators

**Skills Used**: `performance-optimization`  
**Est. Time**: 10 hours

#### Phase 5.6: Polish & Edge Cases
- [ ] Handle empty results
- [ ] Add error messages
- [ ] Add loading states
- [ ] Responsive design for mobile

**Skills Used**: None (UI/UX work)  
**Est. Time**: 8 hours

### Phase 5 Deliverables
✅ Full React Flow UI  
✅ Tier-based navigation working  
✅ Render strategies implemented  
✅ Performance optimized

### Success Criteria
- <1 sec to render Tier-1 (100 modules)
- <500 ms to render Tier-2 (50 files)
- <300 ms to render Tier-3 (100 functions)
- Search UI responsive and intuitive
- No jank or lag on modern browsers

---

## Cross-Phase Tasks

### Ongoing Throughout All Phases
- [ ] Unit test coverage >85%
- [ ] Integration tests
- [ ] Security scanning
- [ ] Performance monitoring
- [ ] Documentation updates
- [ ] Code reviews

---

## Phase Dependencies

```
Phase 1: Foundation
    ↓
Phase 2: Large File Handling
    ↓
Phase 3: Multi-Language Parsing
    ↓
Phase 4: API & Queries
    ↓
Phase 5: Frontend Integration
```

---

## Resource Allocation

### Team Roles by Phase

| Phase | Lead | Support | Est. Hours |
|-------|------|---------|-----------|
| 1 | @backend-dev | @architect, @security | 36 |
| 2 | @architect | @backend-dev, @qa-engineer | 42 |
| 3 | @backend-dev | @architect | 54 |
| 4 | @architect | @backend-dev | 44 |
| 5 | @frontend-dev | @architect | 56 |
| **TOTAL** | | | **232 hours** |

---

## Milestones & Gates

### Gate 1: Complete Phase 1
**Criteria**:
- ✅ Secure upload working
- ✅ Folder walker tested
- ✅ Neo4j running with schema
- ✅ Python parser >90% accuracy

**Approval**: @architect, @security

### Gate 2: Complete Phase 2
**Criteria**:
- ✅ God file detection >95% accurate
- ✅ Chunking <10 sec for 500-function files
- ✅ Virtual modules in Neo4j
- ✅ Comprehensive test suite

**Approval**: @architect, @qa-engineer

### Gate 3: Complete Phase 3
**Criteria**:
- ✅ All 6 languages parsing
- ✅ >90% function detection per language
- ✅ Complexity metrics calculated
- ✅ No performance regressions

**Approval**: @architect, @qa-engineer

### Gate 4: Complete Phase 4
**Criteria**:
- ✅ All endpoints <5 sec
- ✅ Queries optimized
- ✅ Render strategies working
- ✅ Caching >60% hit ratio

**Approval**: @architect, @backend-dev

### Gate 5: Complete Phase 5
**Criteria**:
- ✅ Tier navigation smooth
- ✅ Render strategies functional
- ✅ <500 ms render time
- ✅ All workflows tested E2E

**Approval**: @frontend-dev, @qa-engineer

---

## Weekly Check-ins

**Every Monday**:
- Review completed tasks
- Identify blockers
- Adjust timeline if needed
- Plan sprint work

**Use**: `@pm help me review Phase X progress`

---

## Estimated Timeline

- **Phase 1**: 2 weeks (Weeks 1-2)
- **Phase 2**: 2 weeks (Weeks 3-4)
- **Phase 3**: 2 weeks (Weeks 5-6)
- **Phase 4**: 2 weeks (Weeks 7-8)
- **Phase 5**: 2 weeks (Weeks 9-10)

**Total**: 10 weeks = ~2.5 months for full implementation

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Tree-sitter parser bugs | High | Medium | Extensive testing, comparison with benchmarks |
| Neo4j performance | Medium | High | Early optimization, query profiling |
| God file edge cases | Medium | Medium | Comprehensive test suite, iteration |
| Multi-language complexity | High | Medium | Language experts consulted, incremental |
| Frontend rendering perf | Medium | High | Early profiling, optimization strategy |

---

## Success Metrics (End of Project)

✅ Support 6 programming languages  
✅ Handle 100k+ LOC codebases in <5 sec  
✅ Process God Files (>100 functions) gracefully  
✅ Render <100 nodes instantly  
✅ Search 1000+ functions in <1 sec  
✅ 95%+ accuracy in function detection  
✅ <2% false negatives in call detection  
✅ 90%+ test coverage  

---

## Next Steps

**When ready to start**:
1. Run `@pm: Help me plan Phase 1 implementation`
2. Run `@architecture: Review Phase 1 design decisions`
3. Run `@backend-dev: Start Phase 1 implementation`
