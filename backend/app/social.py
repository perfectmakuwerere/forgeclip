"""Connect social accounts (YouTube, TikTok, Instagram, X) with OAuth 2 and read profile stats.

Tokens are stored server-side in data/connections.json and never sent to the browser.
Each network needs its own developer app; credentials come from backend/.env (see config.py).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode

import httpx

from . import auth, config, store, supa

log = logging.getLogger("clipforge.social")


class SocialError(Exception):
    pass


@dataclass
class Platform:
    id: str
    name: str
    client_id: Callable[[], str]
    client_secret: Callable[[], str]
    auth_url: str
    token_url: str
    scopes: list[str]
    scope_sep: str = " "
    pkce: bool = False
    console_url: str = ""
    env: tuple[str, str] = ("", "")
    https_only: bool = False
    setup: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.client_id() and self.client_secret()) or (self.id == "x" and bool(self.client_id()))

    @property
    def redirect_uri(self) -> str:
        return f"{config.PUBLIC_URL}/api/social/{self.id}/callback"


PLATFORMS: dict[str, Platform] = {
    "youtube": Platform(
        id="youtube", name="YouTube",
        client_id=lambda: config.YOUTUBE_CLIENT_ID, client_secret=lambda: config.YOUTUBE_CLIENT_SECRET,
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/youtube.upload"],
        console_url="https://console.cloud.google.com/apis/credentials",
        env=("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"),
        setup=["Create a project in Google Cloud and enable “YouTube Data API v3”.",
               "Create an OAuth client ID of type “Web application”. On the consent screen add the "
               "youtube.readonly and youtube.upload scopes and add yourself as a test user.",
               "Add the redirect URI below, then copy the client ID and secret into backend/.env."],
    ),
    "tiktok": Platform(
        id="tiktok", name="TikTok",
        client_id=lambda: config.TIKTOK_CLIENT_KEY, client_secret=lambda: config.TIKTOK_CLIENT_SECRET,
        auth_url="https://www.tiktok.com/v2/auth/authorize/",
        token_url="https://open.tiktokapis.com/v2/oauth/token/",
        scopes=["user.info.basic", "user.info.profile", "user.info.stats", "video.publish"], scope_sep=",",
        console_url="https://developers.tiktok.com/apps",
        env=("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"), https_only=True,
        setup=["Create an app at developers.tiktok.com and add the “Login Kit” and “Content Posting API” products "
               "(turn on Direct Post).",
               "Request the scopes user.info.basic, user.info.profile, user.info.stats and video.publish. "
               "Until TikTok audits your app, posts can only be private (“Only me”).",
               "Add the redirect URI below (TikTok requires https, so use a tunnel and set PUBLIC_URL)."],
    ),
    "instagram": Platform(
        id="instagram", name="Instagram",
        client_id=lambda: config.INSTAGRAM_APP_ID, client_secret=lambda: config.INSTAGRAM_APP_SECRET,
        auth_url="https://www.instagram.com/oauth/authorize",
        token_url="https://api.instagram.com/oauth/access_token",
        scopes=["instagram_business_basic", "instagram_business_content_publish"], scope_sep=",",
        console_url="https://developers.facebook.com/apps",
        env=("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET"), https_only=True,
        setup=["Create a Meta app and add “Instagram” → “API setup with Instagram login”.",
               "Works with Instagram professional (Business or Creator) accounts. Enable the "
               "instagram_business_basic and instagram_business_content_publish permissions.",
               "Add the redirect URI below (https required) and copy the Instagram app ID and secret."],
    ),
    "x": Platform(
        id="x", name="X",
        client_id=lambda: config.X_CLIENT_ID, client_secret=lambda: config.X_CLIENT_SECRET,
        auth_url="https://x.com/i/oauth2/authorize",
        token_url="https://api.x.com/2/oauth2/token",
        scopes=["tweet.read", "tweet.write", "users.read", "media.write", "offline.access"], pkce=True,
        console_url="https://developer.x.com/en/portal/dashboard",
        env=("X_CLIENT_ID", "X_CLIENT_SECRET"),
        setup=["In the X developer portal, open your app → “User authentication settings”.",
               "Enable OAuth 2.0 with “Read and write” permissions, type “Web App”, and add the redirect URI below.",
               "Copy the OAuth 2.0 client ID and secret into backend/.env."],
    ),
}

# The permission each network needs before ClipForge can post for you.
PUBLISH_SCOPE = {
    "youtube": "https://www.googleapis.com/auth/youtube.upload",
    "tiktok": "video.publish",
    "instagram": "instagram_business_content_publish",
    "x": "media.write",
}


def can_publish(pid: str, conn: dict) -> bool:
    granted = conn.get("scope") or ""
    return PUBLISH_SCOPE[pid] in granted.replace(",", " ").split()


# ------------------------------------------------------------------ storage --

_lock = threading.Lock()
_pending: dict[str, dict] = {}   # oauth state -> {platform, verifier, at}


def _me() -> str:
    u = auth.uid()
    if not u:
        raise SocialError("Please sign in first.")
    return u


def _load() -> dict:
    """Connections of the signed-in user: {platform: connection} (Supabase table social_connections)."""
    rows = supa.select("social_connections", {"owner": f"eq.{_me()}", "select": "platform,data"})
    return {r["platform"]: r["data"] for r in rows}


def _save(data: dict) -> None:
    me = _me()
    if data:
        supa.insert("social_connections", [{"owner": me, "platform": k, "data": v} for k, v in data.items()],
                    upsert=True, on_conflict="owner,platform")
    gone = [p for p in PLATFORMS if p not in data]
    if gone:
        supa.delete("social_connections", {"owner": f"eq.{me}", "platform": f"in.({','.join(gone)})"})


def _get_platform(pid: str) -> Platform:
    p = PLATFORMS.get(pid)
    if not p:
        raise SocialError("Unknown network")
    return p


def public_list() -> list[dict]:
    """Everything the UI needs. Tokens are stripped."""
    data = _load()
    out = []
    for p in PLATFORMS.values():
        conn = data.get(p.id)
        out.append({
            "id": p.id, "name": p.name, "configured": p.configured,
            "connected": bool(conn), "profile": conn.get("profile") if conn else None,
            "can_publish": bool(conn) and can_publish(p.id, conn),
            "stats": conn.get("stats") if conn else None,
            "history": conn.get("history", []) if conn else [],
            "connected_at": conn.get("connected_at") if conn else None,
            "updated_at": conn.get("updated_at") if conn else None,
            "error": conn.get("error", "") if conn else "",
            "setup": {"steps": p.setup, "env": list(p.env), "redirect_uri": p.redirect_uri,
                      "console_url": p.console_url, "https_only": p.https_only},
        })
    return out


# -------------------------------------------------------------------- oauth --

def authorize_url(pid: str) -> str:
    p = _get_platform(pid)
    if not p.configured:
        raise SocialError(f"{p.name} isn't set up on this server yet. Add {p.env[0]} and {p.env[1]} to backend/.env.")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v["at"] > 900]:
            _pending.pop(k, None)
        _pending[state] = {"platform": pid, "verifier": verifier, "at": now, "user": _me()}

    params = {"redirect_uri": p.redirect_uri, "response_type": "code", "state": state,
              "scope": p.scope_sep.join(p.scopes)}
    if pid == "tiktok":
        params["client_key"] = p.client_id()
    else:
        params["client_id"] = p.client_id()
    if pid == "youtube":
        params.update(access_type="offline", prompt="consent", include_granted_scopes="true")
    if p.pkce:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params.update(code_challenge=challenge, code_challenge_method="S256")
    return f"{p.auth_url}?{urlencode(params)}"


def _token_request(p: Platform, form: dict) -> dict:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = None
    if p.id == "tiktok":
        form = {"client_key": p.client_id(), "client_secret": p.client_secret(), **form}
    elif p.id == "x":
        if p.client_secret():
            auth = (p.client_id(), p.client_secret())  # confidential client: HTTP Basic
        else:
            form = {"client_id": p.client_id(), **form}
    else:
        form = {"client_id": p.client_id(), "client_secret": p.client_secret(), **form}
    try:
        r = httpx.post(p.token_url, data=form, headers=headers, auth=auth, timeout=20)
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SocialError(f"Could not reach {p.name}: {exc}") from exc
    if r.status_code >= 400 or "error" in data and data.get("error") not in (None, "", {}):
        desc = data.get("error_description") or data.get("error_message") or data.get("error")
        raise SocialError(f"{p.name} rejected the sign-in: {desc}")
    # Instagram Login wraps the token in {"data": [...]}
    if p.id == "instagram" and isinstance(data.get("data"), list) and data["data"]:
        data = data["data"][0]
    return data


def _store_tokens(conn: dict, tok: dict) -> None:
    conn["access_token"] = tok["access_token"]
    if tok.get("refresh_token"):
        conn["refresh_token"] = tok["refresh_token"]
    conn["expires_at"] = time.time() + float(tok.get("expires_in") or 3600) - 60
    scope = tok.get("scope") or tok.get("permissions")
    if scope:
        conn["scope"] = " ".join(scope) if isinstance(scope, list) else str(scope)
    for k in ("open_id", "user_id"):
        if tok.get(k):
            conn[k] = str(tok[k])


def complete(pid: str, code: str, state: str) -> dict:
    p = _get_platform(pid)
    with _lock:
        pending = _pending.pop(state, None)
    if not pending or pending["platform"] != pid or pending.get("user") != auth.uid():
        raise SocialError("This sign-in link expired. Please try connecting again.")
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": p.redirect_uri}
    if p.pkce:
        form["code_verifier"] = pending["verifier"]
    tok = _token_request(p, form)
    conn: dict = {"connected_at": time.time()}
    _store_tokens(conn, tok)

    if pid == "instagram":  # swap the 1-hour token for a 60-day one
        try:
            r = httpx.get("https://graph.instagram.com/access_token", timeout=20, params={
                "grant_type": "ig_exchange_token", "client_secret": p.client_secret(),
                "access_token": conn["access_token"]})
            if r.status_code == 200:
                _store_tokens(conn, r.json())
        except httpx.HTTPError as exc:
            log.warning("instagram long-lived exchange failed: %s", exc)

    _fetch_into(pid, conn)
    with _lock:
        data = _load()
        data[pid] = conn
        _save(data)
    return conn["profile"]


def _refresh_if_needed(pid: str, conn: dict) -> None:
    if time.time() < conn.get("expires_at", 0):
        return
    p = _get_platform(pid)
    if pid == "instagram":
        r = httpx.get("https://graph.instagram.com/refresh_access_token", timeout=20,
                      params={"grant_type": "ig_refresh_token", "access_token": conn["access_token"]})
        if r.status_code != 200:
            raise SocialError("Instagram session expired. Reconnect the account.")
        _store_tokens(conn, r.json())
        return
    if not conn.get("refresh_token"):
        raise SocialError(f"{p.name} session expired. Reconnect the account.")
    _store_tokens(conn, _token_request(p, {"grant_type": "refresh_token", "refresh_token": conn["refresh_token"]}))


# ------------------------------------------------------------ profile/stats --

def _get_json(url: str, token: str, params: Optional[dict] = None, bearer: bool = True) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if bearer else {}
    if not bearer:
        params = {**(params or {}), "access_token": token}
    r = httpx.get(url, params=params, headers=headers, timeout=20)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else (data.get("detail") or err or r.text[:200])
        raise SocialError(str(msg))
    return data


def _fetch_profile(pid: str, conn: dict) -> tuple[dict, dict]:
    tok = conn["access_token"]
    if pid == "youtube":
        d = _get_json("https://www.googleapis.com/youtube/v3/channels", tok,
                      {"part": "snippet,statistics", "mine": "true"})
        if not d.get("items"):
            raise SocialError("This Google account has no YouTube channel.")
        ch = d["items"][0]
        sn, st = ch["snippet"], ch.get("statistics", {})
        handle = sn.get("customUrl", "")
        return ({"id": ch["id"], "name": sn.get("title", ""), "handle": handle,
                 "avatar": sn.get("thumbnails", {}).get("default", {}).get("url", ""),
                 "url": f"https://www.youtube.com/{handle}" if handle else f"https://www.youtube.com/channel/{ch['id']}"},
                {"followers": int(st.get("subscriberCount", 0)), "views": int(st.get("viewCount", 0)),
                 "posts": int(st.get("videoCount", 0))})
    if pid == "tiktok":
        d = _get_json("https://open.tiktokapis.com/v2/user/info/", tok, {
            "fields": "open_id,display_name,avatar_url,username,profile_deep_link,"
                      "follower_count,following_count,likes_count,video_count"})
        if (d.get("error") or {}).get("code") not in (None, "ok"):
            raise SocialError(d["error"].get("message", "TikTok error"))
        u = d.get("data", {}).get("user", {})
        return ({"id": u.get("open_id", ""), "name": u.get("display_name", ""),
                 "handle": "@" + u["username"] if u.get("username") else "",
                 "avatar": u.get("avatar_url", ""), "url": u.get("profile_deep_link", "")},
                {"followers": u.get("follower_count", 0), "following": u.get("following_count", 0),
                 "likes": u.get("likes_count", 0), "posts": u.get("video_count", 0)})
    if pid == "instagram":
        d = _get_json("https://graph.instagram.com/me", tok, {
            "fields": "user_id,username,name,profile_picture_url,followers_count,follows_count,media_count"},
            bearer=False)
        return ({"id": str(d.get("user_id") or d.get("id", "")), "name": d.get("name") or d.get("username", ""),
                 "handle": "@" + d.get("username", ""),
                 "avatar": d.get("profile_picture_url", ""), "url": f"https://instagram.com/{d.get('username', '')}"},
                {"followers": d.get("followers_count", 0), "following": d.get("follows_count", 0),
                 "posts": d.get("media_count", 0)})
    if pid == "x":
        d = _get_json("https://api.x.com/2/users/me", tok, {"user.fields": "public_metrics,profile_image_url"})
        u = d.get("data", {})
        m = u.get("public_metrics", {})
        return ({"id": u.get("id", ""), "name": u.get("name", ""), "handle": "@" + u.get("username", ""),
                 "avatar": u.get("profile_image_url", ""), "url": f"https://x.com/{u.get('username', '')}"},
                {"followers": m.get("followers_count", 0), "following": m.get("following_count", 0),
                 "posts": m.get("tweet_count", 0), "likes": m.get("like_count", 0)})
    raise SocialError("Unknown network")


def _fetch_into(pid: str, conn: dict) -> None:
    profile, stats = _fetch_profile(pid, conn)
    now = time.time()
    conn.update(profile=profile, stats=stats, updated_at=now, error="")
    hist = conn.setdefault("history", [])
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    point = {"day": day, **stats}
    if hist and hist[-1]["day"] == day:
        hist[-1] = point
    else:
        hist.append(point)
    del hist[:-120]


def refresh(pid: str) -> dict:
    _get_platform(pid)
    with _lock:
        conn = _load().get(pid)
    if not conn:
        raise SocialError("Not connected")
    try:
        _refresh_if_needed(pid, conn)
        _fetch_into(pid, conn)
    except (SocialError, httpx.HTTPError) as exc:
        conn["error"] = str(exc)[:200]
        with _lock:
            data = _load()
            data[pid] = conn
            _save(data)
        raise SocialError(str(exc)) from exc
    with _lock:
        data = _load()
        data[pid] = conn
        _save(data)
    return conn


def fresh_connection(pid: str) -> dict:
    """Connection with a valid (refreshed if needed) access token. Used by publishing."""
    _get_platform(pid)
    with _lock:
        conn = _load().get(pid)
    if not conn:
        raise SocialError(f"{PLATFORMS[pid].name} isn't connected.")
    before = conn.get("access_token")
    _refresh_if_needed(pid, conn)
    if conn.get("access_token") != before:
        with _lock:
            data = _load()
            if pid in data:
                data[pid].update({k: conn[k] for k in ("access_token", "refresh_token", "expires_at", "scope") if k in conn})
                _save(data)
    return conn


def refresh_stale(max_age: float = 6 * 3600) -> None:
    """Best-effort refresh of accounts whose stats are older than max_age."""
    for pid, conn in _load().items():
        if time.time() - conn.get("updated_at", 0) > max_age:
            try:
                refresh(pid)
            except Exception as exc:  # noqa: BLE001
                log.info("stats refresh for %s failed: %s", pid, exc)


def disconnect(pid: str) -> None:
    with _lock:
        data = _load()
        conn = data.pop(pid, None)
        _save(data)
    if conn and pid == "youtube":  # revoke so the grant disappears from the user's Google account
        try:
            httpx.post("https://oauth2.googleapis.com/revoke", params={"token": conn.get("refresh_token") or conn["access_token"]},
                       timeout=10)
        except httpx.HTTPError:
            pass


def callback_page(ok: bool, message: str) -> str:
    """Tiny page shown in the OAuth popup: tells the opener, then closes."""
    payload = json.dumps({"type": "clipforge-social", "ok": ok, "message": message})
    color = "#c6f432" if ok else "#ff6b6b"
    safe = message.replace("&", "&amp;").replace("<", "&lt;")
    return f"""<!doctype html><meta charset=utf-8><title>ClipForge</title>
<body style="background:#0a0a0b;color:#eee;font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:42px;color:{color}">{'✓' if ok else '!'}</div>
<p>{safe}</p><p style="color:#888;font-size:13px">You can close this window.</p></div>
<script>try{{window.opener&&window.opener.postMessage({payload},"*")}}catch(e){{}}
setTimeout(function(){{ if(window.opener) window.close(); else location.href='/#/connections'; }},{1200 if ok else 4000});</script></body>"""
