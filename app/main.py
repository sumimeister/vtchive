from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import archives
from app.api import channels
from app.api import monitor
from app.api import settings
from app.api import websocket
from app.database import close_db
from app.database import init_db
from app.services import holodex
from app.services.monitor import MonitorService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    svc = MonitorService()
    app.state.monitor = svc
    task = asyncio.create_task(svc.run(), name="monitor")
    app.state.monitor_task = task
    yield

    svc.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await holodex.close()
    await close_db()


app = FastAPI(
    title="VTChive",
    description="YouTube Live-stream Archiver with Holodex monitoring",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
app.include_router(archives.router, prefix="/api/archives", tags=["Archives"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["Monitor"])
app.include_router(websocket.router, prefix="/api", tags=["WebSocket"])
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_spa() -> FileResponse:
    return FileResponse("app/static/index.html")
