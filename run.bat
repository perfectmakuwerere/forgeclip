@echo off
REM ClipForge launcher for Windows. Needs Python 3.10+ and ffmpeg on PATH.
cd /d %~dp0backend
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
