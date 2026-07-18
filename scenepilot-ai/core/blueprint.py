"""
Blueprint generator — converts a story scene graph into a 3D spatial
transform matrix compatible with Unity, Unreal Engine, and Godot.

Layout algorithm:
- BFS assigns each scene a (level, index) position
- X = horizontal index within level, spaced by ROOM_SPACING_X
- Z = level depth, spaced by ROOM_SPACING_Z
- Y = 0 (flat plane); scenes with no outgoing choices are raised to Y=1
  to visually mark them as terminal rooms
"""
from __future__ import annotations

import math
from typing import Any


ROOM_SPACING_X = 12.0   # metres between rooms on same level
ROOM_SPACING_Z = 18.0   # metres between levels
WALL_HEIGHT    = 4.0
ROOM_SIZE      = 8.0

INTERACTION_TYPES = {
    0: "Door_Primary",
    1: "Door_Secondary",
    2: "Door_Tertiary",
}

ASSET_PALETTE: dict[str, list[str]] = {
    "tense":   ["corridor_industrial", "flickering_light", "security_camera"],
    "dark":    ["dungeon_stone_room",   "torch_wall",       "iron_door"],
    "hopeful": ["sunlit_chamber",       "open_archway",     "fountain"],
    "neutral": ["plain_room",           "wooden_door",      "bookshelf"],
    "playful": ["colourful_hall",       "bouncy_platform",  "confetti_trigger"],
}


# ── Public entry point ────────────────────────────────────────────────────────

def generate_blueprint(story: dict[str, Any], story_id: str = "story") -> dict[str, Any]:
    scenes = story.get("scenes", [])
    if not scenes:
        return {"story_id": story_id, "spatial_nodes": []}

    positions = _bfs_layout(scenes)
    scene_map = {s["id"]: s for s in scenes if s.get("id")}

    spatial_nodes = []
    for scene in scenes:
        sid = scene.get("id", "")
        pos = positions.get(sid, (0, 0))
        level, col = pos

        # Centre the column within its level
        level_ids = [k for k, v in positions.items() if v[0] == level]
        count = len(level_ids)
        x = (col - (count - 1) / 2.0) * ROOM_SPACING_X
        z = level * ROOM_SPACING_Z
        choices = scene.get("choices", [])
        is_terminal = len(choices) == 0
        y = 1.0 if is_terminal else 0.0

        # Rotation: face toward the centroid of child rooms
        rotation_y = _calc_rotation(sid, scene_map, positions, level, col)

        tone = scene.get("tone", "neutral")
        assets = ASSET_PALETTE.get(tone, ASSET_PALETTE["neutral"]).copy()

        triggers = []
        for i, choice in enumerate(choices):
            if choice.get("next"):
                triggers.append({
                    "choice_index":    i,
                    "choice_label":    choice.get("text", ""),
                    "target_scene":    choice["next"],
                    "interaction_type": INTERACTION_TYPES.get(i, f"Door_{i}"),
                    "distance_metres": _distance_to(
                        (x, y, z), choice["next"], scene_map, positions
                    ),
                })

        spatial_nodes.append({
            "scene_id":   sid,
            "room_name":  _room_name(scene),
            "tone":       tone,
            "is_terminal": is_terminal,
            "transform": {
                "position": [round(x, 2), round(y, 2), round(z, 2)],
                "rotation": [0.0, round(rotation_y, 1), 0.0],
                "scale":    [1.0, 1.0, 1.0],
            },
            "bounds": {
                "width":  ROOM_SIZE,
                "height": WALL_HEIGHT,
                "depth":  ROOM_SIZE,
            },
            "assets_to_load": assets,
            "triggers": triggers,
        })

    # Summary stats
    total_rooms    = len(spatial_nodes)
    terminal_rooms = sum(1 for n in spatial_nodes if n["is_terminal"])
    max_depth      = max((positions[s["id"]][0] for s in scenes if s.get("id")), default=0)

    return {
        "story_id":       story_id,
        "engine_formats": ["Unity (C# MonoBehaviour)", "Unreal Engine (Blueprint JSON)", "Godot (GDScript Resource)"],
        "world_bounds": {
            "x_extent": round((max(pos[1] for pos in positions.values()) + 1) * ROOM_SPACING_X, 1),
            "z_extent": round((max_depth + 1) * ROOM_SPACING_Z, 1),
            "y_extent": WALL_HEIGHT,
        },
        "stats": {
            "total_rooms":    total_rooms,
            "terminal_rooms": terminal_rooms,
            "max_depth":      max_depth,
            "total_triggers": sum(len(n["triggers"]) for n in spatial_nodes),
        },
        "spatial_nodes": spatial_nodes,
    }


# ── Layout helpers ────────────────────────────────────────────────────────────

def _bfs_layout(scenes: list[dict]) -> dict[str, tuple[int, int]]:
    """BFS from root. Returns {scene_id: (level, col_index)}."""
    scene_map = {s["id"]: s for s in scenes if s.get("id")}
    levels: dict[str, int] = {}
    queue = [scenes[0]["id"]]
    levels[scenes[0]["id"]] = 0

    while queue:
        sid = queue.pop(0)
        scene = scene_map.get(sid)
        if not scene:
            continue
        for choice in scene.get("choices", []):
            nxt = choice.get("next")
            if nxt and nxt not in levels:
                levels[nxt] = levels[sid] + 1
                queue.append(nxt)

    # Assign orphaned scenes
    for s in scenes:
        if s.get("id") and s["id"] not in levels:
            levels[s["id"]] = 0

    # Column index within each level
    by_level: dict[int, list[str]] = {}
    for sid, lvl in levels.items():
        by_level.setdefault(lvl, []).append(sid)

    positions: dict[str, tuple[int, int]] = {}
    for lvl, ids in by_level.items():
        for col, sid in enumerate(ids):
            positions[sid] = (lvl, col)

    return positions


def _calc_rotation(
    sid: str,
    scene_map: dict,
    positions: dict[str, tuple[int, int]],
    level: int,
    col: int,
) -> float:
    """Rotate room to face the average position of its children."""
    scene = scene_map.get(sid)
    if not scene:
        return 0.0
    children = [c["next"] for c in scene.get("choices", []) if c.get("next") and c["next"] in positions]
    if not children:
        return 0.0
    avg_col = sum(positions[c][1] for c in children) / len(children)
    delta = avg_col - col
    if delta > 0:
        return 45.0
    if delta < 0:
        return -45.0
    return 0.0


def _distance_to(
    origin: tuple[float, float, float],
    target_id: str,
    scene_map: dict,
    positions: dict[str, tuple[int, int]],
) -> float:
    if target_id not in positions:
        return 0.0
    t_level, t_col = positions[target_id]
    # Rough world position of target
    level_ids = [k for k, v in positions.items() if v[0] == t_level]
    count = len(level_ids)
    tx = (t_col - (count - 1) / 2.0) * ROOM_SPACING_X
    tz = t_level * ROOM_SPACING_Z
    dx = tx - origin[0]
    dz = tz - origin[2]
    return round(math.sqrt(dx * dx + dz * dz), 2)


def _room_name(scene: dict) -> str:
    """Derive a short room name from scene text."""
    text = scene.get("text", "")
    words = text.replace(".", "").replace(",", "").split()
    # Take first 3-4 meaningful words
    stop = {"you", "the", "a", "an", "is", "are", "and", "in", "at", "to", "of", "it"}
    meaningful = [w.capitalize() for w in words if w.lower() not in stop][:4]
    return " ".join(meaningful) if meaningful else scene.get("id", "Room")
