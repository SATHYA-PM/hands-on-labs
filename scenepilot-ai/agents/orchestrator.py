"""
Orchestrator — LangGraph StateGraph wiring all agents together with a
self-correction retry loop (max 2 retries).
"""
from __future__ import annotations

import os
import uuid
from typing import Literal

from langgraph.graph import END, StateGraph  # type: ignore

from agents.state import ScenePilotState
from agents.story_generator import story_generator_node
from agents.style_vault_agent import style_vault_node
from agents.sandbox_validator import sandbox_validator_node
from agents.compliance_agent import compliance_node
from agents.granite_guardian import granite_guardian_node


# ── Budget reserve constants ──────────────────────────────────────────────────
#
# These represent the minimum token headroom needed to complete one more LLM
# call before allowing a retry.  They are intentionally conservative (include
# ~20 % buffer over observed p95 spend).
#
#   REPAIR path  : repair prompt + patch response ≈ 600–900 tokens → 1,200 cap
#   FULL-GEN path: system prompt + large output   ≈ 7,500–9,000 tokens → 9,500 cap

_REPAIR_RESERVE: int = 1_200
_FULL_GEN_RESERVE: int = 9_500


# ── Routing helpers ───────────────────────────────────────────────────────────

def _has_budget_for_retry(state: ScenePilotState) -> bool:
    """Return True only when enough token headroom remains for one more LLM pass.

    The ceiling is always read live from the environment so that a hot-reload
    config change takes effect without a full process restart.  We deliberately
    do NOT store it in state to avoid stale-value bugs across retries.

    Reserve selection:
      - Repair mode (last_story available, any failure reason): 1,200 tokens
        This covers both cycle-repair and style-repair paths.
      - Full-generation fallback (no saved story yet):          9,500 tokens
    """
    ceiling: int = int(os.environ.get("TOKEN_BUDGET_LIMIT", 10_000))
    spent: int = state.get("token_spend", 0)
    remaining: int = ceiling - spent

    # Style-only retries also qualify as repair — they send a targeted patch
    # not a full regeneration.  The only requirement is that last_story exists
    # so the generator has a base to diff against.
    last = state.get("last_story")
    will_repair = last is not None

    reserve = _REPAIR_RESERVE if will_repair else _FULL_GEN_RESERVE
    return remaining >= reserve


def _route_after_sandbox(state: ScenePilotState) -> Literal["compliance", "retry", "fail"]:
    if state.get("approved"):
        return "compliance"
    can_retry = (
        state.get("retry_count", 0) < state.get("max_retries", 2)
        and _has_budget_for_retry(state)
    )
    return "retry" if can_retry else "fail"


def _increment_retry(state: ScenePilotState) -> ScenePilotState:
    """Bump retry counter and set up state for diff-based repair on next pass.

    Preserved across retries:
      - last_story  : the story from the failed pass — repair patches this
      - broken_nodes: cycle back-edges (if any) from the sandbox
      - style_check : style violations from the style vault — the generator
                      reads these to decide whether to issue a style-repair
                      prompt.  Clearing it (as before) caused repair_mode to
                      never activate for style-only failures.

    Cleared (will be repopulated by the next generate → style → sandbox pass):
      - story / story_json : will be replaced by the patch result
      - validation          : will be repopulated by style_vault + sandbox
      - approved            : always False until sandbox re-approves
    """
    return {
        **state,
        "retry_count": state.get("retry_count", 0) + 1,
        "story": None,
        "story_json": None,
        "approved": False,
        "validation": None,
        # DO NOT clear style_check — the generator reads violations from it
        # to activate style_repair mode on the next pass.
        # Carry forward repair state — do NOT clear last_story / broken_nodes.
        "repair_mode": False,
    }


def _fail_node(state: ScenePilotState) -> ScenePilotState:
    """Terminal failure — mark not approved and persist via compliance.

    Distinguishes between a budget-gate halt and a retry-count exhaustion so
    the API route can produce a precise user-facing message for each case.
    """
    # Carry through a pre-existing budget_halt flag if the generator already
    # set it; otherwise derive it here from whether the budget guard was the
    # reason we reached fail (remaining < reserve when retry_count < max).
    budget_halt: bool = state.get("budget_halt", False)
    if not budget_halt and state.get("retry_count", 0) < state.get("max_retries", 2):
        # We arrived at fail before exhausting the retry counter — the only
        # way that happens is if _has_budget_for_retry returned False.
        budget_halt = True

    default_error = (
        "Insufficient token budget for next retry. Raise TOKEN_BUDGET_LIMIT in .env."
        if budget_halt
        else "Max retries exceeded."
    )

    return {
        **state,
        "approved": False,
        "budget_halt": budget_halt,
        "error": state.get("error") or default_error,
    }


# ── Build graph ───────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(ScenePilotState)

    graph.add_node("generate", story_generator_node)
    graph.add_node("style_vault", style_vault_node)
    graph.add_node("sandbox", sandbox_validator_node)
    graph.add_node("guardian", granite_guardian_node)
    graph.add_node("compliance", compliance_node)
    graph.add_node("retry", _increment_retry)
    graph.add_node("fail", _fail_node)

    graph.set_entry_point("generate")

    graph.add_edge("generate", "style_vault")
    graph.add_edge("style_vault", "sandbox")

    graph.add_conditional_edges(
        "sandbox",
        _route_after_sandbox,
        {
            "compliance": "guardian",   # always pass through Guardian first
            "retry": "retry",
            "fail": "fail",
        },
    )

    graph.add_edge("guardian", "compliance")   # Guardian -> Compliance
    graph.add_edge("retry", "generate")        # self-correction loop
    graph.add_edge("compliance", END)
    graph.add_edge("fail", "compliance")       # still persist audit on failure

    return graph


# Compiled graph (singleton, rebuilt when module is reloaded)
_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled


# ── Public entry point ────────────────────────────────────────────────────────

def run_pipeline(premise: str, genre: str, tone: float) -> ScenePilotState:
    story_id = str(uuid.uuid4())
    # Register a progress queue for SSE streaming before the graph runs.
    # Nodes emit events into this queue; the /api/progress/{id} endpoint drains it.
    from core.progress import register as _reg, close as _close
    _reg(story_id)

    initial: ScenePilotState = {
        "story_id": story_id,
        "premise": premise,
        "genre": genre,
        "tone": tone,
        "story": None,
        "story_json": None,
        "validation": None,
        "style_check": None,
        "approved": False,
        "retry_count": 0,
        "max_retries": int(os.environ.get("MAX_RETRIES", 2)),
        # Diff-based repair fields — empty at pipeline start.
        "broken_nodes": None,
        "last_story": None,
        "repair_mode": False,
        "structural_issues": None,
        # Budget gate fields — false at pipeline start.
        "budget_halt": False,
        # Guardian — None until the node runs.
        "guardian_check": None,
        "audit": None,
        "agent_spans": [],
        "token_spend": 0,
        "error": None,
    }
    graph = get_compiled_graph()
    try:
        result = graph.invoke(initial)
    finally:
        _close(story_id)
    return result
