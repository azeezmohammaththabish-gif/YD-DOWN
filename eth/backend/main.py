from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlmodel import Session, select

from .database import get_session, init_db
from .models import DownloadHistory, DownloadStatus
from .schemas import AnalyzeResult, DownloadCreate, DownloadList, DownloadRead, DownloadUpdate
from .services.downloader import analyze_url, download_to_file, extract_video_id, pick_format


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", str(PROJECT_DIR / "downloads"))).resolve()
STATIC_DIR = (PROJECT_DIR / "static").resolve()


app = FastAPI(title="YouTube Downloader", version="1.0.0")

# In-memory control flags for active downloads (local/dev use).
_stop_flags: dict[int, str] = {}  # id -> "cancel" | "pause"


def to_read_model(row: DownloadHistory) -> DownloadRead:
    download_url = None
    if row.status == DownloadStatus.completed and row.file_path:
        download_url = f"/api/downloads/{row.id}/file"
    return DownloadRead(
        id=row.id or 0,
        video_id=row.video_id,
        title=row.title,
        url=row.url,
        format_id=row.format_id,
        quality_label=row.quality_label,
        status=row.status,
        error_message=row.error_message,
        progress_percent=row.progress_percent,
        downloaded_bytes=row.downloaded_bytes,
        total_bytes=row.total_bytes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        download_url=download_url,
    )


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResult)
def api_analyze(payload: DownloadCreate) -> AnalyzeResult:
    info = analyze_url(payload.url)
    video_id = info["video_id"]
    if not video_id:
        raise HTTPException(status_code=400, detail="Could not extract video info.")
    return AnalyzeResult(
        video_id=video_id,
        title=info["title"],
        duration_seconds=info.get("duration_seconds"),
        thumbnail_url=info.get("thumbnail_url"),
        is_playlist=info.get("is_playlist", False),
        qualities=info["qualities"],
        video_options=info.get("video_options") or [],
        audio_options=info.get("audio_options") or [],
        items=info.get("items") or [],
        options=info["options"],
    )


@app.post("/api/downloads", response_model=DownloadRead)
async def create_download(payload: DownloadCreate) -> DownloadRead:
    # Analyze once so we have a stable video_id and the real title.
    info = analyze_url(payload.url)
    video_id = extract_video_id(payload.url) or info["video_id"] or ""
    title = info["title"] or ""
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL.")

    if payload.formatSelector:
        format_selector = payload.formatSelector
        quality_label = payload.preferredQuality or "custom"
    else:
        format_selector, quality_label = pick_format(payload.preferredQuality)

    output = (payload.output or "").lower().strip() or "mp4"
    if output not in ("mp4", "mp3"):
        output = "mp4"

    with get_session() as session:
        session: Session

        # Cache: if already downloaded same video+quality and file exists, reuse.
        existing = session.exec(
            select(DownloadHistory)
            .where(DownloadHistory.video_id == video_id)
            .where(DownloadHistory.quality_label == quality_label)
            .where(DownloadHistory.status == DownloadStatus.completed)
            .order_by(DownloadHistory.created_at.desc())
        ).first()
        if existing and existing.file_path and Path(existing.file_path).exists():
            cloned = DownloadHistory(
                video_id=existing.video_id,
                title=existing.title or title,
                url=payload.url,
                format_id=existing.format_id,
                quality_label=existing.quality_label,
                status=DownloadStatus.completed,
                file_path=existing.file_path,
                filename=existing.filename,
                progress_percent=100.0,
                downloaded_bytes=existing.downloaded_bytes,
                total_bytes=existing.total_bytes,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(cloned)
            session.commit()
            session.refresh(cloned)
            return to_read_model(cloned)

        row = DownloadHistory(
            video_id=video_id,
            title=title,
            url=payload.url,
            format_id=format_selector,
            quality_label=quality_label,
            status=DownloadStatus.pending,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        download_id = row.id

    async def run_download(download_id: int) -> None:
        def _should_stop() -> bool:
            return download_id in _stop_flags

        def _update_progress(d: dict) -> None:
            status = d.get("status")
            downloaded = d.get("downloaded_bytes")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")

            pct: Optional[float] = None
            if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
                pct = float(downloaded) / float(total) * 100.0

            with get_session() as s2:
                s2: Session
                r2 = s2.get(DownloadHistory, download_id)
                if not r2:
                    return
                if status == "downloading":
                    r2.status = DownloadStatus.downloading
                r2.downloaded_bytes = int(downloaded) if isinstance(downloaded, (int, float)) else r2.downloaded_bytes
                r2.total_bytes = int(total) if isinstance(total, (int, float)) else r2.total_bytes
                r2.progress_percent = pct if pct is not None else r2.progress_percent
                r2.updated_at = datetime.utcnow()
                s2.add(r2)
                s2.commit()

        with get_session() as s3:
            s3: Session
            r3 = s3.get(DownloadHistory, download_id)
            if not r3:
                return
            r3.status = DownloadStatus.downloading
            r3.updated_at = datetime.utcnow()
            s3.add(r3)
            s3.commit()

        try:
            file_path, filename = await asyncio.to_thread(
                download_to_file,
                url=payload.url,
                format_selector=format_selector,
                download_dir=DOWNLOAD_DIR,
                filename_prefix=f"{video_id}_{download_id}",
                output=output,
                on_progress=_update_progress,
                should_stop=_should_stop,
            )
            with get_session() as s4:
                s4: Session
                r4 = s4.get(DownloadHistory, download_id)
                if not r4:
                    return
                r4.status = DownloadStatus.completed
                r4.file_path = str(file_path)
                r4.filename = filename
                r4.progress_percent = 100.0
                r4.updated_at = datetime.utcnow()
                s4.add(r4)
                s4.commit()
        except Exception as e:
            with get_session() as s5:
                s5: Session
                r5 = s5.get(DownloadHistory, download_id)
                if not r5:
                    return
                stop_reason = _stop_flags.pop(download_id, None)
                if str(e) == "STOP_REQUESTED" and stop_reason == "pause":
                    r5.status = DownloadStatus.paused
                    r5.error_message = None
                elif str(e) == "STOP_REQUESTED" and stop_reason == "cancel":
                    r5.status = DownloadStatus.cancelled
                    r5.error_message = None
                else:
                    r5.status = DownloadStatus.failed
                    r5.error_message = str(e)
                r5.updated_at = datetime.utcnow()
                s5.add(r5)
                s5.commit()

    if download_id is not None:
        asyncio.create_task(run_download(int(download_id)))

    with get_session() as session:
        session: Session
        fresh = session.get(DownloadHistory, download_id)
        if not fresh:
            raise HTTPException(status_code=404, detail="Download not found.")
        return to_read_model(fresh)


@app.post("/api/downloads/{download_id}/cancel")
def cancel_download(download_id: int) -> dict[str, bool]:
    _stop_flags[download_id] = "cancel"
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if row and row.status in (DownloadStatus.pending, DownloadStatus.downloading):
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.commit()
    return {"ok": True}


@app.post("/api/downloads/{download_id}/pause")
def pause_download(download_id: int) -> dict[str, bool]:
    _stop_flags[download_id] = "pause"
    return {"ok": True}


@app.post("/api/downloads/{download_id}/resume", response_model=DownloadRead)
async def resume_download(download_id: int) -> DownloadRead:
    # Resume means: start the same download again (yt-dlp will continue partial file if present).
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status not in (DownloadStatus.paused, DownloadStatus.failed, DownloadStatus.cancelled):
            raise HTTPException(status_code=409, detail="Not resumable")

        row.status = DownloadStatus.pending
        row.error_message = None
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)

        url = row.url
        format_selector = row.format_id
        quality_label = row.quality_label

    async def run_again() -> None:
        def _should_stop() -> bool:
            return download_id in _stop_flags

        def _update_progress(d: dict) -> None:
            status = d.get("status")
            downloaded = d.get("downloaded_bytes")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")

            pct: Optional[float] = None
            if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
                pct = float(downloaded) / float(total) * 100.0

            with get_session() as s2:
                s2: Session
                r2 = s2.get(DownloadHistory, download_id)
                if not r2:
                    return
                if status == "downloading":
                    r2.status = DownloadStatus.downloading
                r2.downloaded_bytes = int(downloaded) if isinstance(downloaded, (int, float)) else r2.downloaded_bytes
                r2.total_bytes = int(total) if isinstance(total, (int, float)) else r2.total_bytes
                r2.progress_percent = pct if pct is not None else r2.progress_percent
                r2.updated_at = datetime.utcnow()
                s2.add(r2)
                s2.commit()

        try:
            file_path, filename = await asyncio.to_thread(
                download_to_file,
                url=url,
                format_selector=format_selector,
                download_dir=DOWNLOAD_DIR,
                filename_prefix=f"{row.video_id}_{download_id}",
                output="mp4" if quality_label != "audio" else "mp3",
                on_progress=_update_progress,
                should_stop=_should_stop,
            )
            with get_session() as s4:
                s4: Session
                r4 = s4.get(DownloadHistory, download_id)
                if not r4:
                    return
                r4.status = DownloadStatus.completed
                r4.file_path = str(file_path)
                r4.filename = filename
                r4.progress_percent = 100.0
                r4.updated_at = datetime.utcnow()
                s4.add(r4)
                s4.commit()
        except Exception as e:
            with get_session() as s5:
                s5: Session
                r5 = s5.get(DownloadHistory, download_id)
                if not r5:
                    return
                stop_reason = _stop_flags.pop(download_id, None)
                if str(e) == "STOP_REQUESTED" and stop_reason == "pause":
                    r5.status = DownloadStatus.paused
                    r5.error_message = None
                elif str(e) == "STOP_REQUESTED" and stop_reason == "cancel":
                    r5.status = DownloadStatus.cancelled
                    r5.error_message = None
                else:
                    r5.status = DownloadStatus.failed
                    r5.error_message = str(e)
                r5.updated_at = datetime.utcnow()
                s5.add(r5)
                s5.commit()

    asyncio.create_task(run_again())

    with get_session() as session:
        session: Session
        fresh = session.get(DownloadHistory, download_id)
        if not fresh:
            raise HTTPException(status_code=404, detail="Not found")
        return to_read_model(fresh)


@app.get("/api/downloads", response_model=DownloadList)
def list_downloads(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[DownloadStatus] = None,
) -> DownloadList:
    with get_session() as session:
        session: Session
        stmt = select(DownloadHistory)
        if status is not None:
            stmt = stmt.where(DownloadHistory.status == status)
        stmt = stmt.order_by(DownloadHistory.created_at.desc()).offset(offset).limit(limit)
        items = session.exec(stmt).all()

        total_stmt = select(func.count()).select_from(DownloadHistory)
        if status is not None:
            total_stmt = total_stmt.where(DownloadHistory.status == status)
        total = int(session.exec(total_stmt).one())

        return DownloadList(items=[to_read_model(r) for r in items], total=total)


@app.get("/api/downloads/{download_id}", response_model=DownloadRead)
def get_download(download_id: int) -> DownloadRead:
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return to_read_model(row)


@app.patch("/api/downloads/{download_id}", response_model=DownloadRead)
def update_download(download_id: int, payload: DownloadUpdate) -> DownloadRead:
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        if payload.title is not None:
            row.title = payload.title
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_read_model(row)


@app.delete("/api/downloads/{download_id}")
def delete_download(download_id: int, delete_file: bool = Query(False)) -> dict[str, bool]:
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")

        file_path = row.file_path
        session.delete(row)
        session.commit()

    if delete_file and file_path:
        try:
            Path(file_path).unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass

    return {"deleted": True}


@app.get("/api/downloads/{download_id}/file")
def download_file(download_id: int) -> FileResponse:
    with get_session() as session:
        session: Session
        row = session.get(DownloadHistory, download_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status != DownloadStatus.completed or not row.file_path:
            raise HTTPException(status_code=409, detail="File not ready")

        p = Path(row.file_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="File missing on server")

        return FileResponse(path=str(p), filename=row.filename or p.name, media_type="application/octet-stream")


@app.get("/direct-download")
async def direct_download(
    url: str,
    formatSelector: Optional[str] = None,
    output: str = "mp4",
) -> FileResponse:
    """
    Direct one-shot download for browser.
    Blocks until yt-dlp finishes, then streams the file so the browser
    shows its own download UI. No history/progress on the server.
    """
    output = (output or "mp4").lower()
    if output not in ("mp4", "mp3"):
        output = "mp4"

    if not url:
        raise HTTPException(status_code=400, detail="Missing url")

    # Fallback: pick a reasonable default format when none is provided.
    if not formatSelector:
        formatSelector, _ = pick_format("audio" if output == "mp3" else None)

    vid = extract_video_id(url) or "video"

    def _noop(_d: dict) -> None:
        return None

    file_path, filename = await asyncio.to_thread(
        download_to_file,
        url=url,
        format_selector=formatSelector,
        download_dir=DOWNLOAD_DIR,
        filename_prefix=vid,
        output=output,
        on_progress=_noop,
        should_stop=None,
    )

    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
