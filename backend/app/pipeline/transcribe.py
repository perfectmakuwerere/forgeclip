"""Local speech-to-text with faster-whisper (word-level timestamps).

The model is downloaded once from Hugging Face on first use and then runs
offline on CPU or GPU, so no transcription API is needed.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from .. import config

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()
# One transcription at a time: the model instance serialises calls anyway, and two jobs
# fighting for the CPU makes both look frozen. Waiting jobs are told they're in line.
_run_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel  # imported lazily: heavy
            device = config.WHISPER_DEVICE
            if device == "auto":
                try:
                    import ctranslate2
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                except Exception:
                    device = "cpu"
            compute = config.WHISPER_COMPUTE if device == "cpu" else "float16"
            log.info("Loading Whisper %s on %s (%s)", config.WHISPER_MODEL, device, compute)
            threads = config.WHISPER_THREADS or (os.cpu_count() or 4)
            _model = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute,
                                  cpu_threads=threads, num_workers=1)
        return _model


def transcribe(audio_path: Path, duration: float,
               progress: Optional[Callable[[float], None]] = None,
               on_wait: Optional[Callable[[], None]] = None,
               on_start: Optional[Callable[[], None]] = None) -> dict:
    """Return {"language": str, "segments": [{start,end,text,words:[{start,end,word}]}]}.

    Uses Groq (cloud, fast) when GROQ_API_KEY is set; on any cloud failure, or without a key,
    falls back to local faster-whisper.
    """
    from . import cloud_stt
    if cloud_stt.available() and config.TRANSCRIBE_PROVIDER in ("auto", "groq"):
        try:
            if on_start:
                on_start()
            return cloud_stt.transcribe(audio_path, duration, progress)
        except Exception as exc:  # noqa: BLE001  (any cloud problem -> local backup)
            log.warning("cloud transcription failed, using local Whisper: %s", exc)
            if progress:
                progress(0.0)
    return _transcribe_local(audio_path, duration, progress, on_wait, on_start)


def _transcribe_local(audio_path: Path, duration: float,
                      progress: Optional[Callable[[float], None]] = None,
                      on_wait: Optional[Callable[[], None]] = None,
                      on_start: Optional[Callable[[], None]] = None) -> dict:
    if not _run_lock.acquire(blocking=False):
        if on_wait:
            on_wait()
        _run_lock.acquire()
    try:
        if on_start:
            on_start()
        model = _get_model()
        # Greedy decoding (beam 1), no conditioning on previous text and NO temperature fallback.
        # Fallback re-decodes every unsure 30 s window up to 6 times; on accented or mixed-language
        # speech (e.g. Shona + English) that made transcription 15x+ slower and look frozen.
        segments_iter, info = model.transcribe(
            str(audio_path), word_timestamps=True, beam_size=config.WHISPER_BEAM, best_of=1,
            temperature=0.0, condition_on_previous_text=False, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        segments = []
        for seg in segments_iter:
            words = [
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip()}
                for w in (seg.words or []) if w.word.strip()
            ]
            segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                             "text": seg.text.strip(), "words": words})
            if progress and duration:
                progress(min(seg.end / duration, 1.0))
        return {"language": info.language, "segments": segments, "engine": f"local:{config.WHISPER_MODEL}"}
    finally:
        _run_lock.release()


def all_words(transcript: dict) -> list[dict]:
    return [w for s in transcript.get("segments", []) for w in s.get("words", [])]
