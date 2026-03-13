# YouTube Downloader (FastAPI + HTML/CSS/JS)

Fast YouTube video downloader with **CRUD download history**. Ready to deploy on Vercel + Render (FREE!).

## 🚀 Deploy Online (FREE - 30 seconds)

### Step 1: Deploy Backend (Render.com) - 30 seconds
1. Go to https://render.com (sign up with GitHub)
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Set these values:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables:** Add `PYTHON_VERSION=3.11`
5. Click **Deploy**
6. Copy your Render URL (like `https://youtube-dl-xxxx.onrender.com`)

### Step 2: Deploy Frontend (Vercel) - 30 seconds
1. Go to https://vercel.com (sign up with GitHub)
2. Click **New Project**
3. Import your GitHub repo
4. **Framework:** None (static/HTML)
5. Click **Deploy**
6. Your site is live! Copy the Vercel URL

### Step 3: Connect Frontend to Backend
1. Open your Vercel site
2. Open browser console (F12)
3. Paste this and hit Enter:
   ```javascript
   localStorage.setItem("BACKEND_API_URL", "https://your-render-url.onrender.com")
   location.reload()
   ```
4. Done! Refresh and it works! ✅

---

## 💻 Local Development (Your PC)

### Windows - One Click
```
Double-click start.bat
```
Opens at `http://127.0.0.1:8000/` (automatic)

### Manual Setup
```bash
python -m venv .venv
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux

pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Tech Stack
- **Frontend:** HTML/CSS/JavaScript (Vercel)
- **Backend:** FastAPI + Python (Render.com)
- **Database:** SQLite
- **Downloader:** yt-dlp (video quality + audio merge)

## Features
✅ Download video + audio (best quality)  
✅ MP3 audio extraction  
✅ Download history with CRUD  
✅ Real-time progress tracking  
✅ Cancel/pause downloads  
✅ No compression losses  

## Requirements
- Python 3.10+
- FFmpeg (for video+audio merge) - optional but recommended
  - Windows: `choco install ffmpeg` or download from ffmpeg.org
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

## Dependencies
```
fastapi
uvicorn[standard]
sqlmodel
yt-dlp
python-multipart
```

## ⚙️ Configuration

### Environment Variables (for production)
- `DOWNLOAD_DIR` - Where to save downloads (default: `./downloads`)
- `ALLOWED_ORIGINS` - CORS origins (default: `*`)

### Change Backend URL
Browser console (F12):
```javascript
// Set custom backend URL
localStorage.setItem("BACKEND_API_URL", "https://your-backend.com")
location.reload()

// Reset to local
localStorage.removeItem("BACKEND_API_URL")
location.reload()
```

## 📝 Notes
- Downloads are **lossless** (yt-dlp merges without re-encoding)
- Use only for content you own rights to
- Follow YouTube Terms of Service and copyright laws
- Backend goes to sleep on free Render tier (wake up takes ~30s)

## 🔗 Useful Links
- [Render.com](https://render.com) - Backend hosting (free)
- [Vercel.com](https://vercel.com) - Frontend hosting (free)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Download engine
- [FastAPI](https://fastapi.tiangolo.com) - Backend framework
