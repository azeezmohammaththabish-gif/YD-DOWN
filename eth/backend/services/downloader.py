from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from yt_dlp import YoutubeDL


YOUTUBE_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> Optional[str]:
    m = YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


def _qualities_from_info(info: dict[str, Any]) -> list[str]:
    qualities: set[str] = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        if vcodec and vcodec != "none" and isinstance(h, int) and h > 0:
            qualities.add(f"{h}p")
        if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            qualities.add("audio")
    base = ["auto"]
    numeric = sorted([q for q in qualities if q.endswith("p")], key=lambda s: int(s[:-1]), reverse=True)
    if "audio" in qualities:
        numeric.append("audio")
    return base + numeric


def analyze_url(url: str) -> dict[str, Any]:
    # Allow playlists so we can surface entries.
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    # Detect playlist vs single video.
    is_playlist = bool(info.get("_type") == "playlist" or info.get("entries"))

    items: list[dict[str, Any]] = []
    video_id = info.get("id") or ""
    title = info.get("title") or ""
    duration = int(info.get("duration")) if isinstance(info.get("duration"), (int, float)) else None
    thumbnail = info.get("thumbnail") or None

    if is_playlist:
        entries = info.get("entries") or []
        for index, entry in enumerate(entries, start=1):
            if not entry:
                continue
            e_title = entry.get("title") or f"Video {index}"
            e_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
            if not e_url:
                continue
            e_duration = entry.get("duration")
            items.append(
                {
                    "index": index,
                    "title": e_title,
                    "url": e_url,
                    "duration_seconds": int(e_duration) if isinstance(e_duration, (int, float)) else None,
                }
            )

        if entries:
            first = entries[0] or {}
            video_id = first.get("id") or video_id
            thumbnail = first.get("thumbnail") or thumbnail
            # Use playlist title if present, otherwise first video title.
            if not title:
                title = info.get("title") or first.get("title") or ""

    # For options/qualities, base them on the first video (or the main info).
    base_info = info
    if is_playlist:
        first = (info.get("entries") or [None])[0] or {}
        base_info = first or info

    grouped = build_grouped_options(base_info)
    return {
        "video_id": video_id,
        "title": title,
        "duration_seconds": duration,
        "thumbnail_url": thumbnail,
        "is_playlist": is_playlist,
        "items": items,
        "qualities": _qualities_from_info(base_info),
        "video_options": grouped["video_options"],
        "audio_options": grouped["audio_options"],
        "options": build_format_options(base_info),  # legacy
        "raw": info,
    }


def _fmt_size(n: Any) -> Optional[int]:
    if isinstance(n, (int, float)) and n > 0:
        return int(n)
    return None


def build_format_options(info: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build a y2mate-like list of selectable options.
    Each option returns a yt-dlp format selector (no re-encode).
    """
    formats = info.get("formats") or []

    video_only = []
    audio_only = []
    for f in formats:
        fid = f.get("format_id")
        if not fid:
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        ext = f.get("ext") or ""
        height = f.get("height")
        abr = f.get("abr")
        tbr = f.get("tbr")
        fps = f.get("fps")
        filesize = _fmt_size(f.get("filesize")) or _fmt_size(f.get("filesize_approx"))

        if vcodec and vcodec != "none" and (not acodec or acodec == "none"):
            video_only.append(
                {
                    "format_id": str(fid),
                    "height": height if isinstance(height, int) else None,
                    "ext": ext,
                    "fps": fps if isinstance(fps, (int, float)) else None,
                    "tbr": tbr if isinstance(tbr, (int, float)) else None,
                    "vcodec": vcodec,
                    "filesize": filesize,
                }
            )
        elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            audio_only.append(
                {
                    "format_id": str(fid),
                    "abr": abr if isinstance(abr, (int, float)) else None,
                    "ext": ext,
                    "acodec": acodec,
                    "filesize": filesize,
                }
            )

    # Pick best audio by abr, then filesize, else keep.
    audio_only_sorted = sorted(
        audio_only,
        key=lambda a: (
            -float(a["abr"]) if a.get("abr") else 0.0,
            -(a["filesize"] or 0),
        ),
    )
    best_audio = audio_only_sorted[0]["format_id"] if audio_only_sorted else "bestaudio"

    # Recommended combined options: for each height, pick the best video-only format and pair with best audio.
    by_height: dict[int, list[dict[str, Any]]] = {}
    for v in video_only:
        h = v.get("height")
        if not isinstance(h, int) or h <= 0:
            continue
        by_height.setdefault(h, []).append(v)

    def v_rank(v: dict[str, Any]) -> tuple:
        return (
            float(v.get("tbr") or 0.0),
            float(v.get("fps") or 0.0),
            1.0 if (v.get("ext") == "mp4") else 0.0,
            float(v.get("filesize") or 0),
        )

    options: list[dict[str, Any]] = []

    options.append(
        {
            "type": "auto",
            "label": "Auto (best available)",
            "formatSelector": "bestvideo*+bestaudio/best",
        }
    )

    heights = sorted(by_height.keys(), reverse=True)
    for h in heights:
        best_v = sorted(by_height[h], key=v_rank, reverse=True)[0]
        v_id = best_v["format_id"]
        ext = best_v.get("ext") or ""
        fps = best_v.get("fps")
        size = best_v.get("filesize")
        fps_part = f" • {int(fps)}fps" if isinstance(fps, (int, float)) and fps else ""
        size_part = f" • ~{size} bytes" if isinstance(size, int) else ""
        label = f"Video {h}p ({ext}){fps_part} + Audio (best)"
        options.append(
            {
                "type": "video",
                "height": h,
                "label": label,
                "quality": f"{h}p",
                "formatSelector": f"{v_id}+{best_audio}",
            }
        )

    # Audio-only options (list a few best)
    for a in audio_only_sorted[:8]:
        abr = a.get("abr")
        ext = a.get("ext") or ""
        label = f"Audio ({ext})" + (f" • {int(abr)}kbps" if isinstance(abr, (int, float)) and abr else "")
        options.append(
            {
                "type": "audio",
                "label": label,
                "quality": "audio",
                "formatSelector": a["format_id"],
            }
        )

    # As a fallback, still offer bestaudio selector.
    options.append(
        {
            "type": "audio",
            "label": "Audio (best)",
            "quality": "audio",
            "formatSelector": "bestaudio/best",
        }
    )

    return options


def _human_size(n: Optional[int]) -> Optional[str]:
    if not isinstance(n, int) or n <= 0:
        return None
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    if i == 0:
        return f"{int(v)} {units[i]}"
    return f"{v:.1f} {units[i]}"


def build_grouped_options(info: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    Returns grouped video/audio options with better metadata for UI.
    """
    formats = info.get("formats") or []

    video_only = []
    audio_only = []
    for f in formats:
        fid = f.get("format_id")
        if not fid:
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        ext = f.get("ext") or ""
        height = f.get("height")
        fps = f.get("fps")
        abr = f.get("abr")
        tbr = f.get("tbr")
        filesize = _fmt_size(f.get("filesize")) or _fmt_size(f.get("filesize_approx"))
        protocol = f.get("protocol") or None

        if vcodec and vcodec != "none" and (not acodec or acodec == "none"):
            video_only.append(
                {
                    "format_id": str(fid),
                    "height": height if isinstance(height, int) else None,
                    "ext": ext,
                    "fps": int(fps) if isinstance(fps, (int, float)) else None,
                    "tbr": float(tbr) if isinstance(tbr, (int, float)) else None,
                    "vcodec": vcodec,
                    "filesize_bytes": filesize,
                    "filesize": _human_size(filesize),
                    "protocol": protocol,
                }
            )
        elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            audio_only.append(
                {
                    "format_id": str(fid),
                    "ext": ext,
                    "abr": int(abr) if isinstance(abr, (int, float)) else None,
                    "tbr": float(tbr) if isinstance(tbr, (int, float)) else None,
                    "acodec": acodec,
                    "filesize_bytes": filesize,
                    "filesize": _human_size(filesize),
                    "protocol": protocol,
                }
            )

    audio_only_sorted = sorted(
        audio_only,
        key=lambda a: (
            -float(a["abr"]) if a.get("abr") else 0.0,
            -(a.get("filesize_bytes") or 0),
        ),
    )
    # Prefer M4A for MP4 container compatibility; fallback to best abr.
    m4a_first = [a for a in audio_only_sorted if (a.get("ext") == "m4a")]
    best_audio = (m4a_first[0]["format_id"] if m4a_first else (audio_only_sorted[0]["format_id"] if audio_only_sorted else "bestaudio"))

    by_height: dict[int, list[dict[str, Any]]] = {}
    for v in video_only:
        h = v.get("height")
        if isinstance(h, int) and h > 0:
            by_height.setdefault(h, []).append(v)

    def v_rank(v: dict[str, Any]) -> tuple:
        # Prefer MP4/AVC for best compatibility, then bitrate/fps/size.
        vcodec = (v.get("vcodec") or "").lower()
        is_avc = 1.0 if ("avc" in vcodec or "h264" in vcodec) else 0.0
        return (
            1.0 if (v.get("ext") == "mp4") else 0.0,
            is_avc,
            float(v.get("tbr") or 0.0),
            float(v.get("fps") or 0.0),
            float(v.get("filesize_bytes") or 0.0),
        )

    video_options: list[dict[str, Any]] = []
    for h in sorted(by_height.keys(), reverse=True):
        best_v = sorted(by_height[h], key=v_rank, reverse=True)[0]
        # Combined selector (video+best audio), no re-encode.
        selector = f"{best_v['format_id']}+{best_audio}"
        video_options.append(
            {
                "quality": f"{h}p",
                "height": h,
                "ext": best_v.get("ext"),
                "fps": best_v.get("fps"),
                "filesize": best_v.get("filesize"),  # may be None (yt doesn't always provide)
                "filesize_bytes": best_v.get("filesize_bytes"),
                "formatSelector": selector,
                "label": f"{h}p • MP4",
            }
        )

    audio_options: list[dict[str, Any]] = []
    for a in audio_only_sorted:
        abr = a.get("abr")
        ext = a.get("ext")
        # UI always shows MP3 (we will convert), but selector points to the source audio stream.
        label = "MP3" + (f" • {abr}kbps" if isinstance(abr, int) else "")
        audio_options.append(
            {
                "quality": "audio",
                "ext": "mp3",
                "abr": abr,
                "filesize": a.get("filesize"),
                "filesize_bytes": a.get("filesize_bytes"),
                "formatSelector": a["format_id"],
                "label": label,
                "audioMode": "mp3",
            }
        )
    # Ensure at least one best-audio option.
    audio_options.append(
        {
            "quality": "audio",
            "ext": "mp3",
            "abr": None,
            "filesize": None,
            "filesize_bytes": None,
            "formatSelector": "bestaudio/best",
            "label": "MP3 (best)",
            "audioMode": "mp3",
        }
    )

    return {"video_options": video_options, "audio_options": audio_options}


def pick_format(preferred_quality: Optional[str]) -> tuple[str, str]:
    """
    Returns (format_selector, quality_label).
    Uses yt-dlp format selection without re-encoding (merging may require ffmpeg).
    """
    if not preferred_quality or preferred_quality == "auto":
        return "bestvideo*+bestaudio/best", "auto"

    q = preferred_quality.strip().lower()
    if q == "audio":
        return "bestaudio/best", "audio"

    if q.endswith("p"):
        try:
            h = int(q[:-1])
        except ValueError:
            return "bestvideo*+bestaudio/best", "auto"
        # Prefer exact-or-better within height limit, falling back to best.
        return f"bestvideo*[height<={h}]+bestaudio/best[height<={h}]/best", f"{h}p"

    return "bestvideo*+bestaudio/best", "auto"


def download_to_file(
    *,
    url: str,
    format_selector: str,
    download_dir: Path,
    filename_prefix: str,
    output: Optional[str] = None,  # "mp4" | "mp3"
    on_progress: Callable[[dict[str, Any]], None],
    should_stop: Optional[Callable[[], bool]] = None,
) -> tuple[Path, str]:
    download_dir.mkdir(parents=True, exist_ok=True)

    # Always name the file using the original video title only (no id prefix).
    outtmpl = str((download_dir / "%(title).200B.%(ext)s").as_posix())

    progress_lock = threading.Lock()

    def hook(d: dict[str, Any]) -> None:
        with progress_lock:
            on_progress(d)
        if should_stop and should_stop():
            raise RuntimeError("STOP_REQUESTED")

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": format_selector,
        "outtmpl": outtmpl,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "continuedl": True,
        "nopart": False,
        # Avoid re-encoding. If remux/merge needed, yt-dlp uses ffmpeg.
        "postprocessors": [],
    }

    if output == "mp3":
        # MP3 requires transcoding (lossy). Uses ffmpeg.
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
        ydl_opts["prefer_ffmpeg"] = True
        ydl_opts["extractaudio"] = True
        ydl_opts["audioformat"] = "mp3"
        ydl_opts["merge_output_format"] = None

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        final_path = ydl.prepare_filename(info)
        # yt-dlp may change extension after merge; try requested_downloads.
        rd = info.get("requested_downloads")
        if rd and isinstance(rd, list) and rd[0].get("filepath"):
            final_path = rd[0]["filepath"]
        # For mp3 postprocess, final file is different; try _filename / filepath.
        if output == "mp3":
            fp = info.get("filepath") or info.get("_filename")
            if isinstance(fp, str) and fp:
                final_path = fp

    p = Path(final_path)
    return p, p.name
