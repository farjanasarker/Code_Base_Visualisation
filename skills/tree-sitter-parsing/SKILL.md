# Tree-Sitter Multi-Language Parsing Skill

## Overview
Expertise in using Tree-sitter to parse code in 6 programming languages and extract functions, calls, and complexity metrics.

## When to Use This Skill
- Extracting function definitions from source files
- Analyzing function call relationships
- Calculating cyclomatic complexity
- Handling language-specific patterns (async, decorators, etc.)
- Implementing parsers for multiple languages

## Languages Supported
- Python (`.py`)
- JavaScript (`.js`)
- TypeScript (`.ts`, `.tsx`)
- Java (`.java`)
- Go (`.go`)
- Rust (`.rs`)

## Key Responsibilities
- Initialize Tree-sitter for each language
- Extract function signatures with parameters and return types
- Identify function calls within code
- Filter internal vs external calls
- Calculate McCabe's cyclomatic complexity
- Handle language-specific constructs
- De-duplicate parsed data

## Common Patterns

### Python Parsing
```python
# Extract functions, async functions, class methods
# Handle decorators (@app.route, @property, etc.)
# Extract docstrings
# Track parameters with type hints
```

### JavaScript/TypeScript Parsing
```python
# Extract function declarations, arrow functions, async functions
# Extract class methods
# Handle destructuring in parameters
# Extract async/await patterns
# Handle callbacks in nested structures
```

### Java Parsing
```python
# Extract class methods
# Handle access modifiers (public, private, protected)
# Track class hierarchies (inheritance)
# Extract interface methods
# Handle generics
```

## Output Format
All languages produce normalized output:
```json
{
  "functions": [
    {
      "id": "file:function:line",
      "name": "function_name",
      "line_start": 10,
      "line_end": 25,
      "parameters": ["param1", "param2"],
      "return_type": "string",
      "cyclomatic_complexity": 3,
      "calls": ["other_function"],
      "is_public": true
    }
  ],
  "statistics": {
    "total_functions": 5,
    "avg_complexity": 3.2,
    "max_complexity": 7
  }
}
```

## Best Practices
- Always validate Tree-sitter grammar files are loaded
- Filter external library calls
- Handle parse errors gracefully
- Cache parsed ASTs by file checksum
- De-duplicate calls per function
- Include line number ranges for UI linking

## Common Issues & Solutions

**Issue**: Missing functions  
**Solution**: Check language-specific query strings, ensure grammar is loaded

**Issue**: Incorrect complexity calculation  
**Solution**: Validate branch detection (if/else/loops), handle nested structures

**Issue**: False positive external calls  
**Solution**: Filter by defined functions in project, skip stdlib imports

**Issue**: Performance slow on large files  
**Solution**: Cache ASTs, chunk large files before parsing

## Files in This Skill
- `SKILL.md` - This documentation
- `examples/` - Code examples per language
- `templates/` - Query templates per language
- `validators/` - Test utilities

## Reference
- Tree-sitter Docs: https://tree-sitter.github.io/
- Grammar repositories: https://github.com/tree-sitter/
