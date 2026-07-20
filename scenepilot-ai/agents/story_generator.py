"""
StoryGeneratorAgent — calls Groq (primary) or Gemini (fallback) to turn a
story premise into a fully-structured branching narrative JSON.

Repair mode (retry_count >= 1, last_story present)
───────────────────────────────────────────────────
Two specialised diff-patch prompts replace the expensive full-regeneration:

  • CYCLE REPAIR  — broken_nodes is non-empty (graph back-edges detected).
    Sends only the N affected scene objects + edge list.  LLM returns a
    minimal patch mapping scene_id → new choices[].  Token cost: ~600–900.

  • STYLE REPAIR  — broken_nodes is empty but style_violations is non-empty
    (FAISS / tone check failed).  Sends only the violating scene objects +
    the style-checker report.  LLM rewrites only those scenes' text/tone.
    Token cost: ~500–800.

In both cases core.utils.merge_patch deep-merges the patch back into
last_story, cutting retry token spend by >80 % vs a full cold regeneration.

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
from core.llm_client import llm_call, ProviderQuotaExhausted

# ── Budget reserve constants (must mirror orchestrator.py) ───────────────────
_REPAIR_RESERVE: int = 1_200
_FULL_GEN_RESERVE: int = 9_500

# Maximum scenes to include in a repair prompt — keeps token usage bounded
# even when a large story has many violations.
_MAX_REPAIR_SCENES: int = 12


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
- TONE: Use ONLY these tone values per genre:
    thriller   → dark | tense | neutral
    fantasy    → hopeful | tense | neutral | dark
    sci-fi     → tense | neutral | dark | hopeful
    educational → neutral | hopeful | playful
    marketing  → hopeful | playful | neutral
  The tone score maps to: <=0.3 → dark, 0.31-0.6 → tense/neutral, >0.6 → hopeful/playful.
  Every scene's declared tone MUST match — never use a tone not listed for the genre.
- COMPACTNESS: Each scene "text" must be 1–2 sentences maximum. Show physical action and sensory detail — never state emotions directly ("She was afraid" is wrong; "Her hands shook" is right). Choice labels: 3–6 words.
- SCENE OPENINGS: Never start a scene with "It" or "There". Anchor the reader in action or place immediately.
- SCENE ENDINGS: The last sentence before choices must create a decision moment or micro-cliffhanger.
"""


def _build_user_prompt(premise: str, genre: str, tone: float) -> str:
    # Derive a concrete tone label so the LLM has zero ambiguity
    if tone <= 0.3:
        tone_label = "dark"
    elif tone <= 0.6:
        tone_label = "tense/neutral"
    else:
        tone_label = "hopeful/playful"

    return (
        f"Premise: {premise}\n"
        f"Genre: {genre}\n"
        f"Tone score: {tone:.2f} ({tone_label})\n\n"
        "Generate the full branching narrative JSON now."
    )


# ── Repair-mode prompts (diff-patch) ─────────────────────────────────────────

# --- Cycle repair ---

CYCLE_REPAIR_SYSTEM_PROMPT = """You are ScenePilot in CYCLE REPAIR MODE.
You will receive a subset of an existing branching narrative and a list of
graph cycle violations detected by the validator.

Your ONLY job is to break the cycles by correcting the routing of the listed
scenes. Output ONLY a JSON patch object — no markdown fences, no commentary.

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
- Do NOT touch any scene that is not in the broken_nodes list.
- Each patched scene's choices MUST point to a scene with a HIGHER id number than the source scene (forward-only edges).
- Keep the same number of choices per scene where possible.
- Return ONLY the patch object — nothing else.
"""


def _build_cycle_repair_prompt(
    story: dict[str, Any],
    broken_nodes: list[tuple[str, str]],
    validation_issues: list[str],
) -> str:
    """Build the compact cycle-repair user message."""
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
        + "\n\nBROKEN ROUTING EDGES (source \u2192 target pairs forming cycles):\n"
        + json.dumps(broken_nodes)
        + "\n\nReturn the patch JSON now."
    )


# --- Style repair ---

STYLE_REPAIR_SYSTEM_PROMPT = """You are ScenePilot in STYLE REPAIR MODE.
You will receive ONLY the scenes that failed the style checker, the exact
violation details for each one, and the story's genre and tone target.

Your ONLY job is to rewrite the "text" and/or "tone" of those specific scenes
to fix the violations. Output ONLY a JSON patch object — no markdown, no commentary.

Patch schema:
{
  "<scene_id>": {
    "text": "<rewritten scene text — 1-2 sentences, show-don't-tell, punchy>",
    "tone": "<tense|hopeful|dark|neutral|playful>"
  },
  ...
}

Rules:
- ONLY include scenes that appear in the VIOLATIONS section below.
- Do NOT change scene "id" or "choices". Do NOT touch any other scene.
- Text must be 1-2 sentences maximum. No padding, no exposition dumps.
- Apply show-don't-tell: replace "She was afraid" with physical details.
- Tone MUST match the target tone specified in the prompt.
- Return ONLY the valid JSON patch object — nothing else.
"""


def _build_style_repair_prompt(
    story: dict[str, Any],
    structured: list[dict[str, Any]],
    fallback_strings: list[str],
    genre: str,
    tone_label: str,
) -> str:
    """Build a compact, precise style-repair user message.

    Uses structured violation objects (scene_id, type, score, rule) when
    available so the LLM gets unambiguous targeting — no regex needed.
    Falls back to parsing legacy string list if structured is empty.
    """
    # Extract violating IDs — directly from structured objects (no regex)
    if structured:
        violating_ids: set[str] = {v["scene_id"] for v in structured}
    else:
        import re
        violating_ids = set()
        for v in fallback_strings:
            m = re.search(r"(scene_\d+)", v)
            if m:
                violating_ids.add(m.group(1))

    # Send ONLY the violating scene objects — never the full story
    relevant_scenes = [
        s for s in story.get("scenes", [])
        if s.get("id") in violating_ids
    ]

    # Build a precise violation report per scene
    if structured:
        violation_lines = []
        for v in structured:
            if v["type"] == "tone":
                violation_lines.append(
                    f"  {v['scene_id']}: TONE ERROR — current='{v['current_tone']}', "
                    f"must be one of {v['allowed_tones']}"
                )
            else:
                violation_lines.append(
                    f"  {v['scene_id']}: STYLE MISMATCH — similarity={v['score']:.3f} "
                    f"(threshold 0.35). Nearest rule: \"{v['rule'][:80]}\""
                )
        violation_report = "\n".join(violation_lines)
    else:
        violation_report = "\n".join(f"  - {v}" for v in fallback_strings)

    return (
        f"GENRE: {genre}   TARGET TONE: {tone_label}\n\n"
        "SCENES TO REPAIR (full objects for context):\n"
        + json.dumps({"scenes": relevant_scenes}, indent=2)
        + "\n\nVIOLATIONS (rewrite ONLY these scene IDs):\n"
        + violation_report
        + "\n\nReturn the patch JSON now — one entry per violating scene_id."
    )


# _call_groq / _call_gemini removed — all LLM calls now go through
# core.llm_client.llm_call() which implements the three-provider fallback
# chain: groq-primary → groq-fallback → gemini.


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
    """Parse a full story JSON response and enforce DAG invariant.

    Handles three malformed shapes the LLM occasionally returns:
      1. Correct:  {"title": ..., "scenes": [...]}
      2. Wrapped:  [{"title": ..., "scenes": [...]}]   → unwrap list
      3. Nested:   {"story": {"title": ..., "scenes": [...]}}  → unwrap key
    """
    obj = _parse_json(raw)

    # Shape 2: LLM wrapped the object in an array
    if isinstance(obj, list):
        obj = obj[0] if obj else {}

    # Shape 3: LLM nested the story under a "story" or "data" key
    if isinstance(obj, dict) and "scenes" not in obj:
        for key in ("story", "data", "result", "output"):
            if key in obj and isinstance(obj[key], dict):
                obj = obj[key]
                break

    if not isinstance(obj, dict):
        raise ValueError(f"LLM returned unexpected JSON shape: {type(obj).__name__}")

    return _break_cycles(obj)


def _parse_patch(raw: str) -> dict[str, Any]:
    """Parse a repair-mode patch JSON response.

    The patch must be a plain object mapping scene_id → choices[].
    """
    obj = _parse_json(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Patch response is not a JSON object: {raw[:200]}")
    return obj


def _break_cycles(story: dict[str, Any]) -> dict[str, Any]:
    """Remove back-edges that create cycles using position ordering.

    Safe removal: if stripping back-edges would leave a non-terminal scene
    with 0 choices, redirect those choices to the nearest forward scene
    instead of deleting them — prevents schema errors downstream.
    """
    import copy
    story = copy.deepcopy(story)
    scenes = story.get("scenes")
    if not scenes or not isinstance(scenes, list):
        return story

    order = {s.get("id"): i for i, s in enumerate(scenes) if s.get("id")}
    scene_ids = list(order.keys())

    for scene in scenes:
        choices = scene.get("choices")
        if not isinstance(choices, list):
            continue
        sid = scene.get("id")
        src = order.get(sid, -1)

        forward = [
            c for c in choices
            if c.get("next") is None or order.get(c.get("next"), src + 1) > src
        ]
        backward = [
            c for c in choices
            if c not in forward and c.get("next") is not None
        ]

        if forward:
            scene["choices"] = forward
        elif backward:
            # All choices were back-edges — redirect each to the nearest
            # forward scene rather than producing an empty choices array.
            nearest_forward = next(
                (sid2 for sid2 in scene_ids if order.get(sid2, -1) > src),
                None,
            )
            if nearest_forward:
                scene["choices"] = [{"text": "Continue", "next": nearest_forward}]
            # else: last scene in list — leave empty (acts as terminal)
        # If choices was already [] (terminal scene) leave it untouched

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

    # Read from style_check (preserved across retries — NOT cleared by
    # _increment_retry).  Use structured objects when available; fall back
    # to the legacy string list so old cached state still works.
    _sc = state.get("style_check") or {}
    style_violations: list[str] = _sc.get("violations", [])
    style_violations_structured: list[dict[str, Any]] = _sc.get("structured", [])

    # Repair mode: any retry where we have a saved story to patch against.
    # Two sub-modes:
    #   cycle_repair — broken_nodes is non-empty  (graph back-edges present)
    #   style_repair — broken_nodes empty but style violations exist
    # If neither condition holds on a retry we still fall back to full regen
    # (e.g. schema error on first pass before any story was saved).
    repair_mode = retry_count >= 1 and last_story is not None
    cycle_repair = repair_mode and bool(broken_nodes)
    style_repair = (
        repair_mode
        and not cycle_repair
        and bool(style_violations_structured or style_violations)
    )

    # ── Defence-in-depth budget guard ────────────────────────────────────────
    # The router already checks budget before entering this node, but this
    # guard provides a second line of defence — e.g. if the singleton compiled
    # graph is stale from a hot-reload or a future code path bypasses the router.
    ceiling: int = int(os.environ.get("TOKEN_BUDGET_LIMIT", 10_000))
    spent: int = state.get("token_spend", 0)
    remaining: int = ceiling - spent
    reserve: int = _REPAIR_RESERVE if repair_mode else _FULL_GEN_RESERVE
    # repair_mode already covers both cycle_repair and style_repair above,
    # so _REPAIR_RESERVE (~1,200 tokens) is used for both targeted patch paths.

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

    provider_used: str = "unknown"

    if cycle_repair:
        # ── CYCLE REPAIR ─────────────────────────────────────────────────
        validation = state.get("validation") or {}
        validation_issues: list[str] = validation.get("issues") or []
        user_prompt = _build_cycle_repair_prompt(last_story, broken_nodes, validation_issues)
        try:
            raw, tokens, provider_used = llm_call(
                CYCLE_REPAIR_SYSTEM_PROMPT, user_prompt, max_tokens=1024
            )
            patch = _parse_patch(raw)
            story = merge_patch(last_story, patch)
            story = _break_cycles(story)
        except ProviderQuotaExhausted as qe:
            error = f"PROVIDER QUOTA EXHAUSTED: {qe}"
        except Exception as exc:
            error = f"cycle-repair failed: {exc}"
        agent_label = "StoryGeneratorAgent[cycle-repair]"

    elif style_repair:
        # ── STYLE REPAIR ─────────────────────────────────────────────────
        # Cap scenes sent to LLM at _MAX_REPAIR_SCENES (12) to prevent the
        # 16k-token prompt spike that exhausted both providers in your run.
        # If > 12 violations exist the worst-score batch is fixed first;
        # any residual violations are caught on the next retry pass.
        capped_structured = (style_violations_structured or [])[:_MAX_REPAIR_SCENES]
        capped_strings    = style_violations[:_MAX_REPAIR_SCENES]
        repair_max_tokens = min(4096, max(512, len(capped_structured or capped_strings) * 80 + 200))

        tone_value: float = state.get("tone", 0.5)
        tone_label = (
            "dark" if tone_value <= 0.3
            else "tense/neutral" if tone_value <= 0.6
            else "hopeful/playful"
        )
        user_prompt = _build_style_repair_prompt(
            last_story, capped_structured, capped_strings,
            state.get("genre", "thriller"), tone_label,
        )

        def _apply_style_patch(base: dict[str, Any], spatch: dict[str, Any]) -> dict[str, Any]:
            import copy
            merged = copy.deepcopy(base)
            scene_index = {s["id"]: s for s in merged.get("scenes", []) if "id" in s}
            for scene_id, fields in spatch.items():
                scene = scene_index.get(scene_id)
                if scene is None or not isinstance(fields, dict):
                    continue
                if "text" in fields:
                    scene["text"] = fields["text"]
                if "tone" in fields:
                    scene["tone"] = fields["tone"]
            return merged

        try:
            raw, tokens, provider_used = llm_call(
                STYLE_REPAIR_SYSTEM_PROMPT, user_prompt, max_tokens=repair_max_tokens
            )
            patch = _parse_patch(raw)
            story = _apply_style_patch(last_story, patch)
        except ProviderQuotaExhausted as qe:
            error = f"PROVIDER QUOTA EXHAUSTED: {qe}"
        except Exception as exc:
            error = f"style-repair failed: {exc}"
        agent_label = "StoryGeneratorAgent[style-repair]"

    else:
        # ── FULL GENERATION ───────────────────────────────────────────────
        try:
            raw, tokens, provider_used = llm_call(
                SYSTEM_PROMPT,
                _build_user_prompt(state["premise"], state["genre"], state["tone"]),
            )
            story = _parse_story(raw)
        except ProviderQuotaExhausted as qe:
            error = f"PROVIDER QUOTA EXHAUSTED: {qe}"
        except Exception as exc:
            error = f"generation failed: {exc}"
        agent_label = "StoryGeneratorAgent"

    repair_label = (
        "cycle-repair" if cycle_repair
        else "style-repair" if style_repair
        else "none"
    )
    span = {
        "agent": agent_label,
        "provider": provider_used,
        "duration_ms": int((time.time() - span_start) * 1000),
        "tokens": tokens,
        "repair_mode": repair_mode,
        "repair_type": repair_label,
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
