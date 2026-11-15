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

from . import analytics, auth, billing, config, publish, social, store, supa
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


class ClipPatch(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    title: Optional[str] = None
    hook: Optional[str] = None
    hashtags: Optional[list[str]] = None


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
        result = render_clip(store.project_dir(pid) / proj["source"], store.project_dir(pid) / "clips",
                             clip, _words(pid), settings, proj["video"]["has_audio"])
        mark("done", render=result)
    except Exception as exc:  # noqa: BLE001
        log.exception("render failed")
        mark("error", render_error=str(exc)[:500])


def _analyze(pid: str, body: AnalyzeIn) -> None:
    pdir = store.project_dir(pid)
    try:
        proj = _get(pid)
        video = pdir / proj["source"]
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
                    wav, duration, lambda f: _set_status(pid, progress=round(0.08 + 0.5 * f, 3)))
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
    except Exception as exc:  # noqa: BLE001
        log.exception("analysis failed")
        _set_status(pid, status="error", stage="Failed", message=str(exc)[:600])


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


def _finish_source(pid: str, path: Path) -> None:
    """Probe + thumbnail a freshly saved source file."""
    meta = media.probe(path)
    media.thumbnail(path, store.project_dir(pid) / "thumb.jpg", min(5, meta["duration"] / 3))
    store.update(pid, lambda p: p.update(video=meta, source=path.name))


def _import(pid: str, url: str, after: AutorunIn) -> None:
    pdir = store.project_dir(pid)
    try:
        def on_meta(m):
            store.update(pid, lambda p: p.update(name=m["title"] or p["name"], import_meta=m))

        def on_progress(frac, stage):
            _set_status(pid, progress=round(frac, 3), stage=stage)

        path = importer.download(url, pdir, on_meta, on_progress)
        _set_status(pid, stage="Reading video", progress=1.0)
        _finish_source(pid, path)
        for leftover in pdir.glob("source.*"):
            if leftover != path and leftover.is_file():
                leftover.unlink(missing_ok=True)
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
def auth_session(body: SessionIn):
    """The browser signed in with Supabase; verify its token and keep it in an HttpOnly cookie."""
    user = auth.user_for_token(body.access_token)
    if not user:
        raise HTTPException(401, "Your session expired. Please sign in again.")
    auth.import_old_data(user["id"])
    resp = JSONResponse({"user": user})
    auth.set_cookie(resp, body.access_token)
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


@app.get("/api/info")
def info():
    return {**registry.public_info(), "aspects": list(ASPECTS), "caption_styles": list(STYLES),
            "render_defaults": DEFAULT_RENDER, "whisper_model": config.WHISPER_MODEL,
            "max_upload_mb": config.MAX_UPLOAD_MB, "max_import_minutes": config.MAX_IMPORT_MINUTES,
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
    dst = store.project_dir(proj["id"]) / f"source{ext}"
    size, limit = 0, config.MAX_UPLOAD_MB * 1024 * 1024
    with dst.open("wb") as out:
        while chunk := await file.read(1024 * 1024 * 8):
            size += len(chunk)
            if size > limit:
                out.close()
                store.delete(proj["id"])
                raise HTTPException(413, f"File larger than {config.MAX_UPLOAD_MB} MB.")
            out.write(chunk)
    try:
        _finish_source(proj["id"], dst)
    except media.MediaError as exc:
        store.delete(proj["id"])
        raise HTTPException(400, f"Could not read video: {exc}")
    return _own(proj["id"])


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
                for k, v in body.model_dump(exclude_none=True).items():
                    c[k] = v
                c["start"] = round(max(0.0, min(c["start"], dur - 1)), 2)
                c["end"] = round(max(c["start"] + 1, min(c["end"], dur)), 2)
                return
        raise HTTPException(404, "Clip not found")
    return store.update(pid, fn)


@app.delete("/api/projects/{pid}/clips/{cid}")
def delete_clip(pid: str, cid: str):
    _own(pid)
    return store.update(pid, lambda p: p.update(clips=[c for c in p["clips"] if c["id"] != cid]))


@app.post("/api/projects/{pid}/clips/{cid}/render")
def render(pid: str, cid: str, settings: dict):
    proj = _own(pid)
    if not any(c["id"] == cid for c in proj["clips"]):
        raise HTTPException(404, "Clip not found")
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
    if base not in f.parents or not f.is_file() or f.suffix in (".json", ".wav"):
        raise HTTPException(404)
    if download:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_.")[:80] or f.name
        return FileResponse(f, filename=safe, media_type="video/mp4")
    return FileResponse(f)


@app.exception_handler(supa.SupabaseConfigError)
def _supabase_missing(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(supa.SupabaseError)
def _supabase_failed(request, exc):
    log.error("supabase: %s", exc)
    return JSONResponse({"detail": "The database had a problem. Please try again."}, status_code=502)


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
