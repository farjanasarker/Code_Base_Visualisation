# God File Chunking Algorithm Skill

## Overview
Expertise in intelligently splitting God Files (>100 functions) into manageable, meaningful chunks without losing relationships.

## When to Use This Skill
- Identifying God Files in large codebases
- Designing optimal chunking strategy
- Creating virtual modules with meaningful names
- Maintaining function relationships across chunks
- Handling edge cases (deeply nested, mixed concerns)

## What is a God File?
- **Definition**: File with >100 functions
- **Problem**: Too complex to visualize as single graph
- **Solution**: Split into logical virtual modules
- **Goal**: Preserve functionality while improving understandability

## Chunking Strategies

### Strategy 1: Class-Based Grouping (Priority 1)
**Best For**: Object-oriented code with clear classes

```
FOR each class in file:
  CREATE virtual module named after class
  ASSIGN all methods and inner classes to module
  PRESERVE class hierarchy
```

**Example**:
```python
# File: authentication.py with 3 classes
class UserManager:       # 45 functions
class TokenHandler:      # 35 functions
class PasswordValidator: # 30 functions

# Creates:
- AuthenticationAuthModule_1 (UserManager methods)
- AuthenticationAuthHandler_1 (TokenHandler methods)
- AuthenticationValidator_1 (PasswordValidator methods)
```

### Strategy 2: Complexity-Based Grouping (Priority 2)
**Best For**: Functional code with high complexity variance

```
GROUP functions by complexity level:
  HIGH (complexity >= 10)   → ComplexityHigh_1, _2, ...
  MEDIUM (5-9)              → ComplexityMed_1, _2, ...
  LOW (1-4)                 → ComplexityLow_1, _2, ...

SORT each group to keep related functions together
CREATE virtual modules (50 functions per chunk)
```

**Example**:
```python
# File: data_processing.py with 200 functions
# Complexity range: 1-15

# Groups by complexity:
- ComplexityHigh_1: functions with complexity 10-15 (50 functions)
- ComplexityMed_1: functions with complexity 5-9 (60 functions)
- ComplexityMed_2: functions with complexity 5-9 (50 functions)
- ComplexityLow_1: functions with complexity 1-4 (40 functions)
```

### Strategy 3: Line-Range Grouping (Priority 3 - Fallback)
**Best For**: Simple functions without clear structure

```
CHUNK every 50 functions by line range:
  Range_1: lines 1-2000
  Range_2: lines 2001-4000
  Range_3: lines 4001+

NAME based on line position
```

**Example**:
```python
# File: utilities.py with 150 lines-per-function average
# 200 functions × 150 lines = 30,000 lines

# Creates:
- UtilitiesRange_1: lines 1-3000 (≈50 functions)
- UtilitiesRange_2: lines 3001-6000 (≈50 functions)
- UtilitiesRange_3: lines 6001-9000 (≈50 functions)
- UtilitiesRange_4: lines 9001+ (≈50 functions)
```

## Selection Logic

```python
def select_chunking_strategy(file_analysis):
    # Check if file has classes
    if has_classes(file_analysis):
        return apply_class_based_chunking()
    
    # Check complexity distribution
    complexity_variance = max_complexity - min_complexity
    if complexity_variance > 8:  # High variance
        return apply_complexity_based_chunking()
    
    # Fallback: line-range chunking
    return apply_line_range_chunking()
```

## Virtual Module Naming

### Class-Based Names
```
Format: [ClassName]_[Index]
Examples:
- UserManager_1
- TokenHandler_1
- PasswordValidator_1
```

### Complexity-Based Names
```
Format: [Complexity Level]_[Index]
Examples:
- ComplexityHigh_1
- ComplexityHigh_2
- ComplexityMed_1
- ComplexityLow_1
```

### Range-Based Names
```
Format: [FileName][Range Type]_[Index]
Examples:
- AnalyzerRange_1
- AnalyzerRange_2
- ProcessorRange_1
```

## Edge Cases & Solutions

### Case 1: Mixed Concerns
**Problem**: File has classes + standalone functions  
**Solution**: 
- Chunk classes first
- Create `_Utilities_1` module for standalone functions
- Keep related standalone functions together

### Case 2: Deeply Nested Structures
**Problem**: Functions have complex nesting (>5 levels)  
**Solution**:
- Use complexity-based chunking
- Isolate high-complexity functions together
- Build test cases for nested logic

### Case 3: Generic Utility Functions
**Problem**: 100 similar utility functions  
**Solution**:
- Try class/module grouping if available
- Fall back to complexity-based
- If uniform: group by functional area via naming patterns
- Example: `string_*`, `array_*`, `crypto_*`

### Case 4: God File in Functional Language
**Problem**: Go/Rust file with many package-level functions  
**Solution**:
- Check for internal structure (package hierarchy)
- Use naming patterns as hints
- Rely on complexity-based chunking
- Preserve call relationships across chunks

## Implementation Checklist

- [ ] Detect God Files (>100 functions)
- [ ] Extract function metadata (name, line, complexity, class)
- [ ] Choose best strategy
- [ ] Create chunks with meaningful names
- [ ] Preserve function-to-function calls within chunk
- [ ] Track cross-chunk calls
- [ ] Create virtual module nodes in Neo4j
- [ ] Validate no functions are lost
- [ ] Ensure reasonable chunk sizes (30-60 functions)

## Performance Targets

| Task | Target | Notes |
|------|--------|-------|
| Detect God File | <100 ms | Line counting |
| Analyze structure | <1 sec | AST parsing |
| Choose strategy | <100 ms | Decision logic |
| Create chunks | <5 sec | For 500-function file |
| Store in Neo4j | <2 sec | Batch insert |
| **Total** | **<10 sec** | For large God file |

## Testing Strategy

### Test Cases

**Test 1**: Class-based file (5 classes, 150 functions)
- Expected: 5 virtual modules, one per class
- Validation: All functions assigned, no orphans

**Test 2**: Complexity-varied file (200 functions, complexity 1-20)
- Expected: 3-4 complexity-based modules
- Validation: High-complexity functions grouped together

**Test 3**: Line-range file (200 uniform functions)
- Expected: 4 range-based modules (50 each)
- Validation: Reasonable line ranges, functions ordered

**Test 4**: Mixed file (2 classes + 30 standalone)
- Expected: 2 class modules + utilities module
- Validation: Classes separate, utilities together

**Test 5**: Circular calls (A→B→C→A)
- Expected: All functions in same chunk or marked as circular
- Validation: Relationships preserved

## Files in This Skill
- `SKILL.md` - This documentation
- `algorithms/` - Chunking implementations
- `test_data/` - Sample God files
- `validators/` - Test utilities

## Reference
- Cyclomatic Complexity: https://en.wikipedia.org/wiki/Cyclomatic_complexity
- AST Analysis: https://tree-sitter.github.io/
- Neo4j Graph Storage: https://neo4j.com/
