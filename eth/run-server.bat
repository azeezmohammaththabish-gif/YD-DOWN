@echo off
cd /d "C:\Users\THABISH\Documents\eth"
call ".venv\Scripts\activate.bat"
echo Starting server at http://127.0.0.1:8000/
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
