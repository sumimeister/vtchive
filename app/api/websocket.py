from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi.responses import StreamingResponse

import app.broadcaster as broadcaster
from app.database import acquire


router = APIRouter()


@router.get("/logs/stream")
async def sse_logs(request: Request) -> StreamingResponse:

    async def event_generator() -> AsyncGenerator[str, None]:
        q = broadcaster.subscribe()
        try:
            # flush any queued messages immediately
            while True:
                try:
                    payload = q.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.QueueEmpty:
                    break
            # then stream new ones
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # SSE comment — keeps connection alive
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    vid: Optional[str] = None,
) -> list[dict]:
    if vid:
        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, level, message, vid, created_at FROM logs "
                "WHERE vid = $1 ORDER BY created_at DESC LIMIT $2",
                vid,
                limit,
            )
    else:
        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, level, message, vid, created_at FROM logs "
                "ORDER BY created_at DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in reversed(rows)]
