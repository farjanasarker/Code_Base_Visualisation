# Upload Security Validation Skill

## Overview
Expertise in validating uploaded files and preventing security vulnerabilities including zip-slip, path traversal, and resource exhaustion.

## When to Use This Skill
- Validating zip file uploads
- Preventing zip-slip attacks
- Enforcing file size limits
- Checking file extensions
- Validating folder structures
- Detecting symlinks and other security issues

## Security Vulnerabilities Prevented

### 1. Zip-Slip (Path Traversal)
**Attack**: Zip contains `../../etc/passwd`  
**Impact**: Extract files outside intended directory  
**Prevention**:
```python
# After extract, validate:
for file_path in extracted_files:
    real_path = os.path.realpath(file_path)
    base_path = os.path.realpath(extract_dir)
    
    if not real_path.startswith(base_path):
        raise SecurityError("Zip-slip detected")
```

### 2. File Size Bomb
**Attack**: Highly compressed file expands to 100GB  
**Impact**: Disk space exhaustion  
**Prevention**:
```python
# Limits:
- Max 10 MB per file
- Max 50 MB total upload
- Max 1000 files
```

### 3. Invalid File Types
**Attack**: Upload .exe renamed as .py  
**Impact**: Code execution risk  
**Prevention**:
```python
# Whitelist only:
ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.go', '.rs'}
```

### 4. Symlink Attacks
**Attack**: Symlink points to sensitive files  
**Impact**: Read sensitive data  
**Prevention**:
```python
if os.path.islink(file_path):
    raise SecurityError("Symlinks not allowed")
```

### 5. Deep Directory Traversal
**Attack**: Nested folders 100+ levels deep  
**Impact**: File system errors, DOS  
**Prevention**:
```python
# Max depth: 10 levels
```

### 6. Absolute Paths
**Attack**: Zip contains `/etc/passwd` (absolute)  
**Impact**: Extract to wrong location  
**Prevention**:
```python
# Strip leading slashes, convert to relative
```

## Validation Checklist

| Check | Severity | Action | Implementation |
|-------|----------|--------|-----------------|
| Zip-Slip | CRITICAL | BLOCK | Path validation |
| File Size | HIGH | BLOCK | Size check |
| Total Size | HIGH | BLOCK | Sum check |
| File Count | HIGH | BLOCK | Count check |
| Max Depth | MEDIUM | BLOCK | Depth check |
| Extension | MEDIUM | BLOCK | Whitelist |
| Symlinks | MEDIUM | BLOCK | Symlink test |
| Absolute Paths | LOW | WARN | Convert to relative |

## Implementation

### Upload Validation Function
```python
def validate_upload(upload_type, files, total_size, file_count, max_depth):
    """
    Returns:
      {
        "is_valid": boolean,
        "violations": [{type, severity, details}],
        "cleaned_paths": [string],
        "security_score": 0.0-1.0
      }
    """
    violations = []
    security_score = 1.0
    
    # Check file count
    if file_count > 1000:
        violations.append({
            "type": "file_count_violation",
            "severity": "error",
            "details": f"Too many files: {file_count} > 1000"
        })
    
    # Check total size
    if total_size > 50 * 1024 * 1024:  # 50 MB
        violations.append({
            "type": "size_violation",
            "severity": "error",
            "details": f"Upload too large: {total_size} bytes > 50 MB"
        })
    
    # Check depth
    if max_depth > 10:
        violations.append({
            "type": "depth_violation",
            "severity": "error",
            "details": f"Directory too deep: {max_depth} > 10 levels"
        })
    
    # Check extensions
    for file_path in files:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            violations.append({
                "type": "invalid_extension",
                "severity": "error",
                "details": f"Invalid extension: {ext}",
                "file": file_path
            })
    
    # Adjust security score based on violations
    is_valid = len([v for v in violations if v["severity"] == "error"]) == 0
    security_score = 1.0 - (len(violations) * 0.1)
    
    return {
        "is_valid": is_valid,
        "violations": violations,
        "security_score": max(0.0, security_score)
    }
```

## Zip-Slip Detection

```python
def validate_zip_extraction(zip_path, extract_dir):
    """Prevent zip-slip before extraction"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            # Check for path traversal attempts
            if name.startswith('/') or name.startswith('\\'):
                raise SecurityError(f"Absolute path in zip: {name}")
            
            if '../' in name or '..\\' in name:
                raise SecurityError(f"Zip-slip detected: {name}")
            
            # Check length
            if len(name) > 260:  # Windows path limit
                raise SecurityError(f"Path too long: {name}")
            
            # Extract safely
            member_path = os.path.normpath(os.path.join(extract_dir, name))
            real_extract = os.path.realpath(extract_dir)
            real_member = os.path.realpath(member_path)
            
            if not real_member.startswith(real_extract):
                raise SecurityError(f"Path escape detected: {name}")
```

## Rate Limiting

```python
# Per IP: 10 uploads per hour
# Per session: 5 uploads per 10 minutes
# Per file: Max 10 MB
# Per upload: Max 50 MB total
```

## Security Scoring

- **Perfect**: All checks pass → 1.0
- **Minor warnings**: Warnings but no errors → 0.9-0.95
- **Errors**: Failed critical checks → 0.0-0.5

### Examples
- Valid Python files: 1.0
- Valid Python + one absolute path: 0.9
- Oversized upload: 0.0

## Testing Strategy

### Test Cases

**Test 1**: Valid Python file
- Input: single_file.py (500 KB)
- Expected: is_valid=true, score=1.0

**Test 2**: Valid zip file
- Input: project.zip (5 MB, 50 files, 6 levels)
- Expected: is_valid=true, score=1.0

**Test 3**: Zip-slip attack
- Input: malicious.zip with `../../etc/passwd`
- Expected: is_valid=false, violation type=zip_slip

**Test 4**: File size bomb
- Input: bomb.zip (5 MB compressed → 100 MB expanded)
- Expected: Caught during validation, block before extraction

**Test 5**: Invalid extension
- Input: trojan.exe renamed as trojan.py
- Expected: is_valid=false, violation type=invalid_extension

**Test 6**: Too many files
- Input: archive.zip with 2000 Python files
- Expected: is_valid=false, violation type=file_count_violation

**Test 7**: Excessive depth
- Input: nested folders 15 levels deep
- Expected: is_valid=false, violation type=depth_violation

**Test 8**: Symlink
- Input: folder with symlink → /etc/passwd
- Expected: is_valid=false, violation type=symlink

## Compliance

- ✅ OWASP: Path Traversal prevention
- ✅ CWE-22: Improper Limitation of Pathname
- ✅ CERT Secure Coding: File Input Output

## Files in This Skill
- `SKILL.md` - This documentation
- `validators/` - Validation functions
- `security_tests/` - Test cases with attacks
- `templates/` - Implementation templates

## Reference
- OWASP: https://owasp.org/www-community/attacks/Path_Traversal
- CWE-22: https://cwe.mitre.org/data/definitions/22.html
- Zip-Slip: https://snyk.io/research/zip-slip-vulnerability/
