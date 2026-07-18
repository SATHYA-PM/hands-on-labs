"""
StoryGeneratorAgent — calls Groq (primary) or Gemini (fallback) to turn a
story premise into a fully-structured branching narrative JSON.

On retry_count >= 1 with broken_nodes present the agent switches to
REPAIR MODE: instead of regenerating the full story it sends a targeted
diff-patch prompt, receives a minimal JSON patch, and merges it back into
the previous generation via core.utils.merge_patch — cutting retry token
spend by >80 %.

Defence-in-depth budget guard: at node entry the remaining token balance is
checked against the expected cost of the upcoming LLM call.  If insufficient,
the node aborts without calling any LLM and surfaces last_story as a
best-effort result rather than returning None.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from agents.state import ScenePilotState
from core.utils import merge_patch

# ── Budget reserve constants (must mirror orchestrator.py) ───────────────────
# Kept as module-level constants so both the orchestrator router and this
# node use identical thresholds — single source of truth is the pair of
# constants; both files import from the same values conceptually.
_REPAIR_RESERVE: int = 1_200
_FULL_GEN_RESERVE: int = 9_500

# ── LLM clients (lazy import so missing keys don't crash the whole app) ──────

def _groq_client():
    from groq import Groq  # type: ignore
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def _gemini_client():
    import google.generativeai as genai  # type: ignore
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    return genai.GenerativeModel("gemini-2.5-flash")


# ── Full-generation prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ScenePilot, an expert interactive narrative designer.
Given a story premise, genre, and tone score (0=dark, 1=light), output ONLY a
valid JSON object matching this exact schema — no markdown fences, no commentary:

{
  "title": "<story title>",
  "genre": "<genre>",
  "scenes": [
    {
      "id": "scene_001",
      "text": "<scene description>",
      "tone": "<tense|hopeful|dark|neutral|playful>",
      "choices": [
        {"text": "<choice label>", "next": "<scene_id or null for ending>"}
      ]
    }
  ]
}

Rules:
- Generate as many scenes as the premise naturally requires — typically 12–20 scenes for a rich branching narrative.
- Every non-ending scene must have 2–3 choices.
- Ending scenes have an empty choices array [].
- scene ids are scene_001 … scene_NNN (zero-padded to 3 digits).
- CRITICAL: The story graph MUST be a strict DAG (Directed Acyclic Graph). A choice's "next" value must ALWAYS point to a scene with a HIGHER number than the current scene. Never point backwards.
- Tone must match the tone score: <=0.3 → dark, 0.3-0.7 → tense/neutral, >0.7 → hopeful/playful.
- COMPACTNESS: Each scene "text" must be 1–2 sentences maximum. Choice "text" labels must be 3–6 words. No verbose narration or padding.
"""


def _build_user_prompt(premise: str, genre: str, tone: float) -> str:
    return (
        f"Premise: {premise}\n"
        f"Genre: {genre}\n"
        f"Tone score: {tone:.2f}\n\n"
        "Generate the full branching narrative JSON now."
    )


# ── Repair-mode (diff-patch) prompt ──────────────────────────────────────────

REPAIR_SYSTEM_PROMPT = """You are ScenePilot in REPAIR MODE.
You will receive an existing branching narrative JSON and a list of cycle
violations reported by the graph validator.

Your ONLY job is to break the detected cycles by correcting the routing of the
listed scenes. Output ONLY a JSON patch object — no markdown fences, no
commentary, no other fields.

Patch schema:
{
  "<scene_id>": [
    {"text": "<choice label>", "next": "<scene_id or null>"},
    ...
  ],
  ...
}

Rules:
- Do NOT rewrite scene "text", "tone", or "id" fields.
- Do NOT add, remove, or alter any scene that is not in the broken_nodes list.
- Each patched scene's choices MUST point to a scene with a HIGHER id number than the source scene (forward-only edges).
- Keep the same number of choices per scene where possible.
- Return ONLY the patch object — nothing else.
"""


def _build_repair_prompt(
    story: dict[str, Any],
    broken_nodes: list[tuple[str, str]],
    validation_issues: list[str],
) -> str:
    """Build the compact repair user message (carries only what the LLM needs)."""
    # Extract only the scene objects involved in the broken edges so we don't
    # send the entire story (which could be thousands of tokens).
    broken_ids: set[str] = set()
    for src, dst in broken_nodes:
        broken_ids.add(src)
        broken_ids.add(dst)

    relevant_scenes = [
        s for s in story.get("scenes", [])
        if s.get("id") in broken_ids
    ]

    return (
        "EXISTING STORY (relevant scenes only):\n"
        + json.dumps({"scenes": relevant_scenes}, indent=2)
        + "\n\nCYCLE VIOLATIONS REPORTED BY VALIDATOR:\n"
        + "\n".join(f"  - {issue}" for issue in validation_issues)
        + "\n\nBROKEN ROUTING EDGES (source → target pairs forming cycles):\n"
        + json.dumps(broken_nodes)
        + "\n\nReturn the patch JSON now."
    )


# ── Core LLM calls ────────────────────────────────────────────────────────────

def _call_groq(system: str, user: str, max_tokens: int = 8192) -> tuple[str, int]:
    client = _groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    return content, tokens


def _call_gemini(system: str, user: str, max_tokens: int = 8192) -> tuple[str, int]:
    client = _gemini_client()
    prompt = system + "\n\n" + user
    response = client.generate_content(
        prompt,
        generation_config={"temperature": 0.7, "max_output_tokens": max_tokens},
    )
    content = response.text or ""
    tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", 0) or 0
    return content, tokens


# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse JSON with json_repair fallback."""
    text = _strip_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json  # type: ignore
            return json.loads(repair_json(text))
        except Exception:
            raise


def _parse_story(raw: str) -> dict[str, Any]:
    """Parse a full story JSON response and enforce DAG invariant."""
    story = _parse_json(raw)
    return _break_cycles(story)


def _parse_patch(raw: str) -> dict[str, Any]:
    """Parse a repair-mode patch JSON response.

    The patch must be a plain object mapping scene_id → choices[].
    """
    obj = _parse_json(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Patch response is not a JSON object: {raw[:200]}")
    return obj


def _break_cycles(story: dict[str, Any]) -> dict[str, Any]:
    """Remove back-edges that create cycles using position ordering."""
    scenes = story.get("scenes")
    if not scenes or not isinstance(scenes, list):
        return story

    order = {s.get("id"): i for i, s in enumerate(scenes) if s.get("id")}

    for scene in scenes:
        choices = scene.get("choices")
        if not isinstance(choices, list):
            continue
        sid = scene.get("id")
        src = order.get(sid, -1)
        scene["choices"] = [
            c for c in choices
            if c.get("next") is None or order.get(c.get("next"), src + 1) > src
        ]

    return story


# ── LangGraph node ────────────────────────────────────────────────────────────

def story_generator_node(state: ScenePilotState) -> ScenePilotState:
    span_start = time.time()
    error: str | None = None
    story: dict[str, Any] | None = None
    tokens = 0

    retry_count = state.get("retry_count", 0)
    broken_nodes: list[tuple[str, str]] = state.get("broken_nodes") or []
    last_story: dict[str, Any] | None = state.get("last_story")
    repair_mode = retry_count >= 1 and bool(broken_nodes) and last_story is not None

    # ── Defence-in-depth budget guard ────────────────────────────────────────
    # The router already checks budget before entering this node, but this
    # guard provides a second line of defence — e.g. if the singleton compiled
    # graph is stale from a hot-reload or a future code path bypasses the router.
    ceiling: int = int(os.environ.get("TOKEN_BUDGET_LIMIT", 10_000))
    spent: int = state.get("token_spend", 0)
    remaining: int = ceiling - spent
    reserve: int = _REPAIR_RESERVE if repair_mode else _FULL_GEN_RESERVE

    if remaining < reserve:
        # Surface the best story we already have rather than returning None.
        best_effort = last_story  # may be None on the very first call
        halt_error = (
            f"BUDGET HALT: {remaining:,} tokens remaining, "
            f"{reserve:,} required for {'repair' if repair_mode else 'generation'} pass. "
            f"Raise TOKEN_BUDGET_LIMIT in .env (current ceiling: {ceiling:,})."
        )
        halt_span = {
            "agent": "StoryGeneratorAgent[budget-halt]",
            "duration_ms": 0,
            "tokens": 0,
            "repair_mode": repair_mode,
            "tokens_used": spent,
            "token_ceiling": ceiling,
            "cycles": (state.get("validation") or {}).get("cycles_detected", 0),
            "success": False,
            "error": halt_error,
        }
        return {
            **state,
            "story": best_effort,
            "story_json": json.dumps(best_effort) if best_effort else None,
            "approved": False,
            "budget_halt": True,
            "repair_mode": repair_mode,
            # Exhaust retries so the orchestrator routes straight to fail/compliance.
            "retry_count": state.get("max_retries", 2),
            "agent_spans": [*state.get("agent_spans", []), halt_span],
            "error": halt_error,
        }

    # ── Main generation / repair path ─────────────────────────────────────────

    if repair_mode:
        # ── REPAIR MODE: emit a tiny patch rather than a full story ──────
        validation = state.get("validation") or {}
        validation_issues: list[str] = validation.get("issues") or []

        user_prompt = _build_repair_prompt(last_story, broken_nodes, validation_issues)

        try:
            raw, tokens = _call_groq(REPAIR_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
            patch = _parse_patch(raw)
            story = merge_patch(last_story, patch)
            story = _break_cycles(story)   # safety net: strip any lingering back-edges
        except Exception as groq_err:
            error = f"Groq repair: {groq_err}"
            try:
                raw, tokens = _call_gemini(REPAIR_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
                patch = _parse_patch(raw)
                story = merge_patch(last_story, patch)
                story = _break_cycles(story)
                error = None
            except Exception as gemini_err:
                error = f"Both LLMs failed in repair mode. Groq: {groq_err} | Gemini: {gemini_err}"

        agent_label = "StoryGeneratorAgent[repair]"
    else:
        # ── FULL GENERATION MODE ─────────────────────────────────────────
        try:
            raw, tokens = _call_groq(
                SYSTEM_PROMPT,
                _build_user_prompt(state["premise"], state["genre"], state["tone"]),
            )
            story = _parse_story(raw)
        except Exception as groq_err:
            error = f"Groq: {groq_err}"
            try:
                raw, tokens = _call_gemini(
                    SYSTEM_PROMPT,
                    _build_user_prompt(state["premise"], state["genre"], state["tone"]),
                )
                story = _parse_story(raw)
                error = None
            except Exception as gemini_err:
                groq_msg = str(groq_err)
                gemini_msg = str(gemini_err)
                if "rate_limit_exceeded" in groq_msg or "429" in groq_msg:
                    if (
                        "rate_limit_exceeded" in gemini_msg
                        or "429" in gemini_msg
                        or "quota" in gemini_msg.lower()
                    ):
                        error = (
                            "API quota exhausted on both providers (Groq + Gemini). "
                            "Groq daily token limit resets every 24 hours; "
                            "Gemini free tier resets daily. Please try again later."
                        )
                    else:
                        error = f"Both LLMs failed. Groq: {groq_err} | Gemini: {gemini_err}"
                else:
                    error = f"Both LLMs failed. Groq: {groq_err} | Gemini: {gemini_err}"

        agent_label = "StoryGeneratorAgent"

    span = {
        "agent": agent_label,
        "duration_ms": int((time.time() - span_start) * 1000),
        "tokens": tokens,
        "repair_mode": repair_mode,
        "tokens_used": spent + tokens,
        "token_ceiling": ceiling,
        "cycles": (state.get("validation") or {}).get("cycles_detected", 0),
        "success": story is not None,
        "error": error,
    }

    # If both LLMs failed, exhaust retries so we don't keep burning on a None
    # story that will always fail sandbox.
    if story is None:
        max_retries = state.get("max_retries", 2)
        return {
            **state,
            "story": None,
            "story_json": None,
            "approved": False,
            "repair_mode": repair_mode,
            "retry_count": max_retries,
            "token_spend": state.get("token_spend", 0) + tokens,
            "agent_spans": [*state.get("agent_spans", []), span],
            "error": error,
        }

    return {
        **state,
        "story": story,
        "story_json": json.dumps(story),
        "repair_mode": repair_mode,
        "token_spend": state.get("token_spend", 0) + tokens,
        "agent_spans": [*state.get("agent_spans", []), span],
        "error": error,
    }
