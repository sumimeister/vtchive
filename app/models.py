from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import field_validator


class ChannelBase(BaseModel):
    channel_id: str
    channel_name: str
    english_name: Optional[str] = None
    org: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ChannelCreate(BaseModel):
    channel_id: str  # Holodex channel ID (UC…)


class ChannelOut(ChannelBase):
    added_at: datetime


class ArchiveOut(BaseModel):
    id: int
    vid: str
    title: str
    channel_name: str
    channel_id: str
    topic: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    duration: Optional[int] = None
    status: str
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArchiveListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ArchiveOut]


class ArchiveStats(BaseModel):
    wait: int = 0
    pending: int = 0
    downloading: int = 0
    done: int = 0
    failed: int = 0
    total: int = 0


class SettingItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    settings: dict[str, str]

    @field_validator("settings")
    @classmethod
    def keys_not_empty(cls, v: dict) -> dict:
        for k in v:
            if not k.strip():
                raise ValueError("Setting key must not be empty")
        return v


class MonitorStatus(BaseModel):
    running: bool
    last_checked: Optional[datetime]
    next_check: Optional[datetime]
    active_downloads: int
    queued: int


class LogEntry(BaseModel):
    id: int
    level: str
    message: str
    vid: Optional[str] = None
    created_at: datetime
