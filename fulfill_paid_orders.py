"""
Local fulfillment poller.

Checks Creem API for recently completed orders that haven't been fulfilled locally.
Run every 15 minutes via cron (or manually after a payment).

Usage:
  python3 fulfill_paid_orders.py          # check + fulfil any new orders
  python3 fulfill_paid_orders.py --dry    # check only, no fulfillment
"""
from __future__ import annotations
import argparse, csv, os, subprocess, sys, json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)

TRACKER_CSV = HERE / "work" / "leads_tracker.csv"
CREEM_API_KEY = os.environ.get("CREEM_API_KEY", "")


def _creem_get(path: str) -> dict:
    import urllib.request
    url = f"https://api.creem.io/v1{path}"
    req = urllib.request.Request(url, headers={"x-api-key": CREEM_API_KEY})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _read_tracker() -> list[dict]:
    with open(TRACKER_CSV, newline="") as f:
        return list(csv.DictReader(f))


def _write_tracker(rows: list[dict], fields: list[str]) -> None:
    tmp = Path(str(TRACKER_CSV) + ".tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(TRACKER_CSV)


def _update_tracker(listing_id: str, updates: dict) -> bool:
    with open(TRACKER_CSV, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or rows[0].keys())
    for col in updates:
        if col not in fields:
            fields.append(col)
    found = False
    for r in rows:
        if r["listing_id"] == listing_id:
            r.update(updates)
            found = True
            break
    if found:
        _write_tracker(rows, fields)
    return found


def _run_fulfillment(listing_id: str, row: dict) -> bool:
    env = {**os.environ, "TEASER_MODE": "0", "ALLOW_PAID_IMAGES": "1"}
    py = sys.executable

    def run(cmd: list[str], label: str) -> bool:
        print(f"  [{label}] starting...")
        r = subprocess.run(cmd, cwd=str(HERE), env=env, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            print(f"  [{label}] FAILED:\n{r.stderr[-1000:]}")
            return False
        print(f"  [{label}] done.")
        return True

    if not run([py, str(HERE / "step3_photos.py"), listing_id], "step3"):
        return False
    if not run([py, str(HERE / "step4_pdf.py"), listing_id], "step4"):
        return False

    listing_dir = HERE / "work" / "photos" / listing_id
    if row.get("host_email"):
        deliver_cmd = [
            py, str(HERE / "deliver.py"),
            "--listing-dir", str(listing_dir),
            "--results-dir", str(listing_dir),
            "--host-email", row["host_email"],
            "--host-name", row.get("host_name", "Host"),
            "--listing-title", row.get("title", "Your Airbnb Listing"),
        ]
        if not run(deliver_cmd, "deliver"):
            return False
    else:
        print(f"  [deliver] skipped — no host_email in tracker")

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="Check only, no fulfillment")
    args = parser.parse_args()

    if not CREEM_API_KEY:
        print("CREEM_API_KEY not set — cannot poll orders")
        sys.exit(1)

    print(f"[fulfill] Checking Creem for completed orders...")
    try:
        data = _creem_get("/orders?status=completed&limit=50")
        orders = data.get("data", [])
    except Exception as e:
        print(f"[fulfill] Creem API error: {e}")
        sys.exit(1)

    print(f"[fulfill] Found {len(orders)} completed orders")

    rows = _read_tracker()
    tracker_by_id = {r["listing_id"]: r for r in rows}

    fulfilled = 0
    for order in orders:
        meta = order.get("metadata") or {}
        listing_id = str(meta.get("listing_id", ""))
        if not listing_id:
            continue

        row = tracker_by_id.get(listing_id)
        if not row:
            print(f"  order {order.get('id')} → listing {listing_id} not in tracker, skipping")
            continue

        if row.get("status") == "Fulfilled":
            continue  # already done

        order_id = order.get("id", "")
        print(f"\n[fulfill] New paid order: listing={listing_id} order={order_id}")

        # Mark as paid in tracker
        _update_tracker(listing_id, {
            "paid": "yes",
            "creem_order_id": order_id,
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "status": "Paid",
        })

        if args.dry:
            print(f"  [dry] skipping fulfillment")
            continue

        success = _run_fulfillment(listing_id, row)
        if success:
            _update_tracker(listing_id, {
                "status": "Fulfilled",
                "fulfilled_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"  [fulfill] ✓ complete")
            fulfilled += 1
        else:
            _update_tracker(listing_id, {"notes": "fulfillment_error: see logs"})
            print(f"  [fulfill] ✗ failed — tracker notes updated")

    print(f"\n[fulfill] Done. {fulfilled} order(s) fulfilled this run.")


if __name__ == "__main__":
    main()
