"""
core/progress.py — Per-run progress event bus for SSE streaming.

Each pipeline run registers a queue keyed by story_id.  LangGraph nodes
call `emit()` to push a progress event; the SSE endpoint calls `stream()`
which drains the queue as a generator.

Design decisions
────────────────
- Pure stdlib (queue.Queue + threading) — zero extra dependencies.
- Queue is bounded (maxsize=50) so a slow SSE consumer cannot cause
  unbounded memory growth.
- `emit()` is non-blocking (put_nowait); if the queue is full the event
  is silently dropped rather than blocking the pipeline.
- Queues are cleaned up automatically 60 s after `close()` is called so
  a client that never connects does not leak memory indefinitely.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Generator, Optional

# story_id → Queue[str | None]   (None is the sentinel that closes the stream)
_queues: dict[str, queue.Queue] = {}
_lock = threading.Lock()

_QUEUE_MAXSIZE = 50
_CLEANUP_DELAY = 60   # seconds after close() before the queue is deleted


def register(story_id: str) -> None:
    """Create a fresh queue for a new pipeline run."""
    with _lock:
        _queues[story_id] = queue.Queue(maxsize=_QUEUE_MAXSIZE)


def emit(story_id: str, event: str, data: dict[str, Any]) -> None:
    """Push an SSE event into the queue for `story_id`.

    Silently no-ops if no queue is registered (client never connected)
    or if the queue is full.
    """
    with _lock:
        q = _queues.get(story_id)
    if q is None:
        return
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    try:
        q.put_nowait(payload)
    except queue.Full:
        pass  # slow consumer — drop rather than block pipeline


def close(story_id: str) -> None:
    """Signal end-of-stream by pushing the None sentinel."""
    with _lock:
        q = _queues.get(story_id)
    if q:
        try:
            q.put_nowait(None)
        except queue.Full:
            pass
    # Schedule cleanup after a grace period
    def _cleanup():
        time.sleep(_CLEANUP_DELAY)
        with _lock:
            _queues.pop(story_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()


def stream(story_id: str, timeout: float = 120.0) -> Generator[str, None, None]:
    """Yield SSE-formatted strings until the stream is closed or timeout.

    Sends a keepalive comment every 15 s so the browser connection stays open.
    """
    with _lock:
        q = _queues.get(story_id)
    if q is None:
        yield "event: error\ndata: {\"message\": \"No pipeline registered for this story_id\"}\n\n"
        return

    deadline = time.time() + timeout
    keepalive_interval = 15.0
    next_keepalive = time.time() + keepalive_interval

    while time.time() < deadline:
        try:
            item = q.get(timeout=min(1.0, next_keepalive - time.time()))
        except queue.Empty:
            if time.time() >= next_keepalive:
                yield ": keepalive\n\n"
                next_keepalive = time.time() + keepalive_interval
            continue

        if item is None:
            yield "event: done\ndata: {}\n\n"
            return
        yield item

    yield "event: timeout\ndata: {\"message\": \"SSE stream timed out\"}\n\n"
