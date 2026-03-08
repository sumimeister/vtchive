from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.database import acquire
from app.models import SettingItem
from app.models import SettingsUpdate


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
