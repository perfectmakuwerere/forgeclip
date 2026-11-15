"""App configuration, read from environment variables (or a .env file next to backend/)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
ROOT_DIR = BASE_DIR.parent                         # clipforge/


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0]  # allow inline comments
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

DATA_DIR = Path(os.getenv("CLIPFORGE_DATA_DIR", ROOT_DIR / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

FRONTEND_DIR = ROOT_DIR / "frontend"

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")

# Speech-to-text (runs locally, no API needed)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")      # tiny | base | small | medium | large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")     # auto | cpu | cuda
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")   # int8 | float16 | float32

# Server-side ("owner") LLM. If set, it is used whenever a user has not
# supplied their own key. Leave LLM_PROVIDER empty to require bring-your-own-key.
#   LLM_PROVIDER = anthropic | openai_compat | none
SERVER_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
SERVER_LLM_MODEL = os.getenv("LLM_MODEL", "")
SERVER_LLM_API_KEY = os.getenv("LLM_API_KEY", "")
SERVER_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# Encoding
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "veryfast")
VIDEO_CRF = os.getenv("VIDEO_CRF", "21")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "4096"))

# Public base URL of this app. OAuth redirect URIs are built from it:
#   <PUBLIC_URL>/api/social/<platform>/callback
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")

# Link import (yt-dlp)
MAX_IMPORT_MINUTES = int(os.getenv("MAX_IMPORT_MINUTES", "240"))
IMPORT_MAX_HEIGHT = int(os.getenv("IMPORT_MAX_HEIGHT", "1080"))
# Some sites (Instagram, private X/TikTok posts) need you to be logged in.
# Set to chrome | edge | firefox | brave to reuse that browser's cookies.
YTDLP_COOKIES_FROM_BROWSER = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()

# Social network apps (OAuth). Leave empty to hide "Connect" for that network.
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")        # Google Cloud OAuth client
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID", "")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")

# Supabase (auth + database). URL and publishable key are public; the secret key is server-only.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

# Stripe (subscriptions). Secret + webhook secret are server-only.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
