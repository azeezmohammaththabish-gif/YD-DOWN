from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .models import DownloadStatus


class DownloadCreate(BaseModel):
    url: str = Field(..., min_length=3)
    preferredQuality: Optional[str] = None  # e.g. "1080p", "720p", "audio"
    formatSelector: Optional[str] = None  # e.g. "137+140" or "bestaudio/best"
    output: Optional[str] = None  # "mp4" | "mp3"


class DownloadUpdate(BaseModel):
    title: Optional[str] = None


class DownloadRead(BaseModel):
    id: int
    video_id: str
    title: str
    url: str
    format_id: str
    quality_label: str
    status: DownloadStatus
    error_message: Optional[str]

    progress_percent: Optional[float]
    downloaded_bytes: Optional[int]
    total_bytes: Optional[int]

    created_at: datetime
    updated_at: datetime

    download_url: Optional[str] = None


class DownloadList(BaseModel):
    items: list[DownloadRead]
    total: int


class AnalyzeResult(BaseModel):
    video_id: str
    title: str
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None

    is_playlist: bool = False

    qualities: list[str]  # simplified options

    # y2mate-like grouped options
    video_options: list[dict]
    audio_options: list[dict]

    # For playlists: flat list of items
    items: list[dict] = []

    # legacy flat list (kept for backwards compatibility with older UI)
    options: list[dict]
