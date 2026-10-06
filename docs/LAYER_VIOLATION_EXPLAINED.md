# Layer Violation Detection — কীভাবে কাজ করে

এই ডকুমেন্টে ব্যাখ্যা করা হয়েছে **architectural layer violation** ডিটেকশনের
পেছনের লজিক — কোনো কোড না, শুধু নিয়ম।

> Source ফাইল: `Backend/analyzer/layers.py`, `Backend/analyzer/pipeline.py`,
> `Backend/main.py` (`/layer-violations` endpoint)

---

## ১. মূল ধারণা — Layered Architecture Rule

এই ফিচারটা ধরে নেয় প্রতিটা প্রজেক্ট একটা **layered architecture** মেনে চলার
চেষ্টা করে (Router → Controller → Service → Repository → Model/DB), এবং নিয়ম হলো:

- **প্রতিটা layer শুধু ঠিক তার নিচের layer-কে call করতে পারবে**, layer টপকে
  (skip করে) নিচে যেতে পারবে না
- **কোনো layer উপরের দিকে (reverse) কল করতে পারবে না** — যেমন Repository যদি
  Controller-কে import করে, সেটা ভুল দিকে dependency
- **Utility** layer (helper, config, logger, validator...) একটা exception —
  যেকোনো layer থেকে utility import করা সবসময় allowed, কারণ এটা cross-cutting concern
- **Middleware** (auth, logging, guard) সরাসরি Service-কে call করতে পারে

এটা শুধু **multi-file upload** (folder/ZIP)-এ কাজ করে — single file আপলোডে
কোনো import-graph থাকে না, তাই এই ফিচার skip হয়ে যায়
(`layers.py:223-224`: `if len(files) <= 1: return empty`)।

---

## ২. ধাপ ১ — একটা ফাইল কোন Layer-এ পড়ে সেটা বোঝা (`_detect_file_layer`)

এটা কোনো ML/AST দিয়ে না, **naming convention ভিত্তিক keyword matching**।
৮টা layer-এর জন্য একটা keyword set আছে (`_LAYER_KEYWORDS`):

| Layer | চেনা যায় যেসব নাম দিয়ে |
|---|---|
| `router` | route, routes, router, routing |
| `controller` | controller, handler, api, view, endpoint, resource, action |
| `service` | service, usecase, business, manager, facade, orchestrator |
| `repository` | repository, repo, dao, store, gateway, finder |
| `model` | model, entity, schema, dto, domain, aggregate |
| `database` | db, migration, seed, connection, orm, infra, persistence |
| `middleware` | middleware, interceptor, guard, filter, hook, plugin |
| `utility` | util, helper, shared, common, lib, config, logger, validator, mapper |

**যেভাবে চেক করা হয় (দুই ধাপে, folder আগে, filename পরে):**
1. ফাইলের path-এর প্রতিটা **folder নাম** (সবচেয়ে ভেতরের/deepest folder থেকে
   শুরু করে বাইরের দিকে) কোনো layer-এর keyword-এর সাথে exact match করে কিনা
   দেখা হয় — যেমন `src/services/user.py` হলে `services` ফোল্ডার দেখেই
   `service` layer ধরে নেওয়া হয়।
2. কোনো folder match না পেলে, **filename-এর শেষে/শুরুতে** keyword আছে কিনা
   দেখা হয় (fallback) — যেমন `userController.js`, `UserService.java`।
3. কোনোটাই না মিললে layer = `"unknown"` (এসব ফাইল violation-check থেকে বাদ
   পড়ে যায়)।

**Import reference-এর layer বোঝা (`_detect_import_layer`)** একই পদ্ধতি,
তবে import path-টাকে `/` আর `.` দিয়ে split করে প্রতিটা segment (most-specific
আগে) keyword-এর সাথে মেলানো হয়, ফাইল extension (.js, .py, .java...) আগে থেকে
বাদ দিয়ে।

---

## ৩. ধাপ ২ — Layer Order এবং Allowed Transitions

প্রতিটা layer-এর একটা numeric অর্ডার আছে (`_LAYER_ORDER`) — সংখ্যা যত কম, স্ট্যাক
এ তত উপরে (ইউজারের কাছাকাছি):

```
router(0) → controller(1) → middleware(2) → service(3) → repository(4) → model/database(5)
utility = -1  (cross-cutting, সব layer থেকে allowed)
```

কিন্তু শুধু numeric gap দিয়ে violation ধরা হয় না (কারণ Controller → Service
সঠিক valid জাম্প, কিন্তু ওটাও একটা gap)। এর বদলে একটা **explicit allow-list**
(`_ALLOWED_TRANSITIONS`) আছে যেটাই আসল সোর্স অফ ট্রুথ:

| Source layer | কাকে call করতে পারে (allowed) |
|---|---|
| router | controller, middleware, utility |
| controller | service, utility |
| middleware | service, utility |
| service | repository, model, utility, **service** (একই লেয়ারে service→service allowed) |
| repository | model, database, utility |
| model / database | utility |

লক্ষ্যণীয় — `service → service` allowed করা হয়েছে ইচ্ছাকৃতভাবে, কারণ একটা
service আরেকটা service-কে call করা (orchestration/composition) স্বাভাবিক
প্র্যাকটিস, সেটাকে false-positive হিসেবে flag করা হয় না।

---

## ৪. ধাপ ৩ — Violation-এর প্রকারভেদ (`_check_layer_violation`)

`src_layer` থেকে `tgt_layer`-এ import গেলে প্রথমেই কিছু কেস স্কিপ করা হয়:
- `src_layer` যদি `unknown` বা `utility` হয় → স্কিপ (নিজে যদি layer-ই না থাকে
  বা cross-cutting utility হয়, ওর import নিয়ে সিদ্ধান্ত দেওয়া অর্থহীন)
- `tgt_layer` যদি `unknown`, `utility`, বা `router` হয় → স্কিপ (utility import
  সবসময় ঠিক আছে; router-কে সাধারণত কেউ import করে না, তাই ওটা target হলে
  বিবেচনায় নেওয়া হয় না)

তারপর allow-list চেক করে ৩ ধরনের violation-এর একটাতে ফেলা হয়:

| Violation type | কখন হয় | Severity |
|---|---|---|
| **`reverse_dependency`** | target layer, source-এর চেয়ে স্ট্যাকে উপরে (`tgt_ord < src_ord`) — যেমন Repository → Controller | **high** |
| **`cross_layer`** | দুটোই একই লেয়ার অর্ডারে, কিন্তু allow-list এ নেই (যেমন Repository → Repository সরাসরি coupling) | **medium** |
| **`layer_skip`** | target নিচের দিকেই আছে (`tgt_ord > src_ord`), কিন্তু allow-list এ নেই — মানে মাঝের কোনো layer টপকানো হয়েছে (যেমন Controller সরাসরি Model/DB-কে import করছে, Service বাদ দিয়ে) | **high** |

---

## ৫. ধাপ ৪ — সব ফাইলের উপর প্রয়োগ (`_compute_layer_violations`)

1. প্রতিটা ফাইলের import-লিস্ট (`file_import_map`, parse করার সময় `pipeline.py`-তে
   বের করা হয়) নিয়ে তার নিজের layer বের করা হয়।
2. প্রতিটা import-এর target layer বের করে `_check_layer_violation` দিয়ে চেক
   করা হয়।
3. প্রতিটা violation-এ থাকে: `source_file`, `source_layer`, `target_ref`,
   `target_layer`, `type`, `severity`, `message`।
4. সব violation-কে তাদের **module** (tier-1 গ্রাফের node id, `module_map`
   থেকে) অনুযায়ী গ্রুপ করা হয় (`by_module`), যাতে ফ্রন্টএন্ড tier-1 গ্রাফে
   কোন module-এ violation আছে সেটা রং করে দেখাতে পারে।
5. একটা `summary` তৈরি হয় — মোট কতগুলো violation, কতগুলো high, কতগুলো medium।

---

## ৬. Multi-Service (Monorepo) আপলোডে বিশেষ নিয়ম

`main.py`-তে যদি আপলোডে ২+ আলাদা service folder থাকে (monorepo ধরা হয়), তাহলে
layer violation **প্রতিটা service-এর ভেতরেই আলাদাভাবে** চেক করা হয়
(`main.py:786-826` — প্রতিটা `svc` bucket-এর জন্য আলাদা `analyze_files()` কল)।

**কেন:** একটা service-এর controller অন্য service-এর repository import করলে
সেটা layer violation না, বরং inter-service call (যেটা আলাদা একটা ফিচার —
`detect_service_connections` দিয়ে ধরা হয়)। তাই layer-rule শুধু single
service/single project-এর **নিজের ভেতরের** স্তর-লঙ্ঘন ধরার জন্য, cross-service
dependency আলাদাভাবে হ্যান্ডেল হয়।

---

## ৭. যেখানে ব্যবহার হয় (`GET /layer-violations`)

- Frontend tier-1 গ্রাফের module node গুলোকে color/badge দিয়ে হাইলাইট করতে
  এই endpoint ব্যবহার করে — কোন module-এ কয়টা violation আছে, severity কী।
- `service_id` filter দিয়ে নির্দিষ্ট একটা service-এর violation আলাদা করে
  দেখা যায় (monorepo হলে)।
- প্রতিটা module-এর জন্য compact আকারে `{count, severity}` পাঠানো হয়
  (raw violation-এর বিস্তারিত item ফ্রন্টএন্ডে পাঠানো হয় না, শুধু চাহিদামতো)।

---

## ৮. সীমাবদ্ধতা (Limitations)

- এটা **সম্পূর্ণ naming-convention-ভিত্তিক heuristic** — প্রকৃত type/interface
  analysis না। ফোল্ডার/ফাইলের নাম conventional না হলে (যেমন `stuff/`, `xyz.py`)
  layer = `unknown` হয়ে যাবে আর সেই ফাইল কোনো violation চেক-এই আসবে না।
- import path resolve করে actual file match করা হয় না — শুধু path string-এর
  ভেতরের keyword দেখেই layer অনুমান করা হয়, তাই ambiguous নাম ভুল layer-এ পড়তে
  পারে (যেমন কেউ যদি একটা model file-এর নাম `UserManager.py` রাখে, সেটা
  `manager` keyword দেখে `service` layer ধরা হয়ে যাবে)।
- Single-file আপলোডে কাজ করে না (import graph বানানোর মতো একাধিক ফাইল লাগে)।
- LLM কোনোভাবে জড়িত না — এটা ১০০% rule-based static heuristic, `smell_detector.py`
  এর মতোই (দেখুন [CODE_SMELL_DETECTION_EXPLAINED.md](CODE_SMELL_DETECTION_EXPLAINED.md))।

---

## ৯. সারমর্ম — কোথায় কী আছে

| জিনিস | ফাইল | Function |
|---|---|---|
| Layer keyword sets | `layers.py` | `_LAYER_KEYWORDS` |
| Layer order (stack position) | `layers.py` | `_LAYER_ORDER` |
| Allowed transition table | `layers.py` | `_ALLOWED_TRANSITIONS` |
| ফাইল থেকে layer বের করা | `layers.py` | `_detect_file_layer()` |
| Import থেকে layer বের করা | `layers.py` | `_detect_import_layer()` |
| Violation টাইপ নির্ধারণ | `layers.py` | `_check_layer_violation()` |
| সব ফাইলের উপর প্রয়োগ + grouping | `layers.py` | `_compute_layer_violations()` |
| Import extraction (parse pipeline) | `pipeline.py` | `file_import_map` |
| Multi-service per-bucket handling | `main.py` | `is_multi_service` ব্লক (~line 786) |
| API endpoint | `main.py` | `GET /layer-violations` |

**এক লাইনে বললে:** Layer violation detection একটা naming-convention-ভিত্তিক
static rule engine — প্রতিটা ফাইল/import-কে ৮টা predefined architectural
layer-এর একটাতে বসিয়ে, একটা explicit allow-list দিয়ে চেক করে দেখা হয় কে কাকে
call করতে পারবে; না পারলে সেটা `reverse_dependency`, `cross_layer`, বা
`layer_skip` — এই তিন ধরনের একটা হিসেবে চিহ্নিত হয়।
