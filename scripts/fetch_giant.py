#!/usr/bin/env python3
"""Fetch Giant's current weekly ad and write data/giant.json.

Opens giantfood.com/savings/weekly-ad in a headless browser (like a normal visitor,
once per run) and reads the list of deals the page itself loads. No login, no key.

Needs: pip install playwright && playwright install --with-deps chromium
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "giant.json"
URL = "https://giantfood.com/savings/weekly-ad"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CATEGORIES = {
    "meat": "meat", "seafood": "seafood", "produce": "produce", "dairy": "dairy",
    "bread & bakery": "bakery", "bakery": "bakery", "frozen": "frozen",
    "beverages": "beverages", "snacks": "snacks", "pantry": "pantry",
    "health & beauty": "health", "household": "household",
}


def parse_ad(ad: dict):
    name = " ".join(str(ad.get("name") or "").split())
    if not name:
        return None
    sales = " ".join(str(ad.get("salesText") or "").split())
    price, price_text = None, ""
    m = re.search(r"(\d+)\s*/\s*\$\s*([\d.]+)", sales)  # "5/ $5.00"
    if m:
        qty, total = int(m.group(1)), float(m.group(2))
        price, price_text = round(total / qty, 2), f"{qty} for ${total:.2f}"
    else:
        try:
            price = round(float(ad.get("price")), 2)
        except (TypeError, ValueError):
            price_text = sales
    unit = ""
    m = re.search(r"/\s*(lb|ea|oz|pk|ct)\b", sales, re.I)
    if m:
        unit = {"ea": "each"}.get(m.group(1).lower(), m.group(1).lower())
    notes = []
    if re.search(r"digital coupon", sales, re.I):
        notes.append("with digital coupon")
    desc = " ".join(str(ad.get("description") or "").split())
    desc = re.sub(r"\$[\d.]+\s*/\w+\.?\s*WITHOUT DIGITAL COUPON", "", desc, flags=re.I).strip(" ,")
    if desc:
        notes.append(desc[:90])
    cat_raw = ((ad.get("categories") or [{}])[0].get("name") or "other").lower()
    return {
        "store": "giant",
        "name": name,
        "price": price,
        "price_text": price_text,
        "unit": unit,
        "original_price": None,
        "valid_from": ad.get("startDate") or None,
        "valid_to": ad.get("endDate") or None,
        "category": CATEGORIES.get(cat_raw, "other"),
        "notes": "; ".join(notes),
        "source": "auto",
    }


def parse_response(payload: dict):
    items = [i for i in (parse_ad(a) for a in payload.get("ads", [])) if i]
    # same product can appear twice (e.g. with/without coupon); keep one per name+price+dates
    seen, out = set(), []
    for i in items:
        k = (i["name"], i["price"], i["price_text"], i["valid_from"], i["valid_to"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def fetch_payload():
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = ctx.new_page()
        try:
            with page.expect_response(
                lambda r: "/weekly/circular/users/" in r.url and r.url.endswith("/ads")
                and r.request.method == "POST", timeout=60000) as resp_info:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            resp = resp_info.value
            if resp.status != 200:
                raise RuntimeError(f"Giant returned HTTP {resp.status} for the ad list")
            return resp.json(), resp.url
        except PWTimeout:
            raise RuntimeError("Giant's weekly ad list never loaded (the site may be showing a "
                               "bot check to this server). Nothing was changed.")
        finally:
            browser.close()


def main():
    try:
        payload, url = fetch_payload()
    except Exception as e:
        print(f"[giant] FAILED: {e}", file=sys.stderr)
        return 1
    items = parse_response(payload)
    if not items:
        print("[giant] FAILED: the response had no deals; leaving existing data alone.", file=sys.stderr)
        return 1
    m = re.search(r"/users/\d+/(\d+)/ads", url)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "store_id": m.group(1) if m else None,
        "ad_start": payload.get("adsStartDate"),
        "ad_end": payload.get("adsEndDate"),
        "items": items,
        "sources": {},
    }, indent=1, ensure_ascii=False) + "\n")
    print(f"[giant] {len(items)} deals (store {m.group(1) if m else '?'}), "
          f"{payload.get('adsStartDate')} to {payload.get('adsEndDate')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
