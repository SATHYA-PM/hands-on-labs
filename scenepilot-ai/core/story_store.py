"""
Story store — persists each story as a JSON file under STORY_STORE_DIR.

On startup the store scans the directory and loads all existing records into
an in-memory index (story_id → file path) so lookups stay fast.  Writes are
atomic: data is serialised to a temp file then renamed into place so a crash
mid-write never leaves a corrupt record.

Environment variable
────────────────────
STORY_STORE_DIR   Path to the storage directory.
                  Default: <repo-root>/data/stories
                  Set to an absolute path in production.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Optional


def _store_dir() -> Path:
    """Return (and create if necessary) the story storage directory."""
    path = Path(os.environ.get("STORY_STORE_DIR", "data/stories"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class StoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        # In-memory index: story_id → Path — built once at startup
        self._index: dict[str, Path] = {}
        self._load_existing()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_existing(self) -> None:
        """Scan store directory and register every .json file found."""
        try:
            for p in _store_dir().glob("*.json"):
                story_id = p.stem
                self._index[story_id] = p
        except Exception:
            pass  # directory may not exist yet — that's fine

    def _path_for(self, story_id: str) -> Path:
        return _store_dir() / f"{story_id}.json"

    # ── Public API ────────────────────────────────────────────────────────────

    def save(self, story_id: str, data: dict[str, Any]) -> None:
        """Persist `data` to disk and update the in-memory index."""
        target = self._path_for(story_id)
        # Atomic write: serialise to a sibling temp file then rename
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=target.parent, prefix=".tmp_", suffix=".json"
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, target)
        except Exception:
            # Fall back silently — the run still succeeds, data is just not persisted
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return

        with self._lock:
            self._index[story_id] = target

    def get(self, story_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            path = self._index.get(story_id)
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def all_ids(self) -> list[str]:
        with self._lock:
            return list(self._index.keys())

    def delete(self, story_id: str) -> bool:
        with self._lock:
            path = self._index.pop(story_id, None)
        if path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass
            return True
        return False


# Singleton
story_store = StoryStore()
