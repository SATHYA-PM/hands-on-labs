"""
Core story API routes.

POST /generate          → run the full pipeline
GET  /stories/{id}      → retrieve a stored story
GET  /audit/{id}        → retrieve the audit entry
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator import run_pipeline
from core.story_store import story_store
from core.telemetry import STYLE_VIOLATIONS

router = APIRouter(prefix="/api", tags=["stories"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ceiling() -> int:
    """Always read live from env — no caching — so .env changes take effect on rebuild."""
    return int(os.environ.get("TOKEN_BUDGET_LIMIT", 10_000))


def _estimate_run_cost(premise: str, max_retries: int) -> dict[str, int]:
    """Model the worst-case token budget for a full pipeline run.

    Token components
    ----------------
    premise_tokens  : len(premise) // 4   (1 token ≈ 4 chars)
    system_overhead : 400 tokens          (fixed prompt boilerplate)
    scene_output    : premise_tokens × SCENE_MULTIPLIER
    full_gen_est    : system_overhead + premise_tokens + scene_output

    Retry model (v2 — diff-patch repair)
    ─────────────────────────────────────
    Pass 1 : full generation            ~full_gen_est tokens
    Pass 2+: targeted patch (repair)    ~1,200 tokens each

    Previous model incorrectly added 1,200 × max_retries which was already
    correct in shape but the pre-flight check was comparing worst_case against
    ceiling BEFORE the run, meaning it would reject a 20k-ceiling + 8,700-token
    premise even though retries would only cost ~1,200 each.  The fix: keep the
    repair_reserve component accurate and let the budget guard in the generator
    node catch any actual mid-run exhaustion.

    The 40× SCENE_MULTIPLIER is calibrated to complex-story p95 (~9,000 tokens
    for a 680-char "Seven Conspiracies" premise).

    Returns a dict with all components so the error message can be precise.
    """
    premise_tokens: int = max(len(premise) // 4, 1)
    system_overhead: int = 400
    scene_multiplier: int = int(os.environ.get("SCENE_MULTIPLIER", 40))
    full_gen_est: int = system_overhead + premise_tokens + premise_tokens * scene_multiplier
    # Each retry after the first is a diff-patch repair (~1,200 tokens).
    repair_reserve: int = 1_200 * max_retries
    worst_case: int = full_gen_est + repair_reserve
    # Recommended ceiling = worst case + 15 % headroom, rounded up to nearest 500
    recommended: int = ((int(worst_case * 1.15) + 499) // 500) * 500

    return {
        "premise_tokens": premise_tokens,
        "full_gen_est": full_gen_est,
        "repair_reserve": repair_reserve,
        "worst_case": worst_case,
        "recommended_ceiling": recommended,
    }


# ── Request / response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    premise: str = Field(..., min_length=10, max_length=2000)
    genre: str = Field("thriller", pattern=r"^(thriller|fantasy|sci-fi|educational|marketing)$")
    tone: float = Field(0.5, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    story_id: str
    approved: bool
    title: Optional[str]
    scenes: Optional[list[dict[str, Any]]]
    validation: Optional[dict[str, Any]]
    agent_spans: list[dict[str, Any]]
    token_spend: int
    token_ceiling: int
    error: Optional[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
def generate_story(req: GenerateRequest):
    """
    Run the full LangGraph pipeline: generate → validate → comply.
    Returns the final ScenePilotState projected into the response model.
    """
    ceiling = _get_ceiling()
    max_retries = int(os.environ.get("MAX_RETRIES", 2))

    # ── Pre-flight: estimate worst-case token cost before spending anything ───
    estimate = _estimate_run_cost(req.premise, max_retries)

    if estimate["worst_case"] > ceiling:
        return GenerateResponse(
            story_id=str(uuid.uuid4()),
            approved=False,
            title=None,
            scenes=None,
            validation=None,
            agent_spans=[],
            token_spend=0,
            token_ceiling=ceiling,
            error=(
                f"PRE-FLIGHT REJECTED: This premise requires an estimated "
                f"~{estimate['full_gen_est']:,} tokens to generate "
                f"plus {estimate['repair_reserve']:,} tokens reserved for up to "
                f"{max_retries} repair {'retry' if max_retries == 1 else 'retries'} "
                f"(~{estimate['worst_case']:,} total worst-case). "
                f"Your current ceiling is {ceiling:,} tokens. "
                f"Set TOKEN_BUDGET_LIMIT={estimate['recommended_ceiling']:,} in .env "
                f"to run this premise safely."
            ),
        )

    # ── Run pipeline ──────────────────────────────────────────────────────────
    state = run_pipeline(
        premise=req.premise,
        genre=req.genre,
        tone=req.tone,
    )

    # Record style violations in Prometheus
    sv = (state.get("validation") or {}).get("style_violations", [])
    if sv:
        STYLE_VIOLATIONS.inc(len(sv))

    spent = state.get("token_spend", 0)
    budget_halt = state.get("budget_halt", False)

    # ── Build user-facing error message ───────────────────────────────────────
    error = state.get("error")

    if error:
        # Normalise raw interpreter noise — never expose tracebacks to the UI.
        if "Unterminated string" in error or "JSONDecodeError" in error or "Expecting value" in error:
            error = (
                "Generation Truncated — The LLM response was cut off before the JSON "
                "structure could be completed. Input payload has been structurally condensed "
                "for the next optimisation pass. Please retry."
            )

    # Post-run budget overage (spent > ceiling) — distinct from a mid-pipeline halt.
    budget_exceeded = spent > ceiling
    if not error and budget_exceeded and not budget_halt:
        cycles = (state.get("validation") or {}).get("cycles_detected", 0)
        error = (
            f"BUDGET EXHAUSTED: This story consumed {spent:,} tokens "
            f"(ceiling: {ceiling:,}, overage: {spent - ceiling:,}). "
            + (f"Cycle repairs attempted: {cycles}. " if cycles else "")
            + f"Set TOKEN_BUDGET_LIMIT={estimate['recommended_ceiling']:,} in .env "
            f"to accommodate this premise with full self-healing."
        )

    approved = state.get("approved", False) and not budget_exceeded and not budget_halt

    story = state.get("story") or {}
    return GenerateResponse(
        story_id=state["story_id"],
        approved=approved,
        title=story.get("title"),
        scenes=story.get("scenes"),
        validation=state.get("validation"),
        agent_spans=state.get("agent_spans", []),
        token_spend=spent,
        token_ceiling=ceiling,
        error=error,
    )


@router.get("/stories/{story_id}")
def get_story(story_id: str):
    record = story_store.get(story_id)
    if not record:
        raise HTTPException(status_code=404, detail="Story not found.")
    return record


@router.get("/audit/{story_id}")
def get_audit(story_id: str):
    record = story_store.get(story_id)
    if not record or "audit" not in record:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return record["audit"]


@router.get("/stories")
def list_stories():
    return {"story_ids": story_store.all_ids()}


@router.post("/blueprint")
def generate_blueprint_endpoint(body: dict):
    """
    Generate a 3D spatial blueprint from a story JSON.
    Accepts {story: {...}} or a raw story object.
    """
    from core.blueprint import generate_blueprint
    story    = body.get("story", body)
    story_id = body.get("story_id", "story")
    return generate_blueprint(story, story_id=story_id)


@router.post("/validate")
def validate_story_endpoint(body: dict):
    """
    Lightweight endpoint used by the demo loader to run the sandbox
    validator against a pre-loaded story JSON without running the LLM.
    """
    from sandbox.validator import validate_story
    story = body.get("story", body)  # accept both {story: ...} and raw story
    result = validate_story(story)
    return result
