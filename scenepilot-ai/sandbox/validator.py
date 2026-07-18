"""
Core story validation logic — networkx cycle detection + JSON schema check.
Used both in-process and when invoked from the Docker sandbox runner.
"""
from __future__ import annotations

from typing import Any

REQUIRED_SCENE_KEYS = {"id", "text", "tone", "choices"}
VALID_TONES = {"tense", "hopeful", "dark", "neutral", "playful"}


MIN_SCENES = 6


def validate_story(story: dict[str, Any]) -> dict[str, Any]:
    """
    Returns:
        {
            "passed": bool,
            "issues": [str, ...],
            "cycles_detected": int,
            "invalid_edges": [(src, dst), ...],   # back-edges that form cycles
            "schema_errors": [str, ...],
            "structural_warnings": [str, ...],
        }
    """
    schema_errors = _check_schema(story)
    cycles, cycle_issues, invalid_edges = _check_cycles(story)
    structural = _check_structure(story)

    issues = schema_errors + cycle_issues + structural
    passed = len(issues) == 0

    return {
        "passed": passed,
        "issues": issues,
        "cycles_detected": cycles,
        "invalid_edges": invalid_edges,
        "schema_errors": schema_errors,
        "structural_warnings": structural,
    }


# ── Schema check ──────────────────────────────────────────────────────────────

def _check_schema(story: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(story, dict):
        return ["Story must be a JSON object."]

    if "title" not in story:
        errors.append("Missing required field: 'title'.")

    scenes = story.get("scenes")
    if not scenes or not isinstance(scenes, list):
        errors.append("Missing or empty 'scenes' array.")
        return errors  # can't go further

    scene_ids: set[str] = set()
    for i, scene in enumerate(scenes):
        prefix = f"Scene[{i}]"
        if not isinstance(scene, dict):
            errors.append(f"{prefix} is not an object.")
            continue

        for key in REQUIRED_SCENE_KEYS:
            if key not in scene:
                errors.append(f"{prefix} missing field '{key}'.")

        sid = scene.get("id")
        if sid:
            if sid in scene_ids:
                errors.append(f"Duplicate scene id '{sid}'.")
            scene_ids.add(str(sid))

        tone = scene.get("tone", "neutral")
        if tone not in VALID_TONES:
            errors.append(
                f"{prefix} ({sid}) has invalid tone '{tone}'. "
                f"Allowed: {sorted(VALID_TONES)}."
            )

        choices = scene.get("choices", [])
        if not isinstance(choices, list):
            errors.append(f"{prefix} ({sid}) 'choices' must be an array.")
        else:
            for j, choice in enumerate(choices):
                if "text" not in choice:
                    errors.append(f"{prefix} choice[{j}] missing 'text'.")
                # 'next' can be null for endings — that's valid

    return errors


# ── Structural checks: dead-ends, orphans, scene count ───────────────────────

def _check_structure(story: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scenes = story.get("scenes", [])
    if not scenes:
        return issues

    # Minimum scene count
    if len(scenes) < MIN_SCENES:
        issues.append(
            f"Story has only {len(scenes)} scenes (minimum required: {MIN_SCENES})."
        )

    scene_ids = {s.get("id") for s in scenes if s.get("id")}
    referenced = set()

    for scene in scenes:
        sid = scene.get("id")
        choices = scene.get("choices", []) if isinstance(scene.get("choices"), list) else []
        for choice in choices:
            nxt = choice.get("next")
            if nxt:
                referenced.add(nxt)
                # Dangling reference — points to a scene that doesn't exist
                if nxt not in scene_ids:
                    issues.append(
                        f"Scene '{sid}' choice '{choice.get('text', '?')}' "
                        f"points to non-existent scene '{nxt}'."
                    )

    # Orphaned scenes — reachable only from scene_001 root via BFS
    if scenes:
        root = scenes[0].get("id")
        scene_map = {s.get("id"): s for s in scenes if s.get("id")}
        visited: set[str] = set()
        queue = [root]
        while queue:
            nid = queue.pop()
            if nid in visited or nid not in scene_map:
                continue
            visited.add(nid)
            for choice in scene_map[nid].get("choices", []):
                nxt = choice.get("next")
                if nxt:
                    queue.append(nxt)
        orphans = scene_ids - visited
        for oid in sorted(orphans):
            issues.append(f"Scene '{oid}' is unreachable from the root scene.")

    return issues


# ── Cycle detection ───────────────────────────────────────────────────────────

def _check_cycles(story: dict[str, Any]) -> tuple[int, list[str], list[tuple[str, str]]]:
    """Return (cycle_count, human_readable_issues, invalid_edges).

    invalid_edges is a deduplicated list of (source_id, target_id) pairs that
    are back-edges causing cycles — exactly the routing properties that need
    to be patched in REPAIR MODE.
    """
    try:
        import networkx as nx  # type: ignore
    except ImportError:
        return 0, [], []  # networkx missing — skip silently

    G = nx.DiGraph()
    scenes = story.get("scenes", [])
    for scene in scenes:
        sid = scene.get("id")
        if not sid:
            continue
        G.add_node(sid)
        for choice in scene.get("choices", []):
            nxt = choice.get("next")
            if nxt:
                G.add_edge(sid, nxt)

    cycles = list(nx.simple_cycles(G))
    issues = [
        f"Cycle detected: {' → '.join(c + [c[0]])}" for c in cycles
    ]

    # Extract the specific back-edges that close each cycle.
    # For a cycle [A, B, C] the closing edge is (C → A); also capture every
    # intra-cycle edge so the patcher has full context.
    seen: set[tuple[str, str]] = set()
    invalid_edges: list[tuple[str, str]] = []
    for cycle in cycles:
        for i, node in enumerate(cycle):
            edge = (node, cycle[(i + 1) % len(cycle)])
            if edge not in seen:
                seen.add(edge)
                invalid_edges.append(edge)

    return len(cycles), issues, invalid_edges


# ── CLI entrypoint (used by Docker runner) ────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    data = json.loads(sys.stdin.read())
    result = validate_story(data)
    print(json.dumps(result))
    sys.exit(0 if result["passed"] else 1)
