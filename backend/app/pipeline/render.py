"""Cut, reframe (resize) and caption a clip with a single ffmpeg pass."""
from __future__ import annotations

import time
from pathlib import Path

from .. import config
from .captions import build_ass
from .media import run, thumbnail

# Output sizes for each format at 1080p. RENDER_QUALITY scales them: 720 (default) renders
# ~2x faster and still looks sharp on phones; 1080 is crisper on big screens.
_FULL = {
    "9:16": (1080, 1920),   # TikTok, Reels, Shorts
    "1:1": (1080, 1080),    # feed posts
    "4:5": (1080, 1350),    # Instagram / Facebook feed
    "16:9": (1920, 1080),   # YouTube, X
}


def _even(n: float) -> int:
    return int(round(n / 2)) * 2           # x264 needs even dimensions


_SCALE = max(360, min(config.RENDER_QUALITY, 2160)) / 1080
ASPECTS = {k: (_even(w * _SCALE), _even(h * _SCALE)) for k, (w, h) in _FULL.items()}

DEFAULT_RENDER = {
    "aspect": "9:16",
    "fit": "crop",          # crop (fill the frame) | blur (fit + blurred background) | fit (black bars)
    "crop_x": 0.5,          # 0 = left edge, 1 = right edge (crop mode)
    "captions": True,
    "caption_style": "bold",
    "caption_position": 0.72,   # 0 = top, 1 = bottom (UI presets: top 0.22, middle 0.5, bottom 0.72)
    "caption_size": "m",        # s | m | l
    "show_hook": False,         # big title over the first seconds; off by default
    "bar_color": "#000000",     # border colour for fit mode ("Fit + bars")
}


def _ff_color(value: str) -> str:
    """'#RRGGBB' -> ffmpeg '0xRRGGBB'; anything else falls back to black (never pass raw input to ffmpeg)."""
    v = str(value or "").strip().lstrip("#")
    return f"0x{v.upper()}" if len(v) == 6 and all(c in "0123456789abcdefABCDEF" for c in v) else "black"


def _video_filter(fit: str, w: int, h: int, crop_x: float, bar_color: str = "#000000") -> str:
    if fit == "crop":
        cx = min(max(crop_x, 0.0), 1.0)
        return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:(iw-{w})*{cx:.3f}:(ih-{h})/2,setsar=1[base]")
    if fit == "fit":
        return (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={_ff_color(bar_color)},setsar=1[base]")
    # blur: blurred, zoomed copy fills the frame behind the full picture
    return (f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
            f"boxblur=10:2,scale={w}:{h},eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")


def render_clip(source: "Path | str", out_dir: Path, clip: dict, words: list[dict], settings: dict,
                has_audio: bool = True) -> dict:
    """`source` is a local file or an http(s) URL (e.g. a signed bucket link); ffmpeg seeks either."""
    s = {**DEFAULT_RENDER, **(settings or {})}
    w, h = ASPECTS.get(s["aspect"], ASPECTS["9:16"])
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = float(clip["start"]), float(clip["end"])
    duration = max(end - start, 0.1)

    ass_name = f"{clip['id']}.ass"
    build_ass(out_dir / ass_name, words, start, end, w, h,
              style=s["caption_style"], position=float(s["caption_position"]), size=str(s.get("caption_size", "m")),
              hook=clip.get("hook", "") if s["show_hook"] else "",
              show_captions=bool(s["captions"]))

    graph = _video_filter(s["fit"], w, h, float(s["crop_x"]), s.get("bar_color", "#000000")) + f";[base]ass={ass_name}[out]"
    out_name = f"{clip['id']}.mp4"
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        src_in = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-i", source]
    else:
        src_in = ["-i", str(Path(source).resolve())]
    cmd = [config.FFMPEG, "-y", "-v", "error",
           "-ss", f"{start:.3f}", *src_in, "-t", f"{duration:.3f}",
           "-filter_complex", graph, "-map", "[out]"]
    if has_audio:
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", config.VIDEO_PRESET, "-crf", str(config.VIDEO_CRF),
            "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", out_name]
    # Run inside out_dir so the .ass path is a bare filename (avoids Windows C:\ escaping issues).
    run(cmd, cwd=out_dir)
    thumb = thumbnail(out_dir / out_name, out_dir / f"{clip['id']}.jpg", min(1.0, duration / 2), width=360)
    return {"file": out_name, "thumb": thumb.name, "settings": s, "width": w, "height": h, "at": int(time.time())}
