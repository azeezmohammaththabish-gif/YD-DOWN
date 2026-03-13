@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM ---- Choose Python launcher (python or py) ----
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if "%PYEXE%"=="" (
  where py >nul 2>nul && set "PYEXE=py -3"
)

if "%PYEXE%"=="" (
  echo Python is not installed or not on PATH.
  echo Install Python 3.10+ then try again.
  pause
  exit /b 1
)

REM ---- Create venv if missing ----
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
)

REM ---- Install deps ----
call ".venv\Scripts\activate.bat"
echo Installing/updating dependencies...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements.
  pause
  exit /b 1
)

REM ---- Start server (live reload) in its own window ----
echo Starting server (live reload) at http://127.0.0.1:8000/
start "YouTube Downloader Server" cmd /k "cd /d \"%~dp0\" ^& call .venv\Scripts\activate.bat ^& python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"

REM ---- Wait until server is ready, then open browser ----
set "URL=http://127.0.0.1:8000/"
set "HEALTH=http://127.0.0.1:8000/api/health"
set "READY=0"

for /l %%i in (1,1,60) do (
  powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri '%HEALTH%'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 (
    set "READY=1"
    goto :openBrowser
  )
  timeout /t 1 >nul
)

:openBrowser
if "%READY%"=="1" (
  start "" "%URL%"
) else (
  echo Server is taking longer than expected to start.
  echo You can still try opening: %URL%
)

REM ---- Optional extra shell for manual commands ----
start "YouTube Downloader Shell" cmd /k "cd /d \"%~dp0\" ^& call .venv\Scripts\activate.bat"

exit /b 0
