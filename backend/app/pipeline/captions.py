"""Animated word-by-word captions as an ASS subtitle file (rendered by libass in ffmpeg)."""
from __future__ import annotations

from pathlib import Path

# ASS colours are &HAABBGGRR
STYLES = {
    "bold": {   # big outlined uppercase, current word yellow + pop (classic viral style)
        "font": "Arial Black", "size": 0.050, "primary": "&H00FFFFFF", "highlight": "&H0000F0FF",
        "outline": 0.0045, "shadow": 0, "border_style": 1, "back": "&H80000000",
        "upper": True, "words": 3, "pop": True,
    },
    "neon": {
        "font": "Impact", "size": 0.054, "primary": "&H00FFFFFF", "highlight": "&H0014FF39",
        "outline": 0.004, "shadow": 0.002, "border_style": 1, "back": "&H80000000",
        "upper": True, "words": 2, "pop": True,
    },
    "boxed": {  # white text on a dark box, very readable over busy gameplay
        "font": "Arial", "size": 0.040, "primary": "&H00FFFFFF", "highlight": "&H0000F0FF",
        "outline": 0.008, "shadow": 0, "border_style": 3, "back": "&H50000000",
        "upper": False, "words": 4, "pop": False,
    },
    "minimal": {
        "font": "Arial", "size": 0.036, "primary": "&H00FFFFFF", "highlight": None,
        "outline": 0.0018, "shadow": 0.0015, "border_style": 1, "back": "&H80000000",
        "upper": False, "words": 6, "pop": False,
    },
}


def _ts(t: float) -> str:
    t = max(t, 0)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], max_words: int, max_gap: float = 0.6) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap
                    or cur[-1]["word"][-1:] in ".?!,"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(path: Path, words: list[dict], clip_start: float, clip_end: float,
              width: int, height: int, style: str = "bold", position: float = 0.72,
              hook: str = "", show_captions: bool = True) -> Path:
    st = STYLES.get(style, STYLES["bold"])
    ref = min(width, height) if width > height else height  # scale with the short-form frame
    size = int(ref * st["size"] * (1.25 if width > height else 1))
    outline = max(1, round(ref * st["outline"]))
    shadow = round(ref * st["shadow"])
    margin_v = int((1 - position) * height)
    hook_size = int(size * 0.85)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{size},{st['primary']},{st['primary']},&H00000000,{st['back']},-1,0,0,0,100,100,0,0,{st['border_style']},{outline},{shadow},2,{int(width*0.06)},{int(width*0.06)},{margin_v},1
Style: Hook,{st['font']},{hook_size},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,{max(8, int(hook_size*0.25))},0,8,{int(width*0.08)},{int(width*0.08)},{int(height*0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(min(3.5, clip_end - clip_start))},Hook,,0,0,0,,"
                     f"{{\\fad(150,250)}}{_esc(hook)}")

    if show_captions:
        clip_words = [
            {"start": w["start"] - clip_start, "end": w["end"] - clip_start, "word": w["word"]}
            for w in words if w["end"] > clip_start and w["start"] < clip_end
        ]
        for chunk in chunk_words(clip_words, st["words"]):
            texts = [_esc(w["word"].upper() if st["upper"] else w["word"]) for w in chunk]
            c_end = chunk[-1]["end"] + 0.12
            if not st["highlight"]:
                lines.append(f"Dialogue: 0,{_ts(chunk[0]['start'])},{_ts(c_end)},Cap,,0,0,0,,{' '.join(texts)}")
                continue
            # one event per word: whole chunk visible, active word coloured (and popped)
            for i, w in enumerate(chunk):
                w_start = w["start"]
                w_end = chunk[i + 1]["start"] if i + 1 < len(chunk) else c_end
                parts = []
                for j, t in enumerate(texts):
                    if j == i:
                        pop = "\\fscx112\\fscy112" if st["pop"] else ""
                        parts.append(f"{{\\c{st['highlight']}{pop}}}{t}{{\\c{st['primary']}\\fscx100\\fscy100}}")
                    else:
                        parts.append(t)
                lines.append(f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},Cap,,0,0,0,,{' '.join(parts)}")

    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path
