# Test Strategy & Test Case Generation Skill

## Overview
Expertise in designing comprehensive test strategies, creating test cases, and ensuring quality across unit, integration, and E2E testing.

## When to Use This Skill
- Designing test strategy for new components
- Creating test cases for complex logic
- Identifying edge cases
- Planning test coverage goals
- Validating business logic
- Security testing
- Performance benchmarking
- Regression testing

## Test Strategy Framework

### 1. Identify Critical Paths
**Question**: What breaks the system?

**Examples**:
- Parser fails → No call graph generated
- God file chunking breaks → Visualization impossible
- Neo4j query times out → Frontend hangs
- Upload validation bypassed → Security breach

### 2. Define Test Levels

#### Unit Tests (Developer Level)
- **Scope**: Single function/method
- **Coverage**: 90%+
- **Time**: <100ms each
- **Tools**: pytest, unittest
- **Example**: Test `calculate_complexity()` function

#### Integration Tests (Module Level)
- **Scope**: Multiple components working together
- **Coverage**: 80%+
- **Time**: 1-10 sec each
- **Tools**: pytest, testcontainers
- **Example**: Upload → Parse → Store in Neo4j

#### E2E Tests (System Level)
- **Scope**: Full user workflows
- **Coverage**: 60%+
- **Time**: 30+ sec each
- **Tools**: Selenium, Playwright, pytest
- **Example**: Upload file → Navigate tiers → Search

### 3. Coverage Goals

| Component | Target | Notes |
|-----------|--------|-------|
| Core Logic | 90%+ | Business critical |
| Utils | 80%+ | Important but not core |
| Config | 60%+ | Lower priority |
| UI | 70%+ | User-facing |
| Security | 100% | Non-negotiable |

## Test Case Design

### Test Case Template
```
Title: [What is being tested]
Component: [Which component]
Type: [unit/integration/e2e]

Given: [Initial state]
When: [Action performed]
Then: [Expected result]

Edge Cases: [Special scenarios]
```

### Example Test Cases

#### Test: Python Parser - Extract Functions
```
Title: Extract functions from Python file
Component: tree-sitter-parsing skill
Type: unit

Given: Python file with 5 functions
When: parse_python(content)
Then: 
  - Returns 5 function objects
  - Each has name, line_start, line_end
  - Complexity calculated for each

Edge Cases:
  - Nested functions (should find all)
  - Decorators (@property, @staticmethod)
  - Async functions
  - Class methods
  - Lambda functions (if included in scope)

Test Data:
  - simple_functions.py (5 functions)
  - complex_file.py (nested, async, decorators)
  - edge_cases.py (lambdas, closures)
```

#### Test: God File Chunking
```
Title: Chunk 200-function file intelligently
Component: god-file-chunking skill
Type: unit

Given: File with 5 classes, 200 functions total
When: chunk_god_file(file_analysis)
Then:
  - Returns 5 virtual modules (one per class)
  - All functions assigned to exactly one chunk
  - Chunk names meaningful (e.g., "UserManager_1")

Edge Cases:
  - File with no classes (use complexity-based)
  - Circular function calls (preserved across chunks)
  - Standalone functions + classes (utils module created)
  - Very similar classes (handled differently)

Test Data:
  - authentication.py (5 classes)
  - utilities.py (no classes, 150 functions)
  - mixed.py (3 classes + 50 standalone)
```

#### Test: Upload Security
```
Title: Reject zip-slip attack
Component: upload-security skill
Type: unit + integration

Given: Malicious ZIP with ../../etc/passwd
When: validate_upload(malicious.zip)
Then:
  - Returns is_valid = false
  - violation.type = "zip_slip"
  - File NOT extracted

Edge Cases:
  - Backslash path separators (Windows)
  - Encoded paths (%2e%2e)
  - Mixed separators
  - Absolute paths /etc/passwd

Test Data:
  - malicious_zip_slip.zip
  - malicious_encoded.zip
  - valid_safe.zip
```

## Test Categories

### Happy Path Tests
**Goal**: Verify normal operation  
**Count**: 30-40% of tests

```python
def test_parse_python_simple():
    result = parse_python("def hello(): pass")
    assert len(result.functions) == 1
    assert result.functions[0].name == "hello"
```

### Edge Case Tests
**Goal**: Verify boundary conditions  
**Count**: 40-50% of tests

```python
def test_parse_empty_file():
    result = parse_python("")
    assert len(result.functions) == 0

def test_parse_single_function():
    result = parse_python("def x(): pass")
    assert len(result.functions) == 1

def test_parse_nested_functions():
    code = "def outer(): def inner(): pass"
    result = parse_python(code)
    assert len(result.functions) >= 1  # Depends on scope
```

### Error Handling Tests
**Goal**: Verify failure modes  
**Count**: 15-20% of tests

```python
def test_parse_syntax_error():
    result = parse_python("def broken(")
    assert result.error is not None
    assert result.functions == []

def test_parse_invalid_language():
    with pytest.raises(ValueError):
        parse_code("invalid_language", code)
```

### Performance Tests
**Goal**: Verify speed targets  
**Count**: 5-10% of tests

```python
def test_parse_100_files_under_2sec():
    files = generate_100_test_files()
    start = time.time()
    results = [parse_python(f) for f in files]
    elapsed = time.time() - start
    assert elapsed < 2.0  # seconds
```

### Security Tests
**Goal**: Verify security controls  
**Count**: 5-10% of tests

```python
def test_zip_slip_prevention():
    malicious_zip = create_zip_slip_attack()
    result = validate_upload(malicious_zip)
    assert result.is_valid == False
    assert "zip_slip" in result.violations[0]["type"]
```

## Test Data Strategy

### Test Data Types

#### 1. Minimal Test Data
**Use for**: Unit tests, fast feedback
- Single function Python file
- Empty inputs
- Boundary values

#### 2. Realistic Test Data
**Use for**: Integration tests, real-world scenarios
- 50-line Python file with 5 functions
- Mixed languages project
- Real GitHub projects (with permission)

#### 3. Edge Case Test Data
**Use for**: Stress testing, robustness
- 500-function God file
- Deeply nested structures (10+ levels)
- Circular call graphs
- Large team projects (10k+ functions)

#### 4. Security Test Data
**Use for**: Security testing
- Zip-slip attacks
- Malicious file extensions
- Symlinks to sensitive files
- Path traversal attempts

### Test Data Organization
```
tests/
├── unit/
│   ├── test_parser.py
│   ├── test_chunking.py
│   └── fixtures/
│       ├── simple.py (10 lines)
│       └── complex.py (500 lines)
├── integration/
│   ├── test_upload_to_neo4j.py
│   └── fixtures/
│       ├── sample_project/ (real project)
│       └── god_file_examples/
└── e2e/
    ├── test_full_workflow.py
    └── fixtures/
        └── test_projects/
```

## Execution Plan

### Phase 1 (Week 1): Foundation Tests
- [ ] Parser tests (Python) - 20 tests
- [ ] Upload validation tests - 15 tests
- [ ] Neo4j basic query tests - 10 tests
- **Coverage**: 85%+ of critical paths

### Phase 2 (Week 2): Integration Tests
- [ ] Upload → Parse → Store flow - 10 tests
- [ ] Multi-file project handling - 8 tests
- [ ] God file chunking - 15 tests
- **Coverage**: 80%+ of workflows

### Phase 3 (Week 3-4): E2E & Performance
- [ ] Full UI workflows - 8 tests
- [ ] Performance benchmarks - 5 tests
- [ ] Stress tests (large projects) - 5 tests
- **Coverage**: 70%+ of user journeys

### Continuous: Regression Tests
- [ ] Run on every commit (fast tests)
- [ ] Run nightly (full suite)
- [ ] Alert on failures
- **Target**: <5 minute CI/CD run

## Metrics & Goals

### Coverage Goals
```
Unit Tests:      900+ lines of code
Integration:     500+ lines of code
E2E:            200+ user journeys
Overall:        >85% code coverage
```

### Quality Gates
```
✅ PASS:
- All tests passing
- Coverage >= 85%
- No critical bugs
- Performance targets met

❌ BLOCK:
- Any test failing
- Coverage drop > 2%
- Security test failure
- Performance regression > 10%
```

## Test Tools & Setup

### Unit Testing
```python
# pytest
pytest tests/unit/ -v --cov=src --cov-report=html
```

### Integration Testing
```python
# testcontainers for Neo4j
from testcontainers.neo4j import Neo4jContainer

def test_with_neo4j():
    with Neo4jContainer() as neo4j:
        # Your test here
```

### E2E Testing
```javascript
// Playwright
import { test, expect } from '@playwright/test';

test('upload and navigate tiers', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.click('button:has-text("Upload")');
  // ... test steps
});
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest tests/unit -v
      - run: pytest tests/integration -v
      - run: pytest tests/e2e -v
```

## Files in This Skill
- `SKILL.md` - This documentation
- `templates/` - Test case templates
- `test_data/` - Sample test files
- `checklist.md` - Testing checklist

## Reference
- pytest: https://docs.pytest.org/
- testcontainers: https://testcontainers.com/
- Playwright: https://playwright.dev/
- OWASP Testing Guide: https://owasp.org/www-project-web-security-testing-guide/
