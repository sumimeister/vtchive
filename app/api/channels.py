from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Response

from app.database import acquire
from app.models import ChannelCreate
from app.models import ChannelOut
from app.services import holodex


router = APIRouter()


@router.get("", response_model=list[ChannelOut])
async def list_channels() -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT channel_id, channel_name, english_name, org, thumbnail_url, added_at "
            "FROM channels ORDER BY channel_name"
        )
    return [dict(r) for r in rows]


@router.post("", response_model=ChannelOut, status_code=201)
async def add_channel(body: ChannelCreate) -> dict[str, Any]:
    # Check duplicate
    async with acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT channel_id FROM channels WHERE channel_id = $1",
            body.channel_id,
        )
    if existing:
        raise HTTPException(status_code=409, detail="Channel already tracked")

    # Fetch from Holodex
    data = await holodex.get_channel(body.channel_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{body.channel_id}' not found on Holodex",
        )

    channel_name = data.get("name") or body.channel_id
    english_name = data.get("english_name")
    org = data.get("org")
    thumbnail_url = data.get("photo") or data.get("thumbnail") or data.get("banner")

    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO channels (channel_id, channel_name, english_name, org, thumbnail_url)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING channel_id, channel_name, english_name, org, thumbnail_url, added_at
            """,
            body.channel_id,
            channel_name,
            english_name,
            org,
            thumbnail_url,
        )
    return dict(row)


@router.delete("/{channel_id}", status_code=204)
async def remove_channel(channel_id: str) -> Response:
    async with acquire() as conn:
        result = await conn.execute(
            "DELETE FROM channels WHERE channel_id = $1", channel_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Channel not found")
    return Response(status_code=204)
