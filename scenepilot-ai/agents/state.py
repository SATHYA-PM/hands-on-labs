"""
ScenePilotState — shared TypedDict passed through every LangGraph node.
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class ValidationResult(TypedDict):
    passed: bool
    issues: list[str]
    cycles_detected: int
    schema_errors: list[str]
    style_violations: list[str]


class AuditEntry(TypedDict):
    story_id: str
    fingerprint: str
    timestamp: str
    agent_spans: list[dict[str, Any]]
    token_spend: int
    validation: ValidationResult


class ScenePilotState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    story_id: str
    premise: str
    genre: str          # thriller | fantasy | sci-fi | educational | marketing
    tone: float         # 0.0 (dark) → 1.0 (light)

    # ── Story payload ──────────────────────────────────────────────────────
    story: Optional[dict[str, Any]]          # raw JSON from StoryGeneratorAgent
    story_json: Optional[str]                # serialised string for sandbox

    # ── Validation state ───────────────────────────────────────────────────
    validation: Optional[ValidationResult]
    style_check: Optional[dict[str, Any]]    # raw FAISS result

    # ── Control flow ───────────────────────────────────────────────────────
    approved: bool
    retry_count: int
    max_retries: int

    # ── Diff-based repair state ────────────────────────────────────────────
    # broken_nodes: list of (source_scene_id, target_scene_id) cycle edge pairs
    # reported by the sandbox; used to scope the repair prompt.
    broken_nodes: Optional[list[tuple[str, str]]]
    # last_story: the most recent well-formed story dict carried forward so
    # the repair pass can patch it rather than regenerate from scratch.
    last_story: Optional[dict[str, Any]]
    # repair_mode: True when retry_count >= 1 and broken_nodes is non-empty,
    # signalling the generator to emit a minimal patch instead of a full story.
    repair_mode: bool
    # structural_issues: structural warning strings from the most recent sandbox
    # pass (orphaned scenes, dangling next references); consumed by
    # structural_repair mode in story_generator_node.
    structural_issues: Optional[list[str]]

    # ── Audit / telemetry ──────────────────────────────────────────────────
    audit: Optional[AuditEntry]
    agent_spans: list[dict[str, Any]]
    token_spend: int
    error: Optional[str]
    # budget_halt: True when the mid-pipeline or generator budget guard fired.
    # Lets the API route produce a distinct user-facing message without
    # string-matching the error field.
    budget_halt: bool
    # guardian_check: result dict from GraniteGuardianAgent
    guardian_check: Optional[dict]
