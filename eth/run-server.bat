@echo off
REM YouTube Downloader - Server Only (assumes venv already exists)
cd /d "C:\Users\THABISH\Documents\eth"
call ".venv\Scripts\activate.bat"
echo Starting server at http://127.0.0.1:8000/
echo Live reload enabled - file changes restart the server
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
