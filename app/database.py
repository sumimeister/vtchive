from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg

from app.config import get_settings


logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key         VARCHAR PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channels (
    channel_id    VARCHAR PRIMARY KEY,
    channel_name  VARCHAR NOT NULL,
    english_name  VARCHAR,
    org           VARCHAR,
    thumbnail_url VARCHAR,
    added_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS archives (
    id            SERIAL PRIMARY KEY,
    vid           VARCHAR UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    channel_name  VARCHAR NOT NULL,
    channel_id    VARCHAR NOT NULL,
    topic         VARCHAR,
    start_at      TIMESTAMPTZ,
    end_at        TIMESTAMPTZ,
    duration      INTEGER,
    status        VARCHAR NOT NULL DEFAULT 'WAIT',
    output_path   TEXT,
    error_message TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id         BIGSERIAL PRIMARY KEY,
    level      VARCHAR NOT NULL,
    message    TEXT NOT NULL,
    vid        VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for common query patterns
CREATE INDEX IF NOT EXISTS idx_archives_status   ON archives (status);
CREATE INDEX IF NOT EXISTS idx_archives_channel  ON archives (channel_id);
CREATE INDEX IF NOT EXISTS idx_archives_start_at ON archives (start_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_created_at   ON logs (created_at DESC);

-- Seed default settings (ignore conflicts so user data is preserved)
INSERT INTO settings (key, value, description) VALUES
    ('holodex_token',            '',                   'Holodex API token'),
    ('allowed_topics',           'music_cover,singing','Comma-separated allowed topic IDs (leave blank to allow all)'),
    ('monitor_interval',         '300',                'Monitoring poll interval in seconds'),
    ('max_concurrent_downloads', '3',                  'Maximum simultaneous ytarchive processes'),
    ('schedule_window_before',   '1',                  'Ignore streams scheduled more than N days ahead'),
    ('schedule_window_after',    '12',                 'Ignore streams that started more than N hours ago'),
    ('timezone',                 'Asia/Taipei',        'Display timezone'),
    ('discord_webhook_url',      '',                   'Discord bot webhook URL'),
    ('discord_guild_id',         '',                   'Discord guild ID'),
    ('discord_channel_id',       '',                   'Discord channel ID')
ON CONFLICT DO NOTHING;
"""


async def init_db() -> None:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=2,
        max_size=16,
        command_timeout=60,
    )
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Database initialised")


async def close_db() -> None:
    if _pool:
        await _pool.close()
        logger.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[asyncpg.Connection, None]:
    async with get_pool().acquire() as conn:
        yield conn
