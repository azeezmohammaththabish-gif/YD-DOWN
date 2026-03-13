# YouTube Downloader (FastAPI + HTML/CSS/JS)

This is a small, fast YouTube downloader web app with **CRUD download history**.

## Tech
- Frontend: vanilla **HTML/CSS/JS** served from `static/`
- Backend: **FastAPI** (`backend/main.py`)
- DB: **SQLite** via **SQLModel**
- Downloader: **yt-dlp** (merges streams without extra compression; may require ffmpeg)

## Run
In PowerShell from the project folder:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`

## One-click run (Windows)
Double-click `start.bat`.

## Notes
- Downloads are saved to `downloads/` by default (configure via `DOWNLOAD_DIR` env var).
- For best quality merges (video+audio) install **ffmpeg** and ensure it's on PATH.
- Use only for content you own rights to and follow YouTube ToS/copyright law.
