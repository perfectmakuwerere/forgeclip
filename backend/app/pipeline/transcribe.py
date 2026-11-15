"""Local speech-to-text with faster-whisper (word-level timestamps).

The model is downloaded once from Hugging Face on first use and then runs
offline on CPU or GPU, so no transcription API is needed.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from .. import config

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()


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
            _model = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute)
        return _model


def transcribe(audio_path: Path, duration: float,
               progress: Optional[Callable[[float], None]] = None) -> dict:
    """Return {"language": str, "segments": [{start,end,text,words:[{start,end,word}]}]}."""
    model = _get_model()
    segments_iter, info = model.transcribe(
        str(audio_path), word_timestamps=True, vad_filter=True, beam_size=5,
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
    return {"language": info.language, "segments": segments}


def all_words(transcript: dict) -> list[dict]:
    return [w for s in transcript.get("segments", []) for w in s.get("words", [])]
