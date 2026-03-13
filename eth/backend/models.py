from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class DownloadStatus(str, Enum):
    pending = "pending"
    downloading = "downloading"
    paused = "paused"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"


class DownloadHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    video_id: str = Field(index=True)
    title: str = Field(default="")
    url: str

    format_id: str = Field(default="")
    quality_label: str = Field(default="")

    status: DownloadStatus = Field(default=DownloadStatus.pending, index=True)
    error_message: Optional[str] = Field(default=None)

    # Stored server-side only. Never expose directly to clients.
    file_path: Optional[str] = Field(default=None)
    filename: Optional[str] = Field(default=None)

    progress_percent: Optional[float] = Field(default=None)
    downloaded_bytes: Optional[int] = Field(default=None)
    total_bytes: Optional[int] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
