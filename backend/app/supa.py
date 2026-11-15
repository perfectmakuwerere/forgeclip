"""Minimal Supabase client for the server: PostgREST (database) + Auth user lookup.

The server talks to the database with the project's *secret* key, which bypasses
Row Level Security, so every query here must filter by owner itself.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from . import config


class SupabaseConfigError(RuntimeError):
    pass


class SupabaseError(RuntimeError):
    pass


_client: Optional[httpx.Client] = None


def configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_PUBLISHABLE_KEY and config.SUPABASE_SECRET_KEY)


def _http() -> httpx.Client:
    global _client
    if not configured():
        missing = [k for k, v in (("SUPABASE_URL", config.SUPABASE_URL),
                                  ("SUPABASE_PUBLISHABLE_KEY", config.SUPABASE_PUBLISHABLE_KEY),
                                  ("SUPABASE_SECRET_KEY", config.SUPABASE_SECRET_KEY)) if not v]
        raise SupabaseConfigError(f"Supabase isn't configured on the server: add {', '.join(missing)} to backend/.env "
                                  "and restart ClipForge.")
    if _client is None:
        key = config.SUPABASE_SECRET_KEY
        headers = {"apikey": key}
        if not key.startswith("sb_secret_"):          # legacy service_role JWT also goes in Authorization
            headers["Authorization"] = f"Bearer {key}"
        _client = httpx.Client(base_url=f"{config.SUPABASE_URL}/rest/v1", headers=headers, timeout=20)
    return _client


def _check(r: httpx.Response) -> Any:
    if r.status_code >= 400:
        try:
            d = r.json()
            msg = d.get("message") or d.get("msg") or d.get("error") or r.text
        except ValueError:
            msg = r.text
        raise SupabaseError(f"Database error ({r.status_code}): {str(msg)[:300]}")
    return r.json() if r.content else None


def select(table: str, params: dict) -> list[dict]:
    return _check(_http().get(f"/{table}", params=params)) or []


def select_one(table: str, params: dict) -> Optional[dict]:
    rows = select(table, {**params, "limit": "1"})
    return rows[0] if rows else None


def insert(table: str, rows: dict | list[dict], upsert: bool = False, on_conflict: str = "") -> list[dict]:
    prefer = "return=representation"
    if upsert:
        prefer += ",resolution=merge-duplicates"
    params = {"on_conflict": on_conflict} if on_conflict else None
    return _check(_http().post(f"/{table}", json=rows, params=params, headers={"Prefer": prefer})) or []


def update(table: str, filters: dict, patch: dict) -> list[dict]:
    return _check(_http().patch(f"/{table}", params=filters, json=patch,
                                headers={"Prefer": "return=representation"})) or []


def delete(table: str, filters: dict) -> None:
    if not filters:
        raise ValueError("refusing to delete without a filter")
    _check(_http().delete(f"/{table}", params=filters))


def auth_user(access_token: str) -> Optional[dict]:
    """Validate a Supabase access token by asking Supabase Auth who it belongs to."""
    if not (config.SUPABASE_URL and config.SUPABASE_PUBLISHABLE_KEY):
        raise SupabaseConfigError("Supabase isn't configured on the server.")
    r = httpx.get(f"{config.SUPABASE_URL}/auth/v1/user", timeout=10,
                  headers={"apikey": config.SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        return None
    return r.json()
