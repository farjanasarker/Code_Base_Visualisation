# Code Smell Detection — কী কী লজিক দিয়ে কাজ করে

এই ডকুমেন্টে ৩টা জিনিস ব্যাখ্যা করা হয়েছে:
1. Code smell **detection** এর পেছনের লজিক (কোন ফাইলে, কীভাবে)
2. **ROI Plan** (তুমি যেটাকে "RIO plan" বলেছ) — কীভাবে fix-priority ঠিক হয়
3. **"By Layer"** এবং **"Fix Tree"** (তুমি যেটাকে "by lear" আর "fixed tree" বলেছ) কী বোঝায়

> Source ফাইল: `Backend/analyzer.py`, `Backend/smell_detector.py`, `Backend/smell_graph.py`, `Backend/main.py`, `Backend/llm_engine.py`

---

## ১. Pipeline এর overview

```
analyzer.py          →  smell_detector.py     →  smell_graph.py           →  llm_engine.py
(code parse করে         (metrics থেকে smell        (smell গুলোর মধ্যে           (LLM দিয়ে "কেন" এবং
 metrics বের করে)         detect করে, LLM না)        dependency graph বানায়,     "কীভাবে fix" — reasoning
                                                      ROI অনুযায়ী plan বানায়)     layer, raw code দেয় না)
```

**মূল নীতি (main.py:1371 কমেন্টে লেখা আছে):**
> "Pipeline (no LLM for detection — pure static analysis)"

অর্থাৎ smell **detect** করাটা সম্পূর্ণ **rule-based / metric-based (static analysis)**। LLM (Groq এর Llama-3.3-70b) কোনো smell detect করে না — ও শুধু আগে থেকে detect হওয়া smell গুলো নিয়ে **কেন এটা সমস্যা** এবং **কীভাবে fix করলে ভালো** সেটার reasoning/explanation দেয়। LLM raw source code বা file content কিছুই পায় না — শুধু structured summary (type counts, root cause score) পায়।

---

## ২. ধাপ ১ — Metrics বের করা (`analyzer.py`)

Tree-sitter (Python/JS/Java/Go/Rust এর জন্য) দিয়ে কোড parse করে প্রতিটা function/method এর জন্য এই metric গুলো বের করা হয়:

| Metric | মানে |
|---|---|
| `complexity` (Cyclomatic Complexity) | if/for/while/case ইত্যাদি keyword গুনে approximate করা হয় |
| `fan_in` | কতগুলো জায়গা থেকে এই function কে call করা হচ্ছে (সব ফাইল মিলিয়ে) |
| `fan_out` | এই function নিজে কতগুলো আলাদা function কে call করছে |
| `param_count` | parameter সংখ্যা |
| `max_nesting_depth` | if/for এর ভেতরে if/for কতটা গভীর পর্যন্ত নেস্টেড |
| `literal_count` | ম্যাজিক নাম্বার (unexplained numeric literal) কতটা |
| `is_dead` / `dead_confidence` | function টা সত্যিই ব্যবহার হচ্ছে না কিনা (none/medium/high confidence) |
| `virtual_module` | কোন class-এর ভেতরে function টা আছে (class-level grouping করতে লাগে) |

### Dead code detection এর বিশেষ সাবধানতা
শুধু `fan_in == 0` দেখেই কোনো function কে "dead" বলা হয় না, কারণ এগুলো false-positive হতে পারে:
- Entry point (`main`, `__init__`, `handler`, React lifecycle যেমন `componentDidMount` ইত্যাদি) — এগুলোর একটা hardcoded whitelist (`_ENTRY_POINT_NAMES`) আছে
- prefix pattern (`test_`, `on_`, `handle_` ইত্যাদি) দেখলে entry point ধরে নেওয়া হয়
- callback/hook-সদৃশ নাম (`onClick`, `*Handler`, `*Listener` ইত্যাদি) হলে "high" এর বদলে "medium" confidence দেওয়া হয়, কারণ এগুলো runtime এ (polymorphism/reflection দিয়ে) call হতে পারে যেটা static analysis ধরতে পারবে না

---

## ৩. ধাপ ২ — Smell Detection (`smell_detector.py`)

এখানে ১৭ ধরনের smell কে ৩টা layer এ ভাগ করে রাখা হয়েছে (এটাই তোমার প্রশ্নের **"by lear" = "by layer"** answer, নিচে ৬ নং সেকশনে বিস্তারিত):

- **Function-level**: long_method, too_many_params, dead_code, feature_envy, deep_nesting, switch_smell, magic_numbers
- **Module-level**: god_module, god_class, large_module, shotgun_surgery, divergent_change, lazy_class, duplicate_code, data_clumps
- **Architecture-level**: circular_dependency, long_call_chain, inappropriate_intimacy

প্রতিটা smell এর জন্য একটা fixed numeric **threshold** আছে (`THRESHOLDS` dict, `smell_detector.py:23`), যেমন:

| Smell | কীভাবে detect হয় (threshold-based rule) |
|---|---|
| `long_method` | function ৫০ লাইনের বেশি **অথবা** cyclomatic complexity ১০ এর বেশি হলে |
| `god_class` / `god_module` | class/module এ ৭+ (class) বা ২০+ (module) function থাকলে **এবং** average complexity বেশি হলে |
| `feature_envy` | `fan_out ≥ 5` এবং `fan_out/fan_in ≥ 3.0` (নিজের চেয়ে অন্যকে বেশি call করছে) |
| `shotgun_surgery` | ৮+ আলাদা ফাইল থেকে call হচ্ছে, কিন্তু `fan_in > 30` না হলে (বেশি হলে সেটা ইচ্ছাকৃত shared utility, smell না) |
| `deep_nesting` | nesting depth ≥ 4, অথবা depth metric না থাকলে CC/LOC ratio fallback হিসাব দিয়ে অনুমান |
| `switch_smell` | ছোট function (≤৪০ লাইন) এ CC ≥ ৬ (মানে কম লাইনে অনেক branching — switch/if-chain সন্দেহ) |
| `data_clumps` | একই module এ ৩+ function এর param_count ≥ ৪ হলে |
| `magic_numbers` | function এ ৫+ non-trivial numeric literal থাকলে |
| `circular_dependency` | call-graph এ cycle পাওয়া গেলে (২-৩ নোডের cycle হলে "critical") |
| `long_call_chain` | call chain depth ≥ ৭ হলে |
| `duplicate_code` | **এটা static metric দিয়ে detect করা হয় না** — কমেন্টে লেখা আছে কারণ: শুধু LOC/CC মিলে গেলে duplicate ধরলে false positive বেশি হয়। তাই এটা LLM এর কাছে ছেড়ে দেওয়া হয়েছে (semantic duplicate বোঝার জন্য) |

প্রতিটা detected smell একটা `severity` (critical/high/medium/low) পায়, threshold এর কতটা উপরে গেছে তার ভিত্তিতে, এবং প্রতিটার জন্য একটা fixed **Refactoring Catalog** (`REFACTOR_CATALOG`) থেকে suggestion আসে (যেমন `long_method` → "Extract Method", "Decompose Conditional")। এই catalog টা Martin Fowler এর refactoring pattern নাম থেকে নেওয়া, hardcoded mapping — কোনো ML/AI না।

---

## ৪. Smell Causation Model — কে কার কারণ

`SMELL_CAUSATION` dict (`smell_detector.py:108`) এ প্রতিটা smell type এর জন্য বলা আছে সে **আর কোন কোন smell এর জন্ম দেয়** (downstream), তার fix করতে কতটা effort লাগে (1-5 স্কেল), আর কোন layer এ পড়ে। যেমন:

- `god_class` → downstream এ `long_method`, `feature_envy`, `dead_code` ইত্যাদি অনেক কিছু তৈরি করে (effort ৫, layer: module)
- `feature_envy`, `too_many_params`, `dead_code` — এগুলো "leaf smell", এদের কোনো downstream নেই, সরাসরি fix করতে হয়

এই relationship-টাই পরের ধাপে (ROI plan আর fix tree) ব্যবহার হয়।

---

## ৫. ROI Plan (তোমার "RIO plan") — `smell_graph.py`

তুমি যেটাকে **"RIO"** বলেছ সেটা আসলে **ROI (Return on Investment)** — code এ literally variable নাম `roi_score`। এটা কোনো ML model না, pure graph algorithm:

### ধাপে ধাপে:
1. **Dependency Graph তৈরি** (`build_edges_from_type_rules`): প্রতিটা detected smell instance কে node ধরে, `SMELL_CAUSATION` এর নিয়ম অনুযায়ী upstream→downstream edge টানা হয় (যেমন কোনো নির্দিষ্ট `god_class` instance থেকে সেই class-এর ভেতরের `long_method` instance গুলোর দিকে edge)।

2. **Root Cause Scoring** (`compute_root_cause_scores`): প্রতিটা node থেকে BFS করে তার সব downstream (descendant) smell এর severity যোগ করে একটা `root_cause_score` বের করা হয়।
   ```
   score(A) = severity_weight(A) + Σ severity_weight(সব descendant D)
   ```
   severity weight: critical=4, high=3, medium=2, low=1

3. **Gain Ratio**: `gain_ratio = score / effort` — মানে কম effort এ বেশি downstream smell resolve হলে ratio বেশি।

4. **Minimal-Fix Plan** (`minimal_fix_plan`) — এটাই **Greedy Set-Cover algorithm**:
   - সব unresolved smell থেকে সবচেয়ে বেশি `gain_ratio` ওয়ালাটা বেছে নাও
   - সেটা fix করলে যেসব downstream smell BFS দিয়ে reachable, সবগুলোকে "resolved" মার্ক করে দাও (cascade effect ধরে নেওয়া হয়)
   - এভাবে সর্বোচ্চ ১০ ধাপ (`max_steps=10`) পর্যন্ত repeat করা হয়
   - শেষে প্রতিটা plan item এর জন্য `roi_score = resolves_count / effort` হিসাব করে সেই অনুযায়ী re-rank (sort) করা হয়

   **সহজ ভাষায়**: "কম কষ্টে সবচেয়ে বেশি smell যেটা ঠিক করে দেয়, সেটা আগে ঠিক করো" — এটাই ROI Plan এর মূল যুক্তি।

5. **Top-3 code preview**: প্রথম ৩টা plan item এর জন্য LLM কে দিয়ে before/after code preview generate করানো হয় (`get_code_preview`), বাকিগুলোর জন্য না (performance/cost এর কারণে)।

---

## ৬. "By Layer" (তোমার "by lear") — `main.py:_group_smells_by_layer`

প্রতিটা detected smell তার `SMELL_CAUSATION[type]["layer"]` অনুযায়ী ৩টা bucket এ ভাগ করা হয়:

- **Function Level** — single function এর ভেতরের সমস্যা (long_method, deep_nesting, magic_numbers...)
- **Module / Class Level** — class/module এর ডিজাইন সমস্যা (god_class, lazy_class, data_clumps...)
- **Architecture Level** — একাধিক module/file এর মধ্যেকার সমস্যা (circular_dependency, long_call_chain...)

এটা শুধু একটা **grouping/presentation feature** — UI তে smell গুলোকে granularity অনুযায়ী আলাদা করে দেখানোর জন্য, নতুন কোনো detection logic না।

---

## ৭. "Fix Tree" (তোমার "fixed tree") — `main.py:_build_fix_tree`

এটা ROI plan থেকে আলাদা একটা **visualization feature**:

- যেসব smell type কোনো অন্য detected smell এর downstream না (মানে `root_types = detected_types - downstream_types`), সেগুলোকে **root** ধরা হয়
- প্রতিটা root smell instance থেকে শুরু করে recursively তার downstream instance গুলোকে child হিসেবে বসিয়ে একটা **tree structure** (max depth ৩) বানানো হয়
- একই smell instance একাধিক parent এর নিচে দেখাতে পারে যদি তার upstream টাইপ একাধিক থাকে (এটা expected behavior, কমেন্টে বলা আছে)

**ROI Plan vs Fix Tree এর পার্থক্য:**
- **ROI Plan** = "কোন অর্ডারে fix করব" — একটা ranked, actionable sequence (greedy algorithm দিয়ে)
- **Fix Tree** = "কোন smell কোন smell এর জন্ম দিচ্ছে" — একটা visual hierarchy/structure, কোনো ranking বা priority নেই এখানে, শুধু cause→effect সম্পর্ক দেখানো

---

## ৮. সারমর্ম — কোথায় কী আছে

| জিনিস | ফাইল | Function/Variable |
|---|---|---|
| Metric extraction | `analyzer.py` | `_extract_functions`, `compute_fan_in`, `_compute_nesting_depth` |
| Smell detection rules | `smell_detector.py` | `THRESHOLDS`, `SmellDetector.detect_all()` |
| Refactor suggestions | `smell_detector.py` | `REFACTOR_CATALOG` |
| Causation model | `smell_detector.py` | `SMELL_CAUSATION` |
| Root cause scoring | `smell_graph.py` | `compute_root_cause_scores()` |
| **ROI Plan** | `smell_graph.py` | `minimal_fix_plan()` → `roi_score` |
| **By Layer grouping** | `main.py` | `_group_smells_by_layer()` |
| **Fix Tree** | `main.py` | `_build_fix_tree()` |
| LLM reasoning (WHY/HOW, detection না) | `llm_engine.py` | system prompt + `get_code_preview` |

**এক লাইনে বললে:** পুরো detection ১০০% rule-based static analysis (কোনো machine learning/trained model নেই, সব fixed threshold আর graph algorithm), আর LLM শুধু শেষে এসে already-detected smell গুলোর architectural reasoning আর before/after code example দেয়।
