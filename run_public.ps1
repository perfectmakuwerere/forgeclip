# Run ClipForge on this PC and make it reachable from the internet through a free
# Cloudflare "quick tunnel" (https, no account, no router/firewall changes).
# The public address is random and changes every time you start this script.
#
# Usage: double-click run_public.bat (or: powershell -ExecutionPolicy Bypass -File run_public.ps1)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$python  = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Python environment not found. Run run.bat once first to set ClipForge up." -ForegroundColor Red; exit 1
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared is not installed. Install it with:  winget install --id Cloudflare.cloudflared" -ForegroundColor Red; exit 1
}
# First free port (8000 is often taken by other local projects or by run.bat).
$port = $null
foreach ($p in 8000, 8010, 8020, 8030, 8040) {
    if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { $port = $p; break }
}
if (-not $port) {
    Write-Host "Ports 8000-8040 are all in use. Close another local server and try again." -ForegroundColor Red; exit 1
}
if ($port -ne 8000) { Write-Host "Port 8000 is busy, using $port." -ForegroundColor Yellow }

# 1. Start the tunnel and wait for its public address.
$log = Join-Path $env:TEMP "clipforge-tunnel.log"
Remove-Item $log -ErrorAction SilentlyContinue
$tunnel = Start-Process cloudflared -PassThru -WindowStyle Hidden -RedirectStandardError $log `
    -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$port")

Write-Host "Starting Cloudflare tunnel..."
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
    if ($tunnel.HasExited) { break }
}
if (-not $url) {
    Write-Host "The tunnel didn't start. Details: $log" -ForegroundColor Red
    if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
    exit 1
}

# 2. Start ClipForge with that address as its public URL (used for Stripe return links etc.).
$env:PUBLIC_URL = $url
Write-Host ""
Write-Host "  ClipForge is live at:  $url" -ForegroundColor Green
Write-Host "  On this PC you can also use http://127.0.0.1:$port"
Write-Host "  Keep this window open and the PC awake. Press Ctrl+C to stop."
Write-Host ""
try { Set-Clipboard -Value $url; Write-Host "  (Public address copied to the clipboard.)`n" } catch {}

try {
    Set-Location $backend
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $port
}
finally {
    if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force }
    Write-Host "Tunnel closed."
}
