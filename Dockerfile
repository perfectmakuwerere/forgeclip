# ClipForge server image: FastAPI + ffmpeg + faster-whisper + yt-dlp.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/models

# ffmpeg for cutting/rendering, unzip+curl to fetch Deno (yt-dlp uses a JS runtime for YouTube)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ARG DENO_VERSION=2.1.4
RUN arch="$(uname -m)" \
 && case "$arch" in x86_64) target=x86_64-unknown-linux-gnu ;; aarch64) target=aarch64-unknown-linux-gnu ;; *) echo "unsupported arch $arch" && exit 1 ;; esac \
 && curl -fsSL -o /tmp/deno.zip "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${target}.zip" \
 && unzip -q /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip && deno --version

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY backend/scripts backend/scripts
COPY frontend frontend

# Unprivileged user; data/ and models/ are volumes owned by it
RUN useradd --create-home --uid 1000 clipforge \
 && mkdir -p /app/data /app/models && chown -R clipforge:clipforge /app/data /app/models
USER clipforge

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=4)"

# One worker on purpose: job progress and upload state are tracked in-process.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
