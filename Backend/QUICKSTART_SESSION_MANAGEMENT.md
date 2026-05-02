# Session Management - Quick Start Guide

## For Backend Developers

### 1. Starting the Server with Session Management

```bash
# Backend
cd Backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
🚀 Backend startup - creating cleanup task
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Testing Session Endpoints

#### Create a Session
```bash
curl -X POST http://localhost:8000/start-session
```

**Response:**
```json
{
  "status": "success",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Session created",
  "expires_in_hours": 3.0
}
```

#### Get Session Info
```bash
curl -H "X-Session-ID: 550e8400-e29b-41d4-a716-446655440000" \
  http://localhost:8000/sessions/info
```

#### End Session
```bash
curl -X DELETE \
  -H "X-Session-ID: 550e8400-e29b-41d4-a716-446655440000" \
  http://localhost:8000/end-session
```

#### List All Active Sessions (Admin)
```bash
curl http://localhost:8000/admin/sessions
```

### 3. Uploading Files with Session

```bash
SESSION_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X POST \
  -H "X-Session-ID: $SESSION_ID" \
  -F "file=@mycode.zip" \
  http://localhost:8000/upload
```

**Response includes session_id:**
```json
{
  "message": "Graph generated",
  "status": "success",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "tier1_graph": { ... },
  "total_functions": 245,
  "total_files": 12
}
```

---

## For Frontend Developers

### 1. Starting the Frontend with Session Manager

```bash
# Frontend
cd Frontend
npm install
npm run dev
```

**Expected Output:**
```
🚀 Initializing app...
✅ New session created: 550e8400-e29b-41d4-a716-446655440000
📍 Session ID: 550e8400-e29b-41d4-a716-446655440000
✅ App mounted successfully
```

### 2. Using Session Manager in Components

```vue
<script setup>
import { inject, ref } from 'vue';

const sessionManager = inject('sessionManager');
const loading = ref(false);

async function handleFileUpload(file) {
  loading.value = true;
  try {
    const result = await sessionManager.uploadFile(file);
    console.log('Upload successful:', result);
  } catch (error) {
    console.error('Upload failed:', error);
  } finally {
    loading.value = false;
  }
}

async function loadGraph() {
  try {
    const tier1 = await sessionManager.fetchTier1();
    console.log('Tier1 graph:', tier1);
  } catch (error) {
    console.error('Failed to fetch graph:', error);
  }
}
</script>
```

### 3. Accessing Session ID

```javascript
// In any component
const sessionId = sessionManager.getSessionId();
console.log('Current session:', sessionId);
```

### 4. Manual Session Cleanup

```javascript
// End session manually (usually not needed - automatic on close)
await sessionManager.endSession();
```

---

## Verification Checklist

### Backend Verification

- [ ] Session created with UUID
- [ ] Active sessions tracked in RAM
- [ ] Session directory created: `uploads/<session_id>/`
- [ ] File uploaded to session directory
- [ ] Neo4j nodes tagged with `session_id`
- [ ] Queries filter by `session_id`
- [ ] Session info endpoint works
- [ ] Admin sessions endpoint works
- [ ] Session cleanup on `/end-session` works
- [ ] Background cleanup task running
- [ ] Neo4j data deleted after timeout
- [ ] Upload directory deleted after timeout

### Frontend Verification

- [ ] Session ID created on app init
- [ ] Session stored in sessionStorage
- [ ] X-Session-ID header added to all requests
- [ ] Session restored on page refresh
- [ ] File upload succeeds with session ID
- [ ] Graph fetching works with session ID
- [ ] beforeunload sends session ID
- [ ] Error handling for expired sessions
- [ ] Logging shows session lifecycle

### Integration Verification

- [ ] Backend + Frontend both running
- [ ] Upload file succeeds
- [ ] Can fetch tier1/tier2/tier3 graphs
- [ ] Data isolated per session
- [ ] Close browser → session cleanup
- [ ] Open new tab → new session
- [ ] Two sessions have different UUIDs

---

## Example Multi-User Test

### Simulate 3 Concurrent Users

**Terminal 1 - Backend:**
```bash
cd Backend
python -m uvicorn main:app --reload
```

**Terminal 2 - Frontend (User 1):**
```bash
cd Frontend
npm run dev -- --port 5173
```

**Terminal 3 - Frontend (User 2):**
```bash
cd Frontend
npm run dev -- --port 5174
```

**Terminal 4 - Test Script:**
```bash
#!/bin/bash

# User 1 - Create session & upload
curl -X POST http://localhost:8000/start-session
# Copy session_id from response

SESSION1="<session_id_from_above>"

curl -X POST \
  -H "X-Session-ID: $SESSION1" \
  -F "file=@code1.zip" \
  http://localhost:8000/upload

# User 2 - Create session & upload
SESSION2=$(curl -s -X POST http://localhost:8000/start-session | jq -r '.session_id')

curl -X POST \
  -H "X-Session-ID: $SESSION2" \
  -F "file=@code2.zip" \
  http://localhost:8000/upload

# Verify sessions isolated
curl -H "X-Session-ID: $SESSION1" http://localhost:8000/sessions/info
curl -H "X-Session-ID: $SESSION2" http://localhost:8000/sessions/info

# Admin: List all sessions
curl http://localhost:8000/admin/sessions
```

---

## Troubleshooting

### Problem: "Missing X-Session-ID header"

**Cause**: Frontend not sending session ID

**Solution**:
```javascript
// Check if sessionManager is initialized
console.log(sessionManager.getSessionId());

// If null, session not initialized
// Make sure sessionManager.init() was called
```

### Problem: "Session not found" (404)

**Cause**: Session expired or doesn't exist

**Solution**:
```javascript
// Create new session
await sessionManager.init();

// Then retry request
```

### Problem: Neo4j queries return empty results

**Cause**: Session ID not in query filter

**Check**: Ensure all queries have `{session_id: $session_id}` filter

### Problem: Uploads not appearing in directory

**Cause**: Wrong session directory

**Check**:
```bash
ls -la uploads/
# Should see directories like: 550e8400-e29b-41d4-a716-446655440000/
```

### Problem: Background cleanup not running

**Cause**: App not started or task crashed

**Check logs**:
```
grep "cleanup" server.log
# Should see cleanup messages every 30 minutes
```

---

## Performance Notes

- **RAM Usage**: ~1KB per active session
  - 500 sessions = ~500KB (negligible)
  
- **Neo4j Performance**: O(1) with `{session_id: $session_id}` index
  - 500 sessions = no performance degradation
  
- **Disk Usage**: Scales with code size
  - Average repo: 1-50MB
  - Cleanup keeps total size bounded
  
- **Cleanup Frequency**: 30 minutes (configurable)
  - Can reduce to 10 minutes for faster cleanup
  - Trade-off: more CPU vs faster recovery

---

## Next Steps

1. **Scale Testing**: Run with 100+ concurrent sessions
2. **Performance Profiling**: Monitor Neo4j query times
3. **Persistence**: Add Redis for session metadata (optional)
4. **Monitoring**: Add Prometheus metrics for sessions
5. **Documentation**: Update API docs with session requirements

---

**Contact**: Backend Team
**Last Updated**: May 2, 2026
