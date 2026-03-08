from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from app.models import MonitorStatus
from app.services import downloader


router = APIRouter()


@router.get("/status", response_model=MonitorStatus)
async def monitor_status(request: Request) -> MonitorStatus:
    monitor = request.app.state.monitor
    active = downloader.active_vids()
    return MonitorStatus(
        running=monitor.running,
        last_checked=monitor.last_checked,
        next_check=monitor.next_check,
        active_downloads=len(active),
        queued=0,  # WAIT count comes from /api/archives/stats
    )


@router.post("/trigger", status_code=202)
async def trigger_monitor(request: Request) -> dict[str, str]:
    monitor = request.app.state.monitor
    await monitor.trigger_now()
    return {"detail": "Monitor poll triggered"}
