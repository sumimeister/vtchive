from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Optional

import app.broadcaster as log
from app.database import acquire
from app.services import holodex
from app.settings_store import get_int


logger = logging.getLogger(__name__)

_active: set[str] = set()
_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_limit: int = 0
_semaphore_lock = asyncio.Lock()


async def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore, _semaphore_limit
    async with _semaphore_lock:
        limit = await get_int("max_concurrent_downloads", 3)
        if _semaphore is None or limit != _semaphore_limit:
            _semaphore = asyncio.Semaphore(limit)
            _semaphore_limit = limit
    return _semaphore


def active_vids() -> set[str]:
    return set(_active)


def _sanitize(text: str) -> str:
    """Remove characters illegal in file system paths."""
    return re.sub(r"^[ .]|[/<>:\"\\|?*\x00-\x1f]+|[ .]$", "_", text)


def _display_width(text: str) -> int:
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in "FWA" else 1
    return width


def _truncate(text: str, max_width: int = 60) -> str:
    if _display_width(text) <= max_width:
        return text
    out = ""
    for ch in text:
        if _display_width(out) >= max_width - 3:
            break
        out += ch
    return out.rstrip() + "…"


async def download(vid: str) -> None:
    if vid in _active:
        return

    sem = await _get_semaphore()
    async with sem:
        _active.add(vid)
        await _set_status(vid, "DOWNLOADING")
        await log.info(f"開始下載 {vid}", vid=vid)

        try:
            returncode = await _run_ytdlp(vid)
        except Exception as exc:
            await log.error(f"下載 {vid} 發生例外：{exc}", vid=vid)
            await _set_status(vid, "FAILED", error_message=str(exc))
            _active.discard(vid)
            return

        if returncode == 0:
            await _on_success(vid)
        else:
            await log.error(f"下載 {vid} 失敗，yt-dlp 返回碼 {returncode}", vid=vid)
            await _set_status(vid, "FAILED", error_message=f"yt-dlp exit {returncode}")

        _active.discard(vid)


YTDLP_PATH = "/app/yt-dlp"
OUTPUT_ROOT = "/downloads"


async def _run_ytdlp(vid: str) -> int:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT title, channel_name, channel_id FROM archives WHERE vid = $1", vid
        )
    if not row:
        raise RuntimeError(f"Archive record for {vid} not found in DB")

    channel_dir = _sanitize(row["channel_name"])
    filename = _sanitize(f"【{row['channel_name']}】{_truncate(row['title'])} ({vid})")
    # yt-dlp appends the extension; store path without ext
    output_path_noext = os.path.join(OUTPUT_ROOT, channel_dir, filename)
    output_template = output_path_noext + ".%(ext)s"

    url = f"https://www.youtube.com/watch?v={vid}"
    cmd = [
        YTDLP_PATH,
        "--js-runtimes", "node",
        "--live-from-start",
        "--ignore-config",
        "--merge-output-format", "mkv",
        "--prefer-free-formats",
        "--embed-thumbnail",
        "--embed-metadata",
        "--no-part",
        "-f", "bestvideo*+bestaudio/best",
        "-o", output_template,
    ]
    cmd.append(url)

    await log.info(f"執行指令: {' '.join(cmd)}", vid=vid)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0 and stderr:
        err_text = stderr.decode(errors="replace").strip()
        await log.warning(f"yt-dlp stderr [{vid}]: {err_text[:500]}", vid=vid)

    async with acquire() as conn:
        await conn.execute(
            "UPDATE archives SET output_path = $1 WHERE vid = $2",
            output_path_noext, vid,
        )

    return proc.returncode


async def _on_success(vid: str) -> None:
    video = await holodex.get_video(vid)
    end_at: Optional[datetime] = None
    duration: Optional[int] = None

    if video:
        raw_end = video.get("end_actual") or video.get("end_scheduled")
        if raw_end:
            try:
                end_at = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
            except ValueError:
                pass
        duration = video.get("duration")

    async with acquire() as conn:
        await conn.execute(
            "UPDATE archives SET status = 'DONE', end_at = $1, duration = $2, "
            "error_message = NULL, updated_at = NOW() WHERE vid = $3",
            end_at, duration, vid,
        )
    await log.info(f"下載完成 {vid}", vid=vid)


async def _set_status(
    vid: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE archives SET status = $1, error_message = $2, updated_at = NOW() "
            "WHERE vid = $3",
            status, error_message, vid,
        )


async def retry(vid: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE archives SET status = 'WAIT', error_message = NULL, "
            "updated_at = NOW() WHERE vid = $1 AND status = 'FAILED'",
            vid,
        )
    await log.info(f"重試下載排程 {vid}", vid=vid)
