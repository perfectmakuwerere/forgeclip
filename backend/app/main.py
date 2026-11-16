"""ClipForge API: upload -> transcribe -> find viral moments -> reframe + caption -> download."""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from starlette.concurrency import run_in_threadpool

from . import analytics, auth, billing, config, objstore, publish, social, store, supa
from .llm import registry
from .llm.base import LLMError, LLMSettings
from .pipeline import importer, media, moments, signals, transcribe
from .pipeline.render import ASPECTS, DEFAULT_RENDER, render_clip
from .pipeline.captions import STYLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clipforge")

app = FastAPI(title="ClipForge", version="0.3.0")
app.add_middleware(auth.AuthMiddleware)
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


# ------------------------------------------------------------------ models ---

class LLMIn(BaseModel):
    provider: str = "none"          # anthropic | openai_compat | none
    model: str = ""
    api_key: str = ""               # used for this request only, never stored
    base_url: str = ""

    def to_settings(self) -> Optional[LLMSettings]:
        if self.provider in ("", "none"):
            return None
        return LLMSettings(self.provider, self.model, self.api_key, self.base_url, "user")


class AnalyzeIn(BaseModel):
    min_len: float = Field(15, ge=5, le=180)
    max_len: float = Field(60, ge=8, le=300)
    count: int = Field(8, ge=1, le=30)
    context: str = Field("", max_length=1000)
    auto_render: bool = True
    render: dict = Field(default_factory=dict)
    llm: LLMIn = Field(default_factory=LLMIn)


class ClipIn(BaseModel):
    start: float
    end: float
    title: str = "Manual clip"


class CaptionWord(BaseModel):
    start: float
    end: float
    word: str = Field(..., min_length=1, max_length=60)


class CaptionEdit(BaseModel):
    """User-edited caption words for [start, end] (source-video seconds). Replaces the transcript there."""
    start: float
    end: float
    words: list[CaptionWord] = Field(default_factory=list, max_length=4000)


class ClipPatch(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title: Optional[str] = Field(None, max_length=120)
    hook: Optional[str] = Field(None, max_length=120)
    hashtags: Optional[list[str]] = None
    caption_edit: Optional[CaptionEdit] = None
    clear_caption_edit: bool = False


class AutorunIn(BaseModel):
    """What to do once the source video is ready ("Get clips in 1 click")."""
    mode: str = Field("analyze", pattern="^(analyze|whole|none)$")   # whole = captions/resize the full video
    analyze: AnalyzeIn = Field(default_factory=AnalyzeIn)
    render: dict = Field(default_factory=dict)


class ImportIn(BaseModel):
    url: str = Field(..., min_length=4, max_length=2000)
    folder: Optional[str] = None
    after: AutorunIn = Field(default_factory=lambda: AutorunIn(mode="none"))


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    folder: Optional[str] = None      # "" moves the project out of its folder


class CheckoutIn(BaseModel):
    plan: str = Field(..., pattern="^(pro|business)$")
    interval: str = Field("month", pattern="^(month|year)$")


class SyncIn(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=200, pattern="^cs_[A-Za-z0-9_]+$")


class SessionIn(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=8000)


class PublishIn(BaseModel):
    project_id: str
    clip_id: str
    targets: list[str] = Field(..., min_length=1, max_length=4)
    caption: str = Field("", max_length=5000)
    title: str = Field("", max_length=100)           # YouTube title
    options: dict = Field(default_factory=dict)      # {"youtube": {"privacy": "public"}, "tiktok": {...}}


class FolderIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    color: str = Field("", max_length=9)


class FolderPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=40)
    color: Optional[str] = Field(None, max_length=9)


# ----------------------------------------------------------------- helpers ---

def _get(pid: str) -> dict:
    try:
        proj = store.load(pid)
    except ValueError:
        proj = None
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


def _own(pid: str) -> dict:
    """Project lookup for request handlers: 404 unless it belongs to the signed-in user."""
    proj = _get(pid)
    if proj.get("owner") != auth.uid():
        raise HTTPException(404, "Project not found")
    return proj


_last_progress: dict[str, float] = {}


def _set_status(pid: str, **kw) -> None:
    # Progress ticks arrive many times a second during downloads/transcription. Each write is a
    # database round trip, so pure progress/stage updates are throttled to ~2 per second.
    if set(kw) <= {"progress", "stage"}:
        now = time.time()
        if now - _last_progress.get(pid, 0) < 0.5:
            return
        _last_progress[pid] = now
    store.update(pid, lambda p: p.update(kw))


def _words(pid: str) -> list[dict]:
    return transcribe.all_words(store.read_json(pid, "transcript.json", {"segments": []}))


def _clip_words(pid: str, clip: dict) -> list[dict]:
    """Transcript words, with the user's caption edits (if any) replacing their time range."""
    words = _words(pid)
    edit = clip.get("caption_edit")
    if not edit:
        return words
    s, e = float(edit["start"]), float(edit["end"])
    kept = [w for w in words if w["end"] <= s or w["start"] >= e]
    return sorted(kept + list(edit.get("words") or []), key=lambda w: w["start"])


def _render_one(pid: str, clip_id: str, settings: dict) -> None:
    proj = _get(pid)
    clip = next((c for c in proj["clips"] if c["id"] == clip_id), None)
    if not clip:
        return

    def mark(state, **extra):
        def fn(p):
            for c in p["clips"]:
                if c["id"] == clip_id:
                    c["render_state"] = state
                    c.update(extra)
        store.update(pid, fn)

    mark("rendering", render_error="")
    try:
        with store.workspace(pid) as pdir:
            result = render_clip(store.media_input(pid, proj["source"]), pdir / "clips",
                                 clip, _clip_words(pid, clip), settings, proj["video"]["has_audio"])
            store.persist(pid, f"clips/{result['file']}")
            store.persist(pid, f"clips/{result['thumb']}")
        mark("done", render=result)
    except Exception as exc:  # noqa: BLE001
        log.exception("render failed")
        mark("error", render_error=str(exc)[:500])


def _analyze(pid: str, body: AnalyzeIn) -> None:
    # The whole job holds the scratch dir, so the source is fetched from the bucket once and reused
    # by every clip render below.
    try:
        with store.workspace(pid) as pdir:
            _analyze_in(pid, pdir, body)
    except Exception as exc:  # noqa: BLE001
        log.exception("analysis failed")
        _set_status(pid, status="error", stage="Failed", message=str(exc)[:600])


def _analyze_in(pid: str, pdir: Path, body: AnalyzeIn) -> None:
    proj = _get(pid)
    if not (pdir / proj["source"]).is_file():
        _set_status(pid, status="processing", stage="Preparing video", progress=0.01)
    video = store.local(pid, proj["source"])
    duration = proj["video"]["duration"]
    wav = None
    notes = []

    if proj["video"]["has_audio"]:
        _set_status(pid, status="processing", stage="Extracting audio", progress=0.03)
        wav = media.extract_audio(video, pdir / "audio.wav")

    transcript = {"language": None, "segments": []}
    if wav:
        _set_status(pid, stage="Transcribing speech (local Whisper)", progress=0.08)
        try:
            transcript = transcribe.transcribe(
                wav, duration, lambda f: _set_status(pid, progress=round(0.08 + 0.5 * f, 3)),
                on_wait=lambda: _set_status(pid, stage="Waiting in line"),
                on_start=lambda: _set_status(pid, stage="Transcribing speech (local Whisper)", progress=0.08))
        except Exception as exc:  # noqa: BLE001
            log.warning("transcription failed: %s", exc)
            notes.append(f"transcription unavailable ({str(exc)[:120]})")
    store.write_json(pid, "transcript.json", transcript)
    _set_status(pid, has_transcript=bool(transcript["segments"]))

    _set_status(pid, stage="Scanning for action (audio spikes, scene cuts)", progress=0.6)
    sig = signals.build_signals(wav, video, duration)
    store.write_json(pid, "signals.json", sig)

    provider = registry.resolve(body.llm.to_settings())
    _set_status(pid, stage=f"Finding viral moments{' with ' + provider.describe() if provider else ''}",
                progress=0.7)
    clips, note = moments.find_moments(transcript, sig, duration, provider,
                                       body.min_len, max(body.max_len, body.min_len + 3),
                                       body.count, body.context)
    notes.insert(0, note)
    for c in clips:
        c["render_state"] = "queued" if body.auto_render else "idle"
    store.update(pid, lambda p: p.update(clips=clips, analysis_note="; ".join(notes)))

    if body.auto_render:
        for i, c in enumerate(clips):
            _set_status(pid, stage=f"Rendering clip {i + 1}/{len(clips)}",
                        progress=round(0.75 + 0.25 * i / max(len(clips), 1), 3))
            _render_one(pid, c["id"], body.render)
    _set_status(pid, status="ready", stage="Done", progress=1.0, message="")


def _quota() -> None:
    try:
        billing.check_quota(auth.uid())
    except billing.BillingError as exc:
        raise HTTPException(exc.status, str(exc))


def _check_folder(fid: Optional[str]) -> Optional[str]:
    if not fid:
        return None
    if not any(f["id"] == fid for f in store.list_folders(auth.uid())):
        raise HTTPException(400, "Folder not found")
    return fid


def _render_settings(raw: dict) -> dict:
    return {k: v for k, v in (raw or {}).items() if k in DEFAULT_RENDER}


def _autorun(pid: str, after: AutorunIn) -> None:
    """Runs in a worker thread once the source file is in place."""
    with store.workspace(pid):
        _autorun_in(pid, after)


def _autorun_in(pid: str, after: AutorunIn) -> None:
    try:
        if after.mode == "analyze":
            _set_status(pid, status="processing", stage="Starting", progress=0.0, message="")
            _analyze(pid, after.analyze)
        elif after.mode == "whole":
            proj = _get(pid)
            clip = moments.manual_clip(0, proj["video"]["duration"], proj["name"])
            clip["render_state"] = "queued"
            store.update(pid, lambda p: p["clips"].insert(0, clip))
            _set_status(pid, status="processing", stage="Rendering full video", progress=0.5, message="")
            _render_one(pid, clip["id"], _render_settings(after.render))
            _set_status(pid, status="ready", stage="Done", progress=1.0)
    except Exception as exc:  # noqa: BLE001
        log.exception("autorun failed")
        _set_status(pid, status="error", stage="Failed", message=str(exc)[:600])


def _finish_source(pid: str, src: "Path | str", name: str) -> None:
    """Probe + thumbnail a new source video, then save it. `src` is a file in the project's scratch dir
    (uploaded to the bucket here, if there is one) or a signed URL of a source already in the bucket."""
    meta = media.probe(src)
    with store.workspace(pid) as pdir:
        media.thumbnail(src, pdir / "thumb.jpg", min(5, meta["duration"] / 3))
        store.persist(pid, "thumb.jpg")
        if isinstance(src, Path):
            store.persist(pid, name)
    store.update(pid, lambda p: p.update(video=meta, source=name))


def _import(pid: str, url: str, after: AutorunIn) -> None:
    try:
        # Held for the whole job so the downloaded file is reused by the analysis that follows.
        with store.workspace(pid) as pdir:
            def on_meta(m):
                store.update(pid, lambda p: p.update(name=m["title"] or p["name"], import_meta=m))

            def on_progress(frac, stage):
                _set_status(pid, progress=round(frac, 3), stage=stage)

            path = importer.download(url, pdir, on_meta, on_progress)
            for leftover in pdir.glob("source.*"):
                if leftover != path and leftover.is_file():
                    leftover.unlink(missing_ok=True)
            _set_status(pid, stage="Saving video" if objstore.enabled() else "Reading video", progress=1.0)
            _finish_source(pid, path, path.name)
            _set_status(pid, status="uploaded", stage="", progress=0.0, message="")
            _autorun(pid, after)
    except (importer.ImportError_, media.MediaError) as exc:
        _set_status(pid, status="error", stage="Import failed", message=str(exc)[:600])
    except Exception as exc:  # noqa: BLE001
        log.exception("import failed")
        _set_status(pid, status="error", stage="Import failed", message=str(exc)[:600])


# ------------------------------------------------------------------ routes ---

# -------------------------------------------------------------------- auth ---

@app.post("/api/auth/session")
def auth_session(body: SessionIn, request: Request):
    """The browser signed in with Supabase; verify its token and keep it in an HttpOnly cookie."""
    user = auth.user_for_token(body.access_token)
    if not user:
        raise HTTPException(401, "Your session expired. Please sign in again.")
    auth.import_old_data(user["id"])
    resp = JSONResponse({"user": user})
    auth.set_cookie(resp, body.access_token, secure=request.url.scheme == "https")
    return resp


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get(auth.COOKIE, "")
    if token:
        auth.forget(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def me():
    u = auth.CURRENT.get()
    return {"user": u}


@app.get("/api/health")
def health():
    """Readiness + 'is a job running?' probe. On Cloudflare Containers the Worker uses `busy` to keep
    the container awake until background jobs (imports, analysis, renders, posting) finish."""
    return {"ok": True, "busy": store.busy()}


@app.get("/api/info")
def info():
    return {**registry.public_info(), "aspects": list(ASPECTS), "caption_styles": list(STYLES),
            "render_defaults": DEFAULT_RENDER, "whisper_model": config.WHISPER_MODEL,
            "max_upload_mb": _direct_limit_mb() if objstore.enabled() else config.MAX_UPLOAD_MB,
            "direct_upload": objstore.enabled(),"max_import_minutes": config.MAX_IMPORT_MINUTES,
            "publish_limits": publish.LIMITS,
            "supabase_url": config.SUPABASE_URL, "supabase_key": config.SUPABASE_PUBLISHABLE_KEY,
            "server_ready": supa.configured(), "billing_ready": billing.ready(),
            "plans": [{"id": k, **v} for k, v in billing.PLANS.items()]}


@app.post("/api/llm/test")
def llm_test(body: LLMIn):
    provider = registry.resolve(body.to_settings())
    if not provider:
        raise HTTPException(400, "No usable provider (missing key, URL or model).")
    try:
        reply = provider.complete("Reply with the single word: ready", "Are you there?", max_tokens=10)
    except LLMError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "provider": provider.describe(), "reply": reply.strip()[:50]}


@app.get("/api/projects")
def list_projects():
    return store.list_all(auth.uid())


@app.post("/api/projects")
async def upload(file: UploadFile = File(...), folder: Optional[str] = Form(None)):
    _quota()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}. Use {', '.join(sorted(VIDEO_EXT))}.")
    proj = store.create(Path(file.filename).stem[:80], folder=_check_folder(folder), owner=auth.uid())
    pid = proj["id"]
    dst = store.acquire(pid) / f"source{ext}"
    try:
        size, limit = 0, config.MAX_UPLOAD_MB * 1024 * 1024
        with dst.open("wb") as out:
            while chunk := await file.read(1024 * 1024 * 8):
                size += len(chunk)
                if size > limit:
                    out.close()
                    await run_in_threadpool(store.delete, pid)
                    raise HTTPException(413, f"File larger than {config.MAX_UPLOAD_MB} MB.")
                out.write(chunk)
        try:
            # ffprobe/ffmpeg and the bucket upload block, so keep them off the event loop
            await run_in_threadpool(_finish_source, pid, dst, dst.name)
        except media.MediaError as exc:
            await run_in_threadpool(store.delete, pid)
            raise HTTPException(400, f"Could not read video: {exc}")
    finally:
        await run_in_threadpool(store.release, pid)
    return _own(pid)


class UploadUrlIn(BaseModel):
    filename: str
    size: int = Field(ge=1)
    folder: Optional[str] = None


# S3 and R2 accept a single PUT of up to 5 GiB.
_PUT_LIMIT_MB = 5 * 1024 - 16


def _direct_limit_mb() -> int:
    return min(config.MAX_UPLOAD_MB, _PUT_LIMIT_MB)


@app.post("/api/projects/upload-url")
def upload_url(body: UploadUrlIn):
    """Step 1 of a direct upload: create the project and hand the browser a signed PUT link, so the
    file goes straight to the bucket (not through this server or Cloudflare's 100 MB request cap)."""
    if not objstore.enabled():
        raise HTTPException(400, "Direct upload isn't set up on this server.")
    _quota()
    ext = Path(body.filename).suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}. Use {', '.join(sorted(VIDEO_EXT))}.")
    if body.size > _direct_limit_mb() * 1024 * 1024:
        raise HTTPException(413, f"File larger than {_direct_limit_mb()} MB.")
    proj = store.create(Path(body.filename).stem[:80] or "Video", folder=_check_folder(body.folder), owner=auth.uid())
    name = f"source{ext}"
    ctype = objstore.content_type(name)
    _set_status(proj["id"], status="downloading", stage="Uploading", progress=0.0)
    return {"project": _own(proj["id"]), "url": objstore.upload_url(proj["id"], name, ctype),
            "content_type": ctype}


@app.post("/api/projects/{pid}/upload-done")
def upload_done(pid: str):
    """Step 2 of a direct upload: the browser finished the PUT. Check and probe the file in the bucket
    (ffprobe reads it over HTTP, so the video isn't downloaded here)."""
    proj = _own(pid)
    if proj.get("video"):
        return proj
    if not objstore.enabled():
        raise HTTPException(400, "Direct upload isn't set up on this server.")
    found = next(((n, s) for n in (f"source{e}" for e in sorted(VIDEO_EXT))
                  if (s := objstore.size(pid, n)) is not None), None)
    if not found:
        raise HTTPException(400, "The upload didn't arrive. Please try again.")
    name, size = found
    if size > _direct_limit_mb() * 1024 * 1024:
        store.delete(pid)
        raise HTTPException(413, f"File larger than {_direct_limit_mb()} MB.")
    try:
        _finish_source(pid, objstore.url(pid, name), name)
    except media.MediaError as exc:
        store.delete(pid)
        raise HTTPException(400, f"Could not read video: {exc}")
    _set_status(pid, status="uploaded", stage="", progress=0.0, message="")
    return _own(pid)


@app.post("/api/projects/import")
def import_link(body: ImportIn):
    _quota()
    try:
        url = importer.validate_url(body.url)
    except importer.ImportError_ as exc:
        raise HTTPException(400, str(exc))
    platform = importer.platform_of(url)
    label = {"youtube": "YouTube", "tiktok": "TikTok", "x": "X"}.get(platform, platform.title())
    proj = store.create(f"{label} video" if platform != "web" else "Imported video",
                        folder=_check_folder(body.folder), source_url=url, platform=platform, owner=auth.uid())
    _set_status(proj["id"], status="downloading", stage="Fetching video info", progress=0.0)
    threading.Thread(target=_import, args=(proj["id"], url, body.after), daemon=True).start()
    return _own(proj["id"])


@app.post("/api/projects/{pid}/retry-import")
def retry_import(pid: str, body: AutorunIn):
    proj = _own(pid)
    if not proj.get("source_url") or proj.get("video"):
        raise HTTPException(400, "Nothing to retry.")
    if proj["status"] == "downloading":
        raise HTTPException(409, "Already downloading.")
    _set_status(pid, status="downloading", stage="Fetching video info", progress=0.0, message="")
    threading.Thread(target=_import, args=(pid, proj["source_url"], body), daemon=True).start()
    return {"ok": True}


@app.post("/api/projects/{pid}/autorun")
def autorun(pid: str, body: AutorunIn):
    proj = _own(pid)
    if not proj.get("video"):
        raise HTTPException(409, "The video isn't ready yet.")
    if proj["status"] in ("processing", "downloading"):
        raise HTTPException(409, "Already processing.")
    if body.mode != "none":
        _set_status(pid, status="processing", stage="Starting", progress=0.0, message="")
        threading.Thread(target=_autorun, args=(pid, body), daemon=True).start()
    return {"ok": True}


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch):
    _own(pid)
    changes = {}
    if body.name is not None:
        changes["name"] = body.name.strip()
    if body.folder is not None:
        changes["folder"] = _check_folder(body.folder)
    return store.update(pid, lambda p: p.update(changes))


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _own(pid)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    _own(pid)
    store.delete(pid)
    return {"ok": True}


@app.get("/api/projects/{pid}/transcript")
def get_transcript(pid: str):
    _own(pid)
    return store.read_json(pid, "transcript.json", {"segments": []})


@app.get("/api/projects/{pid}/signals")
def get_signals(pid: str, bins: int = 300):
    """Downsampled excitement curve for the timeline heat bar."""
    _own(pid)
    sig = store.read_json(pid, "signals.json")
    if not sig:
        return {"values": []}
    exc = sig["excitement"]
    step = max(1, len(exc) // bins)
    vals = [max(exc[i:i + step]) for i in range(0, len(exc), step)]
    return {"values": vals, "scene_cuts": sig["scene_cuts"]}


@app.post("/api/projects/{pid}/analyze")
def analyze(pid: str, body: AnalyzeIn):
    proj = _own(pid)
    if not proj.get("video"):
        raise HTTPException(409, "The video isn't ready yet.")
    if proj.get("source_expired"):
        raise HTTPException(410, "The original video was removed to save space. Import it again to make new clips.")
    if proj["status"] in ("processing", "downloading"):
        raise HTTPException(409, "Already processing.")
    _set_status(pid, status="processing", stage="Starting", progress=0.0, message="")
    threading.Thread(target=_analyze, args=(pid, body), daemon=True).start()
    return {"ok": True}


@app.post("/api/projects/{pid}/clips")
def add_clip(pid: str, body: ClipIn):
    proj = _own(pid)
    dur = proj["video"]["duration"]
    start, end = max(0, body.start), min(dur, body.end)
    if end - start < 1:
        raise HTTPException(400, "Clip must be at least 1 second.")
    clip = moments.manual_clip(start, end, body.title)
    clip["render_state"] = "idle"
    store.update(pid, lambda p: p["clips"].insert(0, clip))
    return clip


@app.patch("/api/projects/{pid}/clips/{cid}")
def patch_clip(pid: str, cid: str, body: ClipPatch):
    proj = _own(pid)
    dur = proj["video"]["duration"]

    def fn(p):
        for c in p["clips"]:
            if c["id"] == cid:
                for k, v in body.model_dump(exclude_none=True, exclude={"clear_caption_edit"}).items():
                    c[k] = v
                if body.clear_caption_edit:
                    c.pop("caption_edit", None)
                c["start"] = round(max(0.0, min(c["start"], dur - 1)), 2)
                c["end"] = round(max(c["start"] + 1, min(c["end"], dur)), 2)
                return
        raise HTTPException(404, "Clip not found")
    return store.update(pid, fn)


@app.delete("/api/projects/{pid}/clips/{cid}")
def delete_clip(pid: str, cid: str):
    _own(pid)
    return store.update(pid, lambda p: p.update(clips=[c for c in p["clips"] if c["id"] != cid]))


class RenderAllIn(BaseModel):
    settings: dict = Field(default_factory=dict)


def _render_all(pid: str, settings: dict) -> None:
    proj = _get(pid)
    ids = [c["id"] for c in proj["clips"]]
    with store.workspace(pid):            # one hold for the batch: counts as busy between clips too
        for i, cid in enumerate(ids):
            _set_status(pid, status="processing", stage=f"Rendering clip {i + 1}/{len(ids)}",
                        progress=round(i / max(len(ids), 1), 3))
            _render_one(pid, cid, settings)
    _set_status(pid, status="ready", stage="Done", progress=1.0)


@app.post("/api/projects/{pid}/render-all")
def render_all(pid: str, body: RenderAllIn):
    """Re-render every clip with one look (one at a time, so the machine isn't overloaded)."""
    proj = _own(pid)
    if proj.get("source_expired"):
        raise HTTPException(410, "The original video was removed to save space, so clips can't be re-rendered.")
    if proj["status"] in ("processing", "downloading"):
        raise HTTPException(409, "This video is still being processed.")
    if not proj["clips"]:
        raise HTTPException(400, "No clips to render yet.")
    clean = _render_settings(body.settings)

    def queue(p):
        for c in p["clips"]:
            c["render_state"] = "queued"
    store.update(pid, queue)
    _set_status(pid, status="processing", stage=f"Rendering clip 1/{len(proj['clips'])}", progress=0.0, message="")
    threading.Thread(target=_render_all, args=(pid, clean), daemon=True).start()
    return {"ok": True}


@app.get("/api/projects/{pid}/download-all")
def download_all(pid: str):
    """All rendered clips of a project as one .zip."""
    import tempfile
    import zipfile
    from starlette.background import BackgroundTask

    proj = _own(pid)
    done = [c for c in proj["clips"] if c.get("render_state") == "done" and c.get("render")]
    if not done:
        raise HTTPException(404, "No rendered clips to download yet.")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    used: set[str] = set()
    with store.workspace(pid), \
            zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_STORED) as z:   # mp4 is already compressed
        for c in done:
            try:
                src = store.local(pid, f"clips/{c['render']['file']}")
            except FileNotFoundError:
                continue
            base = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in c.get("title") or "")
            base = "-".join(base.lower().split())[:50] or "clip"
            name = f"{len(used) + 1:02d}-{base}.mp4"
            while name in used:
                name = name.replace(".mp4", "-x.mp4")
            used.add(name)
            z.write(src, name)
    if not used:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(404, "No rendered clips to download yet.")
    safe = "".join(ch for ch in proj["name"] if ch.isalnum() or ch in "-_ ")[:50].strip().replace(" ", "-") or "clips"
    return FileResponse(tmp.name, filename=f"{safe}-shorts.zip", media_type="application/zip",
                        background=BackgroundTask(lambda: Path(tmp.name).unlink(missing_ok=True)))


@app.post("/api/projects/{pid}/clips/{cid}/render")
def render(pid: str, cid: str, settings: dict):
    proj = _own(pid)
    if not any(c["id"] == cid for c in proj["clips"]):
        raise HTTPException(404, "Clip not found")
    if proj.get("source_expired"):
        raise HTTPException(410, "The original video was removed to save space, so this clip can't be re-rendered.")
    clean = _render_settings(settings)
    threading.Thread(target=_render_one, args=(pid, cid, clean), daemon=True).start()
    return {"ok": True}


# ----------------------------------------------------------------- folders ---

@app.get("/api/folders")
def list_folders():
    return store.list_folders(auth.uid())


@app.post("/api/folders")
def create_folder(body: FolderIn):
    return store.create_folder(body.name.strip(), body.color, owner=auth.uid())


@app.patch("/api/folders/{fid}")
def patch_folder(fid: str, body: FolderPatch):
    _check_folder(fid)
    f = store.update_folder(fid, name=body.name.strip() if body.name else None, color=body.color)
    if not f:
        raise HTTPException(404, "Folder not found")
    return f


@app.delete("/api/folders/{fid}")
def delete_folder(fid: str):
    _check_folder(fid)
    if not store.delete_folder(fid):
        raise HTTPException(404, "Folder not found")
    return {"ok": True}


# --------------------------------------------------------------- analytics ---

@app.get("/api/analytics")
def get_analytics(days: int = 30):
    threading.Thread(target=auth.run_as, args=(auth.uid(), social.refresh_stale), daemon=True).start()
    return {**analytics.build(max(7, min(days, 90)), auth.uid()), "social": social.public_list()}


# ------------------------------------------------------------------ social ---

@app.get("/api/social")
def social_list():
    return social.public_list()


@app.get("/api/social/{platform}/connect")
def social_connect(platform: str):
    try:
        return RedirectResponse(social.authorize_url(platform))
    except social.SocialError as exc:
        return HTMLResponse(social.callback_page(False, str(exc)), status_code=400)


@app.get("/api/social/{platform}/callback")
def social_callback(platform: str, code: str = "", state: str = "", error: str = "",
                    error_description: str = ""):
    if error or not code:
        return HTMLResponse(social.callback_page(False, error_description or error or "Sign-in was cancelled."))
    try:
        profile = social.complete(platform, code, state)
    except Exception as exc:  # noqa: BLE001  (network + provider errors all end up in the popup)
        log.warning("social connect %s failed: %s", platform, exc)
        return HTMLResponse(social.callback_page(False, str(exc)[:300]))
    who = profile.get("handle") or profile.get("name") or "your account"
    return HTMLResponse(social.callback_page(True, f"Connected {who}"))


@app.post("/api/social/{platform}/refresh")
def social_refresh(platform: str):
    try:
        social.refresh(platform)
    except social.SocialError as exc:
        raise HTTPException(400, str(exc))
    return next(p for p in social.public_list() if p["id"] == platform)


@app.delete("/api/social/{platform}")
def social_disconnect(platform: str):
    if platform not in social.PLATFORMS:
        raise HTTPException(404, "Unknown network")
    social.disconnect(platform)
    return {"ok": True}


# ----------------------------------------------------------------- billing ---

def _billing(fn, *args):
    try:
        return fn(*args)
    except billing.BillingError as exc:
        raise HTTPException(exc.status, str(exc))


@app.get("/api/billing")
def billing_summary():
    return billing.summary(auth.uid())


@app.post("/api/billing/checkout")
def billing_checkout(body: CheckoutIn):
    user = auth.CURRENT.get()
    return {"url": _billing(billing.checkout, user["id"], user.get("email", ""), body.plan, body.interval, config.PUBLIC_URL)}


@app.post("/api/billing/portal")
def billing_portal():
    return {"url": _billing(billing.portal, auth.uid(), config.PUBLIC_URL)}


@app.post("/api/billing/sync")
def billing_sync(body: SyncIn):
    _billing(billing.sync_checkout, auth.uid(), body.session_id)
    return billing.summary(auth.uid())


@app.post("/api/billing/refresh")
def billing_refresh():
    _billing(billing.refresh, auth.uid())
    return billing.summary(auth.uid())


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    payload = await request.body()
    try:
        billing.verify_signature(payload, request.headers.get("stripe-signature", ""))
        event = json.loads(payload)
        import anyio
        await anyio.to_thread.run_sync(billing.handle_event, event)
    except billing.BillingError as exc:
        log.warning("stripe webhook rejected: %s", exc)
        raise HTTPException(exc.status, str(exc))
    return {"received": True}


# ----------------------------------------------------------------- publish ---

@app.post("/api/publish")
def publish_clip(body: PublishIn):
    _own(body.project_id)
    try:
        return publish.start(body.project_id, body.clip_id, body.targets, body.caption.strip(),
                             body.title.strip(), body.options)
    except (publish.PublishError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/posts")
def list_posts(project_id: str = "", limit: int = 50):
    return publish.list_posts(project_id, max(1, min(limit, 200)))


@app.get("/api/posts/{post_id}")
def get_post(post_id: str):
    p = publish.get_post(post_id)
    if not p:
        raise HTTPException(404, "Post not found")
    return p


@app.get("/media/{pid}/{path:path}")
def media_file(pid: str, path: str, download: bool = False, name: str = ""):
    _own(pid)
    base = store.project_dir(pid).resolve()
    f = (base / path).resolve()
    if base not in f.parents or f.suffix in (".json", ".wav", ".ass", ".part"):
        raise HTTPException(404)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_.")[:80] or f.name
    if f.is_file():                       # no bucket, or the file is in a running job's scratch dir
        if download:
            return FileResponse(f, filename=safe, media_type="video/mp4")
        return FileResponse(f)
    if not objstore.enabled():
        raise HTTPException(404)
    # Send the browser straight to the bucket with a short-lived signed link: video bytes (and range
    # requests while seeking) never pass through this server. The redirect itself is cacheable for
    # a little less than the link's lifetime, so thumbnails don't re-hit the server on every view.
    link = objstore.url(pid, f.relative_to(base).as_posix(), download_name=safe if download else "")
    return RedirectResponse(link, status_code=302, headers={"Cache-Control": "private, max-age=3000"})


# ----------------------------------------------------------------- cleanup ---

def cleanup_sources_once() -> int:
    """Delete source videos older than SOURCE_RETENTION_DAYS. Returns how many projects were trimmed."""
    days = config.SOURCE_RETENTION_DAYS
    if days <= 0 or not supa.configured():
        return 0
    cutoff, trimmed = time.time() - days * 86400, 0
    for d in config.PROJECTS_DIR.iterdir():
        sources = [f for f in d.glob("source.*") if f.suffix.lower() in VIDEO_EXT] if d.is_dir() else []
        if not sources or max(f.stat().st_mtime for f in sources) > cutoff:
            continue
        try:
            proj = store.load(d.name)
        except Exception:  # noqa: BLE001
            continue
        if not proj or proj["status"] in ("processing", "downloading") or \
                any(c.get("render_state") in ("rendering", "queued") for c in proj["clips"]):
            continue
        for f in sources + [d / "audio.wav"]:
            f.unlink(missing_ok=True)
        if objstore.enabled() and proj.get("source"):
            objstore.delete(d.name, proj["source"])
        store.update(d.name, lambda p: p.update(source_expired=True))
        trimmed += 1
    if objstore.enabled():
        rows = supa.select("projects", {"created_at": f"lt.{store._iso(cutoff)}", "source_expired": "is.false",
                                        "source": "not.is.null", "select": "id,source,status,clips"})
        for r in rows:
            if r["status"] in ("processing", "downloading") or \
                    any(c.get("render_state") in ("rendering", "queued") for c in r.get("clips") or []):
                continue
            try:
                objstore.delete(r["id"], r["source"])
                store.update(r["id"], lambda p: p.update(source_expired=True))
                trimmed += 1
            except Exception:  # noqa: BLE001
                log.exception("cleanup: could not remove source of %s", r["id"])
    if trimmed:
        log.info("cleanup: removed source videos of %d project(s) older than %d days", trimmed, days)
    return trimmed


def _cleanup_loop() -> None:
    while True:
        try:
            cleanup_sources_once()
        except Exception:  # noqa: BLE001
            log.exception("cleanup failed")
        time.sleep(6 * 3600)


def _recover_interrupted() -> None:
    """Jobs live in this process. After a restart, anything still marked as running was cut off:
    mark it so the user sees 'Try again' instead of a spinner that never finishes."""
    if not supa.configured():
        return
    try:
        rows = supa.select("projects", {"status": "in.(processing,downloading)", "select": "id"})
    except Exception:  # noqa: BLE001
        log.exception("could not check for interrupted jobs")
        return
    for r in rows:
        def fix(p):
            p.update(status="error", stage="Interrupted",
                     message="ClipForge restarted while this video was being processed.")
            for c in p.get("clips", []):
                if c.get("render_state") in ("rendering", "queued"):
                    c["render_state"] = "idle"
        try:
            store.update(r["id"], fix)
        except Exception:  # noqa: BLE001
            log.exception("could not reset project %s", r["id"])
    if rows:
        log.info("marked %d interrupted job(s) for retry", len(rows))


@app.on_event("startup")
def _start_background_jobs() -> None:
    threading.Thread(target=_recover_interrupted, daemon=True, name="recover").start()
    threading.Thread(target=_cleanup_loop, daemon=True, name="cleanup").start()


@app.exception_handler(supa.SupabaseConfigError)
def _supabase_missing(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(supa.SupabaseError)
def _supabase_failed(request, exc):
    log.error("supabase: %s", exc)
    return JSONResponse({"detail": "The database had a problem. Please try again."}, status_code=502)


class _Frontend(StaticFiles):
    """The no-build frontend has no hashed filenames, so tell browsers to re-check each file
    (a cheap 304 via ETag when unchanged); otherwise they keep running an old app.js after an update."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers.setdefault("Cache-Control", "no-cache")
        return resp


app.mount("/", _Frontend(directory=config.FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
