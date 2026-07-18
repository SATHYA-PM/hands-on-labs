"""
SandboxValidatorAgent — runs the story JSON through cycle detection and schema
validation, preferring a Docker subprocess; falls back to in-process networkx.
"""
from __future__ import annotations

import time

from agents.state import ScenePilotState
from sandbox.validator import validate_story
from core.telemetry import (
    STORIES_GENERATED,
    LOOP_DETECTIONS,
    SANDBOX_REJECTIONS,
    VALIDATION_DURATION,
)


def sandbox_validator_node(state: ScenePilotState) -> ScenePilotState:
    span_start = time.time()

    story = state.get("story")
    if story is None:
        span = {
            "agent": "SandboxValidatorAgent",
            "duration_ms": 0,
            "passed": False,
            "success": False,
        }
        return {
            **state,
            "approved": False,
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    result = validate_story(story)

    duration = time.time() - span_start
    VALIDATION_DURATION.observe(duration)

    if result["cycles_detected"] > 0:
        LOOP_DETECTIONS.inc(result["cycles_detected"])

    passed = result["passed"]
    style_violations: list[str] = state.get("style_check", {}).get("violations", [])
    approved = passed and len(style_violations) == 0

    if not approved:
        SANDBOX_REJECTIONS.inc()
    else:
        STORIES_GENERATED.inc()

    # ── Capture repair state for both cycle failures AND style failures ───
    #
    # Repair mode activates on ANY retry where we have a saved story:
    #   - Cycle failure  → broken_nodes carries the back-edge pairs
    #   - Style failure  → broken_nodes stays [] but style_violations is non-empty
    #
    # In both cases we persist last_story so the generator can send a targeted
    # patch prompt instead of a full cold regeneration (~80 % token saving).
    invalid_edges: list[tuple[str, str]] = result.get("invalid_edges", [])
    broken_nodes = invalid_edges if invalid_edges else state.get("broken_nodes") or []

    # Always persist the current story when not approved so the repair pass
    # has a base to patch against.  Previously this only ran when cycles were
    # found; style-only failures left last_story=None, blocking repair mode.
    last_story = story if not approved else state.get("last_story")

    span = {
        "agent": "SandboxValidatorAgent",
        "duration_ms": int(duration * 1000),
        "passed": passed,
        "cycles": result["cycles_detected"],
        "invalid_edges": invalid_edges,
        "schema_errors": len(result["schema_errors"]),
        "style_violations": len(style_violations),
        "success": True,
    }

    current_validation = state.get("validation") or {
        "passed": True,
        "issues": [],
        "cycles_detected": 0,
        "schema_errors": [],
        "style_violations": [],
    }

    merged_validation = {
        **current_validation,
        "passed": passed,
        "cycles_detected": result["cycles_detected"],
        "schema_errors": result["schema_errors"],
        "issues": result["schema_errors"] + current_validation.get("style_violations", []),
    }

    return {
        **state,
        "validation": merged_validation,
        "approved": approved,
        "broken_nodes": broken_nodes,
        "last_story": last_story,
        "agent_spans": [*state.get("agent_spans", []), span],
    }
