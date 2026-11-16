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

# Delete each project's original video (and extracted audio) this many days after import to save
# disk. Rendered clips are kept. 0 = keep forever.
SOURCE_RETENTION_DAYS = int(os.getenv("SOURCE_RETENTION_DAYS", "0"))

# Speech-to-text speed. Beam 1 (greedy) is several times faster on CPU than 5; raise it on a GPU.
WHISPER_BEAM = int(os.getenv("WHISPER_BEAM", "1"))
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "0"))     # 0 = all CPU cores

# Speech-to-text provider: auto = Groq when GROQ_API_KEY is set, otherwise local Whisper.
# local = always use this machine. Local Whisper is also the automatic backup if Groq fails.
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "auto").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
TRANSCRIBE_LANGUAGE = os.getenv("TRANSCRIBE_LANGUAGE", "").strip()   # e.g. "en"; empty = auto-detect

# Object storage for project media (S3-compatible: Cloudflare R2, AWS S3, Backblaze B2, MinIO...).
# With S3_BUCKET set, source videos, thumbnails, transcripts and rendered clips live in the bucket and
# data/projects/ is only scratch space for running jobs. Leave S3_BUCKET empty to keep media on this disk.
#   R2: S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com  S3_REGION=auto
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "").strip().rstrip("/")
S3_REGION = os.getenv("S3_REGION", "auto").strip()
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "").strip()
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
S3_PREFIX = os.getenv("S3_PREFIX", "").strip().strip("/")     # optional folder inside the bucket

# Rendered short resolution (short side, in pixels): 720 = 720x1280 (fast, default), 1080 = 1080x1920.
RENDER_QUALITY = int(os.getenv("RENDER_QUALITY", "720"))
