# GoF Design Pattern Detection — কী কী লজিক দিয়ে কাজ করে

এই ডকুমেন্টে ব্যাখ্যা করা হয়েছে GoF (Gang of Four) design pattern গুলো (Strategy, Singleton, Decorator, Observer, ইত্যাদি ২৩টা pattern) কীভাবে **detect** করা হয় — কোন ফাইলে কী লজিক আছে, ডেটা কোথা থেকে আসে, আর confidence score কীভাবে হিসাব হয়।

> Source ফোল্ডার: `Backend/patterns/` (পুরো engine), `Backend/main.py` (`/api/gof-patterns/{session_id}` endpoint)
>
> **কোনো LLM ব্যবহার হয় না** — সম্পূর্ণ rule-based, deterministic, structural graph analysis।

---

## ১. Pipeline এর overview

```
db.get_class_graph()  →  graph_view.py         →  rule_engine.py            →  main.py
(Neo4j থেকে class/       (SessionGraphView —       (YAML spec load করে,          (/api/gof-patterns
 field/method graph        session-এর জন্য এক        predicates.py এর vocab       endpoint — JSON
 বের করে)                  বার তৈরি হওয়া             দিয়ে প্রতিটা spec              response বানায়)
                           in-memory structure)      evaluate করে)
```

মূল নীতি: **static analysis, pure structural**। কোনো pattern নাম, ফাইল নাম, বা method নাম-ভিত্তিক keyword heuristic (যেমন আগে ছিল `getInstance`, `notify`, `Factory` ইত্যাদি শব্দ খোঁজা) ব্যবহার করা হয় না — শুধু class/interface/field/method এর মধ্যেকার **actual structural shape** (কে কাকে implement করছে, কার field কী type এর, কে কাকে call করছে, কে কী construct করছে) দেখে pattern চেনা হয়।

`pattern_detector.py` (ArchitecturePatternDetector — MVC, Layered, Clean Architecture, Hexagonal, Repository) এটা সম্পূর্ণ **আলাদা সিস্টেম**, `/api/patterns` endpoint এ চলে, ফাইল-নাম/keyword heuristic ব্যবহার করে। GoF pattern detection এর সাথে এর কোনো সম্পর্ক নেই।

---

## ২. Layer ১ — SessionGraphView (`patterns/graph_view.py`)

এটা পুরো engine এর ভিত্তি। Neo4j-তে upload করা প্রজেক্টের class graph (`db.get_class_graph()`) থেকে একবার (per session) একটা **in-memory, read-only, name-indexed** structure তৈরি হয়, আর প্রতিটা predicate সেই একই structure থেকে পড়ে — প্রতি pattern-এর জন্য আলাদা Neo4j query চালানো হয় না (efficiency এর জন্য)।

এতে যা যা থাকে:
- `classes` — প্রতিটা class/interface এর নাম, file, kind, labels (`INTERFACE_LIKE`, `ABSTRACT_LIKE`), field names, method names
- `implementers_of` / `subclasses_of` — কে কাকে implement/inherit করছে (direct edge)
- `interfaces_of` — **transitive closure**: `A extends B extends C` হলে `A` কে `C`-ও implement করে ধরা হয় (Decorator/Proxy সাধারণত abstract base class-এর উপর interface implement করে, subclass নিজে করে না)
- `fields_of` — class → field edges (কোন field কী type-এর, single না collection)
- `methods_of` — প্রতিটা method এর নাম, `calls` (কে কাকে call করছে + callee কোন class এ resolve হলো), `instantiates` (কোন class এর নতুন instance বানাচ্ছে), `is_abstract`

গুরুত্বপূর্ণ দুইটা helper method:
- **`effective_fields_of(class)`** — নিজের field + parent/interface থেকে inherited field (যদি নিজে override না করে) — কারণ Decorator/Proxy/Chain of Responsibility-তে shared "wrapped" field সাধারণত abstract base class-এ একবারই declare হয়, প্রতিটা subclass এ redeclare হয় না।
- **`self_referential_types(class)`** — নিজের class name + নিজের সব interface/base — "field টা নিজের টাইপেরই কিনা" চেক করার জন্য (literal নিজের class name অথবা shared interface, দুটোই ধরা হয়)।

---

## ৩. Layer ২ — Normalization (`patterns/normalization.py` + `config/method_roles.yaml`)

দুইটা কাজ করে এই layer:

**ক) Kind normalization** — প্রতিটা language এর নিজস্ব keyword (Python এর ABC, Go এর `interface`, Rust এর `trait`, Java/TS এর `interface`/`abstract class`) parse-time এ ৫টা canonical kind এ নামানো হয় (`analyzer/parser.py` এ): `class` / `abstract_class` / `interface` / `struct` / `trait`। এখান থেকে দুইটা boolean concept বের করা হয়:
- `INTERFACE_LIKE` = `interface`, `trait`, বা `abstract_class`
- `ABSTRACT_LIKE` = শুধু `abstract_class`

**খ) Method-role alias map** (`method_roles.yaml`) — একটা spec কে "does this class have a BUILDER_BUILD-role method" জিজ্ঞেস করার সুবিধা দেয়, `build`/`Build`/`construct`/`Construct` এই সব আলাদা ভাষার নাম হার্ডকোড না করে। উদাহরণ:

| Role | Aliases |
|---|---|
| `ITERATOR_NEXT` | next, `__next__`, Next |
| `BUILDER_BUILD` | build, Build, construct, Construct |
| `PROTOTYPE_CLONE` | clone, Clone, `__copy__`, `__deepcopy__` |
| `COMMAND_EXECUTE` | execute, Execute, run, Run |
| `MEMENTO_SAVE` / `MEMENTO_RESTORE` | save/create_memento ... , restore/set_memento ... |
| `INTERPRETER_INTERPRET` | interpret, Interpret |

`build_role_lookup()` এই map টাকে invert করে case-insensitive lookup বানায় (alias → role), আর `predicates.py` এ module load হওয়ার সময় একবারই বানানো হয় (প্রতি call এ re-parse হয় না)।

---

## ৪. Layer ৩ — Predicate Library (`patterns/predicates.py`, ~১০০০ লাইন)

এটাই আসল detection logic এর জায়গা — প্রতিটা GoF pattern এর জন্য এক বা একাধিক **predicate function** আছে, যেগুলো একটা shared vocabulary হিসেবে কাজ করে, যেটা দিয়ে সব spec compose হয়।

### দুই ধরনের predicate

1. **Generator** — পুরো session স্ক্যান করে candidate-দের একটা list রিটার্ন করে (`List[Candidate]`)। যেমন `interface_with_single_method` — যত interface আছে সবগুলোর মধ্যে যাদের ঠিক একটাই method আছে, সেগুলো candidate।
2. **Checker** — একটা নির্দিষ্ট already-bound class/field নাম নিয়ে true/false verdict দেয় (`PredicateResult`)। যেমন `min_implementers(interface, count)`।

কোনো predicate কখনো খালি `True`/`False` রিটার্ন করে না — সবসময় সাথে **evidence** (string list, "কোন ফাইলের কোন লাইনে কী পাওয়া গেছে") থাকে, যাতে ইউজার প্রতিটা match verify করতে পারে।

### `PredicateResult.strength` — confidence-এর গ্রেডেশন

একটা checker পাস হলেই ১.০ কনফিডেন্স পায় না সবসময় — `strength` ফিল্ড দিয়ে evidence-এর মান অনুযায়ী কমানো/বাড়ানো হয়:
- `delegates_to_field`: exact class match হলে strength ১.০, কিন্তু callee class ambiguous হলে (২+ class একই নামের method declare করে) নাম-মিল ভিত্তিক দুর্বল evidence ধরে strength ০.৮
- `min_implementers`: threshold ঠিক ছুঁয়ে গেলে ১.০, কিন্তু threshold-এর চেয়ে বেশি implementer পাওয়া গেলে strength ১.১৫ (আরো জোরালো evidence)

### গুরুত্বপূর্ণ কিছু predicate এর লজিক (উদাহরণ হিসেবে)

| Predicate | কী দেখে |
|---|---|
| `interface_with_single_method` | Interface-এ ঠিক ১টা method (Strategy/Observer এর ভিত্তি) |
| `min_implementers` | কোনো interface-এর কমপক্ষে N টা implementer আছে কিনা |
| `composition_field_of_type` / `collection_composition_field_of_type` | কোনো class-এর field কোনো নির্দিষ্ট type-এর কিনা — single বনাম collection ভেদে Strategy (single) বনাম Observer (list of observers) আলাদা হয় |
| `delegates_to_field` | কোনো method কি field-এর target class-এর কোনো method call করে (delegation প্রমাণ) |
| `has_self_referential_field` / `has_list_of_own_type_field` / `has_single_field_of_own_type` | নিজের টাইপের field আছে কিনা — single হলে Decorator/Proxy/Chain, list হলে Composite |
| `wraps_and_extends` → `is_decorator_wrapping` / `is_proxy_wrapping` | delegation আছে + wrapping method নিজে ১টার বেশি call করে কিনা: বেশি করলে **Decorator** (extra behavior যোগ করছে), ≤১ হলে pure passthrough **Proxy** |
| `field_typed_as_own_interface` | field-এর type কি class নিজেও implement করে (is-a **এবং** has-a একসাথে) — এটাই Decorator-কে সাধারণ wrapper থেকে আলাদা করে |
| `abstract_method_called_from_concrete_sibling_method` | Template Method-এর মূল শেপ: abstract method-কে একই class-এর concrete method call করছে |
| `double_dispatch_pair` / `double_dispatch_candidates` | A→B→A এই দুই-দিকের call pattern (Visitor-এর double dispatch) |
| `fan_out_to_common_hub` + `no_direct_edges_between` | একগুচ্ছ class সবাই একটা common hub class কে call করছে, কিন্তু নিজেদের মধ্যে সরাসরি call নেই (Mediator) |
| `factory_method_candidates` | abstract Creator ক্লাস-এ abstract method, ২+ subclass সেটা override করে **আলাদা আলাদা** product বানাচ্ছে |
| `abstract_factory_candidates` | Factory Method-এর মতোই কিন্তু একসাথে ২+ product method এর পুরো পরিবার (family) ভ্যারি করছে implementer অনুযায়ী |
| `builder_candidates` | `build()`-role method যেটা আলাদা product বানায়, সাথে ২+ setter-এর মতো method (build না করা) |
| `prototype_candidates` | `clone()`-role method যেটা **নিজের** class-এর নতুন instance বানায় (Factory Method এর উল্টা — অন্য class না, নিজের) |
| `singleton_candidates` | নিজের টাইপের field (instance slot) **এবং** নিজেকে construct করা method — দুটোর co-occurrence |
| `factory_candidates` | branching method (if/elif দিয়ে ২+ আলাদা product বানায়) অথবা ২+ আলাদা method প্রতিটা আলাদা product বানায় — **বর্তমানে কোনো spec এ ব্যবহার হয় না** (simple Factory pattern তুলে দেওয়া হয়েছে, নিচে §৭ দেখো) |
| `facade_candidates` | একটা class অনেকগুলো (ডিফল্ট ৫+) আলাদা class কে call করছে, কিন্তু নিজে খুব কম caller-এর দ্বারা call হচ্ছে (entry-point শেপ) |
| `flyweight_candidates` (`cache_keyed_return`) | method কিছু product construct করছে **এবং** class নিজে সেই product type-এর collection field রাখছে (cache-এর loose proxy) — tier: low, কারণ Dict-vs-List আলাদা করার ডেটা নেই |
| `memento_candidates` | `save()`-role method আলাদা (Memento) class বানাচ্ছে + class-এ `restore()`-role method আছে — tier: low, কারণ parameter type verify করা যায় না |
| `interpreter_candidates` | self-referential field + `interpret()`-role method সেই field-এর `interpret()` কে delegate করছে — **Composite-এর সাথে ambiguous**, এটা ডকুমেন্টেই স্বীকার করা আছে |

**সৎভাবে ডকুমেন্টেড gap:** `fluent_return_self` আর `cache_keyed_return`-এর মতো কিছু predicate-এর জন্য method return-type/return-expression ডেটা parser এখনো capture করে না — তাই `fluent_return_self` সবসময় `matched=False` রিটার্ন করে, ভুল heuristic দিয়ে গুঁজে দেওয়া হয়নি।

---

## ৫. Layer ৪ — Rule Engine (`patterns/rule_engine.py`)

এটা predicate library-কে declarative YAML spec-এর সাথে জোড়া লাগায়। **নতুন pattern যোগ করা মানে নতুন Python কোড লেখা না — একটা নতুন YAML spec ফাইল লেখা**, যদি সেই pattern-এর শেপ predicate library ইতিমধ্যে কভার করে।

### Binding model (backtracking search)

একটা spec-এর `requires` লিস্ট **order অনুযায়ী** চেইন হিসেবে প্রসেস হয়:
- **Generator** requirement একটা নতুন role introduce করে (`role:` কী দিয়ে) — engine সেই role-এর জন্য প্রতিটা candidate try করে (ছোট backtracking search), তারপর বাকি requirement গুলো evaluate করে
- **Checker** requirement আগে bind হওয়া role গুলো validate করে — fail করলেই সেই search branch বাদ (কোনো partial credit নেই, **সব requirement mandatory**)

### Role-reference resolution

একটা requirement-এর parameter value যদি আগে bind হওয়া কোনো role-এর নাম হয়, সেটা resolve হয়ে সেই role-এর bound class/interface নামে পরিণত হয় — **শুধু `field` parameter ছাড়া**, যেটা resolve হয় সেই role-এর `class`-এর binding-এ discover হওয়া field name-এ (কারণ `field: <role>` মানে "`class`-এর যে field-টা `<role>`-টাইপের", `<role>`-এর নিজের নাম না)।

### Confidence Calculation

```
প্রতিটা requirement এর জন্য:  weight (confidence_weights এ লেখা) × strength (predicate-এর evidence quality)
মোট confidence = Σ (weight × strength), কিন্তু সর্বোচ্চ ১.০ তে cap করা
```

একই predicate একই spec-এ একাধিকবার চললে (যেমন দুটো `has_role_method`) তাদের মধ্যে **সবচেয়ে কম strength** টা ধরা হয় (`min`), যাতে একটা দুর্বল evidence পুরো স্কোরকে বাড়িয়ে না দেয়।

`confidence < min_confidence_to_report` হলে সেই match আদৌ রিপোর্ট হয় না।

---

## ৬. Spec ফাইলের ফরম্যাট (`patterns/specs/*.yaml`)

উদাহরণ — `strategy.yaml`:

```yaml
pattern: Strategy
tier: high
requires:
  - predicate: interface_with_single_method
    role: strategy_interface
  - predicate: min_implementers
    of: strategy_interface
    count: 2
  - predicate: composition_field_of_type
    type: strategy_interface
    role: context
  - predicate: delegates_to_field
    class: context
    field: strategy_interface
confidence_weights:
  interface_with_single_method: 0.2
  min_implementers: 0.3
  composition_field_of_type: 0.2
  delegates_to_field: 0.3
min_confidence_to_report: 0.6
```

মানে করলে দাঁড়ায়: *"একটা interface খোঁজো যার ঠিক ১টা method আছে (role নাম দাও `strategy_interface`) → সেটার কমপক্ষে ২টা implementer আছে কিনা চেক করো → এমন একটা class খোঁজো যার field সেই interface-টাইপের (role নাম দাও `context`) → সেই `context` class সত্যিই সেই field-কে delegate করছে কিনা চেক করো।"* প্রতিটা ধাপ পাস হলে তার weight যোগ হয়ে চূড়ান্ত confidence বের হয়।

`Observer`-এর spec হুবহু একই শেপ, শুধু `composition_field_of_type` এর জায়গায় `collection_composition_field_of_type` — অর্থাৎ single field না, list field (Subject একগুচ্ছ observer রাখে, Strategy-র Context একটামাত্র strategy রাখে)।

---

## ৭. মোট ২৩টা pattern এবং তাদের Tier

`tier` জিনিসটা **শুধুই presentational/confidence-context**, detection লজিককে প্রভাবিত করে না — evidence কতটা নির্ভরযোগ্য/সম্পূর্ণ সেটার একটা সংকেত। কম `tier` মানে predicate-টা approximate/co-occurrence-based, control-flow বা type-parameter এর মতো ডেটার অভাবে পুরোপুরি verify করতে পারছে না।

| Pattern | Category | Tier | Min confidence |
|---|---|---|---|
| Factory Method | Creational | high | 0.60 |
| Abstract Factory | Creational | high | 0.60 |
| Builder | Creational | high | 0.60 |
| Prototype | Creational | high | 0.60 |
| Singleton | Creational | **medium** | 0.60 |
| Adapter | Structural | high | 0.60 |
| Bridge | Structural | medium | 0.55 |
| Composite | Structural | high | 0.60 |
| Decorator | Structural | high | 0.60 |
| Facade | Structural | medium | 0.60 |
| Flyweight | Structural | **low** | 0.50 |
| Proxy | Structural | high | 0.60 |
| Chain of Responsibility | Behavioral | medium | 0.55 |
| Command | Behavioral | high | 0.60 |
| Interpreter | Behavioral | **low** | 0.50 |
| Iterator | Behavioral | high | 0.60 |
| Mediator | Behavioral | medium | 0.55 |
| Memento | Behavioral | **low** | 0.50 |
| Observer | Behavioral | high | 0.60 |
| State | Behavioral | high | 0.60 |
| Strategy | Behavioral | high | 0.60 |
| Template Method | Behavioral | high | 0.60 |
| Visitor | Behavioral | high | 0.60 |

> **Simple Factory বাদ:** আগে একটা ২৪তম "Factory (simple)" pattern ছিল (`specs/factory.yaml`, `factory_candidates` predicate দিয়ে)। এটা GoF-এর আসল ২৩টা pattern-এর অংশ না এবং false-positive বেশি দিত, তাই spec, category, definition আর test fixture সব সরিয়ে ফেলা হয়েছে — `specs/` এ এখন ২৩টা YAML ফাইল। (`factory_candidates` predicate কোডে রয়ে গেছে কিন্তু কোনো spec ওটা call করে না।)

**কেন Singleton medium** — private constructor আর null-check guard দুটোই Singleton-এর আসল সংজ্ঞার অংশ, কিন্তু গ্রাফে access-modifier বা control-flow ডেটা নেই, তাই এটা "co-occurrence of two signals" (self-field + self-instantiating method), সত্যিকারের enforcement verify না।

**কেন Flyweight/Interpreter/Memento low** — এই তিনটার predicate-ই openly approximate: Flyweight-এ List-vs-Dict cache আলাদা করার ডেটা নেই, Interpreter Composite-এর সাথে structurally identical (grammar-ডেটা ছাড়া আলাদা করা যায় না), Memento-তে method parameter-এর টাইপ verify করা যায় না।

---

## ৮. একটা special case — Language Idiom Singleton (`patterns/language_idioms/singleton_idioms.py`)

Go-এর `sync.Once` আর Rust-এর `lazy_static!`/`OnceCell`/`OnceLock` — এগুলো Singleton pattern প্রকাশ করে **কোনো self-typed field ছাড়াই** (instance-টা রানটাইম/ম্যাক্রো নিজেই মালিকানা রাখে, graph-এ কোনো field-edge তৈরি হয় না)। এটাই পুরো GoF engine-এর একমাত্র জায়গা যেটা genuinely structural না — raw file **content**-এর উপর regex চালানো হয় (`sync\.Once`, `lazy_static!\s*\{`, `OnceCell<`, `OnceLock<`)।

এই ম্যাচগুলো:
- Upload-এর সময় একবারই স্ক্যান হয়ে cache হয় (তখনই file content available থাকে)
- rule-engine-এর confidence score-এর সাথে **কখনো মিশে না** — আলাদাভাবে `"heuristic": true`, `"tier": "heuristic"`, `"confidence": null` ট্যাগ দিয়ে রিপোর্ট হয়, যাতে UI আলাদা করে দেখাতে পারে ("ভেরিফাই করে দেখো নিজে")

---

## ৯. API — `/api/gof-patterns/{session_id}` (`main.py:2048`)

```
1. cache থেকে singleton_idiom_matches (upload-এর সময়ই স্ক্যান করা) বের করে idiom_patterns লিস্ট বানায়
2. Neo4j থেকে get_class_graph() দিয়ে raw graph টানে
3. SessionGraphView.from_raw(raw_graph) দিয়ে একবার view বানায়
4. evaluate_all(view) — patterns/specs/*.yaml এর সব ২৩টা spec একই view-এর বিরুদ্ধে চালায়
5. structural_patterns + idiom_patterns একসাথে merge করে confidence অনুযায়ী sort করে (structural আগে, heuristic শেষে — কারণ heuristic এর confidence None)
```

Response shape (প্রতিটা pattern-এর জন্য):
```json
{
  "pattern": "Strategy",
  "category": "Behavioral",
  "tier": "high",
  "confidence": 0.85,
  "bindings": { "strategy_interface": "PaymentMethod", "context": "PaymentProcessor" },
  "evidence": ["...flat evidence list..."],
  "evidence_detail": [
    { "predicate": "interface_with_single_method", "label": "Interface shape", "strength": 1.0, "evidence": [...] },
    { "predicate": "min_implementers", "label": "Implementer count", "strength": 1.15, "evidence": [...] }
  ],
  "heuristic": false,
  "definition": "Lets interchangeable algorithms or behaviors be swapped in and out behind a shared interface.",
  "why_it_matters": "Makes it easy to add a new behavior without changing the code that uses it."
}
```

`definition` / `why_it_matters` আসে `rule_engine.pattern_info()` থেকে (`PATTERN_DEFINITIONS` dict) — প্রতিটা pattern-এর plain-language ব্যাখ্যা, UI-তে ইউজারকে দেখানোর জন্য। `Singleton (language idiom)` এর জন্যও একই (base name `Singleton` দিয়ে lookup হয়)। `evidence_detail`-এর প্রতিটা entry-তে `role` ফিল্ডও থাকে (generator step হলে কোন role bind হলো; idiom match-এ `null`)।

`evidence` flat (সব requirement এর evidence এক লিস্টে) — পুরনো consumer-দের জন্য; `evidence_detail` per-requirement গ্রুপ করা (কোন structural check কী প্রমাণ করলো, কতটা strong) — "কেন এই ম্যাচ হলো" প্রশ্নের বিস্তারিত উত্তর, UI-তে breakdown দেখানোর জন্য।

---

## ১০. সারসংক্ষেপ — ডিজাইনের মূল দর্শন

1. **No keyword/naming heuristic** — পুরনো ভার্সনে `getInstance`, `notify`, `Factory` ইত্যাদি নাম খুঁজে pattern ধরা হতো; এখন সম্পূর্ণ structural (কে কী implement করছে, কার field কী টাইপ, কে কাকে call করছে)।
2. **Predicate library = shared vocabulary** — একই predicate (`delegates_to_field`, `has_self_referential_field`) অনেকগুলো pattern-এর spec-এ পুনর্ব্যবহার হয়; নতুন pattern লিখতে বেশিরভাগ সময় নতুন Python লজিক লাগে না।
3. **Evidence-first, never a bare bool** — প্রতিটা predicate প্রমাণ সহ verdict দেয়, যাতে false-positive হলেও ইউজার নিজে যাচাই করতে পারে।
4. **Confidence gradation via `strength`** — শুধু pass/fail না, evidence কতটা জোরালো সেটাও স্কোরে ধরা হয়।
5. **Known limitations ডকুমেন্টেড, লুকানো না** — Flyweight/Interpreter/Memento-র approximation, Decorator/Chain-of-Responsibility-র overlap, `fluent_return_self`-এর stub — সবকিছু কোডেই কমেন্ট আকারে স্বীকার করা আছে, fake heuristic দিয়ে ঢাকা হয়নি।

---

# Presentation-এর জন্য: সহজ ব্যাখ্যা + প্রতিটা pattern-এর detection

> এই অংশ সরাসরি প্রশ্নের উত্তর দেওয়ার জন্য — "এটা কীভাবে detect হলো?"
> **মূল কথা:** আমরা class-এর *নাম* দেখে pattern চিনি না। code থেকে একটা structure graph বানাই (কে কাকে implement করে, কার field কোন type-এর, কোন method কাকে call করে ও কী `new` করে), তারপর প্রতিটা pattern-এর "শেপের নিয়ম" সেই graph-এর সাথে মেলাই। মিললে pattern পাওয়া গেছে, আর কী কী মিলেছে সেটা evidence হিসেবে দেখাই। কোনো LLM নেই।

## ১১. Step-by-step: সব pattern-এর জন্য একই ৭টা ধাপ

### ধাপ ১ — Source code parse করা (`analyzer/parser.py`)
Tree-sitter দিয়ে প্রতিটা ফাইল parse করা হয় (Python, Java, JS/TS, Go, Rust ...)। প্রতিটা class/interface থেকে বের করা হয়:
- class-এর ধরন (`class` / `abstract_class` / `interface` / `struct` / `trait`)
- কে কাকে `extends` / `implements` করে
- **field গুলো** — নাম, type, আর সেটা **collection (list/array/map) কিনা** (`is_collection`)
- **method গুলো** — নাম, abstract কিনা, সে **কোন method call করছে** (`calls`), আর সে **কোন class-এর object বানাচ্ছে** (`instantiates`)

### ধাপ ২ — Class graph বানিয়ে Neo4j-তে রাখা (`db.py: store_class_graph`)
Upload-এর সময়ই class → node, আর এই relation গুলো edge হয়ে যায়: `IMPLEMENTS`, `INHERITS_FROM`, `HAS_FIELD` (সাথে `is_collection`), `METHOD_OF` (সাথে `calls`, `instantiates`)।

### ধাপ ৩ — In-memory `SessionGraphView` বানানো (`patterns/graph_view.py`)
`/api/gof-patterns/{session_id}` call হলে Neo4j থেকে graph একবার তুলে একটা in-memory structure বানানো হয়। এখানে ৪টা জিনিস হিসাব করা থাকে যেগুলো সব pattern ব্যবহার করে:
- `implementers_of` / `subclasses_of` — কে কাকে implement/inherit করে
- `interfaces_of` — transitive (A→B→C হলে A, C-ও implement করে ধরা হয়)
- `effective_fields_of` — নিজের field + parent থেকে পাওয়া field
- `methods_of` — প্রতিটা method-এর `calls` (callee কোন class-এ resolve হলো সহ) ও `instantiates`

### ধাপ ৪ — Normalization (`patterns/normalization.py`, `config/method_roles.yaml`)
ভাষাভেদে method নাম আলাদা (`next`/`__next__`/`Next`)। তাই নামের বদলে **role** দিয়ে জিজ্ঞেস করা হয়, যেমন `ITERATOR_NEXT`, `BUILDER_BUILD`, `PROTOTYPE_CLONE`, `COMMAND_EXECUTE`। আবার `interface` / ABC / `trait` সব `INTERFACE_LIKE` হিসেবে একই ধরা হয়।

### ধাপ ৫ — প্রতিটা pattern-এর YAML spec load করা (`patterns/specs/*.yaml`, মোট ২৩টা)
প্রতিটা spec বলে: *"এই pattern মানে এই কয়টা শর্ত, একটার পর একটা, সব পূরণ হতে হবে"* — আর প্রতিটা শর্তের একটা `weight` আছে।

### ধাপ ৬ — Rule engine শর্তগুলো চালায় (`patterns/rule_engine.py`)
শর্ত দুই ধরনের:
- **Generator** — পুরো project স্ক্যান করে *candidate* খোঁজে (যেমন "যেসব interface-এ ঠিক ১টা method")। প্রতিটা candidate-কে একটা **role নাম** দেওয়া হয় (`strategy_interface`, `context`...)।
- **Checker** — আগে পাওয়া role-কে যাচাই করে (যেমন "এই interface-এর কমপক্ষে ২টা implementer আছে?")।

Engine প্রতিটা candidate try করে (backtracking)। কোনো checker fail করলে ওই candidate বাদ — **সব শর্ত mandatory**, partial match নেই।

### ধাপ ৭ — Confidence হিসাব ও report
```
confidence = Σ ( প্রতিটা শর্তের weight × evidence-এর strength )   (সর্বোচ্চ 1.0)
```
`confidence < min_confidence_to_report` হলে report-ই হয় না। যা report হয় তার সাথে যায়: `pattern`, `tier` (high/medium/low), `confidence`, `bindings` (কোন role-এ কোন class), আর `evidence` (কোন ফাইলের কোন লাইনে কী পাওয়া গেছে)।

### একটা সম্পূর্ণ উদাহরণ — Strategy (ধাপ ৫-৭ হাতে-কলমে)
```python
class PaymentMethod(ABC):            # interface, ১টা method
    def pay(self, amt): ...
class CardPayment(PaymentMethod): ... # implementer 1
class UpiPayment(PaymentMethod): ...  # implementer 2
class Checkout:
    def __init__(self, m: PaymentMethod):
        self.method = m               # field, type = PaymentMethod
    def run(self, amt):
        self.method.pay(amt)          # field-এর method call
```
| ধাপ | Engine কী করে | ফল | Weight |
|---|---|---|---|
| ১ | `interface_with_single_method` — ঠিক ১টা method-ওয়ালা interface খোঁজে | `PaymentMethod` → role `strategy_interface` | 0.2 |
| ২ | `min_implementers` — ≥২ implementer? | `CardPayment`, `UpiPayment` ✔ | 0.3 |
| ৩ | `composition_field_of_type` — কোন class-এর field-এর type `PaymentMethod`? | `Checkout` → role `context` | 0.2 |
| ৪ | `delegates_to_field` — `Checkout`-এর কোনো method কি `pay()` call করে? | `Checkout.run()` → `pay()` ✔ | 0.3 |

মোট = 1.0 ≥ 0.6 → **Strategy detected**, `bindings = {strategy_interface: PaymentMethod, context: Checkout}`।

---

## ১২. প্রতিটা Pattern আলাদাভাবে কীভাবে detect হয়

প্রতিটা pattern-এ চারটা জিনিস দেওয়া আছে: **কী খোঁজে**, **কোন predicate/spec**, **অন্য pattern থেকে আলাদা কীভাবে**, আর **সীমাবদ্ধতা** (থাকলে)। Tier = evidence কতটা নির্ভরযোগ্য।

### 🟦 Creational

#### ১. Factory Method — `factory_method.yaml` — tier high, min 0.60
- **শেপ:** একটা abstract/interface **Creator**-এ abstract method আছে। কমপক্ষে ২টা subclass সেই method override করে এবং প্রতিটা **আলাদা আলাদা product class `new` করে**।
- **Predicate:** `factory_method_candidates` (একটাই generator, weight 0.85)।
- **যাচাই:** abstract method বের করা → subclass ≥২ → প্রতিটা subclass-এর override কী `instantiates` করছে → distinct product ≥২।
- **আলাদা কীভাবে:** product-এর বৈচিত্র্য আসে *subclass* থেকে (Abstract Factory-তে একসাথে অনেক product)।

#### ২. Abstract Factory — `abstract_factory.yaml` — tier high, min 0.60
- **শেপ:** একটা interface-এ **২+ creation method**; ২+ implementer, প্রতিটা implementer-এর method গুলো একেকটা product বানায়, আর **implementer ভেদে product-এর পুরো পরিবার (family) আলাদা**।
- **Predicate:** `abstract_factory_candidates` (weight 0.85)।
- **যাচাই:** interface-এর method ≥২ → implementer ≥২ → প্রতিটা implementer কমপক্ষে ২টা product বানায় → implementer গুলোর product-set আলাদা (যেমন Windows: {Button, Checkbox} vs Mac: {MacButton, MacCheckbox})।
- **আলাদা কীভাবে:** Factory Method-এর মতো, কিন্তু একাধিক product-এর family।

#### ৩. Builder — `builder.yaml` — tier high, min 0.60
- **শেপ:** একটা class-এ `build()`-role method (`build`/`Build`/`construct`) যেটা **অন্য class-এর** object বানায়, সাথে **২+ configuration/setter-ধরনের method** যেগুলো নিজে কিছু construct করে না।
- **Predicate:** `builder_candidates` (weight 0.8)।
- **সীমাবদ্ধতা:** method chaining (`return self`) verify করা যায় না — parser return-expression নেয় না, তাই `fluent_return_self` ইচ্ছে করেই ব্যবহার করা হয়নি।

#### ৪. Prototype — `prototype.yaml` — tier high, min 0.60
- **শেপ:** `clone()`-role method (`clone`/`Clone`/`__copy__`/`__deepcopy__`) যেটা **নিজের class-এরই** নতুন instance বানায়।
- **Predicate:** `prototype_candidates` (weight 0.8)।
- **আলাদা কীভাবে:** Factory Method-এর উল্টো — সেখানে *অন্য* class বানায়, এখানে *নিজের*।

#### ৫. Singleton — `singleton.yaml` — tier **medium**, min 0.60
- **শেপ:** class-এর একটা **নিজের type-এর (non-collection) field** আছে (instance slot) **এবং** একটা method আছে যেটা **নিজের নতুন instance বানায়** (lazy accessor)।
- **Predicate:** `singleton_candidates` (weight 0.65)। কোনো `getInstance` নাম দেখা হয় না।
- **কেন medium:** private constructor আর null-check graph-এ দেখা যায় না — তাই দুটো signal-এর co-occurrence মাত্র।
- **Go/Rust এর জন্য আলাদা পথ:** `sync.Once`, `lazy_static!`, `OnceCell`, `OnceLock` — এগুলোতে self-typed field থাকে না, তাই upload-এর সময় raw content-এ regex চালানো হয়। এগুলো `"heuristic": true`, `confidence: null` দিয়ে আলাদা দেখানো হয়, structural score-এর সাথে মেশে না।

### 🟩 Structural

#### ৬. Adapter — `adapter.yaml` — tier high, min 0.60
- **শেপ:** class একটা **Target** abstraction implement করে, কিন্তু তার একটা field-এর type **সম্পূর্ণ অন্য কিছু (Adaptee)** — যে Target implement করে না — এবং class সেই field-এর method call করে (delegate)।
- **Predicate:** `adapter_candidates` (weight 0.8)।
- **আলাদা কীভাবে:** Decorator-এর field *একই* abstraction-এর, Adapter-এর field *ভিন্ন* type-এর।

#### ৭. Bridge — `bridge.yaml` — tier medium, min 0.55
- **শেপ:** Strategy-র পুরো chain (১-method interface → ≥২ implementer → composing class → delegation) **+ composing class-এর নিজেরই ≥২ subclass**।
- **Predicate:** `interface_with_single_method` (0.1), `min_implementers` (0.15), `composition_field_of_type` (0.15), `delegates_to_field` (0.2), `has_min_subclasses` (**0.4** — মূল differentiator)।
- **আলাদা কীভাবে:** Strategy-র Context-এর subclass hierarchy থাকে না; Bridge-এর Abstraction-এর থাকে — দুটো স্বাধীন hierarchy composition দিয়ে জোড়া।
- **কেন medium:** আসল Implementor interface-এ প্রায়ই ১টার বেশি method থাকে, কিন্তু আমরা "ঠিক ১টা method" ধরি — তাই কিছু real Bridge miss হতে পারে।

#### ৮. Composite — `composite.yaml` — tier high, min 0.60
- **শেপ:** class-এর একটা **collection field আছে যার element type নিজেরই (বা নিজের interface-এর)** এবং class সেই field-এর method call করে (`for child in children: child.op()`)।
- **Predicate:** `list_of_own_type_field_candidates` (0.6) + `delegates_to_field` (0.4)।
- **আলাদা কীভাবে:** **list** → Composite; **single** field → Decorator/Proxy/Chain।

#### ৯. Decorator — `decorator.yaml` — tier high, min 0.60
- **শেপ:** class-এর একটা **single field** আছে যার type সেই abstraction যেটা class নিজেও implement করে (**is-a এবং has-a একই জিনিস**), এবং wrapping method **forward করার পাশাপাশি আরও কাজ করে** (মোট call সংখ্যা > ১)।
- **Predicate:** `single_field_of_own_type_candidates` (0.15) + `field_typed_as_own_interface` (0.35) + `is_decorator_wrapping` (0.5)।
- **আলাদা কীভাবে:** Proxy-র সাথে পার্থক্য শুধু "extra behavior যোগ করে কিনা"।

#### ১০. Proxy — `proxy.yaml` — tier high, min 0.60
- **শেপ:** Decorator-এর হুবহু একই শেপ, কিন্তু wrapping method **প্রায় pure passthrough** (মোট call ≤ ১)।
- **Predicate:** `single_field_of_own_type_candidates` (0.15) + `field_typed_as_own_interface` (0.35) + `is_proxy_wrapping` (0.5)।

#### ১১. Facade — `facade.yaml` — tier medium, min 0.60
- **শেপ:** একটা class **৫+ আলাদা class-কে call করে** (fan-out), কিন্তু নিজে খুব কম class-এর দ্বারা call হয় (callers ≤ fan-out-এর ৪০%) — subsystem-এর সামনে একটা সহজ entry point।
- **Predicate:** `facade_candidates` (weight 0.65), threshold গুলো YAML থেকে বদলানো যায় (`min_fan_out: 5`, `max_caller_ratio: 0.4`)।
- **কেন medium:** শুধু call-graph-এর আকার দেখা হয়, "উদ্দেশ্য" বোঝা যায় না।

#### ১২. Flyweight — `flyweight.yaml` — tier **low**, min 0.50
- **শেপ:** একটা method কোনো product **construct করে** এবং একই class **সেই product type-এর collection field রাখে** (cache-এর আনুমানিক রূপ)।
- **Predicate:** `flyweight_candidates` → `cache_keyed_return` (weight 0.5)।
- **কেন low:** আসল cache হয় Dict/Map; কিন্তু graph-এ field-এর type text save হয় না, তাই List আর Dict আলাদা করা যায় না।

### 🟧 Behavioral

#### ১৩. Chain of Responsibility — `chain_of_responsibility.yaml` — tier medium, min 0.55
- **শেপ:** class-এর একটা **single field আছে নিজের/shared handler type-এর** এবং class সেই field-কে delegate করে ("আমি না পারলে next-কে দাও")।
- **Predicate:** `single_field_of_own_type_candidates` (0.4) + `delegates_to_field` (0.6)।
- **সীমাবদ্ধতা (স্বীকৃত):** "শর্তসাপেক্ষে forward" আর "সবসময় forward" আলাদা করতে control-flow লাগে, যা নেই — তাই Decorator/Proxy-র সাথে একই class-এ একসাথে report হতে পারে। এটা bug না, documented আচরণ।

#### ১৪. Command — `command.yaml` — tier high, min 0.60
- **শেপ:** একটা interface যেটার একটা method **`execute`-role** (`execute`/`run`...), এবং ≥২ implementer।
- **Predicate:** `interface_with_single_role_method` (0.5) + `min_implementers` (0.5)।
- **আলাদা কীভাবে:** Strategy-তে method-এর নাম যা-ই হোক চলে; Command-এ নির্দিষ্ট `execute`-role লাগে। `undo()` থাকলেও চলে (শুধু একমাত্র method হতে হয় না)।

#### ১৫. Interpreter — `interpreter.yaml` — tier **low**, min 0.50
- **শেপ:** self-referential field + `interpret()`-role method যেটা **সেই field-এর `interpret()`-কে call করে**।
- **Predicate:** `interpreter_candidates` (weight 0.5)।
- **কেন low:** Composite-এর সাথে structure হুবহু এক; শুধু method-এর role আলাদা। Grammar-এর তথ্য ছাড়া আলাদা করা অসম্ভব — তাই দুটো একসাথে আসতে পারে।

#### ১৬. Iterator — `iterator.yaml` — tier high, min 0.60
- **শেপ:** একই class-এ **`next`-role এবং `hasNext`-role দুটো method-ই** আছে।
- **Predicate:** `every_class` (generator) + `has_role_method(ITERATOR_NEXT)` + `has_role_method(ITERATOR_HAS_NEXT)` (weight 0.9)।
- **কেন জোড়া:** শুধু `next()` নামের method অনেক জায়গায় থাকে, তাই জোড়াটাই আসল signal।

#### ১৭. Mediator — `mediator.yaml` — tier medium, min 0.55
- **শেপ:** **২+ colleague class সবাই একটা common hub class-কে call করে, কিন্তু colleague-রা নিজেদের মধ্যে সরাসরি call করে না।**
- **Predicate:** `mediator_candidates` (weight 0.7) — hub আর colleague group নিজে খুঁজে বের করে (`fan_out_to_common_hub` + `no_direct_edges_between`-এর যুক্তি)।

#### ১৮. Memento — `memento.yaml` — tier **low**, min 0.50
- **শেপ:** Originator class-এ `save`-role method যেটা **অন্য (Memento) class বানায়** + একই class-এ `restore`-role method।
- **Predicate:** `memento_candidates` (weight 0.5)।
- **কেন low:** `restore()` যে সত্যিই Memento object parameter হিসেবে নেয় তা verify করা যায় না — parameter type graph-এ নেই, শুধু method-এর অস্তিত্ব দেখা হয়।

#### ১৯. Observer — `observer.yaml` — tier high, min 0.60
- **শেপ:** Strategy-র হুবহু chain, কিন্তু Subject-এর field **collection (list of observers)**।
- **Predicate:** `interface_with_single_method` (0.2) → `min_implementers ≥২` (0.3) → `collection_composition_field_of_type` (0.2) → `delegates_to_field` (0.3)।
- **আলাদা কীভাবে:** Strategy = **১টা** strategy field; Observer = **list** field। `notify`/`subscribe` নাম দেখা হয় না।

#### ২০. State — `state.yaml` — tier high, min 0.60
- **শেপ:** Strategy-র chain **+ উল্টো দিকের edge**: State-এর কোনো implementer নিজেই Context type-এর একটা field রাখে (back-reference, `context.set_state(...)` করার জন্য)।
- **Predicate:** Strategy-র ৪টা (0.1 / 0.15 / 0.1 / 0.15) + `any_implementer_has_field_of_type` (**0.4** — মূল differentiator)।
- **আলাদা কীভাবে:** Strategy-র implementer তার Context-কে চেনেই না; State-এর চেনে। (সর্বোচ্চ confidence 0.9।)

#### ২১. Strategy — `strategy.yaml` — tier high, min 0.60
- **শেপ:** ১-method interface → ≥২ implementer → একটা Context class যার **single field** ওই interface-type-এর → Context সেই field-এর method call করে।
- **Predicate:** উপরের উদাহরণ দেখো (0.2 / 0.3 / 0.2 / 0.3)।

#### ২২. Template Method — `template_method.yaml` — tier high, min 0.60
- **শেপ:** একই class-এ একটা **abstract method** আছে, এবং ওই class-এরই একটা **concrete (body-ওয়ালা) method সেই abstract method-কে call করে**।
- **Predicate:** `every_class` + `abstract_method_called_from_concrete_sibling_method` (weight 0.9)।
- **Abstract চেনা:** Java/TS/Go/Rust-এ body-ছাড়া signature, Python-এ `@abstractmethod`।

#### ২৩. Visitor — `visitor.yaml` — tier high, min 0.60
- **শেপ:** **Double dispatch** — Element class Visitor-এর কোনো method call করে (`accept → visitX`), আর ওই Visitor method আবার Element-এর কোনো method call করে (`visitX → element.getY()`)।
- **Predicate:** `double_dispatch_candidates` (weight 0.8)।
- **কেন একই নামের callback লাগে না:** সত্যিকারের Visitor-এ `visitX` আবার `accept()` ডাকলে infinite recursion হতো — সে সাধারণত অন্য method (getter) ডাকে।

---

## ১৩. দ্রুত তুলনা: কোন "ভাইবোন" pattern কীভাবে আলাদা হয়

| জোড়া | আলাদা করার structural সূত্র |
|---|---|
| Strategy vs Observer | field **single** vs **collection** |
| Strategy vs State | State-এর implementer-এর কাছে Context-এর **back-reference** আছে |
| Strategy vs Bridge | Bridge-এর composing class-এর নিজের **subclass hierarchy** (≥২) আছে |
| Strategy vs Command | interface-এর method-এর **role = execute** |
| Decorator vs Proxy | wrapping method **extra call করে (>১)** বনাম pure passthrough (≤১) |
| Decorator vs Adapter | field-এর type **একই abstraction** বনাম **সম্পূর্ণ অন্য type** |
| Composite vs Decorator/Proxy | field **list** বনাম **single** |
| Composite vs Interpreter | Interpreter-এ method-এর role = `interpret` (তবু ambiguous) |
| Factory Method vs Abstract Factory | ১টা abstract method বনাম interface-এ **২+ method-এর product family** |
| Factory Method vs Prototype | **অন্য** class বানায় বনাম **নিজের** class বানায় |

## ১৪. Presentation-এ সৎভাবে যা বলা উচিত (Limitations)

1. **Static, structural analysis** — runtime আচরণ দেখা হয় না।
2. **Control-flow নেই** — তাই Decorator / Chain of Responsibility / Proxy একই class-এ একসাথে আসতে পারে।
3. **Parameter/return type ও access modifier নেই** — তাই Singleton (private constructor), Memento (restore-এর parameter), Builder (fluent return) আংশিক যাচাই; এজন্যই Singleton **medium**, Memento/Flyweight/Interpreter **low** tier।
4. **Delegation-এর call field দিয়ে হয়েছে কিনা** নিশ্চিত করা যায় না — callee class unambiguous হলে strength 1.0, নাম-মিল মাত্র হলে 0.8।
5. প্রতিটা report-এর সাথে **evidence** (ফাইল:লাইন) যায়, তাই false positive হলে ব্যবহারকারী নিজে যাচাই করতে পারে।

---

---

## ১৫. নতুন pattern যোগ করতে হলে কী করতে হয়

1. **শেপ যদি existing predicate দিয়ে বোঝানো যায়** — শুধু একটা নতুন YAML spec লিখলেই হয়, Python কোড লাগে না।
2. **যদি না যায়** — একটা নতুন predicate (Python function) লিখতে হয়:
   - `predicates.py`-এ function লেখা (`SessionGraphView` থেকে ডেটা পড়ে, result-এর সাথে evidence দেয়),
   - `rule_engine.py`-এ predicate-এর নাম function-এর সাথে register করা (চাইলে একটা label-ও),
   - তারপর YAML spec লেখা।

   তবুও **engine-এর core, matching algorithm আর confidence হিসাব বদলাতে হয় না** — শুধু একটা নতুন "শব্দ" (predicate) যোগ হয়। এই project-এ Builder, Prototype, Facade, Mediator ইত্যাদির জন্য আলাদা generator predicate লিখতে হয়েছে, তাই "শুধু YAML" সব pattern-এর ক্ষেত্রে সত্যি না।
3. **যদি graph-এই ডেটা না থাকে** (যেমন method-এর return value, `if`-এর ভেতরের logic, parameter type) — নতুন predicate লিখেও হবে না; আগে parser-কে ওই ডেটা capture করতে হবে (যেমন `fluent_return_self`-এর সমস্যা)।

**Presentation-এ বলার মতো করে:** *"নতুন pattern যোগ করতে engine-এর core বদলাতে হয় না। শেপ existing predicate দিয়ে বোঝানো গেলে শুধু YAML লিখি; না গেলে একটা নতুন predicate যোগ করে তারপর YAML লিখি।"*

---

## ১৬. Presentation-এ সংক্ষেপে যা বলবো (সহজ ভাষায়)

### ১. কী করেছি (৩০ সেকেন্ড)
> "আমরা code-এর **structure** দেখে ২৩টা GoF design pattern detect করি। Class-এর নাম দেখি না — যেমন `getInstance` নাম খুঁজি না। আমরা দেখি **কোন class কাকে implement করে, কার field কোন type-এর, আর কোন method কাকে call করে**। কোনো LLM ব্যবহার হয়নি; পুরো process rule-based আর deterministic।"

### ২. কীভাবে কাজ করে (৪টা ধাপ)
1. **Parse:** code থেকে class, field, method আর তাদের call / object-creation বের করি।
2. **Graph:** সব কিছু একটা graph-এ রাখি (Neo4j-তে)।
3. **Rule match:** প্রতিটা pattern-এর জন্য একটা ছোট "শেপের নিয়ম" (YAML) লেখা আছে। আমরা সেটা graph-এর সাথে মেলাই।
4. **Result:** মিললে pattern-এর নাম, confidence score আর proof দেখাই।

### ৩. একটা উদাহরণ (Strategy)
> "ধরেন একটা interface-এ একটা method আছে, যেমন `pay()`। তার দুটো implementer আছে — `CardPayment` আর `UpiPayment`। একটা class `Checkout` ওই interface-টাকে field হিসেবে রাখে আর `pay()` call করে। এই শেপ মিললে আমরা বলি **Strategy pattern**।"

### ৪. Pattern গুলো কীভাবে আলাদা হয়
> "কিছু pattern-এর শেপ প্রায় এক; একটা ছোট detail-এ আলাদা:"
- **Strategy vs Observer:** Strategy-তে field একটা, Observer-এ field list।
- **Decorator vs Proxy:** Decorator extra কাজ করে, Proxy শুধু forward করে।
- **Strategy vs State:** State-এর implementer-রা Context-কে চেনে।

### ৫. Confidence আর proof
> "প্রতিটা match-এর সাথে confidence score আর **proof** থাকে — মানে কোন ফাইলের কোন লাইনে কী পাওয়া গেছে। তাই false positive হলে user নিজে check করতে পারে।"

### ৬. Limitation (সত্যি বলা ভালো)
> "আমরা static analysis করি, runtime দেখি না। Control-flow, parameter type আর private constructor দেখতে পারি না। তাই Decorator, Proxy আর Chain of Responsibility কখনো একসাথে আসতে পারে। আর Singleton, Memento, Flyweight, Interpreter-এর tier কম রেখেছি। এই limitation আমরা লুকাইনি, report-এ লিখে দিয়েছি।"

---

## ১৭. Teacher-রা যা জিজ্ঞেস করতে পারেন

- **"কেন LLM ব্যবহার করোনি?"** — Rule-based হলে result প্রতিবার একই আসে, আর কেন match হলো তা proof দিয়ে দেখানো যায়। LLM-এ এই guarantee দেওয়া কঠিন।
- **"নাম দেখে detect করলে হতো না?"** — নাম দেখলে class-এর নাম বদলালেই pattern miss হতো, আর ভুল নাম দিলে false positive হতো। Structure দেখলে নাম যা-ই হোক কাজ করে।
- **"নতুন pattern add করতে হলে?"** — Engine-এর core বদলাতে হয় না। শেপ যদি আমাদের predicate library আগেই cover করে, শুধু একটা নতুন YAML file লিখলেই হয়। না করলে আগে একটা নতুন predicate (Python function) যোগ করে তারপর YAML লিখতে হয় (বিস্তারিত §১৫)।
- **"কোন pattern নিশ্চিত, কোনটা অনিশ্চিত?"** — `tier` দিয়ে বলা আছে: high = শেপ পুরোপুরি যাচাই হয়; medium/low = কিছু তথ্য graph-এ নেই (যেমন Singleton-এর private constructor), তাই আনুমানিক।
