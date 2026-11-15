"""Post a rendered clip to several networks at once (YouTube Shorts, TikTok, Instagram Reels, X).

Each target runs in its own thread. Post records live in memory and are persisted to
data/posts.json whenever a target changes state (progress ticks stay in memory only).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Iterator

import httpx

from . import auth, config, social, store, supa

log = logging.getLogger("clipforge.publish")

# What each network accepts (seconds). Checked before anything is uploaded.
LIMITS = {
    "youtube": {"min": 1, "max": 12 * 3600, "caption": 5000},
    "tiktok": {"min": 3, "max": 600, "caption": 2200},
    "instagram": {"min": 3, "max": 900, "caption": 2200},
    "x": {"min": 1, "max": 140, "caption": 280},
}
TIKTOK_PRIVACY = {"public": "PUBLIC_TO_EVERYONE", "friends": "MUTUAL_FOLLOW_FRIENDS",
                  "followers": "FOLLOWER_OF_CREATOR", "private": "SELF_ONLY"}
UPLOAD_TIMEOUT = httpx.Timeout(30.0, read=300.0, write=300.0)


class PublishError(Exception):
    pass


# ------------------------------------------------------------------ records --

# Posts live in Supabase (table posts). Uploads in flight are also kept in memory (_live) so
# progress polling doesn't hit the database every second; state changes are written through.

_lock = threading.Lock()
_live: dict[str, dict] = {}
INFLIGHT = ("queued", "uploading", "processing")


def _row(p: dict) -> dict:
    return {"id": p["id"], "owner": p["owner"], "project_id": p["project_id"], "clip_id": p["clip_id"],
            "clip_title": p["clip_title"], "thumb": p.get("thumb"), "caption": p["caption"], "title": p["title"],
            "targets": p["targets"], "created_at": store._iso(p["created"])}


def _from_db(r: dict) -> dict:
    p = {k: r[k] for k in ("id", "owner", "project_id", "clip_id", "clip_title", "thumb", "caption", "title", "targets")}
    p["created"] = store._epoch(r["created_at"])
    if p["id"] not in _live:               # not running in this process: it died with an earlier server
        for t in p["targets"].values():
            if t.get("state") in INFLIGHT:
                t.update(state="error", error="Interrupted: ClipForge was restarted during upload.")
    return p


def _persist(post: dict) -> None:
    supa.insert("posts", _row(post), upsert=True, on_conflict="id")


def _set(post_id: str, platform: str, persist: bool = True, **kw) -> None:
    with _lock:
        post = _live[post_id]
        post["targets"][platform].update(kw)
        snapshot = json.loads(json.dumps(post)) if persist else None
    if snapshot:
        try:
            _persist(snapshot)
        except Exception:  # noqa: BLE001  (keep uploading even if one status write fails)
            log.exception("could not save post status")
        if all(t["state"] not in INFLIGHT for t in snapshot["targets"].values()):
            with _lock:
                _live.pop(post_id, None)


def list_posts(project_id: str = "", limit: int = 50) -> list[dict]:
    me = auth.uid()
    params = {"owner": f"eq.{me}", "select": "*", "order": "created_at.desc", "limit": str(limit)}
    if project_id:
        params["project_id"] = f"eq.{project_id}"
    posts = [_from_db(r) for r in supa.select("posts", params)]
    with _lock:
        return [_live.get(p["id"], p) for p in posts]


def get_post(post_id: str) -> dict | None:
    with _lock:
        live = _live.get(post_id)
        if live:
            return live if live["owner"] == auth.uid() else None
    r = supa.select_one("posts", {"id": f"eq.{post_id}", "owner": f"eq.{auth.uid()}", "select": "*"})
    return _from_db(r) if r else None


# ------------------------------------------------------------------- start --

def start(project_id: str, clip_id: str, targets: list[str], caption: str, title: str,
          options: dict) -> dict:
    proj = store.load(project_id)
    if not proj:
        raise PublishError("Project not found")
    clip = next((c for c in proj["clips"] if c["id"] == clip_id), None)
    if not clip:
        raise PublishError("Clip not found")
    if clip.get("render_state") != "done" or not clip.get("render"):
        raise PublishError("Render the clip before posting it.")
    path = store.project_dir(project_id) / "clips" / clip["render"]["file"]
    if not path.is_file():
        raise PublishError("The rendered file is missing. Render the clip again.")
    targets = [t for t in dict.fromkeys(targets) if t in LIMITS]
    if not targets:
        raise PublishError("Pick at least one account to post to.")

    length = clip["end"] - clip["start"]
    connections = {s["id"]: s for s in social.public_list()}
    problems = []
    for t in targets:
        c, lim = connections.get(t), LIMITS[t]
        name = social.PLATFORMS[t].name
        if not c or not c["connected"]:
            problems.append(f"{name} isn't connected.")
        elif not c["can_publish"]:
            problems.append(f"{name} needs to be reconnected to allow posting.")
        elif not lim["min"] <= length <= lim["max"]:
            problems.append(f"{name} accepts videos of {lim['min']}–{lim['max']} s; this clip is {length:.0f} s.")
    if problems:
        raise PublishError(" ".join(problems))

    post = {
        "id": uuid.uuid4().hex[:12], "created": time.time(), "owner": auth.uid(),
        "project_id": project_id, "clip_id": clip_id,
        "clip_title": clip["title"], "thumb": clip["render"].get("thumb"), "caption": caption, "title": title,
        "targets": {t: {"state": "queued", "progress": 0.0, "url": "", "error": "", "note": ""} for t in targets},
    }
    _persist(post)
    with _lock:
        _live[post["id"]] = post
    for t in targets:
        threading.Thread(target=auth.run_as, args=(auth.uid(), _run, post["id"], t, path, caption, title,
                                                   options.get(t) or {}), daemon=True).start()
    return post


def _run(post_id: str, platform: str, path: Path, caption: str, title: str, opts: dict) -> None:
    last = {"t": 0.0}

    def progress(frac: float) -> None:
        now = time.time()
        if now - last["t"] > 0.4 or frac >= 1:
            last["t"] = now
            _set(post_id, platform, persist=False, progress=round(min(frac, 1.0), 3))

    _set(post_id, platform, state="uploading")
    try:
        conn = social.fresh_connection(platform)
        fn = {"youtube": _youtube, "tiktok": _tiktok, "instagram": _instagram, "x": _x}[platform]
        url, note = fn(conn, path, caption, title, opts, progress,
                       lambda: _set(post_id, platform, state="processing", progress=1.0))
        _set(post_id, platform, state="done", progress=1.0, url=url, note=note)
    except (PublishError, social.SocialError) as exc:
        _set(post_id, platform, state="error", error=str(exc)[:400])
    except httpx.HTTPError as exc:
        _set(post_id, platform, state="error", error=f"Network error: {exc}"[:400])
    except Exception as exc:  # noqa: BLE001
        log.exception("publish to %s failed", platform)
        _set(post_id, platform, state="error", error=str(exc)[:400])


# ------------------------------------------------------------------ helpers --

def _stream(path: Path, progress: Callable[[float], None], start: int = 0, length: int | None = None,
            chunk: int = 1024 * 1024) -> Iterator[bytes]:
    size = path.stat().st_size
    end = size if length is None else start + length
    sent = start
    with path.open("rb") as f:
        f.seek(start)
        while sent < end:
            data = f.read(min(chunk, end - sent))
            if not data:
                break
            sent += len(data)
            progress(sent / size)
            yield data


def _err(r: httpx.Response, network: str) -> PublishError:
    try:
        d = r.json()
    except ValueError:
        return PublishError(f"{network} error {r.status_code}: {r.text[:200]}")
    e = d.get("error")
    if isinstance(e, dict):
        msg = e.get("message") or e.get("error_user_msg") or e.get("code")
    else:
        msg = d.get("detail") or d.get("title") or e or d.get("errors") or r.text[:200]
    return PublishError(f"{network}: {msg}")


def _auth(conn: dict) -> dict:
    return {"Authorization": f"Bearer {conn['access_token']}"}


# ------------------------------------------------------------------ YouTube --

def _youtube(conn, path, caption, title, opts, progress, processing):
    size = path.stat().st_size
    privacy = opts.get("privacy") if opts.get("privacy") in ("public", "unlisted", "private") else "public"
    tags = [w.lstrip("#") for w in caption.split() if w.startswith("#")][:15]
    meta = {"snippet": {"title": (title or "New Short")[:100], "description": caption[:5000], "tags": tags,
                        "categoryId": "22"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    r = httpx.post("https://www.googleapis.com/upload/youtube/v3/videos",
                   params={"uploadType": "resumable", "part": "snippet,status"},
                   headers={**_auth(conn), "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                   json=meta, timeout=30)
    if r.status_code >= 400 or "location" not in r.headers:
        raise _err(r, "YouTube")
    r = httpx.put(r.headers["location"], content=_stream(path, progress), timeout=UPLOAD_TIMEOUT,
                  headers={**_auth(conn), "Content-Type": "video/mp4", "Content-Length": str(size)})
    if r.status_code >= 400:
        raise _err(r, "YouTube")
    vid = r.json()["id"]
    note = "" if privacy == "public" else f"Uploaded as {privacy}."
    return f"https://youtube.com/shorts/{vid}", note


# ------------------------------------------------------------------- TikTok --

def _tiktok(conn, path, caption, title, opts, progress, processing):
    api = "https://open.tiktokapis.com/v2/post/publish"
    headers = {**_auth(conn), "Content-Type": "application/json; charset=UTF-8"}
    r = httpx.post(f"{api}/creator_info/query/", headers=headers, json={}, timeout=20)
    info = r.json() if r.content else {}
    if r.status_code >= 400 or (info.get("error") or {}).get("code") not in (None, "ok"):
        raise PublishError(f"TikTok: {(info.get('error') or {}).get('message') or r.text[:200]}")
    data = info.get("data", {})
    options = data.get("privacy_level_options") or ["SELF_ONLY"]
    wanted = TIKTOK_PRIVACY.get(opts.get("privacy", "public"), "PUBLIC_TO_EVERYONE")
    level = wanted if wanted in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])

    size = path.stat().st_size
    chunk = size if size <= 64 * 1024 * 1024 else 32 * 1024 * 1024
    count = max(1, size // chunk)
    r = httpx.post(f"{api}/video/init/", headers=headers, timeout=30, json={
        "post_info": {"title": caption[:2200], "privacy_level": level, "disable_duet": False,
                      "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                        "total_chunk_count": count}})
    init = r.json() if r.content else {}
    if r.status_code >= 400 or (init.get("error") or {}).get("code") not in (None, "ok"):
        raise PublishError(f"TikTok: {(init.get('error') or {}).get('message') or r.text[:200]}")
    upload_url, publish_id = init["data"]["upload_url"], init["data"]["publish_id"]

    for i in range(count):
        start = i * chunk
        end = size - 1 if i == count - 1 else start + chunk - 1
        r = httpx.put(upload_url, content=_stream(path, progress, start, end - start + 1), timeout=UPLOAD_TIMEOUT,
                      headers={"Content-Type": "video/mp4", "Content-Length": str(end - start + 1),
                               "Content-Range": f"bytes {start}-{end}/{size}"})
        if r.status_code >= 400:
            raise PublishError(f"TikTok upload failed ({r.status_code}).")

    processing()
    for _ in range(120):
        time.sleep(3)
        r = httpx.post(f"{api}/status/fetch/", headers=headers, json={"publish_id": publish_id}, timeout=20)
        d = (r.json() if r.content else {}).get("data", {})
        status = d.get("status")
        if status == "FAILED":
            raise PublishError(f"TikTok rejected the video: {d.get('fail_reason', 'unknown reason')}")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            ids = d.get("publicaly_available_post_id") or []
            handle = (conn.get("profile") or {}).get("handle", "").lstrip("@")
            url = f"https://www.tiktok.com/@{handle}/video/{ids[0]}" if ids and handle else \
                (conn.get("profile") or {}).get("url", "")
            note = "Posted as private (Only me)." if level == "SELF_ONLY" else ""
            if level == "SELF_ONLY" and wanted != "SELF_ONLY":
                note = ("TikTok only allowed “Only me” for this app. Unaudited TikTok apps can only post "
                        "privately; submit the app for audit to post publicly.")
            return url, note
    raise PublishError("TikTok is still processing the video. Check your TikTok profile in a few minutes.")


# ---------------------------------------------------------------- Instagram --

def _instagram(conn, path, caption, title, opts, progress, processing):
    base = "https://graph.instagram.com"
    uid = (conn.get("profile") or {}).get("id") or conn.get("user_id")
    tok = conn["access_token"]
    if not uid:
        raise PublishError("Instagram account id unknown. Reconnect Instagram.")
    r = httpx.post(f"{base}/{uid}/media", timeout=30, params={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok})
    if r.status_code >= 400:
        raise _err(r, "Instagram")
    container, uri = r.json()["id"], r.json()["uri"]
    size = path.stat().st_size
    r = httpx.post(uri, content=_stream(path, progress), timeout=UPLOAD_TIMEOUT,
                   headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size),
                            "Content-Length": str(size)})
    if r.status_code >= 400:
        raise _err(r, "Instagram")

    processing()
    for _ in range(100):
        time.sleep(4)
        r = httpx.get(f"{base}/{container}", params={"fields": "status_code,status", "access_token": tok}, timeout=20)
        d = r.json() if r.content else {}
        if d.get("status_code") == "FINISHED":
            break
        if d.get("status_code") in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram couldn't process the video: {d.get('status', 'unknown error')}")
    else:
        raise PublishError("Instagram is still processing the video after several minutes.")

    r = httpx.post(f"{base}/{uid}/media_publish", params={"creation_id": container, "access_token": tok}, timeout=30)
    if r.status_code >= 400:
        raise _err(r, "Instagram")
    media_id = r.json()["id"]
    try:
        link = httpx.get(f"{base}/{media_id}", params={"fields": "permalink", "access_token": tok},
                         timeout=15).json().get("permalink", "")
    except (httpx.HTTPError, ValueError):
        link = ""
    return link or (conn.get("profile") or {}).get("url", ""), ""


# ------------------------------------------------------------------------ X --

def _x(conn, path, caption, title, opts, progress, processing):
    api = "https://api.x.com/2/media/upload"
    size = path.stat().st_size
    r = httpx.post(f"{api}/initialize", headers=_auth(conn), timeout=30,
                   json={"media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"})
    if r.status_code >= 400:
        raise _err(r, "X")
    media_id = r.json()["data"]["id"]

    seg, sent, chunk = 0, 0, 4 * 1024 * 1024
    with path.open("rb") as f:
        while data := f.read(chunk):
            r = httpx.post(f"{api}/{media_id}/append", headers=_auth(conn), timeout=UPLOAD_TIMEOUT,
                           data={"segment_index": str(seg)}, files={"media": ("chunk", data, "application/octet-stream")})
            if r.status_code >= 400:
                raise _err(r, "X")
            seg += 1
            sent += len(data)
            progress(sent / size)

    r = httpx.post(f"{api}/{media_id}/finalize", headers=_auth(conn), timeout=60)
    if r.status_code >= 400:
        raise _err(r, "X")
    info = (r.json().get("data") or {}).get("processing_info")
    if info:
        processing()
    for _ in range(90):
        if not info or info.get("state") == "succeeded":
            break
        if info.get("state") == "failed":
            raise PublishError(f"X couldn't process the video: {(info.get('error') or {}).get('message', '')}")
        time.sleep(max(1, min(int(info.get("check_after_secs", 3)), 10)))
        r = httpx.get(api, params={"command": "STATUS", "media_id": media_id}, headers=_auth(conn), timeout=20)
        info = (r.json().get("data") or {}).get("processing_info") if r.content else None

    r = httpx.post("https://api.x.com/2/tweets", headers=_auth(conn), timeout=30,
                   json={"text": caption[:280], "media": {"media_ids": [media_id]}})
    if r.status_code >= 400:
        raise _err(r, "X")
    tid = r.json()["data"]["id"]
    handle = (conn.get("profile") or {}).get("handle", "").lstrip("@") or "i"
    return f"https://x.com/{handle}/status/{tid}", ""
