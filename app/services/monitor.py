from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from typing import Optional

import app.broadcaster as log
from app.database import acquire
from app.services import downloader
from app.services import holodex
from app.settings_store import get_int
from app.settings_store import get_list


logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(self) -> None:
        self.running: bool = False
        self.last_checked: Optional[datetime] = None
        self.next_check: Optional[datetime] = None
        self._stop_event = asyncio.Event()
        self._trigger_event = asyncio.Event()


    def stop(self) -> None:
        self._stop_event.set()

    async def trigger_now(self) -> None:
        self._trigger_event.set()


    async def run(self) -> None:
        self.running = True
        await log.info("監控服務已啟動")
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                await log.error(f"監控輪詢發生例外：{exc}")

            interval = await get_int("monitor_interval", 300)
            self.next_check = datetime.now(timezone.utc) + timedelta(seconds=interval)
            self._trigger_event.clear()
            stop_task = asyncio.ensure_future(self._stop_event.wait())
            trig_task  = asyncio.ensure_future(self._trigger_event.wait())
            try:
                await asyncio.wait(
                    {stop_task, trig_task},
                    timeout=interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                break
            finally:
                stop_task.cancel()
                trig_task.cancel()

            if self._stop_event.is_set():
                break

        self.running = False
        await log.info("監控服務已停止")


    async def _poll(self) -> None:
        self.last_checked = datetime.now(timezone.utc)
        self.next_check = None

        channel_ids = await self._load_channel_ids()
        if not channel_ids:
            await log.warning("尚未設定任何監控頻道")
            return

        allowed_topics = await get_list("allowed_topics")
        window_before = await get_int("schedule_window_before", 1)
        window_after = await get_int("schedule_window_after", 12)

        streams = await holodex.get_live_streams(channel_ids)
        await log.info(f"發現 {len(streams)} 個直播項目")

        channel_id_set = set(channel_ids)
        now = datetime.now(timezone.utc)

        for stream in streams:
            await self._process_stream(
                stream=stream,
                channel_id_set=channel_id_set,
                allowed_topics=allowed_topics,
                now=now,
                window_before_days=window_before,
                window_after_hours=window_after,
            )

        await self._resume_waiting()

    async def _process_stream(
        self,
        stream: dict[str, Any],
        channel_id_set: set[str],
        allowed_topics: list[str],
        now: datetime,
        window_before_days: int,
        window_after_hours: int,
    ) -> None:
        vid = stream.get("id", "")
        channel = stream.get("channel", {})
        channel_id = channel.get("id", "")

        if channel_id not in channel_id_set:
            return

        if stream.get("type") != "stream":
            return

        topic = (stream.get("topic_id") or "").lower()
        if allowed_topics and topic not in allowed_topics:
            return

        raw_scheduled = stream.get("start_scheduled") or stream.get("available_at")
        if not raw_scheduled:
            return
        try:
            start_at = datetime.fromisoformat(raw_scheduled.replace("Z", "+00:00"))
        except ValueError:
            return

        if now < start_at - timedelta(days=window_before_days):
            return
        if now > start_at + timedelta(hours=window_after_hours):
            return

        already = await self._is_tracked(vid)
        if already:
            return

        created = await self._create_archive(stream, channel, start_at, topic)
        if created:
            await log.info(
                f"新增下載排程 【{channel.get('name', '?')}】"
                f"{stream.get('title', '')[:40]} ({vid})",
                vid=vid,
            )
            asyncio.create_task(downloader.download(vid))

    async def _resume_waiting(self) -> None:
        active = downloader.active_vids()
        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT vid FROM archives WHERE status = 'WAIT' AND vid != ALL($1::text[])",
                list(active),
            )
        for row in rows:
            vid = row["vid"]
            if vid not in active:
                await log.info(f"重啟等待中的下載任務 {vid}", vid=vid)
                asyncio.create_task(downloader.download(vid))


    async def _load_channel_ids(self) -> list[str]:
        async with acquire() as conn:
            rows = await conn.fetch("SELECT channel_id FROM channels")
        return [r["channel_id"] for r in rows]

    async def _is_tracked(self, vid: str) -> bool:
        if vid in downloader.active_vids():
            return True
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM archives WHERE vid = $1", vid
            )
        return row is not None

    async def _create_archive(
        self,
        stream: dict[str, Any],
        channel: dict[str, Any],
        start_at: datetime,
        topic: str,
    ) -> bool:
        vid = stream["id"]
        title = stream.get("title") or vid
        channel_name = channel.get("name") or channel.get("id", "unknown")
        channel_id = channel.get("id", "")

        async with acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO archives
                    (vid, title, channel_name, channel_id, topic, start_at, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'WAIT')
                ON CONFLICT (vid) DO NOTHING
                RETURNING id
                """,
                vid, title, channel_name, channel_id, topic or None, start_at,
            )
        return row is not None
