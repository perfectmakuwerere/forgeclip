"""Subscriptions with Stripe Checkout + Customer Portal.

- Plans and limits live in PLANS below (edit prices/limits here; run scripts/stripe_setup.py after
  changing prices so Stripe has matching Price objects).
- Prices are found in Stripe by lookup key (clipforge_<plan>_<month|year>), so no price IDs in .env.
- Subscription state is stored in Supabase table `subscriptions` and updated from:
    * the Stripe webhook (POST /api/billing/webhook, signature verified), and
    * a direct sync when the user returns from Checkout (works even without a webhook in local dev).
- Talks to the Stripe REST API with httpx, pinned to one API version so field names don't shift.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from . import config, supa

log = logging.getLogger("clipforge.billing")

API = "https://api.stripe.com/v1"
STRIPE_VERSION = "2024-06-20"

PLANS: dict[str, dict] = {
    "free": {"name": "Free", "month": 0, "year": 0, "videos": 3,
             "tagline": "Try ClipForge on a few videos.",
             "features": ["3 videos a month", "AI moment finding", "Animated captions", "All formats: 9:16, 1:1, 4:5, 16:9",
                          "Folders and analytics"]},
    "pro": {"name": "Pro", "month": 19, "year": 190, "videos": 30, "popular": True,
            "tagline": "For creators posting every week.",
            "features": ["30 videos a month", "Everything in Free", "Cancel anytime"]},
    "business": {"name": "Business", "month": 49, "year": 490, "videos": None,
                 "tagline": "For teams and agencies clipping daily.",
                 "features": ["Unlimited videos", "Everything in Pro", "Cancel anytime"]},
}
PAID = ("pro", "business")
ACTIVE = ("active", "trialing", "past_due")   # past_due keeps access while Stripe retries the card


class BillingError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ready() -> bool:
    # Only real Stripe secret/restricted keys; never send some other secret (e.g. a pasted Supabase key) to Stripe.
    return config.STRIPE_SECRET_KEY.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_"))


def test_mode() -> bool:
    return config.STRIPE_SECRET_KEY.startswith(("sk_test_", "rk_test_"))


# ------------------------------------------------------------------ Stripe --

def _flatten(data: dict, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out += _flatten(v, key)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out += _flatten(item, f"{key}[{i}]")
                else:
                    out.append((f"{key}[{i}]", str(item)))
        elif isinstance(v, bool):
            out.append((key, "true" if v else "false"))
        elif v is not None:
            out.append((key, str(v)))
    return out


def stripe(method: str, path: str, data: Optional[dict] = None, params: Optional[dict] = None) -> Any:
    if not ready():
        bad = config.STRIPE_SECRET_KEY and not ready()
        raise BillingError("STRIPE_SECRET_KEY in backend/.env isn't a Stripe secret key (it should start with sk_test_ "
                           "or sk_live_)." if bad else "Payments aren't set up yet: add STRIPE_SECRET_KEY to backend/.env.", 503)
    headers = {"Authorization": f"Bearer {config.STRIPE_SECRET_KEY}", "Stripe-Version": STRIPE_VERSION}
    body = None
    if data:
        # Encoded here: httpx's `data=` only takes a dict, and Stripe's nested/array fields need
        # repeated bracketed keys (line_items[0][price]=...), so a list of pairs is required.
        body = urlencode(_flatten(data))
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        r = httpx.request(method, f"{API}{path}", headers=headers, timeout=30,
                          content=body, params=_flatten(params) if params else None)
    except httpx.HTTPError as exc:
        raise BillingError(f"Couldn't reach Stripe: {exc}", 502) from exc
    body = r.json() if r.content else {}
    if r.status_code >= 400:
        msg = (body.get("error") or {}).get("message") or r.text[:200]
        log.warning("stripe %s %s -> %s: %s", method, path, r.status_code, msg)
        raise BillingError(f"Stripe: {msg}", 502)
    return body


_price_cache: dict[str, tuple[float, dict]] = {}
_price_lock = threading.Lock()


def lookup_key(plan: str, interval: str) -> str:
    return f"clipforge_{plan}_{interval}"


def price_for(plan: str, interval: str) -> dict:
    key = lookup_key(plan, interval)
    with _price_lock:
        hit = _price_cache.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
    res = stripe("GET", "/prices", params={"lookup_keys": [key], "active": True, "limit": 1})
    if not res.get("data"):
        raise BillingError(f"No Stripe price with lookup key '{key}'. Run backend/scripts/stripe_setup.py.", 503)
    with _price_lock:
        _price_cache[key] = (time.time(), res["data"][0])
    return res["data"][0]


def _plan_from_price(price: dict) -> tuple[str, str]:
    key = price.get("lookup_key") or ""
    for plan in PAID:
        for interval in ("month", "year"):
            if key == lookup_key(plan, interval):
                return plan, interval
    return "free", (price.get("recurring") or {}).get("interval")


# ------------------------------------------------------------- local state --

def _row(owner: str) -> Optional[dict]:
    return supa.select_one("subscriptions", {"owner": f"eq.{owner}", "select": "*"})


REFRESH_AFTER = 600   # seconds; without a webhook, cancellations/renewals are picked up this way


def _fresh_row(owner: str) -> Optional[dict]:
    """Subscription row, re-read from Stripe when it's older than REFRESH_AFTER.
    Makes the webhook optional for local installs (it's still recommended in production)."""
    row = _row(owner)
    sub_id = (row or {}).get("stripe_subscription_id")
    if not (ready() and sub_id):
        return row
    try:
        age = time.time() - datetime.fromisoformat(row["updated_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        age = REFRESH_AFTER + 1
    if age > REFRESH_AFTER:
        try:
            _apply_subscription(owner, stripe("GET", f"/subscriptions/{sub_id}"))
            row = _row(owner)
        except BillingError as exc:
            log.warning("subscription refresh failed: %s", exc)
    return row


def _upsert(owner: str, **fields) -> None:
    supa.insert("subscriptions", {"owner": owner, **fields}, upsert=True, on_conflict="owner")


def effective_plan(row: Optional[dict]) -> str:
    if row and row.get("plan") in PAID and row.get("status") in ACTIVE:
        return row["plan"]
    return "free"


def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def videos_this_month(owner: str) -> int:
    rows = supa.select("projects", {"owner": f"eq.{owner}", "created_at": f"gte.{_month_start()}", "select": "id"})
    return len(rows)


def check_quota(owner: str) -> None:
    """Raise if the user has used up this month's videos on their plan."""
    plan = effective_plan(_fresh_row(owner))
    limit = PLANS[plan]["videos"]
    if limit is None:
        return
    used = videos_this_month(owner)
    if used >= limit:
        nxt = "Pro" if plan == "free" else "Business"
        raise BillingError(f"You've used all {limit} videos on the {PLANS[plan]['name']} plan this month. "
                           f"Upgrade to {nxt} on the Plans page to keep going.", 402)


def summary(owner: str) -> dict:
    row = _fresh_row(owner)
    plan = effective_plan(row)
    return {
        "plan": plan,
        "status": (row or {}).get("status", "none"),
        "interval": (row or {}).get("billing_interval"),
        "current_period_end": (row or {}).get("current_period_end"),
        "cancel_at_period_end": bool((row or {}).get("cancel_at_period_end")),
        "has_customer": bool((row or {}).get("stripe_customer_id")),
        "usage": {"videos": videos_this_month(owner), "limit": PLANS[plan]["videos"]},
        "plans": [{"id": k, **v} for k, v in PLANS.items()],
        "stripe_ready": ready(),
        "test_mode": ready() and test_mode(),
    }


# ---------------------------------------------------------------- actions --

def _customer(owner: str, email: str) -> str:
    row = _row(owner)
    if row and row.get("stripe_customer_id"):
        return row["stripe_customer_id"]
    cust = stripe("POST", "/customers", {"email": email, "metadata": {"clipforge_user": owner}})
    _upsert(owner, stripe_customer_id=cust["id"])
    return cust["id"]


def checkout(owner: str, email: str, plan: str, interval: str, origin: str) -> str:
    if plan not in PAID or interval not in ("month", "year"):
        raise BillingError("Unknown plan.")
    row = _row(owner)
    if effective_plan(row) in PAID:
        raise BillingError("You already have a subscription. Use “Manage billing” to change or cancel it.", 409)
    price = price_for(plan, interval)
    session = stripe("POST", "/checkout/sessions", {
        "mode": "subscription",
        "customer": _customer(owner, email),
        "client_reference_id": owner,
        "line_items": [{"price": price["id"], "quantity": 1}],
        "allow_promotion_codes": True,
        "subscription_data": {"metadata": {"clipforge_user": owner}},
        "success_url": f"{origin}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}#/billing",
        "cancel_url": f"{origin}/#/billing",
    })
    return session["url"]


def portal(owner: str, origin: str) -> str:
    row = _row(owner)
    if not row or not row.get("stripe_customer_id"):
        raise BillingError("No billing account yet. Choose a plan first.")
    s = stripe("POST", "/billing_portal/sessions", {"customer": row["stripe_customer_id"],
                                                    "return_url": f"{origin}/?portal=return#/billing"})
    return s["url"]


def refresh(owner: str) -> None:
    """Re-read the user's subscription from Stripe now (used when they come back from the portal)."""
    row = _row(owner)
    sub_id = (row or {}).get("stripe_subscription_id")
    if sub_id:
        _apply_subscription(owner, stripe("GET", f"/subscriptions/{sub_id}"))


def _apply_subscription(owner: str, sub: dict) -> None:
    item = ((sub.get("items") or {}).get("data") or [{}])[0]
    plan, interval = _plan_from_price(item.get("price") or {})
    status = sub.get("status", "none")
    end = sub.get("current_period_end") or item.get("current_period_end")
    _upsert(owner,
            stripe_customer_id=sub.get("customer"),
            stripe_subscription_id=sub.get("id"),
            plan=plan if status not in ("canceled", "incomplete_expired") else "free",
            billing_interval=interval,
            status=status,
            current_period_end=datetime.fromtimestamp(end, tz=timezone.utc).isoformat() if end else None,
            cancel_at_period_end=bool(sub.get("cancel_at_period_end")))


def sync_checkout(owner: str, session_id: str) -> None:
    """Called when the browser returns from Checkout: pull the result straight from Stripe."""
    s = stripe("GET", f"/checkout/sessions/{session_id}", params={"expand": ["subscription"]})
    if s.get("client_reference_id") != owner:
        raise BillingError("That checkout belongs to a different account.", 403)
    sub = s.get("subscription")
    if isinstance(sub, dict):
        _apply_subscription(owner, sub)


# ---------------------------------------------------------------- webhook --

def verify_signature(payload: bytes, header: str, tolerance: int = 300) -> None:
    secret = config.STRIPE_WEBHOOK_SECRET
    if not secret:
        raise BillingError("STRIPE_WEBHOOK_SECRET isn't set.", 503)
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    sigs = [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    ts = parts.get("t", "")
    if not ts.isdigit() or not sigs:
        raise BillingError("Bad signature header.", 400)
    if abs(time.time() - int(ts)) > tolerance:
        raise BillingError("Signature too old.", 400)
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise BillingError("Signature mismatch.", 400)


def _owner_for(obj: dict) -> Optional[str]:
    owner = (obj.get("metadata") or {}).get("clipforge_user") or obj.get("client_reference_id")
    if owner:
        return owner
    cust = obj.get("customer")
    if cust:
        row = supa.select_one("subscriptions", {"stripe_customer_id": f"eq.{cust}", "select": "owner"})
        return row["owner"] if row else None
    return None


def handle_event(event: dict) -> None:
    kind, obj = event.get("type", ""), (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed" and obj.get("mode") == "subscription":
        owner = _owner_for(obj)
        if owner and obj.get("subscription"):
            _apply_subscription(owner, stripe("GET", f"/subscriptions/{obj['subscription']}"))
    elif kind in ("customer.subscription.created", "customer.subscription.updated",
                  "customer.subscription.deleted", "customer.subscription.paused",
                  "customer.subscription.resumed"):
        owner = _owner_for(obj)
        if owner:
            _apply_subscription(owner, obj)
        else:
            log.warning("webhook %s: no ClipForge user for customer %s", kind, obj.get("customer"))
