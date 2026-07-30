"""
HallucinationVerifierAgent — RAG-style confidence + grounding check.

Implements the four-layer framework:
  1. Retrieval confidence  — cosine similarity of each scene against the premise;
                             low scores signal the scene may be hallucinated.
  2. Evidence grounding    — every scene must trace back to at least one premise
                             fragment; the best-matching fragment is stored as
                             evidence so the UI can show it.
  3. Verification          — rule-based checks: does the scene introduce proper
                             nouns, locations, or plot elements absent from the
                             premise?  Flagged as low-confidence.
  4. No blind rejection    — scenes below the confidence threshold are NOT
                             blocked outright.  They are flagged in
                             hallucination_check so the repair loop can rewrite
                             them with a targeted prompt instead of failing.

Fail-safe design
────────────────
- If sentence-transformers is unavailable the node passes through immediately
  (non-blocking) — zero cost for envs without the heavy ML dependency.
- Flagging never blocks the pipeline; it enriches the ValidationReport and
  feeds the repair loop.

Environment variables
─────────────────────
  HALLUCINATION_CONFIDENCE_THRESHOLD   0.0–1.0  (default: 0.20)
      Scenes with premise-similarity below this are flagged as low-confidence.
  HALLUCINATION_ENABLED                true | false  (default: true)
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

from agents.state import ScenePilotState

_THRESHOLD = float(os.environ.get("HALLUCINATION_CONFIDENCE_THRESHOLD", "0.20"))


def _is_enabled() -> bool:
    return os.environ.get("HALLUCINATION_ENABLED", "true").lower() != "false"


def _premise_fragments(premise: str) -> list[str]:
    """Split premise into overlapping sentence-level fragments for retrieval."""
    sentences = [s.strip() for s in re.split(r"[.!?;]", premise) if s.strip()]
    # Also add the full premise as a fragment so broad thematic matches score well
    if premise.strip() not in sentences:
        sentences.append(premise.strip())
    return sentences or [premise]


def _embed(texts: list[str]):
    """Return a numpy array of embeddings using sentence-transformers."""
    from sentence_transformers import SentenceTransformer  # type: ignore
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(texts, normalize_embeddings=True)


def _cosine(a, b) -> float:
    """Cosine similarity for already-normalised vectors (dot product)."""
    import numpy as np  # type: ignore
    return float(np.dot(a, b))


def _retrieval_gap(premise_embs, scene_emb) -> float:
    """Gap between top-1 and top-2 premise-fragment similarity scores.

    A large gap (> 0.15) means one fragment dominates — high confidence.
    A small gap (< 0.05) means the scene matches nothing specifically — risky.
    """
    import numpy as np  # type: ignore
    scores = sorted([_cosine(scene_emb, p) for p in premise_embs], reverse=True)
    if len(scores) < 2:
        return 1.0  # only one fragment — treat as confident
    return scores[0] - scores[1]


def hallucination_verifier_node(state: ScenePilotState) -> ScenePilotState:
    """LangGraph node — confidence + grounding check for every scene.

    Positioned between story_generator and style_vault:
      generate → hallucination_verifier → style_vault → sandbox → guardian → compliance

    Never blocks the pipeline — flags low-confidence scenes for repair or review.
    """
    span_start = time.time()

    if not _is_enabled():
        span = {
            "agent": "HallucinationVerifierAgent",
            "duration_ms": 0,
            "enabled": False,
            "flagged": False,
            "scenes_checked": 0,
            "success": True,
        }
        return {
            **state,
            "hallucination_check": {"enabled": False, "flagged": False,
                                    "scene_scores": [], "low_confidence_scenes": [],
                                    "retrieval_gap": 1.0},
            "agent_spans": [*state.get("agent_spans", []), span],
        }

    story = state.get("story")
    premise = state.get("premise", "")
    error_msg: str | None = None
    scene_scores: list[dict[str, Any]] = []
    low_confidence: list[str] = []
    avg_gap = 1.0

    try:
        fragments = _premise_fragments(premise)
        all_texts = fragments + [
            scene.get("text", "") for scene in (story or {}).get("scenes", [])
            if scene.get("text")
        ]

        embeddings = _embed(all_texts)
        premise_embs = embeddings[:len(fragments)]
        scene_embs   = embeddings[len(fragments):]

        scenes = (story or {}).get("scenes", [])
        valid_scenes = [s for s in scenes if s.get("text")]
        gaps: list[float] = []

        for idx, scene in enumerate(valid_scenes):
            scene_id = scene.get("id", f"scene_{idx:03d}")
            emb = scene_embs[idx]

            # ── Layer 1: retrieval confidence ──────────────────────────────
            sim_scores = [(_cosine(emb, p), fragments[i])
                          for i, p in enumerate(premise_embs)]
            sim_scores.sort(key=lambda x: x[0], reverse=True)

            best_score, best_fragment = sim_scores[0]
            grounded = best_score >= _THRESHOLD

            # ── Layer 2: evidence grounding ────────────────────────────────
            evidence = best_fragment if grounded else (
                f"No strong match (best={best_score:.3f}) — "
                f"nearest: \"{best_fragment[:80]}\""
            )

            # ── Layer 3: retrieval gap ─────────────────────────────────────
            gap = _retrieval_gap(premise_embs, emb)
            gaps.append(gap)

            # ── Layer 4: rule-based verification ──────────────────────────
            # Flag scenes that reference named entities not found in premise
            scene_text = scene.get("text", "")
            premise_words = set(re.findall(r"\b[A-Z][a-z]+\b", premise))
            scene_proper = set(re.findall(r"\b[A-Z][a-z]+\b", scene_text))
            novel_entities = scene_proper - premise_words - {
                "The", "A", "An", "He", "She", "They", "It", "His", "Her"
            }
            # Novel entities alone don't flag — they penalise the confidence score
            entity_penalty = min(0.05 * len(novel_entities), 0.15)
            adjusted_score = max(0.0, best_score - entity_penalty)

            if not grounded or adjusted_score < _THRESHOLD:
                low_confidence.append(scene_id)

            scene_scores.append({
                "scene_id":   scene_id,
                "confidence": round(adjusted_score, 3),
                "raw_score":  round(best_score, 3),
                "grounded":   grounded,
                "evidence":   evidence,
                "gap":        round(gap, 3),
                "novel_entities": sorted(novel_entities)[:5],
            })

        avg_gap = round(sum(gaps) / len(gaps), 3) if gaps else 1.0

    except ImportError:
        error_msg = "sentence-transformers not available — hallucination check skipped"
    except Exception as exc:
        error_msg = f"HallucinationVerifier error (non-blocking): {exc}"

    flagged = bool(low_confidence)
    duration = time.time() - span_start

    span = {
        "agent":               "HallucinationVerifierAgent",
        "duration_ms":         int(duration * 1000),
        "enabled":             True,
        "flagged":             flagged,
        "scenes_checked":      len(scene_scores),
        "low_confidence":      len(low_confidence),
        "avg_retrieval_gap":   avg_gap,
        "success":             error_msg is None,
        "error":               error_msg,
    }

    return {
        **state,
        "hallucination_check": {
            "enabled":               True,
            "flagged":               flagged,
            "scene_scores":          scene_scores,
            "low_confidence_scenes": low_confidence,
            "retrieval_gap":         avg_gap,
            "threshold":             _THRESHOLD,
            "error":                 error_msg,
        },
        "agent_spans": [*state.get("agent_spans", []), span],
    }
