"""Project + folder store backed by Supabase Postgres.

Metadata (projects, clips, folders) lives in Supabase. Media stays on this machine in
data/projects/<id>/ (source video, transcript.json, signals.json, rendered clips),
because ffmpeg needs local files and videos are far larger than free-tier storage.
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

from . import config, supa

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
    (project_dir(pid) / name).write_text(json.dumps(data), encoding="utf-8")


def read_json(pid: str, name: str, default=None):
    f = project_dir(pid) / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


# --------------------------------------------------------------- conversion --

def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


_COLS = ("id", "owner", "name", "status", "stage", "progress", "message", "video", "source", "source_url",
         "platform", "import_meta", "analysis_note", "has_transcript", "clips")


def _to_row(p: dict) -> dict:
    row = {k: p.get(k) for k in _COLS}
    row.update(folder_id=p.get("folder") or None, created_at=_iso(p["created"]),
               source_url=p.get("source_url") or "", platform=p.get("platform") or "upload",
               clips=p.get("clips") or [], message=p.get("message") or "", stage=p.get("stage") or "",
               analysis_note=p.get("analysis_note") or "", has_transcript=bool(p.get("has_transcript")))
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
    project_dir(pid).mkdir(parents=True)
    (project_dir(pid) / "clips").mkdir()
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
