"""
One-shot backfill: fetch image_urls for all tracker leads that are missing them.
Runs all URLs through Apify in a single actor call (cheap, one start fee).
Updates tracker with cover_photo_url + image_urls_json.
"""
import csv, json, sys
from pathlib import Path
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)
sys.path.insert(0, str(HERE))

from scraper import _run_actor, parse_listing
from tracker_io import write_rows

TRACKER_CSV = HERE / "work" / "leads_tracker.csv"
BATCH_SIZE  = 50   # Apify handles more but 50 keeps run time predictable

def main():
    rows = list(csv.DictReader(open(TRACKER_CSV)))
    fieldnames = list(rows[0].keys())
    for col in ("cover_photo_url", "image_urls_json"):
        if col not in fieldnames:
            fieldnames.append(col)

    # Only fetch leads that are missing image URLs
    need = [r for r in rows if not r.get("image_urls_json") and r.get("url")]
    print(f"[fetch_images] {len(need)} leads need image URLs (of {len(rows)} total)")
    if not need:
        print("[fetch_images] All leads already have image URLs — nothing to do.")
        return

    by_id = {r["listing_id"]: r for r in rows}

    # Process in batches
    total_updated = 0
    for i in range(0, len(need), BATCH_SIZE):
        batch = need[i:i + BATCH_SIZE]
        urls  = [r["url"] for r in batch]
        print(f"\n[fetch_images] Batch {i//BATCH_SIZE + 1}: {len(urls)} URLs...")

        try:
            items = _run_actor({
                "startUrls": [{"url": u} for u in urls],
                "skipDetailPages": False,
                "calendarMonths": 1,
                "maxListings": len(urls) + 5,
                "locale": "en-GB",
                "currency": "GBP",
            }, timeout_secs=600)
        except Exception as e:
            print(f"  [fetch_images] batch failed: {e}")
            continue

        for item in items:
            try:
                listing = parse_listing(item)
            except Exception:
                continue
            lid = str(listing.get("listing_id", ""))
            row = by_id.get(lid)
            if row is None:
                continue
            image_urls = listing.get("image_urls") or []
            if not image_urls:
                continue
            row["cover_photo_url"]  = image_urls[0]
            row["image_urls_json"]  = json.dumps(image_urls)
            total_updated += 1
            print(f"  {lid}: {len(image_urls)} images")

        write_rows(TRACKER_CSV, rows, fieldnames)
        print(f"  [fetch_images] tracker saved ({total_updated} updated so far)")

    still_missing = sum(1 for r in rows if not r.get("image_urls_json"))
    print(f"\n[fetch_images] Done. {total_updated} updated. {still_missing} still missing.")

if __name__ == "__main__":
    main()
