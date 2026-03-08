from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import timezone
from typing import Any

from app.database import acquire


logger = logging.getLogger(__name__)

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


async def log(level: str, message: str, vid: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    try:
        async with acquire() as conn:
            await conn.execute(
                "INSERT INTO logs (level, message, vid, created_at) "
                "VALUES ($1, $2, $3, $4)",
                level.upper(),
                message,
                vid,
                now,
            )
    except Exception:
        logger.exception("Failed to persist log entry")

    payload: dict[str, Any] = {
        "level": level.upper(),
        "message": message,
        "vid": vid,
        "created_at": now.isoformat(),
    }
    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.discard(q)

    getattr(logger, level.lower(), logger.info)(message)


async def info(message: str, vid: str | None = None) -> None:
    await log("INFO", message, vid)


async def warning(message: str, vid: str | None = None) -> None:
    await log("WARNING", message, vid)


async def error(message: str, vid: str | None = None) -> None:
    await log("ERROR", message, vid)
