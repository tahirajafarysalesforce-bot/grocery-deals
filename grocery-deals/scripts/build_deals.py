#!/usr/bin/env python3
"""Merge data/<store>.json files into data/deals.json (the file the web page reads).

Items whose end date passed more than KEEP_DAYS ago are dropped. If no real store
data exists yet, data/sample.json is used and the output is flagged as sample.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STORES = {"giant": "Giant", "lidl": "Lidl", "aldi": "Aldi", "lotte": "Lotte Plaza Market"}
KEEP_DAYS = 3


def load_items(store):
    p = DATA / f"{store}.json"
    return json.loads(p.read_text()).get("items", []) if p.exists() else []


def main():
    items = [i for s in STORES for i in load_items(s)]
    sample = False
    has_real = any((DATA / f"{s}.json").exists() for s in STORES)
    if not has_real and (DATA / "sample.json").exists():
        items = json.loads((DATA / "sample.json").read_text())["items"]
        sample = True

    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    items = [i for i in items if not i.get("valid_to") or i["valid_to"] >= cutoff]
    for i in items:
        i.pop("source", None)

    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": sample,
        "stores": {k: {"name": v} for k, v in STORES.items()},
        "items": items,
    }
    (DATA / "deals.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote data/deals.json: {len(items)} items" + (" (sample)" if sample else ""))


if __name__ == "__main__":
    main()
