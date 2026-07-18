"""
In-memory story state store. Keyed by story_id UUID.
Replace with Redis or a DB in production.
"""
from __future__ import annotations

from threading import Lock
from typing import Any, Optional


class StoryStore:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = Lock()

    def save(self, story_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._store[story_id] = data

    def get(self, story_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._store.get(story_id)

    def all_ids(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())

    def delete(self, story_id: str) -> bool:
        with self._lock:
            if story_id in self._store:
                del self._store[story_id]
                return True
            return False


# Singleton
story_store = StoryStore()
