"""Workspace analytics computed from the local project store."""
from __future__ import annotations

import time
from collections import Counter, defaultdict

from . import store


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def build(days: int = 30, owner: str | None = None) -> dict:
    projects = store.list_all(owner) if owner else []
    folders = {f["id"]: f for f in store.list_folders(owner)} if owner else {}
    now = time.time()
    day_keys = [_day(now - i * 86400) for i in range(days - 1, -1, -1)]
    imported = defaultdict(int)
    rendered = defaultdict(int)

    clips_total = rendered_total = 0
    source_sec = clip_sec = 0.0
    scores: list[int] = []
    tags: Counter = Counter()
    platforms: Counter = Counter()
    sources: Counter = Counter()
    per_folder: Counter = Counter()
    top: list[dict] = []

    for p in projects:
        platforms[p.get("platform") or "upload"] += 1
        per_folder[p.get("folder") or ""] += 1
        imported[_day(p["created"])] += 1
        if p.get("video"):
            source_sec += p["video"].get("duration", 0)
        for c in p.get("clips", []):
            clips_total += 1
            sources[c.get("source", "manual")] += 1
            if c.get("source") != "manual":
                scores.append(int(c.get("score", 0)))
            tags.update(t.lower() for t in c.get("hashtags", []) if t)
            if c.get("render_state") == "done" and c.get("render"):
                rendered_total += 1
                clip_sec += c["end"] - c["start"]
                rendered[_day(c["render"].get("at", p["created"]))] += 1
            top.append({"project_id": p["id"], "project": p["name"], "id": c["id"], "title": c["title"],
                        "score": c.get("score", 0), "source": c.get("source"), "length": round(c["end"] - c["start"]),
                        "thumb": c["render"]["thumb"] if c.get("render_state") == "done" and c.get("render") else None,
                        "file": c["render"]["file"] if c.get("render_state") == "done" and c.get("render") else None})

    buckets = [0] * 10
    for s in scores:
        buckets[min(9, max(0, s // 10))] += 1
    top.sort(key=lambda c: -c["score"])

    return {
        "totals": {
            "projects": len(projects), "clips": clips_total, "rendered": rendered_total,
            "source_minutes": round(source_sec / 60, 1), "clip_minutes": round(clip_sec / 60, 1),
            "avg_score": round(sum(scores) / len(scores)) if scores else None,
            "viral_clips": sum(1 for s in scores if s >= 80),
        },
        "daily": [{"day": d, "imported": imported.get(d, 0), "rendered": rendered.get(d, 0)} for d in day_keys],
        "score_buckets": buckets,
        "platforms": dict(platforms.most_common()),
        "clip_sources": dict(sources),
        "top_hashtags": tags.most_common(12),
        "top_clips": top[:8],
        "folders": [{"id": fid, "name": folders[fid]["name"] if fid in folders else "Unsorted",
                     "color": folders[fid]["color"] if fid in folders else "#6b6b76", "projects": n}
                    for fid, n in per_folder.most_common()],
    }
