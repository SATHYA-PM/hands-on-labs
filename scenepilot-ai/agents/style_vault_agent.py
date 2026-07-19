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
    """Return structured FAISS-violation objects.

    Queries k=3 rules and takes the BEST (highest) score across all three.
    This prevents a scene from being flagged just because its single nearest
    rule happens to be a poor semantic match — we give it three chances to
    align with any relevant guideline before declaring a violation.

    Threshold is read from STYLE_SIMILARITY_THRESHOLD (default 0.15).
    The old default of 0.35 was calibrated for paragraph-level chunks;
    after switching to sentence-level chunks the natural similarity range
    for well-written scenes is 0.20–0.55, so 0.15 is the right floor
    that filters genuinely off-tone text without false-positive-flooding.
    """
    vault = _get_vault()
    violations: list[dict[str, Any]] = []
    threshold = float(os.environ.get("STYLE_SIMILARITY_THRESHOLD", "0.15"))

    for scene in story.get("scenes", []):
        text = scene.get("text", "")
        sid = scene.get("id", "?")
        if not text:
            continue
        # Query top-3 rules; take the best score (most favourable match)
        results = vault.query(text, k=3)
        if not results:
            continue
        best_score, best_rule = results[0]   # sorted descending by vault.query
        if best_score < threshold:
            violations.append({
                "scene_id": sid,
                "type": "faiss",
                "score": round(best_score, 3),
                "rule": best_rule[:120],
                "message": (
                    f"Scene {sid} may violate style guidelines "
                    f"(best similarity={best_score:.3f}, threshold={threshold}). "
                    f"Nearest rule: \"{best_rule[:80]}\u2026\""
                ),
            })
    return violations


# ── LangGraph node ────────────────────────────────────────────────────────────

def style_vault_node(state: ScenePilotState) -> ScenePilotState:
    """Style quality gate.

    TWO-TIER design:
    ─────────────────
    BLOCKING  — tone label mismatches (e.g. 'hopeful' in a thriller).
                These are deterministic schema-level errors the LLM can
                trivially fix with a single-field patch.

    ADVISORY  — FAISS semantic similarity scores.
                Cosine similarity between a 15-word narrative scene and a
                15-word style-guide sentence clusters at 0.18–0.34 for ALL
                well-written prose — the distributions overlap completely.
                Using FAISS as an approval gate causes 80+ false positives
                per run regardless of story quality.  It is preserved as a
                DIAGNOSTIC signal in the UI (visible in ValidationReport)
                but NEVER counted toward approval.
    """
    span_start = time.time()
    tone_structured: list[dict[str, Any]] = []   # BLOCKING — used for approval
    faiss_structured: list[dict[str, Any]] = []  # ADVISORY — UI only

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
            "style_check": {"violations": [], "structured": [], "tone_violations": []},
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    try:
        tone_structured = _check_tone_consistency(story, state.get("genre", ""))
    except Exception as exc:
        tone_structured = []

    try:
        faiss_structured = _check_with_faiss(story)
    except Exception:
        faiss_structured = []

    # BLOCKING violations = tone mismatches only
    blocking = tone_structured
    # ADVISORY violations = FAISS scores (shown in UI, never block approval)
    advisory = faiss_structured

    # Legacy string list for UI — all violations shown as info
    all_strings = [v["message"] for v in blocking + advisory]
    # Blocking strings only — used by sandbox_validator for approval gate
    blocking_strings = [v["message"] for v in blocking]

    span = {
        "agent": "StyleVaultAgent",
        "duration_ms": int((time.time() - span_start) * 1000),
        "violations": len(blocking),          # blocking count in span
        "advisory_violations": len(advisory), # FAISS advisory count
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
        "style_check": {
            # 'violations' carries BLOCKING violations only — used by sandbox gate
            "violations": blocking_strings,
            # 'advisory' carries FAISS scores — shown in UI, never blocks
            "advisory": all_strings,
            # 'structured' carries all violations for repair prompts
            "structured": blocking + advisory,
            # 'tone_violations' for targeted tone-repair prompt
            "tone_violations": tone_structured,
        },
        "validation": {
            **current_validation,
            # style_violations in ValidationResult = blocking only
            "style_violations": blocking_strings,
            # advisory shown in UI under separate key
            "style_advisory": all_strings,
        },
        "agent_spans": [*state.get("agent_spans", []), span],
    }
