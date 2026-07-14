"""
ListingBoost webhook + tracking server.

Endpoints:
  POST /webhook/creem        — Creem payment webhook → fulfil listing automatically
  GET  /t/<listing_id>       — Email open tracking pixel (1×1 GIF)
  GET  /health               — Railway health check

Deploy on Railway (or any host):
  Procfile:  web: gunicorn webhook_server:app -b 0.0.0.0:$PORT
  Env vars:  CREEM_WEBHOOK_SECRET, CREEM_API_KEY, AIRBNB_LISTER_DIR (abs path to repo),
             NANO_BANANA_KEY, GEMINI_API_KEY, plus any image-backend keys

After a payment:
  1. Signature verified
  2. listing_id pulled from order.metadata
  3. Tracker updated: paid=yes, paid_at, creem_order_id
  4. Background thread: step3 (full set, no TEASER) → step4 → email
"""
from __future__ import annotations
import csv, hashlib, hmac, json, logging, os, subprocess, sys, threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv

# ── Bootstrap ─────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)

REPO          = Path(os.environ.get("AIRBNB_LISTER_DIR", HERE))
TRACKER_CSV   = REPO / "work" / "leads_tracker.csv"
WEBHOOK_SECRET = os.environ.get("CREEM_WEBHOOK_SECRET", "")
PORT          = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [webhook] %(levelname)s %(message)s")
log = logging.getLogger("webhook")

app = Flask(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_creem(payload_bytes: bytes, sig: str) -> bool:
    if not WEBHOOK_SECRET:
        log.warning("CREEM_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def _read_tracker() -> tuple[list[dict], list[str]]:
    with open(TRACKER_CSV, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or list(rows[0].keys())
    return rows, fields


def _write_tracker(rows: list[dict], fields: list[str]) -> None:
    import tempfile, fcntl
    tmp = Path(str(TRACKER_CSV) + ".tmp")
    with open(tmp, "w", newline="") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        fcntl.flock(f, fcntl.LOCK_UN)
    tmp.replace(TRACKER_CSV)


def _update_tracker_fields(listing_id: str, updates: dict) -> bool:
    """Atomically update fields for one listing. Returns True if found."""
    rows, fields = _read_tracker()
    for col in updates:
        if col not in fields:
            fields.append(col)
    found = False
    for r in rows:
        if r["listing_id"] == str(listing_id):
            r.update(updates)
            found = True
            break
    if found:
        _write_tracker(rows, fields)
    return found


# ── Fulfillment ───────────────────────────────────────────────────────────────

def _run_fulfillment(listing_id: str) -> None:
    """
    Background thread: full step3 → step4 → email for one purchased listing.
    Called after payment confirmed.
    """
    env = {**os.environ, "TEASER_MODE": "0", "ALLOW_PAID_IMAGES": "1"}
    py = sys.executable

    def run(cmd: list[str], label: str) -> bool:
        log.info(f"[{listing_id}] {label} starting...")
        result = subprocess.run(
            cmd, cwd=str(REPO), env=env,
            capture_output=True, text=True, timeout=3600
        )
        if result.returncode != 0:
            log.error(f"[{listing_id}] {label} FAILED:\n{result.stderr[-2000:]}")
            return False
        log.info(f"[{listing_id}] {label} done.")
        return True

    # Step 3 — full photo set (no TEASER_MODE)
    if not run([py, str(REPO / "step3_photos.py"), listing_id], "step3"):
        _update_tracker_fields(listing_id, {"notes": "fulfillment_error: step3 failed"})
        return

    # Step 4 — PDF
    if not run([py, str(REPO / "step4_pdf.py"), listing_id], "step4"):
        _update_tracker_fields(listing_id, {"notes": "fulfillment_error: step4 failed"})
        return

    # Step 5 — Deliver ZIP to host
    rows, _ = _read_tracker()
    row = next((r for r in rows if r["listing_id"] == listing_id), None)
    if row and row.get("host_email"):
        listing_dir = REPO / "work" / "photos" / listing_id
        results_dir = REPO / "work" / "photos" / listing_id
        deliver_cmd = [
            py, str(REPO / "deliver.py"),
            "--listing-dir", str(listing_dir),
            "--results-dir", str(results_dir),
            "--host-email",  row["host_email"],
            "--host-name",   row.get("host_name", "Host"),
            "--listing-title", row.get("title", "Your Airbnb Listing"),
        ]
        if not run(deliver_cmd, "deliver"):
            _update_tracker_fields(listing_id, {"notes": "fulfillment_error: deliver failed"})
            return
    else:
        log.warning(f"[{listing_id}] no host_email in tracker — skipping email send")

    # Mark fulfilled
    _update_tracker_fields(listing_id, {
        "status": "Fulfilled",
        "fulfilled_at": datetime.now(timezone.utc).isoformat(),
    })
    log.info(f"[{listing_id}] fulfillment complete ✓")


# ── Routes ────────────────────────────────────────────────────────────────────

RELAY_MODE = not TRACKER_CSV.exists()
if RELAY_MODE:
    log.warning("Tracker not found — running in RELAY MODE (validate + ack only, no local fulfillment)")

@app.route("/health")
def health():
    info = {"status": "ok", "mode": "relay" if RELAY_MODE else "full"}
    if not RELAY_MODE:
        info["tracker_rows"] = sum(1 for _ in open(TRACKER_CSV))
    return jsonify(info)


@app.route("/webhook/creem", methods=["POST"])
def creem_webhook():
    payload = request.get_data()
    sig = request.headers.get("Creem-Signature", "")

    if not _verify_creem(payload, sig):
        log.warning("Creem webhook: invalid signature — rejected")
        return jsonify({"error": "invalid signature"}), 401

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return jsonify({"error": "bad JSON"}), 400

    event_type = event.get("type", "")
    log.info(f"Creem event: {event_type} | keys: {list(event.keys())}")

    # Only act on completed payments
    if event_type not in ("payment.succeeded", "order.paid", "checkout.completed"):
        return jsonify({"received": True, "action": "ignored"}), 200

    order = event.get("data", event.get("order", {}))
    order_id = order.get("id", "")
    metadata = order.get("metadata") or {}
    listing_id = str(metadata.get("listing_id", ""))
    host_email = str(metadata.get("host_email", ""))
    product_id = order.get("product_id", "")

    log.info(f"Payment confirmed: order={order_id} listing={listing_id} product={product_id}")

    if not listing_id:
        log.warning("No listing_id in metadata — cannot fulfil")
        return jsonify({"received": True, "action": "no_listing_id"}), 200

    # In relay mode (Railway deploy), just ack — local machine polls Creem API for fulfillment
    if RELAY_MODE:
        log.info(f"RELAY MODE: order {order_id} for listing {listing_id} acknowledged — local cron handles fulfillment")
        return jsonify({"received": True, "action": "relay_acked", "listing_id": listing_id}), 200

    now = datetime.now(timezone.utc).isoformat()
    found = _update_tracker_fields(listing_id, {
        "paid": "yes",
        "creem_order_id": order_id,
        "paid_at": now,
        "paid_product_id": product_id,
        "status": "Paid",
    })

    if not found:
        log.error(f"listing_id {listing_id} not in tracker — manual review needed")
        return jsonify({"received": True, "action": "listing_not_found"}), 200

    # Launch fulfillment in background so we return 200 immediately
    t = threading.Thread(target=_run_fulfillment, args=(listing_id,), daemon=True)
    t.start()

    log.info(f"Fulfillment thread launched for {listing_id}")
    return jsonify({"received": True, "action": "fulfillment_started",
                    "listing_id": listing_id}), 200


# 1×1 transparent GIF (43 bytes)
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
    b"\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@app.route("/t/<listing_id>")
def tracking_pixel(listing_id: str):
    """Email open tracking pixel. Fired when the email HTML loads the image."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows, fields = _read_tracker()
        for col in ("opened", "opened_at"):
            if col not in fields:
                fields.append(col)
        for r in rows:
            if r["listing_id"] == listing_id and not r.get("opened"):
                r["opened"] = "yes"
                r["opened_at"] = now
                log.info(f"Email opened: listing={listing_id}")
                break
        _write_tracker(rows, fields)
    except Exception as e:
        log.warning(f"Tracking write failed for {listing_id}: {e}")

    return Response(
        _PIXEL_GIF,
        mimetype="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/")
def index():
    return jsonify({
        "service": "ListingBoost webhook + tracking server",
        "endpoints": ["/webhook/creem", "/t/<listing_id>", "/health"],
    })


if __name__ == "__main__":
    log.info(f"Starting on port {PORT}, repo={REPO}, relay_mode={RELAY_MODE}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
