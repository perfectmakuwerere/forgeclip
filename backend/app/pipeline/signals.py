"""Non-LLM signals that point at "something happened here".

These matter a lot for gameplay footage (e.g. GTA), where there may be little
or no speech: explosions, crashes, gunfire, crowd/streamer screams show up as
loudness spikes, and chases or chaos show up as dense scene cuts / fast motion.
"""
from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np

from .. import config
from .media import run

HOP = 0.5  # seconds per signal bin


def loudness_curve(wav_path: Path) -> np.ndarray:
    """RMS loudness (dB) per HOP-second bin, from a mono 16-bit wav."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(sr * HOP)
    if hop == 0 or len(data) < hop:
        return np.zeros(1, dtype=np.float32)
    n = len(data) // hop
    frames = data[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-10)
    return 20 * np.log10(rms + 1e-10)


def scene_changes(video_path: Path, threshold: float = 0.3) -> list[float]:
    """Timestamps (s) of visual cuts / big frame changes, via ffmpeg's scene score.

    Video is downscaled first so this stays fast on long gameplay recordings.
    """
    proc = run([config.FFMPEG, "-hide_banner", "-i", str(video_path), "-an",
                "-vf", f"scale=320:-2,fps=10,select='gt(scene,{threshold})',showinfo",
                "-f", "null", "-"])
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]


def zscore(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    std = float(x.std())
    return (x - x.mean()) / std if std > 1e-6 else np.zeros_like(x)


def build_signals(wav_path: Path | None, video_path: Path, duration: float) -> dict:
    n_bins = max(int(np.ceil(duration / HOP)), 1)
    loud = np.zeros(n_bins, dtype=np.float32)
    if wav_path is not None and wav_path.exists():
        curve = loudness_curve(wav_path)
        loud[: min(len(curve), n_bins)] = curve[:n_bins]
    # Excitement = how far above its local (30 s) baseline the audio is.
    k = max(int(30 / HOP), 1)
    baseline = np.convolve(loud, np.ones(k) / k, mode="same") if len(loud) > k else np.full_like(loud, loud.mean())
    excitement = zscore(loud - baseline)

    cuts = scene_changes(video_path)
    cut_density = np.zeros(n_bins, dtype=np.float32)
    for t in cuts:
        i = int(t / HOP)
        if 0 <= i < n_bins:
            cut_density[i] += 1
    return {
        "hop": HOP,
        "loudness_db": [round(float(v), 2) for v in loud],
        "excitement": [round(float(v), 3) for v in excitement],
        "cut_density": [float(v) for v in cut_density],
        "scene_cuts": [round(t, 2) for t in cuts],
    }
