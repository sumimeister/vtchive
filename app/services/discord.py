from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone
from typing import Any

import aiohttp

from app.settings_store import get


logger = logging.getLogger(__name__)

_STATUS_COLORS: dict[str, int] = {
    "WAIT": 0x95A5A6,  # Grey
    "PENDING": 0xF1C40F,  # Yellow
    "DOWNLOADING": 0x3498DB,  # Blue
    "DONE": 0x2ECC71,  # Green
    "FAILED": 0xE74C3C,  # Red
}

_STATUS_LABELS: dict[str, str] = {
    "WAIT": "排定",
    "PENDING": "等待中",
    "DOWNLOADING": "下載中",
    "DONE": "完成",
    "FAILED": "失敗",
}


async def notify_status(
    vid: str,
    title: str,
    channel_name: str,
    channel_id: str,
    start_at: datetime,
    status: str,
    error_message: str | None = None,
) -> None:
    webhook_url = await get("discord_webhook_url")
    dc_guild_id = await get("discord_guild_id")
    dc_channel_id = await get("discord_channel_id")

    if not (webhook_url and dc_guild_id and dc_channel_id):
        return

    color = _STATUS_COLORS.get(status, 0x95A5A6)
    label = _STATUS_LABELS.get(status, status)
    yt_url = f"https://www.youtube.com/watch?v={vid}"

    description_lines = []
    if error_message:
        description_lines.append(f"**錯誤：** {error_message[:200]}")

    embed: dict[str, Any] = {
        "author": {
            "name": channel_name,
            "url": f"https://www.youtube.com/channel/{channel_id}",
        },
        "title": title,
        "url": yt_url,
        "description": "\n".join(description_lines),
        "color": color,
        "fields": [
            {
                "name": "直播開始時間",
                "value": f"<t:{int(start_at.timestamp())}:F>",
                "inline": True,
            },
            {
                "name": "VTchive 狀態",
                "value": label,
                "inline": True,
            },
        ],
        "image": {
            "url": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload: dict[str, Any] = {
        "target": "guild",
        "target_id": dc_guild_id,
        "sub_target_id": dc_channel_id,
        "embed": embed,
        "time": datetime.now(timezone.utc).isoformat(),
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:  # noqa: SIM117
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    body = await resp.text()
                    logger.warning(
                        "Discord webhook returned HTTP %s: %s",
                        resp.status,
                        body[:200],
                    )
    except Exception as exc:
        logger.warning("Discord webhook error: %r", exc)
