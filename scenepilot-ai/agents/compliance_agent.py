"""
ComplianceAgent — generates a SHA-256 fingerprint of the approved story and
writes a structured audit entry into the state.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from agents.state import AuditEntry, ScenePilotState
from core.story_store import story_store


def compliance_node(state: ScenePilotState) -> ScenePilotState:
    from core.progress import emit as _emit
    span_start = time.time()

    _emit(state.get("story_id", ""), "progress", {
        "stage": "compliance",
        "message": "Generating compliance fingerprint…",
        "approved": state.get("approved", False),
    })

    story = state.get("story")
    story_id = state.get("story_id", "unknown")

    fingerprint = ""
    if story:
        raw = json.dumps(story, sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()

    audit: AuditEntry = {
        "story_id": story_id,
        "fingerprint": fingerprint,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_spans": state.get("agent_spans", []),
        "token_spend": state.get("token_spend", 0),
        "validation": state.get("validation") or {
            "passed": False,
            "issues": [],
            "cycles_detected": 0,
            "schema_errors": [],
            "style_violations": [],
        },
    }

    # Persist to the in-memory store
    story_store.save(story_id, {
        "story": story,
        "audit": audit,
        "approved": state.get("approved", False),
        "premise": state.get("premise", ""),
        "genre": state.get("genre", ""),
        "tone": state.get("tone", 0.5),
    })

    span = {
        "agent": "ComplianceAgent",
        "duration_ms": int((time.time() - span_start) * 1000),
        "fingerprint": fingerprint[:16] + "…",
        "success": True,
    }

    return {
        **state,
        "audit": audit,
        "agent_spans": [*state.get("agent_spans", []), span],
    }
