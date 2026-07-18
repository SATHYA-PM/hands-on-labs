"""
StyleVaultAgent — uses FAISS + sentence-transformers to check whether the
generated story scenes match the loaded style-guide rules.

Structured violation objects
────────────────────────────
Each violation is now stored as a dict (not a plain string):

    {
        "scene_id":   "scene_003",
        "type":       "faiss" | "tone",
        "score":      0.113,          # FAISS similarity (faiss violations only)
        "current_tone": "playful",    # tone violations only
        "rule":       "SHOW DON'T TELL ...",  # nearest rule excerpt
        "message":    "<human-readable string>"
    }

This lets the generator's repair prompt extract violating scene IDs with
zero fragile regex parsing — it reads scene_id directly from the struct.
The legacy `violations` list of strings is also preserved for the UI.
"""
from __future__ import annotations

import os
import time
from typing import Any

from agents.state import ScenePilotState

# Lazy-loaded vault singleton (populated on first use)
_vault = None


def _get_vault():
    global _vault
    if _vault is None:
        from core.style_vault import StyleVault
        _vault = StyleVault()
        rules_dir = os.path.join(os.path.dirname(__file__), "..", "data", "rules")
        _vault.load_rules_dir(os.path.abspath(rules_dir))
    return _vault


# ── Tone mapping ──────────────────────────────────────────────────────────────

VALID_TONES_BY_GENRE: dict[str, set[str]] = {
    "thriller": {"tense", "dark", "neutral"},
    "fantasy": {"hopeful", "tense", "neutral", "dark"},
    "sci-fi": {"tense", "neutral", "dark", "hopeful"},
    "educational": {"neutral", "hopeful", "playful"},
    "marketing": {"hopeful", "playful", "neutral"},
}


def _check_tone_consistency(
    story: dict[str, Any], genre: str
) -> list[dict[str, Any]]:
    """Return structured tone-violation objects."""
    allowed = VALID_TONES_BY_GENRE.get(genre, set())
    violations: list[dict[str, Any]] = []
    for scene in story.get("scenes", []):
        tone = scene.get("tone", "neutral")
        sid = scene.get("id", "?")
        if allowed and tone not in allowed:
            violations.append({
                "scene_id": sid,
                "type": "tone",
                "current_tone": tone,
                "allowed_tones": sorted(allowed),
                "rule": f"Genre '{genre}' only allows tones: {sorted(allowed)}",
                "message": (
                    f"Scene {sid} has tone '{tone}' which is not suitable "
                    f"for '{genre}' genre."
                ),
            })
    return violations


def _check_with_faiss(story: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured FAISS-violation objects."""
    vault = _get_vault()
    violations: list[dict[str, Any]] = []
    threshold = float(os.environ.get("STYLE_SIMILARITY_THRESHOLD", "0.35"))

    for scene in story.get("scenes", []):
        text = scene.get("text", "")
        sid = scene.get("id", "?")
        if not text:
            continue
        results = vault.query(text, k=1)
        if results:
            score, rule_text = results[0]
            if score < threshold:
                violations.append({
                    "scene_id": sid,
                    "type": "faiss",
                    "score": round(score, 3),
                    "rule": rule_text[:120],
                    "message": (
                        f"Scene {sid} may violate style guidelines "
                        f"(similarity={score:.3f}). "
                        f"Nearest rule: \"{rule_text[:80]}\u2026\""
                    ),
                })
    return violations


# ── LangGraph node ────────────────────────────────────────────────────────────

def style_vault_node(state: ScenePilotState) -> ScenePilotState:
    span_start = time.time()
    structured: list[dict[str, Any]] = []   # new — structured violation objects
    violation_strings: list[str] = []       # legacy — plain strings for UI

    story = state.get("story")
    if story is None:
        span = {
            "agent": "StyleVaultAgent",
            "duration_ms": 0,
            "violations": 0,
            "success": False,
        }
        return {
            **state,
            "style_check": {"violations": [], "structured": []},
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    try:
        tone_violations = _check_tone_consistency(story, state.get("genre", ""))
        structured.extend(tone_violations)

        faiss_violations = _check_with_faiss(story)
        structured.extend(faiss_violations)
    except Exception as exc:
        violation_strings.append(f"StyleVault error (non-blocking): {exc}")

    # Build legacy string list from structured objects (UI compatibility)
    violation_strings = [v["message"] for v in structured]

    span = {
        "agent": "StyleVaultAgent",
        "duration_ms": int((time.time() - span_start) * 1000),
        "violations": len(structured),
        "success": True,
    }

    current_validation = state.get("validation") or {
        "passed": True,
        "issues": [],
        "cycles_detected": 0,
        "schema_errors": [],
        "style_violations": [],
    }

    return {
        **state,
        # structured: list of {scene_id, type, score/current_tone, rule, message}
        # violations: legacy string list — preserved for UI / ValidationReport
        "style_check": {
            "violations": violation_strings,
            "structured": structured,
        },
        "validation": {
            **current_validation,
            "style_violations": violation_strings,
        },
        "agent_spans": [*state.get("agent_spans", []), span],
    }
