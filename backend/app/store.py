"""Project + folder store backed by Supabase Postgres.

Metadata (projects, clips, folders) lives in Supabase. Media (source video, thumbnails,
transcript.json, signals.json, rendered clips) lives in an S3-compatible bucket when S3_BUCKET is set,
with data/projects/<id>/ as scratch space for ffmpeg; otherwise it stays in data/projects/<id>/.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config, objstore, supa

_locks: dict[str, threading.RLock] = {}
_global = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _global:
        return _locks.setdefault(pid, threading.RLock())


# ------------------------------------------------------------- file helpers --

def atomic_write(f: Path, text: str) -> None:
    """Write via temp file + rename. Retries because on Windows a concurrent reader
    (or antivirus/indexer) holding the target open makes os.replace fail briefly."""
    tmp = f.with_name(f"{f.stem}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(25):
        try:
            tmp.replace(f)
            return
        except PermissionError:
            if attempt == 24:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.02 * (attempt + 1))


def _read_text(f: Path) -> str:
    for attempt in range(25):
        try:
            return f.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == 24:
                raise
            time.sleep(0.02 * (attempt + 1))
    return ""


def project_dir(pid: str) -> Path:
    if not pid.isalnum():
        raise ValueError("bad project id")
    return config.PROJECTS_DIR / pid


def write_json(pid: str, name: str, data) -> None:
    if objstore.enabled():
        objstore.put_json(pid, name, data)
        return
    project_dir(pid).mkdir(parents=True, exist_ok=True)
    (project_dir(pid) / name).write_text(json.dumps(data), encoding="utf-8")


def read_json(pid: str, name: str, default=None):
    if objstore.enabled():
        data = objstore.get_json(pid, name)
        if data is not None:
            return data
    f = project_dir(pid) / name          # local copy (no bucket, or a project from before the bucket)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


# ------------------------------------------------------ media + scratch space --
#
# Without a bucket, data/projects/<id>/ is the permanent home of a project's media.
# With a bucket (S3_BUCKET), the bucket is; data/projects/<id>/ is scratch space that a job fills
# on demand (local()) while it holds the workspace, and that is emptied when the last job using the
# project lets go. Anything worth keeping is uploaded (persist()) as soon as it is produced.

# Never uploaded: job intermediates and partial downloads.
_SCRATCH_SUFFIXES = {".wav", ".ass", ".part", ".tmp", ".ytdl", ".imported"}
_users: dict[str, int] = {}
_users_lock = threading.Lock()


def acquire(pid: str) -> Path:
    """Mark the project's scratch dir as in use (pair with release())."""
    with _users_lock:
        _users[pid] = _users.get(pid, 0) + 1
    d = project_dir(pid)
    (d / "clips").mkdir(parents=True, exist_ok=True)
    return d


def busy() -> int:
    """How many jobs currently hold a project's scratch dir (imports, analysis, renders, posts)."""
    with _users_lock:
        return sum(_users.values())


def release(pid: str) -> None:
    with _users_lock:
        n = _users.get(pid, 1) - 1
        if n > 0:
            _users[pid] = n
            return
        _users.pop(pid, None)
    if objstore.enabled():
        try:
            _clear_scratch(pid)
        except Exception:  # noqa: BLE001  (never fail a job over cleanup; files get retried next time)
            import logging
            logging.getLogger("clipforge").exception("could not clear scratch space of %s", pid)


class workspace:
    """`with store.workspace(pid) as d:` holds the project's scratch dir `d` for the duration."""

    def __init__(self, pid: str):
        self.pid = pid

    def __enter__(self) -> Path:
        return acquire(self.pid)

    def __exit__(self, *exc) -> None:
        release(self.pid)


def _clear_scratch(pid: str) -> None:
    """Upload anything not yet in the bucket (e.g. media from before the bucket was set up), then
    delete the local copy. Re-checks the user count so a job that just started keeps its files."""
    d = project_dir(pid)
    if not d.is_dir():
        return
    if supa.select_one("projects", {"id": f"eq.{pid}", "select": "id"}) is None:
        # Deleted while a job was running: drop the files instead of uploading them again.
        objstore.delete_project(pid)
        with _users_lock:
            if not _users.get(pid):
                shutil.rmtree(d, ignore_errors=True)
        return
    stored = objstore.list_rel(pid)
    for f in d.rglob("*"):
        rel = f.relative_to(d).as_posix()
        if f.is_file() and f.suffix.lower() not in _SCRATCH_SUFFIXES and f.name != "project.json" \
                and rel not in stored:
            objstore.upload(pid, rel, f)
    with _users_lock:
        if _users.get(pid):
            return
        shutil.rmtree(d, ignore_errors=True)


def persist(pid: str, rel: str) -> None:
    """Save a file a job just produced in the project's scratch dir to the bucket (no-op without one).
    The local copy stays until the workspace is released, so the job can keep using it."""
    if objstore.enabled():
        objstore.upload(pid, rel, project_dir(pid) / rel)


def local(pid: str, rel: str) -> Path:
    """Local path of a project file, downloading it from the bucket if needed.
    Call while holding the workspace. Raises FileNotFoundError if it exists nowhere."""
    f = project_dir(pid) / rel
    if f.is_file():
        return f
    if objstore.enabled():
        return objstore.download(pid, rel, f)
    raise FileNotFoundError(rel)


def media_input(pid: str, rel: str) -> "Path | str":
    """What to hand ffmpeg for reading a file: the local copy if there is one, otherwise a signed
    bucket URL (ffmpeg seeks over HTTP, so rendering a 30 s clip doesn't fetch a 2 GB source)."""
    f = project_dir(pid) / rel
    if f.is_file() or not objstore.enabled():
        return f
    return objstore.url(pid, rel, expires=6 * 3600)


def has(pid: str, rel: str) -> bool:
    if (project_dir(pid) / rel).is_file():
        return True
    return objstore.enabled() and objstore.exists(pid, rel)


def remove(pid: str, rel: str) -> None:
    (project_dir(pid) / rel).unlink(missing_ok=True)
    if objstore.enabled():
        objstore.delete(pid, rel)


# --------------------------------------------------------------- conversion --

def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


_COLS = ("id", "owner", "name", "status", "stage", "progress", "message", "video", "source", "source_url",
         "platform", "import_meta", "analysis_note", "has_transcript", "clips", "source_expired")


def _to_row(p: dict) -> dict:
    row = {k: p.get(k) for k in _COLS}
    row.update(folder_id=p.get("folder") or None, created_at=_iso(p["created"]),
               source_url=p.get("source_url") or "", platform=p.get("platform") or "upload",
               clips=p.get("clips") or [], message=p.get("message") or "", stage=p.get("stage") or "",
               analysis_note=p.get("analysis_note") or "", has_transcript=bool(p.get("has_transcript")),
               source_expired=bool(p.get("source_expired")))
    return row


def _from_row(r: dict) -> dict:
    p = {k: r.get(k) for k in _COLS}
    p.update(folder=r.get("folder_id"), created=_epoch(r["created_at"]))
    return p


# ----------------------------------------------------------------- projects --

def create(name: str, folder: Optional[str] = None, source_url: str = "", platform: str = "upload",
           owner: Optional[str] = None) -> dict:
    if not owner:
        raise ValueError("a project needs an owner")
    pid = uuid.uuid4().hex[:12]
    if not objstore.enabled():                 # with a bucket, jobs create scratch dirs on demand
        (project_dir(pid) / "clips").mkdir(parents=True)
    proj = {
        "id": pid, "name": name, "created": time.time(),
        "status": "uploaded", "stage": "", "progress": 0.0, "message": "",
        "video": None, "source": None, "clips": [], "analysis_note": "", "has_transcript": False,
        "folder": folder, "source_url": source_url, "platform": platform, "owner": owner, "import_meta": None,
    }
    supa.insert("projects", _to_row(proj))
    return proj


def load(pid: str) -> Optional[dict]:
    if not pid.isalnum():
        raise ValueError("bad project id")
    row = supa.select_one("projects", {"id": f"eq.{pid}", "select": "*"})
    return _from_row(row) if row else None


def save(proj: dict) -> None:
    with _lock(proj["id"]):
        supa.insert("projects", _to_row(proj), upsert=True, on_conflict="id")


def update(pid: str, fn) -> dict:
    """load -> mutate -> save, serialised per project inside this server process."""
    with _lock(pid):
        proj = load(pid)
        if proj is None:
            raise KeyError(pid)
        fn(proj)
        save(proj)
        return proj


def list_all(owner: str) -> list[dict]:
    rows = supa.select("projects", {"owner": f"eq.{owner}", "select": "*", "order": "created_at.desc"})
    return [_from_row(r) for r in rows]


def delete(pid: str) -> None:
    supa.delete("projects", {"id": f"eq.{pid}"})
    if objstore.enabled():
        objstore.delete_project(pid)
    shutil.rmtree(project_dir(pid), ignore_errors=True)


# ------------------------------------------------------------------ folders --

FOLDER_COLORS = ["#c6f432", "#5eead4", "#a78bfa", "#f472b6", "#fbbf24", "#60a5fa", "#fb7185"]


def _folder(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "color": r["color"], "owner": r["owner"], "created": _epoch(r["created_at"])}


def list_folders(owner: str) -> list[dict]:
    return [_folder(r) for r in supa.select("folders", {"owner": f"eq.{owner}", "select": "*", "order": "created_at.asc"})]


def create_folder(name: str, color: str = "", owner: Optional[str] = None) -> dict:
    if not owner:
        raise ValueError("a folder needs an owner")
    count = len(list_folders(owner))
    row = {"id": uuid.uuid4().hex[:10], "owner": owner, "name": name,
           "color": color or FOLDER_COLORS[count % len(FOLDER_COLORS)]}
    return _folder(supa.insert("folders", row)[0])


def update_folder(fid: str, **changes) -> Optional[dict]:
    patch = {k: v for k, v in changes.items() if v is not None and k in ("name", "color")}
    rows = supa.update("folders", {"id": f"eq.{fid}"}, patch) if patch else supa.select("folders", {"id": f"eq.{fid}"})
    return _folder(rows[0]) if rows else None


def delete_folder(fid: str) -> bool:
    """Remove a folder. Its projects are kept and become unsorted (FK: on delete set null)."""
    supa.delete("folders", {"id": f"eq.{fid}"})
    return True


# ------------------------------------------------- one-time import of old data --

def _marker() -> Path:
    return config.DATA_DIR / "imported_to_supabase.json"


def import_local_data(owner: str) -> int:
    """Copy projects/folders saved by the pre-Supabase version (JSON files) into Supabase,
    owned by `owner`. Runs once (a marker file records it). Returns the number of projects."""
    if _marker().exists():
        return 0
    folders = []
    ff = config.DATA_DIR / "folders.json"
    if ff.exists():
        try:
            folders = json.loads(_read_text(ff))
        except json.JSONDecodeError:
            folders = []
    folder_ids = set()
    for f in folders:
        supa.insert("folders", {"id": f["id"], "owner": owner, "name": f["name"][:40] or "Folder",
                                "color": f.get("color") or FOLDER_COLORS[0],
                                "created_at": _iso(f.get("created") or time.time())}, upsert=True, on_conflict="id")
        folder_ids.add(f["id"])
    count = 0
    for d in config.PROJECTS_DIR.iterdir() if config.PROJECTS_DIR.exists() else []:
        pf = d / "project.json"
        if not pf.exists():
            continue
        try:
            p = json.loads(_read_text(pf))
        except json.JSONDecodeError:
            continue
        p["owner"] = owner
        if p.get("folder") not in folder_ids:
            p["folder"] = None
        if p.get("status") in ("processing", "downloading"):   # whatever was running died with the old server
            p.update(status="error", message="Interrupted by an update. Run it again.")
        supa.insert("projects", _to_row(p), upsert=True, on_conflict="id")
        pf.rename(pf.with_suffix(".json.imported"))
        count += 1
    atomic_write(_marker(), json.dumps({"owner": owner, "at": time.time(), "projects": count}))
    return count
