# Session Management - Visual Diagrams

## 1. Session Lifecycle Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER OPENS                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Frontend: main.js loads → sessionManager.init()                 │
│  • Check sessionStorage['bmad_session_id']                      │
│  • If not found: POST /start-session                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Backend: POST /start-session                                    │
│  • session_id = uuid.uuid4() → "abc123"                         │
│  • mkdir -p uploads/abc123                                      │
│  • active_sessions["abc123"] = {created_at, files, ...}         │
│  • Return: {session_id: "abc123"}                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Frontend: Store in sessionStorage                               │
│  • sessionStorage.setItem('bmad_session_id', 'abc123')          │
│  • Setup beforeunload listener                                  │
│  • Mount Vue app with sessionManager provided                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
            ┌────────────────┴────────────────┐
            ↓                                  ↓
   ┌──────────────────────┐      ┌───────────────────────┐
   │   USER ACTIVE       │      │  IDLE (NO ACTIVITY)  │
   │  (Using app)        │      │  (3+ hours)          │
   │  • Upload files     │      │                       │
   │  • Click expand     │      │ Background cleanup    │
   │  • Fetch graphs     │      │ task (every 30 min)   │
   │                     │      │  • Check inactivity   │
   │ Update              │      │  • End session        │
   │ last_active → now   │      │  • Delete data        │
   └──────────────────────┘      └───────────────────────┘
            ↓                                  ↓
   ┌──────────────────────┐      ┌───────────────────────┐
   │  BROWSER CLOSE      │      │  ORPHAN CLEANUP     │
   │  (User action)      │      │  (Automatic)        │
   │                     │      │                     │
   │ beforeunload fires  │      │ end_session_cleanup │
   │ navigator.sendBeacon│      │  • Del Neo4j        │
   │  /end-session       │      │  • Del uploads/     │
   └──────────────────────┘      │  • Pop active_sess  │
            ↓                     │  • Clear cache      │
   ┌──────────────────────┐      └───────────────────────┘
   │   END SESSION       │                    ↓
   │  CLEANUP            │      ┌───────────────────────┐
   │                     │      │   DATA GONE ✓        │
   │ Backend:            │      │                       │
   │  • Del Neo4j nodes  │      │ • Neo4j: deleted     │
   │  • Del uploads/abc  │      │ • Disk: deleted      │
   │  • Pop from RAM     │      │ • RAM: deleted       │
   │                     │      │ • Cache: deleted     │
   │ Frontend:           │      └───────────────────────┘
   │  • sessionStorage   │
   │    auto-clear       │
   └──────────────────────┘
            ↓
   ┌──────────────────────┐
   │   DATA GONE ✓       │
   │                     │
   │ • Neo4j: deleted   │
   │ • Disk: deleted    │
   │ • RAM: deleted     │
   │ • Cache: deleted   │
   └──────────────────────┘
```

---

## 2. Request/Response Flow with Session ID

```
FRONTEND                          BACKEND                       NEO4J
   ↓                                 ↓                            ↓
   │ GET /graph/tier1                │                            │
   ├─Header: X-Session-ID: abc123───→│                            │
   │                                 │                            │
   │                    validate_session("abc123")                │
   │                         ✓ valid │                            │
   │                                 │                            │
   │                    update_session_activity()                 │
   │                    active_sessions["abc123"]["last_active"]= │
   │                    datetime.now()                            │
   │                                 │                            │
   │                    get_tier1("abc123")                      │
   │                                 ├─────MATCH (mod:Module     │
   │                                 │ {session_id: "abc123"})───→│
   │                                 │                            │
   │                                 │←──── Returns nodes/edges──┤
   │←────Response: {nodes, edges}────┤                            │
   │ + session_id in body             │                            │
   │                                 │                            │
```

---

## 3. Multi-User Data Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                    SHARED NEO4J DATABASE                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User A (session_id: abc123)          User B (session_id: xyz789)
│  ┌──────────────────────────┐        ┌──────────────────────────┐
│  │ Module                   │        │ Module                   │
│  │ {name: "utils"           │        │ {name: "models"          │
│  │  session_id: "abc123"}   │        │  session_id: "xyz789"}   │
│  │        ↑                 │        │        ↑                 │
│  │        │                 │        │        │                 │
│  │  File                    │        │  File                    │
│  │  {path: "utils.py"       │        │  {path: "models.py"      │
│  │   session_id: "abc123"}  │        │   session_id: "xyz789"}  │
│  │        ↑                 │        │        ↑                 │
│  │        │                 │        │        │                 │
│  │  Function                │        │  Function                │
│  │  {name: "parse"          │        │  {name: "train"          │
│  │   session_id: "abc123"}──┤        │   session_id: "xyz789"}──┤
│  │        ↑                 │        │        ↑                 │
│  │        │ CALLS           │        │        │ CALLS           │
│  │  Function                │        │  Function                │
│  │  {name: "validate"       │        │  {name: "predict"       │
│  │   session_id: "abc123"}  │        │   session_id: "xyz789"}  │
│  └──────────────────────────┘        └──────────────────────────┘
│                                                             │
│  Query for User A:                                          │
│  MATCH (mod:Module {name: "utils", session_id: "abc123"})   │
│  → Only returns User A's utils module                       │
│                                                             │
│  Query for User B:                                          │
│  MATCH (mod:Module {name: "models", session_id: "xyz789"})  │
│  → Only returns User B's models module                      │
│                                                             │
│  ✓ No cross-contamination!                                  │
│  ✓ Each user isolated!                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. File Storage Isolation

```
DISK STORAGE
│
└── uploads/
    │
    ├── abc123-user-A/          ← User A's uploads
    │   ├── src/
    │   │   ├── main.py
    │   │   ├── utils.py
    │   │   └── models/
    │   │       └── net.py
    │   └── config.json
    │
    ├── xyz789-user-B/          ← User B's uploads
    │   ├── backend/
    │   │   ├── api.py
    │   │   └── db.py
    │   └── requirements.txt
    │
    └── def456-user-C/          ← User C's uploads
        ├── frontend/
        │   ├── App.vue
        │   └── components/
        └── package.json

When user A uploads: files → uploads/abc123/
When user B uploads: files → uploads/xyz789/
When user A closes: rm -rf uploads/abc123/
When user B closes: rm -rf uploads/xyz789/

No file overlap. Complete isolation.
```

---

## 5. Backend Session Tracking

```
ACTIVE SESSIONS (In-Memory Dictionary)
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  active_sessions = {                                        │
│    "abc123": {                                              │
│      "created_at": <datetime>,                              │
│      "last_active": <datetime>,                             │
│      "files": ["main.py", "utils.py"],                      │
│      "upload_dir": "uploads/abc123"                         │
│    },                                                       │
│    "xyz789": {                                              │
│      "created_at": <datetime>,                              │
│      "last_active": <datetime>,                             │
│      "files": ["api.py", "db.py"],                          │
│      "upload_dir": "uploads/xyz789"                         │
│    },                                                       │
│    "def456": {                                              │
│      "created_at": <datetime>,                              │
│      "last_active": <datetime>,                             │
│      "files": ["App.vue"],                                  │
│      "upload_dir": "uploads/def456"                         │
│    }                                                        │
│  }                                                          │
│                                                             │
│  MEMORY USAGE: ~1 KB per session                            │
│  500 users = ~500 KB (negligible)                           │
│                                                             │
│  LOOKUP: O(1) dictionary access                             │
│  500 users = no performance impact                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Cleanup Timeline

```
TIME                          EVENT                        ACTION
────────────────────────────────────────────────────────────────
12:00 PM  User A opens browser   POST /start-session       ✅ Session abc123 created

12:10 PM  User A uploads code    POST /upload              ✅ Files stored in uploads/abc123

12:15 PM  User A uses app        GET /graph/tier1          ✅ last_active updated

12:20 PM  User A closes browser  beforeunload              🗑️ CLEANUP IMMEDIATE
                                                           • Delete Neo4j
                                                           • Delete uploads/abc123
                                                           • Pop from active_sessions
                                                           ✅ 100% gone


TIME                          EVENT                        ACTION
────────────────────────────────────────────────────────────────
01:00 PM  User B opens browser   POST /start-session       ✅ Session xyz789 created

01:05 PM  User B uploads code    POST /upload              ✅ Files stored in uploads/xyz789

01:10 PM  User B AFK (idle)      No activity               ⏰ last_active = 01:10 PM


02:00 PM  Background task runs   cleanup_orphan_sessions() ⏱️ Check inactivity
          (Every 30 min)                                   (50 minutes idle - OK)


05:10 PM  Background task runs   cleanup_orphan_sessions() ⏱️ Check inactivity
          (Every 30 min)                                   (4 hours > 3 hour timeout)
                                                           🗑️ CLEANUP AUTOMATIC
                                                           • Delete Neo4j
                                                           • Delete uploads/xyz789
                                                           • Pop from active_sessions
                                                           ✅ 100% gone
```

---

## 7. Error Handling Flow

```
REQUEST ARRIVES
      ↓
┌─────────────────────────────────────────┐
│ Check for X-Session-ID header           │
└─────────────────────────────────────────┘
      ↓
    Is header present?
   /                \
NO                  YES
│                    │
└──→ ❌ 401          └──→ ┌──────────────────────┐
     "Missing              │ Check if session     │
     X-Session-ID         │ in active_sessions   │
     header"              └──────────────────────┘
                                 ↓
                            Is session valid?
                           /              \
                        NO                YES
                        │                 │
                   └──→ ❌ 404             └──→ ✅ Process request
                        "Session           │ (update last_active)
                        not found:         │ (execute query)
                        {id}"              │ (return response)
                                          └──→ 200 OK
```

---

## 8. Scaling to 500+ Users

```
CONCURRENT USERS: 500

┌────────────────────────────────────────────────────────────┐
│ FASTAPI WORKERS                                            │
│  • Can handle 1000s of concurrent requests                │
│  • Each request processed in separate async task           │
│  • No blocking on session lookup                           │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ SESSION VALIDATION: O(1)                                   │
│  • active_sessions.get(session_id) → <1μs                 │
│  • 500 users: 500 lookups = 500μs (negligible)            │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ NEO4J QUERY: O(1) with {session_id} index                 │
│  • MATCH (n {session_id: $id}) → indexed lookup           │
│  • 500 users: 500 queries = ~500ms (on SSD)               │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ DISK I/O: Bounded                                          │
│  • Each user: max 50MB (MAX_UPLOAD_SIZE)                  │
│  • 500 users: 25GB max (temporary, gets cleaned up)       │
│  • Storage keeps files only during session                │
└────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────┐
│ MEMORY: Negligible                                         │
│  • Per session: ~1KB metadata                             │
│  • 500 sessions: ~500KB (negligible)                      │
└────────────────────────────────────────────────────────────┘
                           ↓
           ✅ Scales linearly to 500+ users
```

---

## 9. Request Sequence Diagram

```
User                Frontend                Backend              Neo4j
 │                     │                       │                  │
 │ Opens Browser       │                       │                  │
 ├────────────────────→│                       │                  │
 │                     │ POST /start-session   │                  │
 │                     ├──────────────────────→│                  │
 │                     │                       │ create UUID      │
 │                     │                       │ mkdir uploads/   │
 │                     │                       │                  │
 │                     │ {session_id: abc123}  │                  │
 │                     │←──────────────────────┤                  │
 │ sessionStorage set  │                       │                  │
 ├────────────────────→│                       │                  │
 │                     │ App mounted ✓         │                  │
 │ Selects file        │                       │                  │
 ├────────────────────→│                       │                  │
 │                     │ POST /upload          │                  │
 │                     │ X-Session-ID: abc123  │                  │
 │                     ├──────────────────────→│                  │
 │                     │                       │ Parse code       │
 │                     │                       │ store_all()      │
 │                     │                       │ ┌───────────────→│
 │                     │                       │ │ Create nodes   │
 │                     │                       │ │ {session_id}   │
 │                     │                       │←┘────────────────┤
 │                     │ {tier1_graph}         │                  │
 │                     │←──────────────────────┤                  │
 │ Graph renders ✓     │                       │                  │
 │ Clicks expand       │                       │                  │
 ├────────────────────→│                       │                  │
 │                     │ GET /graph/tier2      │                  │
 │                     │ X-Session-ID: abc123  │                  │
 │                     ├──────────────────────→│                  │
 │                     │                       │ ┌───────────────→│
 │                     │                       │ │ MATCH {session}│
 │                     │                       │←┘────────────────┤
 │                     │ {tier2_graph}         │                  │
 │                     │←──────────────────────┤                  │
 │ Zooms in ✓          │                       │                  │
 │ Closes browser      │                       │                  │
 │ beforeunload event  │                       │                  │
 ├────────────────────→│ DELETE /end-session   │                  │
 │                     │ (sendBeacon)          │                  │
 │                     ├──────────────────────→│                  │
 │                     │                       │ delete_session() │
 │                     │                       │ ┌───────────────→│
 │                     │                       │ │ DETACH DELETE  │
 │                     │                       │←┘────────────────┤
 │ sessionStorage      │                       │                  │
 │ auto-clear          │ {status: success}     │                  │
 ├────────────────────→│←──────────────────────┤                  │
 │                     │                       │                  │
```

---

**All diagrams show complete isolation between users with automatic cleanup!**
