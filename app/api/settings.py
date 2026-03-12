from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

import aiohttp
from fastapi import APIRouter
from fastapi import HTTPException

from app.database import acquire
from app.models import SettingItem
from app.models import SettingsUpdate
from app.settings_store import get


router = APIRouter()


@router.get("", response_model=list[SettingItem])
async def get_settings() -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, description, updated_at FROM settings ORDER BY key"
        )
    return [dict(r) for r in rows]


@router.put("", response_model=list[SettingItem])
async def update_settings(body: SettingsUpdate) -> list[dict[str, Any]]:
    async with acquire() as conn:
        async with conn.transaction():
            for key, value in body.settings.items():
                await conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    key,
                    value,
                )
        rows = await conn.fetch(
            "SELECT key, value, description, updated_at FROM settings ORDER BY key"
        )
    return [dict(r) for r in rows]


@router.post("/test-webhook")
async def test_webhook() -> dict[str, str]:
    webhook_url = await get("discord_webhook_url")
    guild_id = await get("discord_guild_id")
    channel_id = await get("discord_channel_id")

    if not webhook_url:
        raise HTTPException(status_code=400, detail="尚未設定 Discord Webhook 網址")

    embed: dict[str, Any] = {
        "author": {"name": "VTchive"},
        "title": "Webhook 測試",
        "description": "此為 VTchive 發送的測試訊息",
        "color": 0x2ECC71,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload: dict[str, Any] = {"embeds": [embed]}

    if guild_id and channel_id:
        payload = {
            "target": "guild",
            "target_id": guild_id,
            "sub_target_id": channel_id,
            "embed": embed,
            "time": datetime.now(timezone.utc).isoformat(),
        }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:  # noqa: SIM117
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    body = await resp.text()
                    raise HTTPException(
                        status_code=502,
                        detail=f"Webhook 回應錯誤 HTTP {resp.status}: {body[:200]}",
                    )
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"Webhook 連線失敗: {exc}") from exc
    return {"detail": "ok"}
