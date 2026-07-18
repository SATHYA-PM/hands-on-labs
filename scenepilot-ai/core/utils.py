"""
core/utils.py — Shared utility helpers for ScenePilot AI.

merge_patch: deeply merges a diff-based repair patch returned by the LLM in
REPAIR MODE back into the original full story object, updating only the
'choices' arrays of the scenes listed in the patch.
"""
from __future__ import annotations

import copy
from typing import Any


def merge_patch(
    original_story: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Merge a repair patch into *original_story* and return a new story dict.

    The patch is a mapping of ``scene_id → list[choice]`` — the minimal diff
    returned by the LLM in REPAIR MODE.  Only the ``choices`` array of each
    named scene is replaced; every other scene and all top-level story fields
    (``title``, ``genre``, scene ``text`` / ``tone``) are preserved verbatim.

    Parameters
    ----------
    original_story:
        The full story dict produced in Attempt 1 (stored as ``last_story``
        in the LangGraph state).
    patch:
        A dict whose keys are scene IDs and whose values are the replacement
        ``choices`` list for that scene.  Example::

            {
                "scene_004": [
                    {"text": "Confront the mole", "next": "scene_013"},
                    {"text": "Flee the building",  "next": "scene_015"}
                ],
                "scene_012": [
                    {"text": "Trust the handler", "next": "scene_016"}
                ]
            }

    Returns
    -------
    dict
        A deep copy of *original_story* with the patched ``choices`` arrays
        applied.  The original object is never mutated.
    """
    if not patch:
        return original_story

    merged = copy.deepcopy(original_story)
    scenes = merged.get("scenes")
    if not isinstance(scenes, list):
        return merged

    # Build a quick-lookup index so patching is O(patch_size) not O(n²)
    scene_index: dict[str, dict[str, Any]] = {
        s["id"]: s for s in scenes if isinstance(s, dict) and "id" in s
    }

    for scene_id, new_choices in patch.items():
        scene = scene_index.get(scene_id)
        if scene is None:
            # Patch references a scene that doesn't exist — skip gracefully
            continue
        if not isinstance(new_choices, list):
            continue
        scene["choices"] = new_choices

    return merged
