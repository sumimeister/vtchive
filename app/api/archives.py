from __future__ import annotations

from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Response

from app.database import acquire
from app.models import ArchiveListResponse
from app.models import ArchiveStats
from app.services import downloader


router = APIRouter()


def _row_to_archive(r: Any) -> dict[str, Any]:
    return dict(r)


@router.get("", response_model=ArchiveListResponse)
async def list_archives(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    channel_id: Optional[str] = None,
    q: Optional[str] = None,
) -> ArchiveListResponse:
    conditions = []
    params: list = []
    idx = 1

    if status:
        statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            conditions.append(f"status = ${idx}")
            params.append(statuses[0])
            idx += 1
        else:
            placeholders = ", ".join(f"${idx + i}" for i in range(len(statuses)))
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)
            idx += len(statuses)
    if channel_id:
        conditions.append(f"channel_id = ${idx}")
        params.append(channel_id)
        idx += 1
    if q:
        conditions.append(f"(title ILIKE ${idx} OR channel_name ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    async with acquire() as conn:
        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM archives {where}", *params
        )
        total = total_row["cnt"]
        rows = await conn.fetch(
            f"""
            SELECT id, vid, title, channel_name, channel_id, topic,
                start_at, end_at, duration, status, output_path,
                error_message, created_at, updated_at
            FROM archives {where}
            ORDER BY start_at DESC NULLS LAST, created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
            page_size,
            offset,
        )

    return ArchiveListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_row_to_archive(r) for r in rows],
    )


@router.get("/stats", response_model=ArchiveStats)
async def get_stats() -> ArchiveStats:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS cnt FROM archives GROUP BY status"
        )
    counts = {r["status"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    return ArchiveStats(
        wait=counts.get("WAIT", 0),
        pending=counts.get("PENDING", 0),
        downloading=counts.get("DOWNLOADING", 0),
        done=counts.get("DONE", 0),
        failed=counts.get("FAILED", 0),
        total=total,
    )


@router.post("/{vid}/retry", status_code=202)
async def retry_archive(vid: str) -> dict[str, str]:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM archives WHERE vid = $1", vid)
    if not row:
        raise HTTPException(status_code=404, detail="Archive record not found")
    if row["status"] != "FAILED":
        raise HTTPException(
            status_code=409, detail=f"Cannot retry archive in '{row['status']}' status"
        )
    await downloader.retry(vid)
    return {"detail": "Retry scheduled"}


@router.post("/{vid}/mark-done", status_code=200)
async def mark_done(vid: str) -> dict[str, str]:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM archives WHERE vid = $1", vid)
        if not row:
            raise HTTPException(status_code=404, detail="Archive record not found")
        if row["status"] != "FAILED":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot mark done archive in '{row['status']}' status",
            )
        await conn.execute("UPDATE archives SET status = 'DONE' WHERE vid = $1", vid)
    return {"detail": "Marked as done"}


@router.delete("/{vid}", status_code=204)
async def delete_archive(vid: str) -> Response:
    async with acquire() as conn:
        result = await conn.execute("DELETE FROM archives WHERE vid = $1", vid)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Archive record not found")
    return Response(status_code=204)
