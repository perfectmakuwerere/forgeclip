@echo off
REM Start ClipForge and share it on the internet through a Cloudflare quick tunnel.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_public.ps1"
pause
