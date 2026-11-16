"""Supabase Auth integration.

The browser signs in with supabase-js (email + password, confirmation and reset emails are
handled by Supabase). It then hands its access token to POST /api/auth/session, which
validates it with Supabase and stores it in an HttpOnly cookie so plain <video src> requests
are authenticated too. supabase-js refreshes the token hourly and re-posts it.

The signed-in user lives in a ContextVar set by AuthMiddleware for each request.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from contextvars import ContextVar
from typing import Callable, Optional

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from . import store, supa

log = logging.getLogger("clipforge.auth")

COOKIE = "cf_sb"
CURRENT: ContextVar[Optional[dict]] = ContextVar("clipforge_user", default=None)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def uid() -> Optional[str]:
    u = CURRENT.get()
    return u["id"] if u else None


def run_as(user_id: Optional[str], fn: Callable, *args):
    """Run fn with CURRENT set (background threads don't inherit request context)."""
    token = CURRENT.set({"id": user_id} if user_id else None)
    try:
        return fn(*args)
    finally:
        CURRENT.reset(token)


# ------------------------------------------------------------ token checks --

_cache: dict[str, tuple[float, Optional[dict]]] = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 60


def _public(u: dict) -> dict:
    meta = u.get("user_metadata") or {}
    email = u.get("email") or ""
    return {"id": u["id"], "email": email, "name": meta.get("name") or meta.get("full_name") or email.split("@")[0]}


def user_for_token(token: str) -> Optional[dict]:
    """Supabase user for an access token, cached briefly so media range requests stay fast."""
    if not token:
        return None
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        raw = supa.auth_user(token)
    except Exception as exc:  # noqa: BLE001  (network trouble: treat as signed out, don't crash the request)
        log.warning("token check failed: %s", exc)
        return None
    user = _public(raw) if raw and raw.get("id") else None
    with _cache_lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (now, user)
    return user


def forget(token: str) -> None:
    with _cache_lock:
        _cache.pop(hashlib.sha256(token.encode()).hexdigest(), None)


def set_cookie(resp, token: str, secure: bool) -> None:
    # Access tokens live ~1 h; the browser re-posts the refreshed one. Keep the cookie a day.
    # `secure` follows the scheme this request actually arrived on (https through a tunnel/proxy,
    # http on 127.0.0.1), so the same server works locally and via its public https address.
    resp.set_cookie(COOKIE, token, max_age=86400, httponly=True, samesite="lax", secure=secure, path="/")


# ------------------------------------------------- one-time import of old data --

_import_lock = threading.Lock()


def import_old_data(user_id: str) -> None:
    with _import_lock:
        try:
            n = store.import_local_data(user_id)
            if n:
                log.info("imported %d local projects into Supabase for %s", n, user_id)
        except Exception:  # noqa: BLE001
            log.exception("importing local data failed")


# --------------------------------------------------------------- middleware --

PUBLIC_PATHS = {"/api/info", "/api/health","/api/auth/session", "/api/auth/logout", "/api/auth/me",
                "/api/billing/webhook"}   # Stripe calls this; it is verified by signature instead


class AuthMiddleware:
    """Attach the signed-in user to every request and guard /api and /media."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        guarded = (path.startswith("/api/") and path not in PUBLIC_PATHS) or path.startswith("/media/")
        user = None
        if guarded or path == "/api/auth/me":
            conn = HTTPConnection(scope)
            bearer = conn.headers.get("authorization", "")
            token = bearer[7:] if bearer.lower().startswith("bearer ") else conn.cookies.get(COOKIE, "")
            if token:
                import anyio
                user = await anyio.to_thread.run_sync(user_for_token, token)
        ctx = CURRENT.set(user)
        try:
            if guarded and not user:
                resp = JSONResponse({"detail": "Please sign in to continue."}, status_code=401)
                return await resp(scope, receive, send)
            await self.app(scope, receive, send)
        finally:
            CURRENT.reset(ctx)
