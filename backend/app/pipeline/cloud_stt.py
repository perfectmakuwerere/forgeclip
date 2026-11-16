"""Cloud speech-to-text via Groq (Whisper large-v3 turbo), with word-level timestamps.

Used by transcribe.transcribe() when GROQ_API_KEY is set; any failure there falls back to
local faster-whisper, so the user never sees a transcription error.

The 16 kHz WAV is re-encoded to 32 kbps mono MP3 (~14 MB per hour) and sent in 10-minute
pieces, which keeps every request well under Groq's upload limit (25 MB on the free tier).
Timestamps of each piece are shifted by its offset and stitched back together.
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from .. import config
from .media import run

log = logging.getLogger(__name__)

API = "https://api.groq.com/openai/v1/audio/transcriptions"
CHUNK_SECONDS = 600


class CloudSTTError(Exception):
    pass


def available() -> bool:
    return bool(config.GROQ_API_KEY)


def _encode_chunk(wav: Path, start: float, length: float, out: Path) -> Path:
    run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(wav),
         "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(out)])
    return out


def _request(path: Path) -> dict:
    data = {"model": config.GROQ_STT_MODEL, "response_format": "verbose_json", "temperature": "0",
            "timestamp_granularities[]": ["word", "segment"]}
    if config.TRANSCRIBE_LANGUAGE:
        data["language"] = config.TRANSCRIBE_LANGUAGE
    for attempt in range(3):
        with path.open("rb") as f:
            try:
                r = httpx.post(API, headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                               data=data, files={"file": (path.name, f, "audio/mpeg")},
                               timeout=httpx.Timeout(30.0, read=180.0))
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise CloudSTTError(f"network error: {exc}") from exc
                time.sleep(2 * (attempt + 1))
                continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (500, 502, 503) and attempt < 2:      # brief outage: retry
            time.sleep(2 * (attempt + 1))
            continue
        try:
            msg = (r.json().get("error") or {}).get("message", "")
        except ValueError:
            msg = r.text[:200]
        # 401 bad key, 413 too large, 429 rate/plan limit -> let the caller fall back to local
        raise CloudSTTError(f"Groq {r.status_code}: {msg[:200]}")
    raise CloudSTTError("Groq: no response")


def _to_segments(resp: dict, offset: float) -> list[dict]:
    words = [{"start": round(float(w["start"]) + offset, 3), "end": round(float(w["end"]) + offset, 3),
              "word": str(w.get("word", "")).strip()}
             for w in resp.get("words") or [] if str(w.get("word", "")).strip()]
    segments = []
    for s in resp.get("segments") or []:
        s0, s1 = float(s["start"]) + offset, float(s["end"]) + offset
        seg_words = [w for w in words if s0 - 0.05 <= w["start"] < s1]
        text = str(s.get("text", "")).strip()
        if not text and not seg_words:
            continue
        segments.append({"start": round(s0, 3), "end": round(s1, 3), "text": text, "words": seg_words})
    if not segments and words:                    # no segment info: one segment per piece
        segments = [{"start": words[0]["start"], "end": words[-1]["end"],
                     "text": " ".join(w["word"] for w in words), "words": words}]
    return segments


def transcribe(wav: Path, duration: float, progress: Optional[Callable[[float], None]] = None) -> dict:
    """Same output shape as the local transcriber: {"language", "segments": [{start,end,text,words}]}."""
    if not available():
        raise CloudSTTError("no GROQ_API_KEY")
    total = max(duration, 1.0)
    segments: list[dict] = []
    language = None
    with tempfile.TemporaryDirectory(prefix="cf-stt-") as tmp:
        start = 0.0
        while start < total:
            length = min(CHUNK_SECONDS, total - start)
            if length < 0.5:
                break
            piece = _encode_chunk(wav, start, length, Path(tmp) / f"part{int(start)}.mp3")
            resp = _request(piece)
            language = language or resp.get("language")
            segments += _to_segments(resp, start)
            start += length
            if progress:
                progress(min(start / total, 1.0))
    log.info("cloud transcription: %d segments, %s", len(segments), language)
    return {"language": language, "segments": segments, "engine": f"groq:{config.GROQ_STT_MODEL}"}
