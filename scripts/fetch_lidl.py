#!/usr/bin/env python3
"""Download Lidl's current and upcoming weekly-ad page images into flyers/lidl/.

Lidl publishes its ad as page pictures, not a list of items, so this script only
fetches the pictures. scripts/extract_flyers.py then reads the prices from them
(that step needs ANTHROPIC_API_KEY).

Files are named lidl_<validfrom>_<validto>_pNN.jpg so the dates travel with them.
Old auto-downloaded Lidl flyers are removed, which also removes their deals.

Needs: pip install playwright && playwright install --with-deps chromium
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "flyers" / "lidl"
LIST_URL = "https://www.lidl.com/c/offers-leaflets/s10092873"
BASE = "https://www.lidl.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def flyer_ids(hrefs):
    ids = []
    for h in hrefs:
        m = re.search(r"/flyer/esi-flyer/(weekly-ad[^/]*)/", h)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def page_urls(flyer: dict):
    """Best available image URL for each page, in page order."""
    pages = sorted(flyer.get("pages", []), key=lambda p: p.get("number", 0))
    urls = []
    for p in pages:
        if p.get("pageType", "page") != "page":
            continue
        u = p.get("image") or p.get("zoom")
        if u:
            urls.append((p.get("number"), u))
    return urls


def main():
    from playwright.sync_api import sync_playwright
    FOLDER.mkdir(parents=True, exist_ok=True)
    keep = set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA, locale="en-US")
        page = ctx.new_page()
        page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        ids = flyer_ids(hrefs)
        if not ids:
            print("[lidl] FAILED: no weekly ad links found on Lidl's offers page. "
                  "Existing data left alone.", file=sys.stderr)
            browser.close()
            return 1

        for fid in ids[:2]:  # this week and next week
            r = ctx.request.get(f"{BASE}/flyer/endpoints/v4/flyer",
                                params={"flyer_identifier": fid, "region_id": "0", "region_code": "0"})
            if r.status != 200:
                print(f"[lidl] {fid}: HTTP {r.status}, skipped", file=sys.stderr)
                continue
            flyer = r.json().get("flyer", {})
            start = flyer.get("offerStartDate") or flyer.get("startDate") or "unknown"
            end = flyer.get("offerEndDate") or flyer.get("endDate") or "unknown"
            n = 0
            for num, url in page_urls(flyer):
                dest = FOLDER / f"lidl_{start}_{end}_p{int(num):02d}.jpg"
                keep.add(dest.name)
                if dest.exists():
                    continue
                img = ctx.request.get(url)
                if img.status == 200:
                    dest.write_bytes(img.body())
                    n += 1
            print(f"[lidl] {fid}: {start} to {end}, {n} new page images")
        browser.close()

    if not keep:
        print("[lidl] FAILED: no page images found.", file=sys.stderr)
        return 1
    for f in FOLDER.glob("lidl_*.jpg"):  # drop expired auto-downloads
        if f.name not in keep:
            f.unlink()
            print(f"[lidl] removed old {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
