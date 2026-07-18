"""
StyleVaultAgent — uses FAISS + sentence-transformers to check whether the
generated story scenes match the loaded style-guide rules.
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


def _check_tone_consistency(story: dict[str, Any], genre: str) -> list[str]:
    allowed = VALID_TONES_BY_GENRE.get(genre, set())
    violations: list[str] = []
    for scene in story.get("scenes", []):
        tone = scene.get("tone", "neutral")
        if allowed and tone not in allowed:
            violations.append(
                f"Scene {scene.get('id', '?')} has tone '{tone}' "
                f"which is not suitable for '{genre}' genre."
            )
    return violations


def _check_with_faiss(story: dict[str, Any]) -> list[str]:
    """Embed each scene text and check distance against style-guide rules."""
    vault = _get_vault()
    violations: list[str] = []
    threshold = float(os.environ.get("STYLE_SIMILARITY_THRESHOLD", "0.35"))

    for scene in story.get("scenes", []):
        text = scene.get("text", "")
        if not text:
            continue
        results = vault.query(text, k=1)
        if results:
            score, rule_text = results[0]
            if score < threshold:
                violations.append(
                    f"Scene {scene.get('id', '?')} may violate style guidelines "
                    f"(similarity={score:.3f}). Nearest rule: \"{rule_text[:80]}…\""
                )
    return violations


# ── LangGraph node ────────────────────────────────────────────────────────────

def style_vault_node(state: ScenePilotState) -> ScenePilotState:
    span_start = time.time()
    violations: list[str] = []

    story = state.get("story")
    if story is None:
        # Nothing to check — pass through
        span = {
            "agent": "StyleVaultAgent",
            "duration_ms": 0,
            "violations": 0,
            "success": False,
        }
        return {**state, "style_check": {"violations": []}, "agent_spans": [*state.get("agent_spans", []), span]}

    try:
        tone_violations = _check_tone_consistency(story, state.get("genre", ""))
        violations.extend(tone_violations)

        faiss_violations = _check_with_faiss(story)
        violations.extend(faiss_violations)
    except Exception as exc:
        violations.append(f"StyleVault error (non-blocking): {exc}")

    span = {
        "agent": "StyleVaultAgent",
        "duration_ms": int((time.time() - span_start) * 1000),
        "violations": len(violations),
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
        "style_check": {"violations": violations},
        "validation": {
            **current_validation,
            "style_violations": violations,
        },
        "agent_spans": [*state.get("agent_spans", []), span],
    }
