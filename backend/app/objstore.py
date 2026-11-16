"""S3-compatible object storage (Cloudflare R2, AWS S3, Backblaze B2, MinIO...) for project media.

Objects are stored as <S3_PREFIX>/projects/<project id>/<relative path>, mirroring data/projects/.
Only used when S3_BUCKET is set; see store.py for how jobs combine it with local scratch space.
"""
from __future__ import annotations

import json
import mimetypes
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from . import config

_client_obj = None
_client_lock = threading.Lock()

# ffmpeg/browsers need these; Python's mimetypes table misses some on Windows/slim images.
_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
          ".webm": "video/webm", ".avi": "video/x-msvideo", ".jpg": "image/jpeg", ".json": "application/json"}


class StorageError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.S3_BUCKET)


def _client():
    global _client_obj
    with _client_lock:
        if _client_obj is None:
            import boto3
            from botocore.config import Config

            _client_obj = boto3.client(
                "s3",
                endpoint_url=config.S3_ENDPOINT or None,
                region_name=config.S3_REGION or None,
                aws_access_key_id=config.S3_ACCESS_KEY_ID or None,
                aws_secret_access_key=config.S3_SECRET_ACCESS_KEY or None,
                config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"},
                              # R2/MinIO/B2 endpoints want path-style URLs; AWS works with the default.
                              s3={"addressing_style": "path" if config.S3_ENDPOINT else "auto"}),
            )
        return _client_obj


def key(pid: str, rel: str) -> str:
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("bad path")
    base = f"projects/{pid}/{rel}"
    return f"{config.S3_PREFIX}/{base}" if config.S3_PREFIX else base


def content_type(name: str) -> str:
    ext = Path(name).suffix.lower()
    return _TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def _missing(exc: Exception) -> bool:
    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return code in ("404", "NoSuchKey", "NotFound")


# ------------------------------------------------------------------- files --

def upload(pid: str, rel: str, path: Path) -> None:
    """Upload a local file (multipart for big files, handled by boto3)."""
    _client().upload_file(str(path), config.S3_BUCKET, key(pid, rel),
                          ExtraArgs={"ContentType": content_type(path.name)})


def download(pid: str, rel: str, dest: Path) -> Path:
    """Download to `dest` via a temp file, so a half-finished download never looks complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex[:6]}.part")
    try:
        _client().download_file(config.S3_BUCKET, key(pid, rel), str(tmp))
        tmp.replace(dest)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if _missing(exc):
            raise FileNotFoundError(rel) from exc
        raise
    return dest


def size(pid: str, rel: str) -> Optional[int]:
    """Object size in bytes, or None if it doesn't exist."""
    try:
        return int(_client().head_object(Bucket=config.S3_BUCKET, Key=key(pid, rel))["ContentLength"])
    except Exception as exc:
        if _missing(exc):
            return None
        raise


def exists(pid: str, rel: str) -> bool:
    return size(pid, rel) is not None


def list_rel(pid: str) -> set[str]:
    """Relative paths of every object stored for a project."""
    base = key(pid, "")
    out: set[str] = set()
    for page in _client().get_paginator("list_objects_v2").paginate(Bucket=config.S3_BUCKET, Prefix=base):
        out.update(o["Key"][len(base):] for o in page.get("Contents", []))
    return out


def delete(pid: str, rel: str) -> None:
    _client().delete_object(Bucket=config.S3_BUCKET, Key=key(pid, rel))


def delete_project(pid: str) -> None:
    keys = [key(pid, r) for r in list_rel(pid)]
    for i in range(0, len(keys), 1000):
        _client().delete_objects(Bucket=config.S3_BUCKET,
                                 Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


# -------------------------------------------------------------------- json --

def put_json(pid: str, rel: str, data: Any) -> None:
    _client().put_object(Bucket=config.S3_BUCKET, Key=key(pid, rel), Body=json.dumps(data).encode("utf-8"),
                         ContentType="application/json")


def get_json(pid: str, rel: str, default: Any = None) -> Any:
    try:
        body = _client().get_object(Bucket=config.S3_BUCKET, Key=key(pid, rel))["Body"].read()
    except Exception as exc:
        if _missing(exc):
            return default
        raise
    return json.loads(body)


# ------------------------------------------------------------- signed URLs --

def url(pid: str, rel: str, download_name: str = "", expires: int = 3600) -> str:
    """Short-lived GET link. The browser (or ffmpeg) fetches the object straight from the bucket."""
    params = {"Bucket": config.S3_BUCKET, "Key": key(pid, rel)}
    if download_name:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
    return _client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires)


def upload_url(pid: str, rel: str, ctype: str, expires: int = 3600) -> str:
    """Short-lived PUT link so the browser uploads straight to the bucket. The browser must send
    exactly this Content-Type header. The bucket needs a CORS rule allowing PUT from the site."""
    return _client().generate_presigned_url(
        "put_object", Params={"Bucket": config.S3_BUCKET, "Key": key(pid, rel), "ContentType": ctype},
        ExpiresIn=expires)
