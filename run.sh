#!/usr/bin/env bash
# ClipForge launcher for macOS / Linux. Needs Python 3.10+ and ffmpeg on PATH.
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
