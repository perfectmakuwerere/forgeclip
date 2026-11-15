"""Find viral-worthy moments.

Two stages:
  1. Signals (always): loudness spikes, scene-cut bursts, hype words in the
     transcript -> a ranked list of candidate windows. No model needed.
  2. LLM (optional): the model reads the timestamped transcript plus the signal
     candidates and picks/refines clips, writing a title, hook, score and reason.
If the LLM is missing or fails, stage 1's candidates are returned as-is.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

import numpy as np

from ..llm.base import LLMError, LLMProvider
from .transcribe import all_words

log = logging.getLogger(__name__)

HYPE = re.compile(
    r"\b(no way|oh my god|omg|what the|wtf|holy|let'?s go|insane|crazy|bro+|yo+|wow|"
    r"run+|go go|oh no|nah|bruh|clutch|ha(ha)+|lol|dude|unbelievable|watch this|look at)\b",
    re.I,
)


def fmt_ts(t: float) -> str:
    t = max(t, 0)
    return f"{int(t // 60):02d}:{t % 60:05.2f}" if t < 3600 else f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


# ----------------------------------------------------------------- signals ---

def _bin_scores(signals: dict, transcript: dict, duration: float) -> np.ndarray:
    hop = signals["hop"]
    exc = np.clip(np.array(signals["excitement"], dtype=np.float32), -1, 4)
    cuts = np.array(signals["cut_density"], dtype=np.float32)
    n = len(exc)
    # cut bursts: cuts in a 3 s neighbourhood
    k = max(int(3 / hop), 1)
    cut_burst = np.convolve(cuts, np.ones(k), mode="same")
    cut_z = np.clip((cut_burst - cut_burst.mean()) / (cut_burst.std() + 1e-6), -1, 4) if cut_burst.std() > 0 else np.zeros(n)

    hype = np.zeros(n, dtype=np.float32)
    speech = np.zeros(n, dtype=np.float32)
    for seg in transcript.get("segments", []):
        i0, i1 = int(seg["start"] / hop), int(seg["end"] / hop) + 1
        speech[i0:i1] = 1
        hits = len(HYPE.findall(seg["text"])) + seg["text"].count("!") + seg["text"].count("?") * 0.3
        if hits:
            hype[i0:i1] += min(hits, 4)
    score = 0.55 * exc + 0.30 * cut_z + 0.45 * hype + 0.15 * speech
    # smooth so we favour sustained action over a single click
    s = max(int(2 / hop), 1)
    return np.convolve(score, np.ones(s) / s, mode="same")


def _snap(start: float, end: float, transcript: dict, duration: float) -> tuple[float, float]:
    """Move cut points so they don't slice through a sentence."""
    segs = transcript.get("segments", [])
    for seg in segs:
        if seg["start"] < start < seg["end"] and start - seg["start"] < 2.5:
            start = seg["start"]
            break
    for seg in segs:
        if seg["start"] < end < seg["end"] and seg["end"] - end < 3.5:
            end = seg["end"]
            break
    return round(max(0.0, start - 0.15), 2), round(min(duration, end + 0.25), 2)


def _text_in(transcript: dict, start: float, end: float) -> str:
    return " ".join(s["text"] for s in transcript.get("segments", []) if s["end"] > start and s["start"] < end).strip()


def signal_candidates(signals: dict, transcript: dict, duration: float,
                      min_len: float, max_len: float, count: int) -> list[dict]:
    hop = signals["hop"]
    score = _bin_scores(signals, transcript, duration)
    if duration <= min_len or len(score) < 3:
        return [_new_clip(0, duration, "Full video", "", 50, "Video is shorter than the minimum clip length.", "signals")]
    target = (min_len + max_len) / 2
    order = np.argsort(score)[::-1]
    taken: list[tuple[float, float]] = []
    clips = []
    top = float(score[order[0]]) or 1.0
    for idx in order:
        peak = idx * hop
        # put the peak ~35% into the clip: a little setup, then payoff, then reaction
        start = max(0.0, peak - 0.35 * target)
        end = min(duration, start + target)
        start = max(0.0, end - target)
        start, end = _snap(start, end, transcript, duration)
        if any(min(end, b) - max(start, a) > 0.3 * (end - start) for a, b in taken):
            continue
        taken.append((start, end))
        rel = float(score[idx]) / top if top > 0 else 0
        pct = int(np.clip(55 + 40 * rel, 40, 95))
        reasons = []
        i0, i1 = int(start / hop), int(end / hop)
        exc = signals["excitement"][i0:i1]
        if exc and max(exc) > 1.5:
            reasons.append(f"audio spike at {fmt_ts(i0 * hop + int(np.argmax(exc)) * hop)}")
        n_cuts = sum(1 for t in signals["scene_cuts"] if start <= t <= end)
        if n_cuts >= 4:
            reasons.append(f"{n_cuts} fast scene changes")
        text = _text_in(transcript, start, end)
        if HYPE.search(text):
            reasons.append("hype reaction in speech")
        title = (text[:60].rsplit(" ", 1)[0] + "…") if len(text) > 60 else (text or f"Moment at {fmt_ts(peak)}")
        clips.append(_new_clip(start, end, title, text[:120], pct,
                               "; ".join(reasons) or "high activity", "signals"))
        if len(clips) >= count:
            break
    return sorted(clips, key=lambda c: -c["score"])


# --------------------------------------------------------------------- LLM ---

SYSTEM = """You are a senior short-form video editor who has cut thousands of viral \
TikToks, YouTube Shorts and Instagram Reels, including gaming clips. You find the \
moments people will rewatch and share: big reactions, funny or chaotic events, clutch \
plays, surprising reveals, quotable lines, strong opinions, emotional peaks.

Rules for every clip:
- It must stand alone: a viewer with no context understands it.
- Hook in the first 3 seconds. Start right before the action or line, not mid-word.
- End on the payoff or reaction, not in the middle of a sentence.
- Respect the requested length range.
- Use the signal candidates (audio spikes, fast cuts) as strong hints, especially when \
there is little speech, e.g. gameplay.

Reply with JSON only, no prose, in exactly this shape:
{"clips": [{"start": 12.3, "end": 41.0, "title": "short punchy title (max 60 chars)",
"hook": "on-screen hook text for the first seconds (max 8 words)",
"score": 0-100 virality estimate, "reason": "one sentence why it will perform",
"hashtags": ["#tag", "#tag"]}]}"""


def _transcript_lines(transcript: dict, t0: float, t1: float) -> str:
    return "\n".join(
        f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
        for s in transcript.get("segments", []) if s["end"] > t0 and s["start"] < t1
    )


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def llm_clips(provider: LLMProvider, transcript: dict, candidates: list[dict], duration: float,
              min_len: float, max_len: float, count: int, context: str = "") -> list[dict]:
    chunk_len = 20 * 60  # long videos are analysed in 20-minute windows
    windows = [(t, min(t + chunk_len + 60, duration)) for t in np.arange(0, max(duration, 1), chunk_len)]
    per_window = max(2, int(np.ceil(count * 1.5 / len(windows))))
    results: list[dict] = []
    for t0, t1 in windows:
        cand_text = "\n".join(
            f"- {c['start']:.1f}-{c['end']:.1f}s (signal score {c['score']}): {c['reason']}"
            for c in candidates if c["start"] < t1 and c["end"] > t0
        ) or "(none)"
        lines = _transcript_lines(transcript, t0, t1) or "(no speech detected: rely on the signal candidates)"
        user = (
            f"Video length: {duration:.1f}s. Analysing {t0:.0f}-{t1:.0f}s.\n"
            f"Creator context: {context or 'not given'}\n"
            f"Wanted: up to {per_window} clips, each {min_len:.0f}-{max_len:.0f} seconds.\n\n"
            f"SIGNAL CANDIDATES (loudness spikes / fast cuts / hype words):\n{cand_text}\n\n"
            f"TRANSCRIPT (seconds):\n{lines[:60000]}"
        )
        reply = provider.complete(SYSTEM, user)
        data = _parse_json(reply)
        for c in data.get("clips", []):
            try:
                start, end = float(c["start"]), float(c["end"])
            except (KeyError, TypeError, ValueError):
                continue
            start, end = max(0.0, start), min(duration, end)
            if end - start < min_len * 0.6:
                end = min(duration, start + min_len)
            if end - start > max_len * 1.4:
                end = start + max_len
            if end <= start:
                continue
            start, end = _snap(start, end, transcript, duration)
            results.append(_new_clip(
                start, end, str(c.get("title", ""))[:80], str(c.get("hook", ""))[:80],
                int(np.clip(float(c.get("score", 70)), 0, 100)), str(c.get("reason", ""))[:300], "ai",
                [str(h) if str(h).startswith("#") else f"#{h}" for h in c.get("hashtags", [])][:8],
            ))
    # de-duplicate overlapping picks, keep the higher score
    results.sort(key=lambda c: -c["score"])
    kept: list[dict] = []
    for c in results:
        if all(min(c["end"], k["end"]) - max(c["start"], k["start"]) < 0.5 * (c["end"] - c["start"]) for k in kept):
            kept.append(c)
    return kept[:count]


def find_moments(transcript: dict, signals: dict, duration: float, provider: Optional[LLMProvider],
                 min_len: float = 15, max_len: float = 60, count: int = 8, context: str = "") -> tuple[list[dict], str]:
    candidates = signal_candidates(signals, transcript, duration, min_len, max_len, max(count * 2, 6))
    if provider is None:
        return candidates[:count], "signals only (no LLM connected)"
    try:
        clips = llm_clips(provider, transcript, candidates, duration, min_len, max_len, count, context)
        if clips:
            return clips, f"AI ranked with {provider.describe()}"
        return candidates[:count], "LLM returned no clips, used signals"
    except (LLMError, ValueError, json.JSONDecodeError) as exc:
        log.warning("LLM ranking failed: %s", exc)
        return candidates[:count], f"LLM failed ({str(exc)[:160]}), used signals"


def _new_clip(start, end, title, hook, score, reason, source, hashtags=None) -> dict:
    return {
        "id": uuid.uuid4().hex[:10],
        "start": round(float(start), 2), "end": round(float(end), 2),
        "title": title or "Untitled clip", "hook": hook or "", "score": int(score),
        "reason": reason, "hashtags": hashtags or [], "source": source,
        "render": None,
    }


def manual_clip(start: float, end: float, title: str = "Manual clip") -> dict:
    return _new_clip(start, end, title, "", 0, "Created by hand", "manual")


__all__ = ["find_moments", "manual_clip", "all_words", "fmt_ts"]
