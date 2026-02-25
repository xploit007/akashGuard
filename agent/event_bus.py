"""
Lightweight in-process event bus for SSE broadcasting.

The monitoring loop calls ``emit()`` at each stage. Connected SSE clients
subscribe via ``subscribe()`` and receive events through an asyncio.Queue.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

_subscribers: list[asyncio.Queue[dict]] = []
_recent_events: list[dict] = []
MAX_RECENT = 200


def subscribe() -> asyncio.Queue[dict]:
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue[dict]) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def emit(event_type: str, data: dict[str, Any]) -> None:
    event = {
        "type": event_type,
        "data": data,
        "timestamp": time.time(),
    }
    _recent_events.append(event)
    while len(_recent_events) > MAX_RECENT:
        _recent_events.pop(0)

    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop for slow clients


def get_recent_events(limit: int = 20) -> list[dict]:
    return list(_recent_events[-limit:])
