# Session Management System for 500+ Concurrent Users

## Overview

This system implements **per-user session isolation** to support 500+ concurrent users without data conflicts. Each user gets a unique `session_id` that tracks their uploaded files, analysis graphs, and temporary data.

## Architecture

```
Browser Session
    ↓
sessionStorage stores UUID
    ↓
/start-session → Creates UUID + RAM entry
    ↓
All requests include X-Session-ID header
    ↓
Backend matches session_id in Neo4j & file storage
    ↓
Browser closes → beforeunload → /end-session
    ↓
Server deletes Neo4j data + uploaded files + RAM entry
```

## Key Features

### 1. **Per-User Data Isolation**
- Each user's uploaded files stored in `uploads/<session_id>/`
- All Neo4j nodes tagged with `session_id` property
- No data cross-contamination between users

### 2. **Automatic Cleanup**
- **On Browser Close**: `beforeunload` event triggers `/end-session`
- **Inactivity Timeout**: Background task cleans up sessions inactive for 3+ hours
- **Disk Cleanup**: Upload directories automatically deleted
- **Neo4j Cleanup**: All session data deleted from database

### 3. **Scale to 500+ Users**
- In-memory session tracking (dictionary)
- Neo4j queries indexed by session_id
- Background cleanup every 30 minutes
- No session data persists after cleanup

## Backend Implementation

### Session Endpoints

```python
POST /start-session
  → Returns: {"session_id": "uuid-123"}
  → Called: On page load (app initialization)
  → Stores: Active session metadata in RAM

DELETE /end-session
  → Header: X-Session-ID
  → Deletes: Neo4j data + uploads + RAM entry
  → Called: beforeunload event

GET /sessions/info
  → Returns: Current session metadata
  → For debugging/monitoring

GET /admin/sessions
  → Returns: All active sessions (admin endpoint)
```

### Updated Database Queries

**All Neo4j queries now include `session_id` filter:**

```cypher
// Before
MATCH (fn:Function {name: $name})-[:CALLS]->(b)
RETURN b.name AS name

// After (Session-isolated)
MATCH (fn:Function {name: $name, session_id: $session_id})-[:CALLS]->(b)
RETURN b.name AS name
```

### Upload Tracking

```python
@app.post("/upload")
async def upload(request: Request, file: UploadFile):
    # Get session from header
    session_id = request.headers.get("X-Session-ID")
    
    # Validate session exists
    if session_id not in active_sessions:
        raise HTTPException(404, "Session not found")
    
    # Store file in session directory
    session_dir = f"uploads/{session_id}"
    
    # Parse and store with session_id
    store_all(functions, session_id)
    
    # Track in active_sessions[session_id]["files"]
```

### Background Cleanup Task

```python
async def cleanup_orphan_sessions():
    while True:
        await asyncio.sleep(1800)  # Every 30 minutes
        
        for session_id, data in active_sessions.items():
            if datetime.now() - data["last_active"] > SESSION_TIMEOUT:
                # Delete from Neo4j
                delete_session_data(session_id)
                
                # Delete from disk
                shutil.rmtree(f"uploads/{session_id}")
                
                # Delete from RAM
                active_sessions.pop(session_id)
```

## Frontend Implementation

### Session Manager (`sessionManager.js`)

```javascript
sessionManager.init()
  → Checks sessionStorage for existing session_id
  → If not found: calls /start-session
  → Stores in sessionStorage (auto-cleared on close)

sessionManager.apiCall(endpoint, options)
  → All API calls go through this
  → Automatically adds X-Session-ID header
  → Handles errors and session expiration

sessionManager.endSession()
  → Called on beforeunload
  → Uses navigator.sendBeacon() for reliability
  → Clears local sessionStorage
```

### App Initialization

```javascript
// main.js
async function initializeApp() {
  // 1. Initialize session
  const sessionId = await sessionManager.init();
  
  // 2. Setup cleanup
  setupCleanup();
  
  // 3. Provide to components
  app.provide('sessionManager', sessionManager);
  
  // 4. Mount Vue app
  app.mount('#app');
}
```

### Using Session Manager in Components

```vue
<script>
import { inject } from 'vue';

export default {
  setup() {
    const sessionManager = inject('sessionManager');
    
    const uploadFile = async (file) => {
      const result = await sessionManager.uploadFile(file);
      console.log('Session:', result.session_id);
    };
    
    const fetchGraph = async () => {
      const graph = await sessionManager.fetchTier1();
    };
    
    return { uploadFile, fetchGraph };
  }
}
</script>
```

## Request/Response Flow

### 1. User Opens Browser
```
Browser loads → main.js runs → sessionManager.init()
  ↓
/start-session → Backend creates UUID + RAM entry
  ↓
Returns: {"session_id": "abc123"}
  ↓
sessionStorage.setItem('bmad_session_id', 'abc123')
```

### 2. User Uploads File
```
POST /upload
  Headers: {"X-Session-ID": "abc123"}
  Body: multipart/form-data
  ↓
Backend validates session exists
  ↓
Saves to: uploads/abc123/<filename>
  ↓
Parses → store_all(functions, "abc123")
  ↓
Neo4j: {session_id: "abc123"} tagged on all nodes
  ↓
Response: {"session_id": "abc123", "tier1_graph": {...}}
```

### 3. User Closes Browser
```
beforeunload event fires
  ↓
navigator.sendBeacon('/end-session', {'session_id': 'abc123'})
  ↓
Backend end_session_cleanup('abc123')
  ↓
Steps:
  1. Delete from Neo4j: MATCH (n {session_id: 'abc123'}) DETACH DELETE n
  2. Delete uploads: rm -rf uploads/abc123
  3. Remove from RAM: active_sessions.pop('abc123')
  ↓
sessionStorage auto-clears on browser close
```

## Data Management

### Session Timeout (3 hours)
```python
SESSION_TIMEOUT = timedelta(hours=3)

# Checking activity
inactivity = now - session_data["last_active"]
if inactivity > SESSION_TIMEOUT:
    # Clean up
```

### Max Upload Size
```python
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB per user
MAX_FILE_COUNT = 1000              # 1000 files per upload
```

### Directory Structure
```
uploads/
  └── abc123-uuid/
      ├── main.py
      ├── utils/
      │   └── helpers.py
      └── config.json
  └── xyz789-uuid/
      └── ...
```

## Monitoring & Admin

### Check Active Sessions
```bash
curl http://localhost:8000/admin/sessions
```

Response:
```json
{
  "status": "success",
  "total_sessions": 487,
  "sessions": [
    {
      "session_id": "abc123",
      "created_at": "2026-05-02T10:30:00",
      "inactivity_minutes": 15,
      "files_count": 5
    }
  ]
}
```

### Get Session Info
```bash
curl -H "X-Session-ID: abc123" http://localhost:8000/sessions/info
```

Response:
```json
{
  "session_id": "abc123",
  "created_at": "2026-05-02T10:30:00",
  "last_active": "2026-05-02T10:45:00",
  "inactivity_minutes": 3,
  "files": ["main.py", "utils/helpers.py"],
  "upload_dir": "uploads/abc123"
}
```

## Error Handling

### Missing Session Header
```
Request: GET /graph/tier1 (no X-Session-ID header)
Response: 401 Unauthorized
{
  "detail": "Missing X-Session-ID header"
}
```

### Invalid Session
```
Request: GET /graph/tier1 (X-Session-ID: invalid)
Response: 404 Not Found
{
  "detail": "Session not found: invalid"
}
```

### Session Expired
```
Request: GET /graph/tier1 (X-Session-ID: expired-session)
Response: 404 Not Found + Frontend clears sessionStorage
Frontend: Shows "Session expired. Please refresh the page."
```

## Security Considerations

### 1. **No Session Leakage**
- UUIDs are cryptographically random
- Session IDs never logged or exposed
- Each session isolated in database

### 2. **No Data Persistence**
- All uploads deleted on session end
- No backup of user code
- No logs containing user data

### 3. **Zip Slip Prevention**
- Path validation: `if not str(member_path).startswith(str(extract_root))`
- No path traversal attacks
- Safe extraction to session directory

### 4. **File Size Limits**
- Max 50MB total upload
- Max 500KB per file
- Max 1000 files per upload

## Performance Optimization

### 1. **Per-Session Cache**
```python
SESSION_CACHE[session_id] = {
    "functions": [...],
    "tier1": {...}
}
```
- Reduces Neo4j load
- Faster fallback on DB failure

### 2. **Async Session Cleanup**
- Background task doesn't block requests
- 30-minute intervals (configurable)
- Scales linearly with user count

### 3. **Indexed Neo4j Queries**
```cypher
MATCH (n:Function {session_id: $session_id, name: $name})
```
- Index on `{session_id, name}` for fast lookups
- Separate indexes per session namespace

## Testing the System

### 1. Test Single User Workflow
```bash
# Start app
npm run dev

# Check session created
sessionStorage.getItem('bmad_session_id')

# Upload file
POST /upload with X-Session-ID header

# Verify Neo4j isolation
```

### 2. Test Multi-User (Simulate 500 users)
```python
# Script to simulate 500 concurrent sessions
import asyncio
import aiohttp

async def simulate_user(session_id):
    async with aiohttp.ClientSession() as session:
        # Upload file
        # Fetch graphs
        # Check isolation
        pass

# Run 500 concurrent tasks
```

### 3. Test Session Cleanup
```bash
# Let browser idle for 3+ hours
# Verify session auto-deleted from Neo4j + disk
```

## Troubleshooting

### Issue: "Session not found" error
**Cause**: Session expired or browser was closed
**Fix**: Reload page → new session created

### Issue: Duplicate data in Neo4j
**Cause**: Session ID not properly filtered in queries
**Fix**: Check all queries include `{session_id: $session_id}` filter

### Issue: Disk space grows indefinitely
**Cause**: Cleanup task not running
**Fix**: Check background task in logs, restart server

### Issue: 500+ users causes slowdown
**Cause**: Large active_sessions dictionary
**Fix**: Reduce SESSION_TIMEOUT, run cleanup more frequently

---

## Future Enhancements

1. **Persistent Sessions**: Add database persistence for session metadata
2. **Session Sharing**: Allow users to share graph URLs with expiring links
3. **Multi-Device Support**: Sync sessions across browser tabs
4. **Export**: Allow users to export their analysis before session ends
5. **Analytics**: Track session duration, file sizes, graph complexity

---

**Last Updated**: May 2, 2026
**Version**: 1.0
