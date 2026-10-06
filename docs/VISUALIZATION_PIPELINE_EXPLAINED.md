# Visualization Pipeline — Tier1 / Tier2 / Tier3(/4) কীভাবে কাজ করে

এই ডকুমেন্টে ব্যাখ্যা করা হয়েছে আপলোড করা কোড থেকে কীভাবে **multi-tier graph**
বের হয়, Neo4j (graph database)-এ কীভাবে রাখা হয়, আর frontend কীভাবে ধাপে ধাপে
(drill-down) সেটা visualize করে।

> Source ফাইল: `Backend/analyzer/pipeline.py`, `Backend/analyzer/graph_builder.py`,
> `Backend/analyzer/chunking.py`, `Backend/db.py`, `Backend/main.py`,
> `Frontend/src/components/GraphView.vue`

---

## ১. বড় ছবি — পুরো ফ্লো

```
Upload (file/zip/folder)
        │
        ▼
analyzer.analyze_files()        ← parse (tree-sitter/regex) + metrics + layer violations
        │
        ▼
build_module_graph(functions)   ← in-memory Tier-1 (module-level) গ্রাফ তৈরি (তাৎক্ষণিক)
        │                            + decide_render_strategy() (কতটা দেখানো হবে)
        ├──────────────► response এ tier1_graph সাথে সাথে ফেরত যায় (Neo4j-এর জন্য অপেক্ষা করে না)
        │
        ▼
store_all(functions, session_id) ← same ডেটা Neo4j-তে persist হয় (best-effort, non-blocking)
        │                            Module/File/Function/Chunk নোড + সম্পর্ক তৈরি হয়
        ▼
Neo4j (Aura, cloud-hosted)  ── session_id দিয়ে প্রতিটা ইউজারের ডেটা আলাদা (multi-tenant)
        │
        ▼
Frontend (Vue Flow) — ইউজার একটা module/file node এ ক্লিক করলে তখনই
GET /graph/tier2/{module}  বা  GET /graph/tier3?file_path=...  কল হয়ে
Neo4j থেকে পরের লেভেলের সাব-গ্রাফ আনা হয় (lazy / on-demand drill-down)
```

**মূল নীতি:** পুরো কোডবেজের পুরো গ্রাফ একসাথে কখনোই frontend-এ পাঠানো হয় না।
শুধু Tier-1 (module সামারি) সাথে সাথে দেখানো হয়; এর নিচের লেভেল
(file → function → chunk-internal function) ইউজার যখন সেই node-এ ক্লিক/ডাবল-ক্লিক
করে, তখনই আলাদা API কল দিয়ে আনা হয়। এভাবে বড় কোডবেজেও প্রথম রেসপন্স দ্রুত আসে।

---

## ২. Tier-1 (Module Level) — কীভাবে তৈরি হয়

**ফাইল:** `graph_builder.py` (`build_module_graph`)

Parse করা প্রতিটা function-এর `module` ফিল্ড (ফাইলের path-এর প্রথম folder,
বা module structure detection থেকে পাওয়া) অনুযায়ী গ্রুপ করা হয় —

- **Node** = একটা module/top-level folder; তার সাথে `loc` (মোট লাইন), `fn_count`
  (মোট function সংখ্যা), `languages` (কোন কোন ভাষায় কোড আছে) যোগ করা হয়।
- **Edge** = দুইটা module-এর মধ্যে কল সম্পর্ক — module A-এর কোনো function যদি
  module B-এর কোনো function-কে call করে, তাহলে A→B edge টানা হয়, আর কতবার call
  হচ্ছে সেটা `call_count` হিসেবে গোনা হয় (একাধিক function-call-এর সংখ্যা যোগ হয়ে)।
- এই graph টা **সম্পূর্ণ in-memory Python dict দিয়ে** বানানো হয় — তখনো Neo4j
  স্পর্শ করা হয় না, তাই এটা তাৎক্ষণিক (fast path)।

### Render Strategy — কতগুলো node দেখানো হবে

**ফাইল:** `chunking.py` (`decide_render_strategy`)

Tier-1 এর node সংখ্যা (কতগুলো module আছে) দেখে ৩ ধরনের strategy ঠিক হয়:

| Node সংখ্যা | Strategy | কী হয় |
|---|---|---|
| < 100 | `show_all` | সব node/edge সরাসরি দেখানো হয় |
| 100–500 | `make_group` | কম-গুরুত্বপূর্ণ node গুলোকে collapse করে group-summary node বানানো হয় |
| > 500 | `search_only` | fan-in+fan-out দিয়ে সবচেয়ে গুরুত্বপূর্ণ ১০০টা node দেখানো হয়, বাকিগুলো search করে খুঁজে বের করতে হয় (`filter_top_nodes`) |

এই strategy-টা শুধু একটা **decision hint** ফ্রন্টএন্ডকে পাঠানো হয় — actual
filtering/grouপing মূলত ফ্রন্টএন্ড-সাইডে করা হয় এই hint অনুসরণ করে।

---

## ৩. Neo4j-তে Persist করা (`db.py: store_all`)

Tier-1 রেসপন্স পাঠানোর **পরে** (parallel/best-effort, response block করে না)
পুরো parsed ডেটা Neo4j-তে লেখা হয় Cypher `MERGE` কুয়েরি দিয়ে। এই ধাপে ব্যর্থ হলেও
আপলোড রেসপন্স fail করে না — শুধু log হয় (`store_all` একটা try/except এ wrap করা)।

### Node টাইপ:
- **Module** — top-level folder
- **File** — প্রতিটা সোর্স ফাইল, `path`, `language` property সহ
- **Function** — প্রতিটা function/method, `complexity`, `fan_in`, `fan_out`,
  `line_start/end`, `virtual_module` property সহ
- **Chunk** — যেসব "God File" (অতিরিক্ত বড় ফাইল) কে ছোট ছোট virtual module-এ
  ভাগ করা হয়েছে, তাদের প্রতিটা ভাগ একটা আলাদা Chunk node

### Relationship টাইপ:
- `(File)-[:BELONGS_TO]->(Module)`
- `(Function)-[:DEFINED_IN]->(File)`  অথবা chunked হলে ফাংশনটা chunk এর অংশ
- `(Function)-[:CALLS]->(Function)` — কল গ্রাফ, সব node-এর মূল ভিত্তি
- `(Chunk)-[:IN_FILE]->(File)` এবং `(Function)-[:PART_OF]->(Chunk)`

### Multi-tenant Isolation — `session_id`
প্রতিটা node-এ একটা `session_id` property থাকে, আর প্রতিটা Cypher query
`WHERE ... session_id: $session_id` দিয়ে filter করে। ফলে একই Neo4j ডেটাবেজে
হাজারো ইউজারের ডেটা মিশে থাকলেও, প্রতিটা ইউজার শুধু **নিজের সেশনের** গ্রাফ
দেখে। সেশন শেষ হলে (`delete_session_data`) সেই session_id-এর সব node/edge
`DETACH DELETE` দিয়ে মুছে ফেলা হয়।

### Monorepo (Multi-service) হলে
প্রতিটা service bucket আলাদাভাবে `store_all(..., service_id=svc_id)` দিয়ে
persist হয় — প্রতিটা Module/File node-এ একটা `service` property যোগ হয়, যাতে
পরে querying-এর সময় একটা নির্দিষ্ট service-এর গ্রাফ আলাদা করে বের করা যায়।

---

## ৪. Tier-2 (File Level) — Drill-down

**Trigger:** ইউজার একটা module node-এ ক্লিক করলে `GET /graph/tier2/{module_name}`
কল হয় (`GraphView.vue`)।

**ফাইল:** `db.py: get_tier2`

Neo4j-তে সরাসরি Cypher কুয়েরি চলে (in-memory কিছু ব্যবহার হয় না) —
1. সেই module-এর সব File node বের করা হয় (`BELONGS_TO`)
2. একই module-এর দুইটা ভিন্ন ফাইলের মধ্যে function-call আছে কিনা দেখা হয়
   (cross-file calls within module) — সেগুলোই edge
3. যেসব ফাইলে কোনো cross-file call নেই (isolated file) তাদেরও node হিসেবে
   অন্তর্ভুক্ত করা হয়, যাতে module-এর সব ফাইল দেখা যায়

ফলাফল: সেই module-এর ভেতরের ফাইলগুলো নোড, আর ফাইল-টু-ফাইল কল-নির্ভরতা edge।

---

## ৫. Tier-3 (Function Level, বা Chunk Level) — আরেক ধাপ Drill-down

**Trigger:** ইউজার একটা file node-এ ক্লিক করলে `GET /graph/tier3?file_path=...`
কল হয়।

**ফাইল:** `db.py: get_tier3`

এখানে একটা branching logic আছে:

- **যদি ফাইলটা "God File" হিসেবে chunk করা হয়ে থাকে** (একাধিক Chunk node
  `IN_FILE` দিয়ে সেই File-এর সাথে যুক্ত আছে) → **Chunk-level graph** রিটার্ন
  হয়: node = প্রতিটা virtual chunk (যেমন `AuthModule_1`), edge = দুই chunk-এর
  মধ্যে function-call থাকলে।
- **নাহলে (স্বাভাবিক ছোট ফাইল)** → **Function-level graph** রিটার্ন হয়:
  node = প্রতিটা function (complexity, fan_in, fan_out, line range সহ),
  edge = একই ফাইলের ভেতরে কোন function কাকে call করছে।

**God File Chunking কেন লাগে:** একটা ফাইলে যদি শত শত function থাকে, সরাসরি সব
function node একসাথে দেখালে গ্রাফ অপাঠযোগ্য হয়ে যায় — তাই আগে থেকেই (parsing
সময়ে, `chunking.py`) সেই ফাইলকে ছোট ছোট logical group-এ ভাগ করে রাখা হয়, আর
Tier-3-এ প্রথমে সেই গ্রুপ-লেভেল ভিউ দেখানো হয়।

---

## ৬. God File Chunking — Node Clustering কীভাবে হয় (কোন Basis-এ)

Tier-3-এ যেসব ফাইলকে "chunked" দেখানো হয়, সেই chunking আসলে **parsing-এর
সময়েই** (upload-এর মুহূর্তে, Neo4j-তে যাওয়ার আগে) ঠিক হয়ে যায় — এটা কোনো
runtime/on-the-fly clustering algorithm না, বরং প্রতিটা function-এর গায়ে
একটা `virtual_module` লেবেল বসিয়ে দেওয়া হয়, যেটাই পরে Chunk node-এর নাম হয়ে
যায়।

### ধাপ ১ — প্রতিটা ফাইল কোন strategy পাবে (`chunking.py: detect_file_strategy`)

প্রথমে প্রতিটা ফাইলকে ৪ ভাগের একটাতে ফেলা হয়:

| শর্ত | Strategy | ফলাফল |
|---|---|---|
| Generated ফাইল (`.pb.go`, `.gen.go`, `_grpc.pb.go` ইত্যাদি প্যাটার্ন) এবং লাইন ≤ ১,০০,০০০ | `god_file` (জোর করে) | সবসময় chunk হবে — কারণ generated ফাইলে অনেক function থাকে কিন্তু chunk না করলে module graph-এ `fn_count=0` দেখায় |
| Generated ফাইল কিন্তু লাইন > ১,০০,০০০ | `data_file` | পুরোপুরি স্কিপ (বিশাল আকারের কারণে) |
| মোট লাইন ≤ ১০,০০০ | `normal` | chunking লাগে না, function count যাই হোক |
| লাইন > ১০,০০০ এবং real function count < ৩ | `data_file` | সম্ভবত কোড না, ডেটা/config ফাইল — স্কিপ |
| লাইন > ১০,০০০ এবং function count ৩–১০০ | `large_normal` | বড় কিন্তু chunk করার দরকার নেই, single node হিসেবেই থাকে |
| লাইন > ১০,০০০ এবং function count > ১০০ | `god_file` | **chunk করতে হবে** |

অর্থাৎ chunking-এর মূল trigger হলো: **ফাইল অনেক বড় (>১০k লাইন) এবং তাতে
১০০-এর বেশি function** — শুধু লাইন সংখ্যা বা শুধু function সংখ্যা দিয়ে না,
দুটো শর্তই লাগে।

### ধাপ ২ — Grouping কোন Basis-এ হয় (`chunking.py: chunk_god_file`)

একটা `god_file` চিহ্নিত হলে, তিনটা strategy **ক্রমান্বয়ে** try করা হয় — প্রথমটা
কাজ করলে বাকিগুলো আর চেষ্টা করা হয় না (fallback chain):

**Strategy 1 — Class-based grouping (সবচেয়ে প্রাধান্য পায়):**
- Python-এ AST দিয়ে সরাসরি সব `class` definition বের করা হয়; অন্য ভাষায়
  (JS/TS/Java/Go...) tree-sitter দিয়ে `class_definition` query চালানো হয়।
- প্রতিটা ক্লাসের `line_start`–`line_end` রেঞ্জ বের করে, যেসব function-এর
  `line_start` সেই রেঞ্জের ভেতরে পড়ে সেগুলোকে ওই ক্লাসের method হিসেবে ধরে
  একটা chunk-এ গ্রুপ করা হয় (basis = **লাইন-রেঞ্জ ওভারল্যাপ দিয়ে ক্লাস
  membership বের করা**, নাম বা import দিয়ে না)।
- এটা কাজ করে (মানে ফাইলে অন্তত একটা class পাওয়া গেলে) — এখানেই থেমে যাওয়া হয়,
  পরের strategy try হয় না।

**Strategy 2 — Complexity-based grouping (class না পাওয়া গেলে fallback):**
- ফাইলের **সব** function-কে তাদের cyclomatic complexity (CC) অনুযায়ী ৩টা
  fixed bucket-এ ভাগ করা হয়:
  - CC > 15 → **High Complexity**
  - 5 < CC ≤ 15 → **Medium Complexity**
  - CC ≤ 5 → **Low Complexity**
- যদি High বা Medium bucket-এ অন্তত একটা function থাকে, এই ৩টা bucket-ই
  chunk হিসেবে রিটার্ন হয় (এমনকি খালি bucket-ও, তাই কখনো কখনো একটা chunk
  ০-function নিয়ে দেখা যেতে পারে)।
- basis পুরোপুরি **numeric threshold**, কোনো semantic/naming বিবেচনা নেই।

**Strategy 3 — Line-range chunking (শেষ fallback, সবসময় কাজ করে):**
- যদি কোনো class না থাকে **এবং** সব function-ই Low Complexity হয় (High/Medium
  দুটোই খালি), তখন শুধু **অবস্থান (position)** দিয়ে ভাগ করা হয়:
  functions-কে `line_start` অনুযায়ী sort করে প্রতি ৫০টা (`CHUNK_SIZE = 50`)
  function নিয়ে একটা করে chunk বানানো হয় — semantic কোনো সম্পর্ক ছাড়াই,
  শুধু ফাইলে তারা কোথায় লেখা আছে তার ক্রম অনুযায়ী।

### ধাপ ৩ — Node-এর নাম (virtual_module) কীভাবে ঠিক হয়

Chunk-এর নামটাই পরে Neo4j-তে **Chunk node**-এর `name` হয়ে যায়
(`db.py: store_all` — `vm != fpath` হলে `Chunk {name: vm}` তৈরি হয়)। নামকরণ
strategy-ভেদে আলাদা:

| Strategy | নামের উৎস | উদাহরণ |
|---|---|---|
| Class-based | **সোর্স কোড থেকে সরাসরি নেওয়া আসল class-এর নাম** (কোনো generate/invent করা নাম না) | `AuthManager`, `UserService` |
| Complexity-based | **৩টা fixed, hardcoded label** — সবসময় একই তিনটা নাম, কোনো ফাইল-নির্দিষ্ট তথ্য নেই | `High Complexity`, `Medium Complexity`, `Low Complexity` |
| Line-range | ব্যাচ-ইনডেক্স + সেই ব্যাচের প্রথম ও শেষ function-এর প্রকৃত line number দিয়ে **অটো-জেনারেটেড** | `Group 1 (lines 1–842)`, `Group 2 (lines 845–1690)` |

**গুরুত্বপূর্ণ:** নামকরণে কোনো LLM/AI ব্যবহার হয় না — সবই deterministic rule
(হয় সোর্স থেকে সরাসরি নেওয়া, নাহলে hardcoded লেবেল, নাহলে line-number থেকে
বানানো স্ট্রিং)। প্রতিটা function-এর dict-এ `virtual_module` আর `is_god_file: true`
সেট হয়ে যায় (`pipeline.py:80-83`), এবং পরে `functions` list-এর একই dict
object mutate হয় বলেই প্রতিটা function সঠিক chunk-এ bind থাকে — নাম মিলিয়ে
পরে ম্যাচ করা হয় না (কারণ `__init__`, `run` এর মতো common নাম একাধিক
class/chunk-এ থাকতে পারে, নাম-ম্যাচিং করলে ভুল chunk-এ বসে যেত)।

---

## ৮. Tier-4 (Chunk-এর ভেতরের Function) — সর্বশেষ ধাপ

**Trigger:** Chunk-level Tier-3 থেকে একটা chunk node-এ ক্লিক করলে
`GET /graph/chunk?file_path=...&chunk_name=...` কল হয়।

**ফাইল:** `db.py: get_chunk_functions`

সেই নির্দিষ্ট chunk-এর ভেতরের সব function node আর তাদের একে অপরকে call করার
সম্পর্ক রিটার্ন হয় — এটাই সবচেয়ে গভীর (leaf) লেভেল।

---

## ৯. Fallback / Resilience Logic

- **Tier-1** সবসময় প্রথমে **in-memory cache** (`SESSION_CACHE`) থেকে আসে
  (আপলোডের সময় বানানো, তাৎক্ষণিক)। পরবর্তীতে `GET /graph/tier1` কল হলে
  Neo4j থেকে fresh query করা হয়, কিন্তু সেটা fail করলে **in-memory cache-এ
  fallback** করা হয় (`main.py: api_tier1`) — তাই Neo4j সাময়িকভাবে ডাউন থাকলেও
  ইউজার অন্তত পুরনো/cached তথ্য দেখতে পায়।
- **Service-scoped Tier-1** এর ক্ষেত্রে ইচ্ছাকৃতভাবে in-memory build কেই
  প্রাধান্য দেওয়া হয় (Neo4j query-এর চেয়ে), কারণ in-memory version এ import/require
  statement থেকে অনুমান করা extra edge-ও থাকে যেটা শুধু `CALLS` relationship-ভিত্তিক
  Neo4j query তে নেই।
- Tier-2/Tier-3/Chunk **সবসময় সরাসরি Neo4j থেকে** আসে (কোনো in-memory fallback
  নেই) — এগুলো drill-down এ lazy-loaded, তাই কম ঘন ঘন কল হয় আর প্রতিবার fresh
  ডেটা দরকার হয়।

---

## ১০. Frontend Rendering (`GraphView.vue`)

- Graph rendering library: **Vue Flow** (`@vue-flow/core`) — node/edge layout,
  drag, zoom, minimap (`@vue-flow/minimap`), control প্যানেল
  (`@vue-flow/controls`) সহ।
- **Progressive disclosure**: শুরুতে শুধু Tier-1 render হয়। ইউজার একটা module
  node-এ ডাবল-ক্লিক করলে তখনই Tier-2 fetch হয়ে সেই module-এর ভেতরের ফাইলগুলো
  expand হয়ে দেখানো হয় — পুরো tree আগে থেকে লোড করা হয় না।
- একইভাবে file node ক্লিকে Tier-3, আর chunked file হলে chunk node ক্লিকে
  Tier-4 — প্রতিটা ধাপ একটা আলাদা network call, on-demand।
- Multi-service upload হলে প্রথমে একটা **service-level graph** (কোন service
  কাকে call করছে, HTTP/message-queue detection দিয়ে বের করা) দেখানো হয়,
  তারপর একটা service-এ ঢুকলে সেই service-এর নিজের Tier-1 (module graph) দেখা যায়।

---

## ১১. সারমর্ম — কোথায় কী আছে

| জিনিস | ফাইল | Function |
|---|---|---|
| Parse + metrics + layer violations | `pipeline.py` | `analyze_files()` |
| In-memory Tier-1 build | `graph_builder.py` | `build_module_graph()` |
| Render strategy decision | `chunking.py` | `decide_render_strategy()`, `filter_top_nodes()` |
| File-size triage (normal/large/god/data) | `chunking.py` | `detect_file_strategy()`, `count_functions_ast()` |
| God file clustering (class/complexity/line-range) | `chunking.py` | `chunk_god_file()` |
| Neo4j-তে persist করা | `db.py` | `store_all()` |
| Tier-1 (DB থেকে) | `db.py` | `get_tier1()` |
| Tier-2 (file-level) | `db.py` | `get_tier2()` |
| Tier-3 (function বা chunk-level) | `db.py` | `get_tier3()` |
| Tier-4 (chunk-এর ভেতরের function) | `db.py` | `get_chunk_functions()` |
| Session isolation / cleanup | `db.py` | `session_id` property, `delete_session_data()` |
| API endpoints | `main.py` | `/upload`, `/graph/tier1`, `/graph/tier2/{module}`, `/graph/tier3`, `/graph/chunk` |
| Frontend rendering + drill-down | `GraphView.vue` | Vue Flow render + tier2/tier3/chunk fetch calls |

**এক লাইনে বললে:** Upload হওয়ার সাথে সাথে Tier-1 (module graph) in-memory থেকে
তাৎক্ষণিক দেখানো হয়, একই ডেটা সমান্তরালে Neo4j-তে session-scoped গ্রাফ হিসেবে
persist হয়, আর তারপর ইউজার যত গভীরে ক্লিক করে (module → file → function/chunk →
chunk-internal function), ততই lazily Neo4j থেকে পরের tier-এর সাব-গ্রাফ fetch
করে Vue Flow দিয়ে render করা হয় — পুরো গ্রাফ কখনোই একসাথে লোড হয় না।
