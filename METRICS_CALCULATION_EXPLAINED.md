# Code Metrics — কিভাবে ক্যালকুলেট করা হয়েছে

এই ডকুমেন্টে `Backend/analyzer/` প্যাকেজে যেসব কোড মেট্রিক্স (Cyclomatic Complexity,
Halstead, Maintainability Index, ইত্যাদি) ডিটেক্ট করা হয়, সেগুলোর পেছনের **লজিক**
ব্যাখ্যা করা হয়েছে। কোনো কোড স্নিপেট নেই — শুধু হিসাবের নিয়ম।

---

## ১. Cyclomatic Complexity (CC)

**ফাইল:** `parser.py`

প্রতিটা ফাংশনের জন্য CC হিসাব করা হয় দুইভাবে, ভাষা/পার্সিং-পথ অনুযায়ী —

- **Tree-sitter (AST) পথ** (Python, JS/TS, Go ইত্যাদি যেগুলোর জন্য tree-sitter
  parser আছে): ফাংশনের পুরো body-টা একটা টেক্সট হিসেবে নিয়ে তার ভেতরে
  ডিসিশন-কিওয়ার্ড কতবার আসছে সেটা গোনা হয় — `if`, `elif`, `else:`, `for`,
  `while`, `case`, `catch`, `except`, `&&`, `||`।
- **Regex fallback পথ** (Java, JS/TS-এর regex-based parser): একই ধারণা, তবে
  কিওয়ার্ড সেট একটু ছোট — `if`, `for`, `while`, `case`, `catch`, `&&`, `||`।

**সূত্র:** `CC = 1 + (প্রতিটা ডিসিশন-কিওয়ার্ডের occurrence যোগফল)`

শুরুতে বেস ভ্যালু ১ (একটা linear path তো থাকেই), তারপর প্রতিটা ব্রাঞ্চিং/লুপিং
কিওয়ার্ডের জন্য +১ করে যোগ হয়। এটা প্রকৃত McCabe Cyclomatic Complexity-এর একটা
**heuristic approximation** — control-flow graph বানিয়ে edge/node গোনা হয় না,
বরং কিওয়ার্ড-কাউন্টিং দিয়ে দ্রুত অনুমান করা হয় (multi-language support রাখার জন্য
এই ট্রেড-অফ নেওয়া হয়েছে)।

---

## ২. Nesting Depth

**ফাইল:** `heuristics.py`

ফাংশনের body-এর প্রতিটা ক্যারেক্টার একবার করে স্ক্যান করা হয় —
`{` পেলে depth counter +১, `}` পেলে depth counter −১, আর প্রতি ধাপে সর্বোচ্চ
depth-টা ট্র্যাক রাখা হয়। শেষে ফাংশনের নিজের বাইরের ব্রেস-জোড়ার জন্য ১ বিয়োগ করা
হয়, যাতে ফলাফলটা হয় শুধু **ভেতরের (inner) নেস্টিং**-এর গভীরতা — ফাংশনের নিজের
body-ই যদি সবচেয়ে বাইরের ব্লক হয়, তাহলে depth = 0 বোঝায় কোনো নেস্টেড if/for নেই।

---

## ৩. Magic Number Count

**ফাইল:** `heuristics.py`

ফাংশন body-তে যত standalone সংখ্যা (numeric literal) আছে তার regex দিয়ে খোঁজা হয়,
তারপর একটা "সাধারণভাবে বোধগম্য" সংখ্যার তালিকা (0, 1, 2, 3, −1, 10, 100, 1000)
বাদ দিয়ে বাকিগুলোকে "magic number" হিসেবে গোনা হয়। যুক্তি — এই ছোট সংখ্যাগুলো
সাধারণত সেলফ-এক্সপ্ল্যানেটরি (loop start, index offset ইত্যাদি), কিন্তু অন্য কোনো
হার্ডকোডেড সংখ্যা (যেমন 86400, 0.075) আসলে একটা named constant হওয়া উচিত।

---

## ৪. Fan-In / Fan-Out

**ফাইল:** `parser.py`

- **Fan-out** = একটা ফাংশনের ভেতর থেকে *কতগুলো ইউনিক ফাংশনকে* কল করা হচ্ছে —
  ফাংশন body পার্স করে callee-নামগুলোর সেট বানিয়ে তার সাইজ নেওয়া হয়।
- **Fan-in** = পুরো কোডবেজ জুড়ে সব ফাংশনের calls-লিস্ট একত্র করে, প্রতিটা
  ফাংশন-নাম কতবার *অন্য কারো* calls-লিস্টে আসছে সেটা গোনা হয় (একটা reverse
  lookup / frequency map)। অর্থাৎ একটা ফাংশনকে সারা কোডবেজে মোট কতজন কল করছে।

এই দুটো মেট্রিক পরে **risk level** নির্ধারণেও ব্যবহার হয়:
fan_in ≥ 10 → high risk, ≥ 3 → medium, ≥ 1 → low, 0 → none। ধারণাটা হলো — যে
ফাংশনকে অনেকে কল করে, সেটাতে পরিবর্তন আনলে ব্লাস্ট-রেডিয়াস বড়, তাই রিস্ক বেশি।

---

## ৫. Halstead Metrics (Volume, Difficulty, Effort)

**ফাইল:** `metrics.py` (`_halstead_metrics`)

পুরো কোডবেজের সব ফাইলের কনটেন্ট থেকে প্রথমে কমেন্ট আর স্ট্রিং লিটারেল বাদ দেওয়া হয়
(যাতে সেগুলো ভুলভাবে operator/operand হিসেবে না গোনা হয়)। এরপর দুই ভাগে ভাগ করা হয় —

- **Operators**: ভাষার কিওয়ার্ড (if, for, class, return, ...) এবং প্রতীক
  (`+`, `-`, `==`, `&&`, `=>` ইত্যাদি) regex দিয়ে ম্যাচ করা হয়।
- **Operands**: identifier-এর মতো টোকেন (variable/function নাম) regex দিয়ে
  ম্যাচ করা হয়, তবে যেগুলো ইতিমধ্যে operator/কিওয়ার্ড হিসেবে চিহ্নিত হয়েছে সেগুলো
  বাদ দিয়ে।

তারপর ক্লাসিক Halstead সূত্র প্রয়োগ হয়:

- `n1` = ইউনিক অপারেটরের সংখ্যা, `n2` = ইউনিক অপারেন্ডের সংখ্যা
- `N1` = মোট অপারেটর occurrence, `N2` = মোট অপারেন্ড occurrence
- **Vocabulary** = n1 + n2
- **Length** = N1 + N2
- **Volume** = Length × log₂(Vocabulary) — প্রোগ্রামটা "কতটা তথ্য বহন করছে"
- **Difficulty** = (n1 / 2) × (N2 / n2) — অপারেটরের বৈচিত্র্য আর একই operand-এর
  পুনরাবৃত্তি যত বেশি, difficulty তত বেশি
- **Effort** = Difficulty × Volume — প্রোগ্রামটা লিখতে/বুঝতে মানসিক শ্রম কেমন লাগবে
  তার প্রক্সি

এটা প্রকৃত টোকেনাইজার/লেক্সার দিয়ে নয়, regex-based approximation — তাই সব ভাষায়
কাজ করে কিন্তু নিখুঁত নয়।

---

## ৬. Maintainability Index (MI)

**ফাইল:** `metrics.py` (`_maintainability_index`)

Microsoft-এর প্রচলিত Maintainability Index ফর্মুলা ব্যবহার করা হয়েছে, যেখানে তিনটা
ইনপুট লাগে — Halstead Volume, average Cyclomatic Complexity, আর average LOC
**প্রতি ফাংশনে** (per-file LOC নয় — কারণ পুরো ফাইলের LOC ব্যবহার করলে বড়
কোডবেজে MI অস্বাভাবিকভাবে কমে যায়)।

**লজিক:**
1. একটা raw স্কোর বের করা হয় যেখানে Volume, Complexity, আর LOC — প্রতিটার
   লগারিদমিক/লিনিয়ার প্রভাব বিয়োগ করা হয় ১৭১ থেকে (Volume আর LOC-এর প্রভাব
   log স্কেলে, কারণ এগুলো বাড়লে maintainability কমে কিন্তু diminishing ভাবে)।
2. সেই raw স্কোরকে normalize করে 0–171 স্কেল থেকে 0–100 স্কেলে আনা হয়।
3. ফলাফল 0 থেকে 100-এর মধ্যে clamp করা হয় (নেগেটিভ বা ১০০-এর বেশি হতে পারবে না)।

**লেবেলিং থ্রেশহোল্ড:**
- MI ≥ 85 → **Highly Maintainable**
- MI ≥ 65 → **Maintainable**
- MI ≥ 40 → **Needs Attention**
- MI < 40 → **Hard to Maintain**

মূল কথা — Volume (কোড কতটা জটিল/বড়), Complexity (কতটা ব্রাঞ্চিং), আর ফাংশন-সাইজ
(LOC) — এই তিনটা যত বেশি, MI তত কম, অর্থাৎ কোড তত কম maintainable।

---

## ৭. Cognitive Complexity (Approximation)

**ফাইল:** `metrics.py`

এটা প্রকৃত cognitive complexity নয় (যেটার জন্য পুরো AST-এ নেস্টিং ওয়াক করা দরকার
হয়) — বরং একটা **অনুমান**:

`Cognitive CC ≈ (average Cyclomatic Complexity × 1.2) + (গড় নেস্টিং ডেপথ × 0.5)`

যুক্তি — cognitive complexity, cyclomatic complexity-এর চেয়ে নেস্টিংকে বেশি ভারী
হিসেবে ধরে (কারণ নেস্টেড if-এর ভেতর if বুঝা লিনিয়ার if-চেইনের চেয়ে কঠিন), তাই
আগে থেকে হিসাব করা average nesting depth-কে একটা এক্সট্রা পেনাল্টি হিসেবে যোগ
করা হয়েছে গড় CC-এর উপর।

---

## ৮. Circular Dependency (Cycle Detection)

**ফাইল:** `metrics.py` (`_detect_cycles`)

পুরো কোডবেজের call-graph বানিয়ে (কোন ফাংশন কাকে কল করে) তার উপর DFS চালানো হয়।
DFS চলাকালীন যে নোডগুলো এখনো "on stack" (অর্থাৎ বর্তমান path-এ আছে) সেগুলোর কাছে
আবার ফিরে গেলে সেটা একটা **cycle** ধরা হয় — তবে শুধু ৬ ধাপের মধ্যে ফিরে এলে
(খুব লম্বা ইনডাইরেক্ট রিলেশনকে false-positive cycle ধরা এড়াতে)। ডুপ্লিকেট cycle
(একই সেট, ভিন্ন স্টার্টিং পয়েন্ট) বাদ দিয়ে সর্বোচ্চ ১০টা ইউনিক cycle রিপোর্ট করা হয়।

---

## ৯. Max Call Chain Depth

**ফাইল:** `metrics.py` (`_max_call_chain_depth`)

যেসব ফাংশনের fan_in = 0 (অর্থাৎ কেউ তাদের কল করে না — সম্ভাব্য entry point),
সেগুলোকে "root" ধরে প্রতিটা থেকে BFS চালানো হয় call-graph-এর উপর। প্রতিটা
BFS পাথে ভিজিটেড নোডের সেট আলাদাভাবে ট্র্যাক রাখা হয় (যাতে সাইকেলে অসীম লুপ না
হয়), সর্বোচ্চ ৪০ ডেপথ পর্যন্ত এক্সপ্লোর করা হয়, এবং সব root থেকে পাওয়া
সর্বোচ্চ ডেপথটাই হলো `max_call_chain_depth`। গভীর চেইন মানে খারাপ layering —
একটা কাজ শেষ করতে অনেকগুলো ধাপ পার হতে হচ্ছে।

---

## ১০. মেট্রিক্সগুলোর মধ্যে সম্পর্ক

```
per-function CC, nesting, fan_in/out, magic numbers  →  aggregate (avg/max/sum)
                                                              │
                            ┌─────────────────────────────────┼─────────────────────┐
                            ▼                                 ▼                     ▼
                    Cognitive Complexity           Halstead Volume         Circular Deps /
                    (avg CC + nesting)              (regex token count)     Call Chain Depth
                                                              │
                                                              ▼
                                          Maintainability Index
                                (Halstead Volume + avg CC + avg LOC/function)
```

সব ফাংশন-লেভেল মেট্রিক্স (CC, nesting, fan_in/out) আগে প্রতিটা ফাংশনের জন্য আলাদাভাবে
বসানো হয় parsing-এর সময়, তারপর `compute_aggregate_metrics()` সেগুলোকে গড়/সর্বোচ্চ/যোগফল
আকারে একত্র করে dashboard-এর জন্য একটাই মেট্রিক্স ডিকশনারি বানায় — এবং সেই একই
aggregate ডেটা থেকেই Halstead ও Maintainability Index বের করা হয়।
