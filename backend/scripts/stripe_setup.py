"""Create ClipForge's products and prices in your Stripe account (safe to re-run).

    cd backend
    .venv\\Scripts\\python scripts\\stripe_setup.py

Uses STRIPE_SECRET_KEY from backend/.env. Run it with your *test* key first (sk_test_...),
then again with the live key when you go live. Prices come from PLANS in app/billing.py and
are tagged with lookup keys like clipforge_pro_month, which is how the server finds them.
If you change a price, re-run: the old price is archived and the lookup key moves to the new one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import billing, config  # noqa: E402


def main() -> None:
    if not config.STRIPE_SECRET_KEY:
        sys.exit("Add STRIPE_SECRET_KEY to backend/.env first.")
    mode = "TEST" if billing.test_mode() else "LIVE"
    print(f"Stripe {mode} mode")

    for plan in billing.PAID:
        spec = billing.PLANS[plan]
        found = billing.stripe("GET", "/products/search", params={"query": f"metadata['clipforge_plan']:'{plan}'"})
        if found.get("data"):
            product = found["data"][0]
            print(f"  product {spec['name']}: exists ({product['id']})")
        else:
            product = billing.stripe("POST", "/products", {
                "name": f"ClipForge {spec['name']}", "description": spec["tagline"],
                "metadata": {"clipforge_plan": plan}})
            print(f"  product {spec['name']}: created ({product['id']})")

        for interval in ("month", "year"):
            key = billing.lookup_key(plan, interval)
            cents = int(spec[interval] * 100)
            existing = billing.stripe("GET", "/prices", params={"lookup_keys": [key], "limit": 1}).get("data", [])
            if existing and existing[0]["unit_amount"] == cents and existing[0]["active"]:
                print(f"    {key}: ${spec[interval]}/{interval} exists ({existing[0]['id']})")
                continue
            price = billing.stripe("POST", "/prices", {
                "product": product["id"], "currency": "usd", "unit_amount": cents,
                "recurring": {"interval": interval}, "lookup_key": key, "transfer_lookup_key": True,
                "nickname": f"{spec['name']} {interval}ly"})
            if existing:
                billing.stripe("POST", f"/prices/{existing[0]['id']}", {"active": False})
            print(f"    {key}: ${spec[interval]}/{interval} created ({price['id']})")
    print("Done. Next: turn on the Customer Portal (Stripe dashboard -> Settings -> Billing -> Customer portal).")


if __name__ == "__main__":
    try:
        main()
    except billing.BillingError as exc:
        sys.exit(str(exc))
