"""Cut, reframe (resize) and caption a clip with a single ffmpeg pass."""
from __future__ import annotations

import time
from pathlib import Path

from .. import config
from .captions import build_ass
from .media import run, thumbnail

ASPECTS = {
    "9:16": (1080, 1920),   # TikTok, Reels, Shorts
    "1:1": (1080, 1080),    # feed posts
    "4:5": (1080, 1350),    # Instagram / Facebook feed
    "16:9": (1920, 1080),   # YouTube, X
}

DEFAULT_RENDER = {
    "aspect": "9:16",
    "fit": "blur",          # crop | blur | fit
    "crop_x": 0.5,          # 0 = left edge, 1 = right edge (crop mode)
    "captions": True,
    "caption_style": "bold",
    "caption_position": 0.72,
    "show_hook": True,
}


def _video_filter(fit: str, w: int, h: int, crop_x: float) -> str:
    if fit == "crop":
        cx = min(max(crop_x, 0.0), 1.0)
        return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:(iw-{w})*{cx:.3f}:(ih-{h})/2,setsar=1[base]")
    if fit == "fit":
        return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[base]")
    # blur: blurred, zoomed copy fills the frame behind the full picture
    return (f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
            f"boxblur=10:2,scale={w}:{h},eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")


def render_clip(source: Path, out_dir: Path, clip: dict, words: list[dict], settings: dict,
                has_audio: bool = True) -> dict:
    s = {**DEFAULT_RENDER, **(settings or {})}
    w, h = ASPECTS.get(s["aspect"], ASPECTS["9:16"])
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = float(clip["start"]), float(clip["end"])
    duration = max(end - start, 0.1)

    ass_name = f"{clip['id']}.ass"
    build_ass(out_dir / ass_name, words, start, end, w, h,
              style=s["caption_style"], position=float(s["caption_position"]),
              hook=clip.get("hook", "") if s["show_hook"] else "",
              show_captions=bool(s["captions"]))

    graph = _video_filter(s["fit"], w, h, float(s["crop_x"])) + f";[base]ass={ass_name}[out]"
    out_name = f"{clip['id']}.mp4"
    cmd = [config.FFMPEG, "-y", "-v", "error",
           "-ss", f"{start:.3f}", "-i", str(source.resolve()), "-t", f"{duration:.3f}",
           "-filter_complex", graph, "-map", "[out]"]
    if has_audio:
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", config.VIDEO_PRESET, "-crf", str(config.VIDEO_CRF),
            "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", out_name]
    # Run inside out_dir so the .ass path is a bare filename (avoids Windows C:\ escaping issues).
    run(cmd, cwd=out_dir)
    thumb = thumbnail(out_dir / out_name, out_dir / f"{clip['id']}.jpg", min(1.0, duration / 2), width=360)
    return {"file": out_name, "thumb": thumb.name, "settings": s, "width": w, "height": h, "at": int(time.time())}
