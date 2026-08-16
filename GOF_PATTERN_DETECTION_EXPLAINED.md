# GoF Design Pattern Detection — কী কী লজিক দিয়ে কাজ করে

এই ডকুমেন্টে ব্যাখ্যা করা হয়েছে GoF (Gang of Four) design pattern গুলো (Strategy, Singleton, Decorator, Observer, ইত্যাদি ২৪টা pattern) কীভাবে **detect** করা হয় — কোন ফাইলে কী লজিক আছে, ডেটা কোথা থেকে আসে, আর confidence score কীভাবে হিসাব হয়।

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
| `factory_candidates` | branching method (if/elif দিয়ে ২+ আলাদা product বানায়) অথবা ২+ আলাদা method প্রতিটা আলাদা product বানায় |
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

## ৭. মোট ২৪টা pattern এবং তাদের Tier

`tier` জিনিসটা **শুধুই presentational/confidence-context**, detection লজিককে প্রভাবিত করে না — evidence কতটা নির্ভরযোগ্য/সম্পূর্ণ সেটার একটা সংকেত। কম `tier` মানে predicate-টা approximate/co-occurrence-based, control-flow বা type-parameter এর মতো ডেটার অভাবে পুরোপুরি verify করতে পারছে না।

| Pattern | Category | Tier | Min confidence |
|---|---|---|---|
| Factory Method | Creational | high | 0.60 |
| Abstract Factory | Creational | high | 0.60 |
| Builder | Creational | high | 0.60 |
| Prototype | Creational | high | 0.60 |
| Singleton | Creational | **medium** | 0.60 |
| Factory (simple) | Creational | medium | 0.55 |
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

**কেন Singleton medium** — private constructor আর null-check guard দুটোই Singleton-এর আসল সংজ্ঞার অংশ, কিন্তু গ্রাফে access-modifier বা control-flow ডেটা নেই, তাই এটা "co-occurrence of two signals" (self-field + self-instantiating method), সত্যিকারের enforcement verify না।

**কেন Flyweight/Interpreter/Memento low** — এই তিনটার predicate-ই openly approximate: Flyweight-এ List-vs-Dict cache আলাদা করার ডেটা নেই, Interpreter Composite-এর সাথে structurally identical (grammar-ডেটা ছাড়া আলাদা করা যায় না), Memento-তে method parameter-এর টাইপ verify করা যায় না।

---

## ৮. একটা special case — Language Idiom Singleton (`patterns/language_idioms/singleton_idioms.py`)

Go-এর `sync.Once` আর Rust-এর `lazy_static!`/`OnceCell`/`OnceLock` — এগুলো Singleton pattern প্রকাশ করে **কোনো self-typed field ছাড়াই** (instance-টা রানটাইম/ম্যাক্রো নিজেই মালিকানা রাখে, graph-এ কোনো field-edge তৈরি হয় না)। এটাই পুরো GoF engine-এর একমাত্র জায়গা যেটা genuinely structural না — raw file **content**-এর উপর regex চালানো হয় (`sync\.Once`, `lazy_static!\s*\{`, `OnceCell<`, `OnceLock<`)।

এই ম্যাচগুলো:
- Upload-এর সময় একবারই স্ক্যান হয়ে cache হয় (তখনই file content available থাকে)
- rule-engine-এর confidence score-এর সাথে **কখনো মিশে না** — আলাদাভাবে `"heuristic": true`, `"tier": "heuristic"`, `"confidence": null` ট্যাগ দিয়ে রিপোর্ট হয়, যাতে UI আলাদা করে দেখাতে পারে ("ভেরিফাই করে দেখো নিজে")

---

## ৯. API — `/api/gof-patterns/{session_id}` (`main.py:1909`)

```
1. cache থেকে singleton_idiom_matches (upload-এর সময়ই স্ক্যান করা) বের করে idiom_patterns লিস্ট বানায়
2. Neo4j থেকে get_class_graph() দিয়ে raw graph টানে
3. SessionGraphView.from_raw(raw_graph) দিয়ে একবার view বানায়
4. evaluate_all(view) — patterns/specs/*.yaml এর সব ২৪টা spec একই view-এর বিরুদ্ধে চালায়
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
  "heuristic": false
}
```

`evidence` flat (সব requirement এর evidence এক লিস্টে) — পুরনো consumer-দের জন্য; `evidence_detail` per-requirement গ্রুপ করা (কোন structural check কী প্রমাণ করলো, কতটা strong) — "কেন এই ম্যাচ হলো" প্রশ্নের বিস্তারিত উত্তর, UI-তে breakdown দেখানোর জন্য।

---

## ১০. সারসংক্ষেপ — ডিজাইনের মূল দর্শন

1. **No keyword/naming heuristic** — পুরনো ভার্সনে `getInstance`, `notify`, `Factory` ইত্যাদি নাম খুঁজে pattern ধরা হতো; এখন সম্পূর্ণ structural (কে কী implement করছে, কার field কী টাইপ, কে কাকে call করছে)।
2. **Predicate library = shared vocabulary** — একই predicate (`delegates_to_field`, `has_self_referential_field`) অনেকগুলো pattern-এর spec-এ পুনর্ব্যবহার হয়; নতুন pattern লিখতে বেশিরভাগ সময় নতুন Python লজিক লাগে না।
3. **Evidence-first, never a bare bool** — প্রতিটা predicate প্রমাণ সহ verdict দেয়, যাতে false-positive হলেও ইউজার নিজে যাচাই করতে পারে।
4. **Confidence gradation via `strength`** — শুধু pass/fail না, evidence কতটা জোরালো সেটাও স্কোরে ধরা হয়।
5. **Known limitations ডকুমেন্টেড, লুকানো না** — Flyweight/Interpreter/Memento-র approximation, Decorator/Chain-of-Responsibility-র overlap, `fluent_return_self`-এর stub — সবকিছু কোডেই কমেন্ট আকারে স্বীকার করা আছে, fake heuristic দিয়ে ঢাকা হয়নি।
