"""Thin wrappers around ffmpeg / ffprobe."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from .. import config


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise MediaError(f"{Path(cmd[0]).name} failed: {proc.stderr[-1500:]}")
    return proc


def probe(path: Path) -> dict:
    proc = run([config.FFPROBE, "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)])
    info = json.loads(proc.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video:
        raise MediaError("No video stream found in file.")
    width, height = int(video["width"]), int(video["height"])
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = abs(int(sd["rotation"]))
    if rotation in (90, 270):
        width, height = height, width
    num, _, den = (video.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return {
        "duration": float(info["format"].get("duration", 0) or 0),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "has_audio": audio is not None,
    }


def extract_audio(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    run([config.FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)])
    return dst


def thumbnail(src: Path, dst: Path, at: float, width: int = 480) -> Path:
    run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{max(at, 0):.3f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"scale={width}:-2", str(dst)])
    return dst
