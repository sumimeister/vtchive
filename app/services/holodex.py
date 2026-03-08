from __future__ import annotations

import asyncio
import logging
from typing import Any
from typing import Optional

import aiohttp

from app.settings_store import get as setting_get


logger = logging.getLogger(__name__)

BASE_URL = "https://holodex.net/api/v2"
_session: Optional[aiohttp.ClientSession] = None
_session_lock = asyncio.Lock()


async def _get_session() -> aiohttp.ClientSession:
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": "vtchive/2.0"},
            )
    return _session


async def close() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def _auth_headers() -> dict[str, str]:
    token = await setting_get("holodex_token")
    return {"X-APIKEY": token} if token else {}



async def get_live_streams(channel_ids: list[str]) -> list[dict[str, Any]]:
    if not channel_ids:
        return []
    session = await _get_session()
    headers = await _auth_headers()
    params = {"channels": ",".join(channel_ids)}
    try:
        async with session.get(
            f"{BASE_URL}/users/live", headers=headers, params=params
        ) as resp:
            if resp.status != 200:
                logger.warning("Holodex /users/live returned HTTP %s", resp.status)
                return []
            return await resp.json()
    except aiohttp.ClientError as exc:
        logger.error("Holodex live request failed: %s", exc)
        return []


async def get_video(vid: str) -> Optional[dict[str, Any]]:
    session = await _get_session()
    headers = await _auth_headers()
    try:
        async with session.get(
            f"{BASE_URL}/videos/{vid}", headers=headers
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except aiohttp.ClientError as exc:
        logger.error("Holodex get_video(%s) failed: %s", vid, exc)
        return None


async def get_channel(channel_id: str) -> Optional[dict[str, Any]]:
    session = await _get_session()
    headers = await _auth_headers()
    try:
        async with session.get(
            f"{BASE_URL}/channels/{channel_id}", headers=headers
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except aiohttp.ClientError as exc:
        logger.error("Holodex get_channel(%s) failed: %s", channel_id, exc)
        return None
