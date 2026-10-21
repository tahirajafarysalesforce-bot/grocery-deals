#!/usr/bin/env python3
"""Read new flyer images/PDFs in flyers/<store>/ and extract deals with Claude vision.

Each store's results go to data/<store>.json. A flyer is only processed once
(tracked by file hash); if you delete a flyer file, its items are removed too.

Needs: pip install anthropic pillow   and   ANTHROPIC_API_KEY in the environment.
"""
import base64, hashlib, io, json, os, re, sys
from datetime import date
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
FLYERS = ROOT / "flyers"
DATA = ROOT / "data"
STORES = {"giant": "Giant", "lidl": "Lidl", "aldi": "Aldi", "lotte": "Lotte Plaza Market"}
MODEL = os.environ.get("DEALS_MODEL", "claude-sonnet-5-5")
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}
MAX_IMG_BYTES = 4_500_000

PROMPT = """This is a page from the weekly sale flyer for {store} (a US supermarket). Today is {today}.

Extract EVERY individual sale item you can read. Return ONLY a JSON array, no other text.
Each element must have these keys:
  "name": product name with size/brand if shown, e.g. "Large Eggs, 18 ct"
  "price": number in dollars for the sale price (e.g. 2.99), or null if it is not a plain price
  "price_text": the price exactly as printed when "price" is null or is part of a deal (e.g. "2 for $5", "BOGO", "$1.99 with card"); otherwise ""
  "unit": the unit the price applies to, e.g. "lb", "each", "12 oz", "per 2"; "" if unclear
  "original_price": regular price as a number if printed, else null
  "valid_from": start date as YYYY-MM-DD if printed on the page, else null
  "valid_to": end date as YYYY-MM-DD if printed on the page, else null
  "category": one of produce, meat, seafood, dairy, bakery, frozen, pantry, snacks, beverages, household, health, other
  "notes": short condition such as "with loyalty card", "limit 4", "while supplies last"; "" if none

Rules: use the sale price, not the regular price. For "2 for $5" set price to 2.50, unit "each", price_text "2 for $5".
Infer the year from today's date when the flyer shows only month/day. Do not invent items or prices.
If the page has no sale items, return []."""


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def shrink_image(raw: bytes, media: str):
    """Downscale big images to stay under the API size limit."""
    if len(raw) <= MAX_IMG_BYTES:
        return raw, media
    from PIL import Image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    scale = 0.9
    while True:
        w, h = img.size
        small = img.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=85)
        if buf.tell() <= MAX_IMG_BYTES or scale < 0.3:
            return buf.getvalue(), "image/jpeg"
        scale -= 0.1


def content_block(path: Path):
    ext = path.suffix.lower()
    raw = path.read_bytes()
    if ext == ".pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.standard_b64encode(raw).decode()}}
    raw, media = shrink_image(raw, IMG_TYPES[ext])
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.standard_b64encode(raw).decode()}}


def parse_json_array(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array in response")
    return json.loads(text[start:end + 1])


def num(v):
    try:
        return None if v is None or v == "" else round(float(v), 2)
    except (TypeError, ValueError):
        return None


def datestr(v):
    return v if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


def clean(item: dict, store: str, source: str):
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    return {
        "store": store,
        "name": name,
        "price": num(item.get("price")),
        "price_text": str(item.get("price_text") or "").strip(),
        "unit": str(item.get("unit") or "").strip(),
        "original_price": num(item.get("original_price")),
        "valid_from": datestr(item.get("valid_from")),
        "valid_to": datestr(item.get("valid_to")),
        "category": str(item.get("category") or "other").strip().lower(),
        "notes": str(item.get("notes") or "").strip(),
        "source": source,
    }


def extract(client, path: Path, store: str):
    msg_content = [content_block(path),
                   {"type": "text", "text": PROMPT.format(store=STORES[store], today=date.today().isoformat())}]
    with client.messages.stream(model=MODEL, max_tokens=16000,
                                messages=[{"role": "user", "content": msg_content}]) as stream:
        resp = stream.get_final_message()
    text = "".join(b.text for b in resp.content if b.type == "text")
    return parse_json_array(text)


def main():
    DATA.mkdir(exist_ok=True)
    client = None
    changed = False
    for store in STORES:
        folder = FLYERS / store
        folder.mkdir(parents=True, exist_ok=True)
        out = DATA / f"{store}.json"
        state = json.loads(out.read_text()) if out.exists() else {"items": [], "sources": {}}

        files = {sha(p): p for p in sorted(folder.iterdir())
                 if p.suffix.lower() in IMG_TYPES or p.suffix.lower() == ".pdf"}

        # drop items from flyers that were removed
        gone = set(state["sources"]) - set(files)
        if gone:
            state["items"] = [i for i in state["items"] if i.get("source") not in gone]
            for g in gone:
                state["sources"].pop(g)
            changed = True

        for h, path in files.items():
            if h in state["sources"]:
                continue
            if client is None:
                client = anthropic.Anthropic()
            print(f"[{store}] reading {path.name} ...", flush=True)
            try:
                raw_items = extract(client, path, store)
            except Exception as e:  # keep going; this file will be retried next run
                print(f"[{store}] FAILED {path.name}: {e}", file=sys.stderr)
                continue
            items = [c for c in (clean(i, store, h) for i in raw_items if isinstance(i, dict)) if c]
            state["items"].extend(items)
            state["sources"][h] = path.name
            changed = True
            print(f"[{store}]   {len(items)} items", flush=True)

        out.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")

    print("done" + ("" if changed else " (nothing new)"))


if __name__ == "__main__":
    main()
