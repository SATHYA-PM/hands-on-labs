"""
GraniteGuardianAgent — IBM Granite Guardian 3.2 content safety gate.

Runs every generated story through IBM's Granite Guardian model before the
Compliance node approves it.  Guardian checks each scene's text for harmful
content categories (hate, violence, sexual content, profanity, etc.) using
the `ibm-watsonx-ai` SDK.

Fail-safe design
────────────────
- If GUARDIAN_ENABLED=false (default) the node passes through immediately
  without calling any API — zero cost for local dev / quota-limited runs.
- If the watsonx API is unreachable or the key is missing the node logs a
  warning span and passes through (non-blocking) — the pipeline never crashes
  because Guardian is unavailable.
- Only explicit BLOCKED verdicts from Guardian cause approval to be revoked.

Environment variables
─────────────────────
  GUARDIAN_ENABLED       true | false   (default: false)
  WATSONX_API_KEY        IBM Cloud API key
  WATSONX_PROJECT_ID     watsonx.ai project ID
  WATSONX_URL            https://eu-de.ml.cloud.ibm.com     (default — Frankfurt)
  GUARDIAN_THRESHOLD     0.0–1.0 risk score cutoff          (default: 0.8)

Guardian model used: ibm/granite-guardian-3-2-2b
  - Lightweight 2B model — fast, low-cost, purpose-built for safety checks.
  - Returns a risk_score (0.0 = safe, 1.0 = harmful) and a label (Yes/No).
"""
from __future__ import annotations

import os
import time
from typing import Any

from agents.state import ScenePilotState
from core.telemetry import GUARDIAN_BLOCKS


# Guardian model identifier on watsonx.ai
# granite-guardian-3-8b is the version available on Lite/free plans in us-south.
# granite-guardian-3-2-2b is available on Frankfurt (eu-de) paid plans.
_GUARDIAN_MODEL = os.environ.get("GUARDIAN_MODEL", "ibm/granite-guardian-3-8b")

# Risk categories we ask Guardian to evaluate
_RISK_CATEGORIES = [
    "harm",
    "violence",
    "hate",
    "sexual_content",
    "profanity",
]


def _is_enabled() -> bool:
    return os.environ.get("GUARDIAN_ENABLED", "false").lower() == "true"


def _get_client():
    """Return a watsonx.ai ModelInference client (lazy, cached per process)."""
    from ibm_watsonx_ai import Credentials  # type: ignore
    from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore

    credentials = Credentials(
        url=os.environ.get("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com"),
        api_key=os.environ["WATSONX_API_KEY"],
    )
    return ModelInference(
        model_id=_GUARDIAN_MODEL,
        credentials=credentials,
        project_id=os.environ["WATSONX_PROJECT_ID"],
    )


def _check_scene(client: Any, scene_text: str, threshold: float) -> dict[str, Any]:
    """Run a single scene text through Guardian and return the result dict.

    Returns:
        {
            "blocked": bool,
            "risk_score": float,
            "label": "Yes" | "No",
            "category": str,   # highest-risk category
        }
    """
    highest_score = 0.0
    highest_category = "none"
    blocked = False

    for category in _RISK_CATEGORIES:
        # Guardian uses a chat-style prompt with a specific instruction format
        prompt = (
            f"<|start_of_role|>user<|end_of_role|>"
            f"[{category}] {scene_text}"
            f"<|end_of_text|>"
            f"<|start_of_role|>assistant<|end_of_role|>"
        )

        response = client.generate(
            prompt=prompt,
            params={
                "max_new_tokens": 20,
                "temperature": 0.0,   # deterministic — safety checks must be consistent
            },
        )

        generated = (
            response.get("results", [{}])[0]
            .get("generated_text", "")
            .strip()
            .lower()
        )

        # Guardian returns "Yes" (harmful) or "No" (safe) followed by a score
        is_harmful = generated.startswith("yes")

        # Extract risk_score if present in response metadata
        risk_score: float = (
            response.get("results", [{}])[0]
            .get("attributes", {})
            .get("risk_score", 1.0 if is_harmful else 0.0)
        )

        if risk_score > highest_score:
            highest_score = risk_score
            highest_category = category

        if is_harmful and risk_score >= threshold:
            blocked = True
            break   # one confirmed harmful category is enough to block

    return {
        "blocked": blocked,
        "risk_score": highest_score,
        "label": "Yes" if blocked else "No",
        "category": highest_category,
    }


def granite_guardian_node(state: ScenePilotState) -> ScenePilotState:
    """LangGraph node — IBM Granite Guardian content safety gate.

    Positioned between sandbox_validator and compliance in the pipeline:
      sandbox → guardian → compliance

    When GUARDIAN_ENABLED=false (default): pass-through, zero API calls.
    When enabled: checks every scene; blocks on any harmful content.
    """
    span_start = time.time()

    # ── Fast pass-through when disabled ──────────────────────────────────────
    if not _is_enabled():
        span = {
            "agent": "GraniteGuardianAgent",
            "duration_ms": 0,
            "enabled": False,
            "blocked": False,
            "scenes_checked": 0,
            "success": True,
        }
        return {
            **state,
            "guardian_check": {"enabled": False, "blocked": False, "violations": []},
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    story = state.get("story")
    if story is None:
        span = {
            "agent": "GraniteGuardianAgent",
            "duration_ms": 0,
            "enabled": True,
            "blocked": False,
            "scenes_checked": 0,
            "success": False,
            "error": "No story to check",
        }
        return {
            **state,
            "guardian_check": {"enabled": True, "blocked": False, "violations": []},
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    threshold = float(os.environ.get("GUARDIAN_THRESHOLD", "0.8"))
    scenes = story.get("scenes", [])
    violations: list[dict[str, Any]] = []
    guardian_blocked = False
    error_msg: str | None = None

    try:
        client = _get_client()

        for scene in scenes:
            scene_id = scene.get("id", "?")
            text = scene.get("text", "")
            if not text:
                continue

            result = _check_scene(client, text, threshold)

            if result["blocked"]:
                guardian_blocked = True
                violations.append({
                    "scene_id":   scene_id,
                    "category":   result["category"],
                    "risk_score": result["risk_score"],
                    "text_excerpt": text[:120],
                })
                GUARDIAN_BLOCKS.inc()

    except Exception as exc:
        # Non-blocking — Guardian unavailability must never crash the pipeline
        error_msg = f"GraniteGuardian unavailable (non-blocking): {exc}"
        guardian_blocked = False  # do not penalise story for API unavailability

    duration = time.time() - span_start

    span = {
        "agent":          "GraniteGuardianAgent",
        "duration_ms":    int(duration * 1000),
        "enabled":        True,
        "blocked":        guardian_blocked,
        "scenes_checked": len(scenes),
        "violations":     len(violations),
        "success":        error_msg is None,
        "error":          error_msg,
    }

    # Revoke approval if Guardian found harmful content
    approved = state.get("approved", False) and not guardian_blocked

    return {
        **state,
        "approved": approved,
        "guardian_check": {
            "enabled":    True,
            "blocked":    guardian_blocked,
            "violations": violations,
            "threshold":  threshold,
            "error":      error_msg,
        },
        "agent_spans": [*state.get("agent_spans", []), span],
    }
