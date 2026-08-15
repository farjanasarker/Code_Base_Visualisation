"""
llm_engine.py — LLM Reasoning Engine (Groq / GPT-OSS-120b).

Role in the pipeline:
  Static analysis (smell_detector + smell_graph) detects WHAT is wrong.
  This module asks the LLM to reason about WHY and HOW TO FIX IT.

The LLM receives:
  - Structured smell summary (type counts, root cause scores)
  - Preliminary minimal-fix plan (from greedy set-cover algorithm)
  - Project context (size, complexity, depth)

The LLM does NOT receive:
  - Raw source code
  - File contents
  - Unstructured data

LLM output:
  - Executive summary of architectural state
  - Prioritised refactor plan enriched with architectural rationale
  - Risk assessment per step
  - Long-term architectural recommendation
"""

import json
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Load .env if present (development convenience) ────────────────────────────
def _load_dotenv() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()


# ── Configuration ─────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL        = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TEMPERATURE  = 0.20   # low temperature → deterministic, structured output

# ── System Prompt ─────────────────────────────────────────────────────────────
_SYSTEM = """\
You are a senior software architect and expert in Martin Fowler-style refactoring.

You receive STRUCTURED DATA from a static analysis tool — not raw source code.
Your role is architectural reasoning:
  1. Identify the PRIMARY ROOT CAUSE of the smell cluster (the structural anti-pattern)
  2. Validate and enrich the preliminary fix plan with architectural insight
  3. Explain WHY each step must happen BEFORE subsequent steps (dependency ordering)
  4. Identify which refactoring pattern resolves the maximum number of downstream smells
  5. Assess realistic effort and risk for each step

HARD RULES:
- Never suggest trivial stylistic cleanups
- Focus only on structural / architectural refactoring
- Each step must explicitly state its DOWNSTREAM IMPACT
- Use precise GoF or Fowler pattern names (Extract Class, Move Method, Facade, etc.)
- Think about MINIMAL CHANGE → MAXIMUM SMELL REDUCTION
- Return ONLY valid compact JSON — no markdown, no prose outside JSON

Required JSON schema:
{
  "executive_summary": "<2-3 sentence architectural diagnosis>",
  "primary_root_cause": "<the one architectural anti-pattern driving most smells>",
  "smell_root_causes": {
    "primary":   "<smell type that is the true root>",
    "secondary": "<second contributing smell type>"
  },
  "refactor_plan": [
    {
      "priority":         1,
      "pattern":          "<Refactoring Pattern Name>",
      "target":           "<module / class / function name>",
      "what_to_do":       "<specific concrete action>",
      "why_this_first":   "<why fixing this now maximises downstream impact>",
      "resolves_smells":  ["<smell_type>"],
      "estimated_effort": "high|medium|low",
      "risk":             "high|medium|low",
      "risk_reason":      "<brief risk note>"
    }
  ],
  "long_term_recommendation": "<architectural direction>"
}"""


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _build_prompt(
    smell_summary:     Dict,
    preliminary_plan:  List[Dict],
    project_context:   Optional[Dict] = None,
) -> str:
    ctx_block = ""
    if project_context:
        ctx_block = (
            f"\nPROJECT SCALE:\n"
            f"  Files: {project_context.get('total_files', '?')}\n"
            f"  Functions: {project_context.get('total_functions', '?')}\n"
            f"  Avg cyclomatic CC: {project_context.get('avg_cyclomatic', '?')}\n"
            f"  Max call chain depth: {project_context.get('max_call_chain_depth', '?')}\n"
        )

    plan_block = json.dumps(preliminary_plan[:6], separators=(",", ":"))

    summary_block = json.dumps({
        "total_smells":      smell_summary.get("total_smells"),
        "smell_type_counts": smell_summary.get("smell_type_counts"),
        "top_root_causes":   smell_summary.get("top_root_causes", [])[:5],
    }, separators=(",", ":"))

    return (
        f"STATIC ANALYSIS RESULTS:{ctx_block}\n"
        f"SMELL SUMMARY: {summary_block}\n\n"
        f"PRELIMINARY MINIMAL-FIX PLAN (greedy set-cover, static analysis): {plan_block}\n\n"
        f"Generate the architectural refactor plan as JSON."
    )


# ── LLM Call ──────────────────────────────────────────────────────────────────

def get_refactor_plan(
    smell_summary:    Dict,
    preliminary_plan: List[Dict],
    project_context:  Optional[Dict] = None,
) -> Dict:
    """
    Call Groq (openai/gpt-oss-120b) to reason about the refactor plan.
    Returns parsed plan dict, or a static-analysis fallback on any failure.
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set — add it to Backend/.env")
        return _fallback_plan(preliminary_plan, error="GROQ_API_KEY not configured")

    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed — run: pip install groq")
        return _fallback_plan(preliminary_plan, error="groq package not installed")

    client   = Groq(api_key=GROQ_API_KEY)
    user_msg = _build_prompt(smell_summary, preliminary_plan, project_context)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
        )
        raw    = response.choices[0].message.content
        parsed = json.loads(raw)
        parsed["_source"] = f"groq:{MODEL}"
        return parsed

    except json.JSONDecodeError as exc:
        logger.warning(f"[{MODEL}] non-JSON response: {exc}")
        return _fallback_plan(preliminary_plan, error=f"JSON parse error: {exc}")

    except Exception as exc:
        logger.error(f"[{MODEL}] Groq call failed: {exc}")
        return _fallback_plan(preliminary_plan, error=str(exc))


# ── Fallback (when LLM unavailable) ──────────────────────────────────────────

def _effort_label(effort_val) -> str:
    """Map a numeric effort (1-5) to a high|medium|low label for LLM-shaped output."""
    try:
        v = float(effort_val)
    except (TypeError, ValueError):
        return "medium"
    return "high" if v >= 4 else "medium" if v >= 2 else "low"


def _fallback_plan(preliminary_plan: List[Dict], error: str = "") -> Dict:
    """
    Return a structured plan derived purely from the static analysis.
    Used when Groq is unavailable or returns invalid output.
    """
    top = preliminary_plan[:6]
    steps = [
        {
            "priority":         i + 1,
            "pattern":          (step.get("refactor_suggestions") or ["Refactor"])[0],
            "target":           step.get("target_name", ""),
            "what_to_do":       step.get("description", ""),
            "why_this_first":   step.get("upstream_note", ""),
            "resolves_smells":  step.get("cascades_types", []),
            "estimated_effort": _effort_label(step.get("effort", 2)),
            "risk":             "medium",
            "risk_reason":      "Estimated from static analysis only",
        }
        for i, step in enumerate(top)
    ]
    return {
        "executive_summary":        "Plan generated from static analysis (LLM unavailable).",
        "primary_root_cause":       (top[0].get("type") if top else "unknown"),
        "smell_root_causes":        {
            "primary":   top[0].get("type") if top else "?",
            "secondary": top[1].get("type") if len(top) > 1 else "?",
        },
        "refactor_plan":            steps,
        "long_term_recommendation": "Address root cause smells first; see smell dependency graph.",
        "_source":                  "static_analysis_fallback",
        "_error":                   error,
    }


# ── Code Preview (before/after snippet) ──────────────────────────────────────

_CODE_PREVIEW_SYSTEM = """\
You are a refactoring assistant. Given a code smell and refactoring suggestion,
produce a SHORT before/after Python/pseudocode snippet (max 15 lines total).
Return JSON only: { before: string, after: string, explanation: string }"""


def get_code_preview(
    smell_type: str,
    target_name: str,
    metrics:     Dict,
    suggestion:  str,
    language:    str,
) -> Optional[Dict]:
    """
    Ask the LLM for a short before/after refactor snippet for a single smell.
    Returns { before, after, explanation } or None on any failure (never raises).
    """
    if not GROQ_API_KEY:
        return None

    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed — run: pip install groq")
        return None

    user_msg = (
        f"Smell: {smell_type} on function '{target_name}'\n"
        f"Metrics: {json.dumps(metrics, separators=(',', ':'))}\n"
        f"Suggested refactor: {suggestion}\n"
        f"Language: {language}\n"
        f"Write a realistic before/after snippet showing the refactor."
    )

    try:
        client   = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _CODE_PREVIEW_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)
        if not all(k in parsed for k in ("before", "after", "explanation")):
            return None
        return {
            "before":      parsed["before"],
            "after":       parsed["after"],
            "explanation": parsed["explanation"],
        }
    except Exception as exc:
        logger.warning(f"get_code_preview failed for {smell_type}/{target_name}: {exc}")
        return None
