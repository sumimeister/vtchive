from __future__ import annotations

from typing import Optional

from app.database import acquire


async def get(key: str, default: str = "") -> str:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE key = $1", key
        )
    return row["value"] if row else default


async def get_all() -> dict[str, str]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


async def set(key: str, value: str) -> None:  # noqa: A001
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            key, value,
        )


async def set_many(pairs: dict[str, str]) -> None:
    async with acquire() as conn:
        async with conn.transaction():
            for key, value in pairs.items():
                await conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    key, value,
                )


async def get_int(key: str, default: int = 0) -> int:
    raw = await get(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


async def get_list(key: str, default: Optional[list[str]] = None) -> list[str]:
    raw = await get(key, "")
    if not raw.strip():
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]
