"""Import a video from a link (YouTube, TikTok, Instagram, X, Twitch, Vimeo, Drive, direct .mp4 ...) via yt-dlp."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from .. import config

log = logging.getLogger("clipforge.import")

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

# host suffix -> platform id (used for icons and analytics)
_HOSTS = {
    "youtube.com": "youtube", "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "x.com": "x", "twitter.com": "x",
    "twitch.tv": "twitch",
    "facebook.com": "facebook", "fb.watch": "facebook",
    "vimeo.com": "vimeo",
    "drive.google.com": "drive",
    "kick.com": "kick",
    "reddit.com": "reddit",
}


class ImportError_(Exception):
    """User-facing import failure."""


def platform_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for suffix, name in _HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return "web"


def validate_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        raise ImportError_("That doesn't look like a link. Paste a full video URL.")
    return url


def _ffmpeg_location() -> Optional[str]:
    path = shutil.which(config.FFMPEG) or config.FFMPEG
    return str(Path(path).parent) if Path(path).exists() else None


def _friendly(exc: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace("ERROR: ", "")
    low = msg.lower()
    if "login" in low or "cookies" in low or "rate-limit" in low or "sign in" in low:
        return ("This site wants you to be logged in. Set YTDLP_COOKIES_FROM_BROWSER=chrome (or edge/firefox) "
                "in backend/.env, or download the video and upload it.")
    if "private" in low:
        return "This video is private."
    if "unsupported url" in low:
        return "That link isn't a video page we can read. Try the post's direct link."
    if "unavailable" in low or "404" in low:
        return "Video unavailable (deleted, region-locked or not public)."
    return msg[:300]


def download(url: str, dest_dir: Path, on_meta: Callable[[dict], None],
             on_progress: Callable[[float, str], None]) -> Path:
    """Download `url` into dest_dir/source.<ext>. Returns the file path.

    on_meta gets {title, duration, thumbnail, uploader, platform} before the download starts.
    on_progress gets (fraction 0..1, human stage text).
    """
    from yt_dlp import YoutubeDL  # imported lazily: heavy module

    limit_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    h = config.IMPORT_MAX_HEIGHT
    parts = {"n": 0}

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            frac = (d.get("downloaded_bytes", 0) / total) if total else 0.0
            kind = "audio" if d.get("info_dict", {}).get("vcodec") == "none" else "video"
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            extra = " · ".join(x for x in (speed, f"{eta} left" if eta and eta != "Unknown" else "") if x)
            on_progress(min(frac, 1.0), f"Downloading {kind}{' · ' + extra if extra else ''}")
        elif d.get("status") == "finished":
            parts["n"] += 1
            on_progress(1.0, "Merging audio and video")

    opts = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "format": (f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/"
                   f"b[height<={h}][ext=mp4]/b[height<={h}]/b"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "max_filesize": limit_bytes,
        "socket_timeout": 30,
        "retries": 3,
    }
    if loc := _ffmpeg_location():
        opts["ffmpeg_location"] = loc
    if config.YTDLP_COOKIES_FROM_BROWSER:
        opts["cookiesfrombrowser"] = (config.YTDLP_COOKIES_FROM_BROWSER,)

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
                if not entries:
                    raise ImportError_("That playlist is empty.")
                info = entries[0]
            if info.get("is_live"):
                raise ImportError_("Live streams can't be imported until they end. Use the VOD link.")
            duration = float(info.get("duration") or 0)
            if duration and duration > config.MAX_IMPORT_MINUTES * 60:
                raise ImportError_(f"Video is {duration / 60:.0f} min long; the limit is {config.MAX_IMPORT_MINUTES} min "
                                   "(MAX_IMPORT_MINUTES in backend/.env).")
            on_meta({
                "title": (info.get("title") or info.get("description") or "Imported video")[:80],
                "duration": duration,
                "thumbnail": info.get("thumbnail") or "",
                "uploader": info.get("uploader") or info.get("channel") or "",
                "platform": platform_of(url),
            })
            ydl.process_ie_result(info, download=True)
    except ImportError_:
        raise
    except Exception as exc:  # noqa: BLE001  (yt-dlp raises many error types)
        log.warning("import failed for %s: %s", platform_of(url), exc)
        raise ImportError_(_friendly(exc)) from exc

    files = [f for f in dest_dir.glob("source.*") if f.suffix.lower() in VIDEO_EXT]
    if not files:
        raise ImportError_("Download finished but no video file was produced (is ffmpeg installed?).")
    return max(files, key=lambda f: f.stat().st_size)
