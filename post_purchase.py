"""
Post-purchase follow-up emailer.

Sends D+3 check-in, D+7 upsell, D+30 outcome/testimonial emails to paid customers.
Run daily via cron.

Usage:
  python3 post_purchase.py          # send due emails
  python3 post_purchase.py --dry    # print, don't send
  python3 post_purchase.py --force  # ignore already-sent gate
"""
from __future__ import annotations
import argparse, base64, csv, json, os, re, sys
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)

TRACKER     = HERE / "work" / "leads_tracker.csv"
TEARDOWNS   = HERE / "work" / "teardowns"
GMAIL_SEND  = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "fakhrialmubarok@gmail.com")
FROM_ADDR   = "AL <hello@scalr-us.com>"

GUMROAD_URL = os.environ.get("GUMROAD_URL", "https://itsalfahri.gumroad.com/l/bkitwy")


def _access_token() -> str:
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     os.environ["GMAIL_CLIENT_ID"],
        "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _send(to: str, subject: str, plain: str) -> None:
    token = _access_token()
    msg = MIMEMultipart("alternative")
    msg["To"]      = to
    msg["From"]    = FROM_ADDR
    msg["Subject"] = subject
    msg.attach(MIMEText(plain, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = requests.post(
        GMAIL_SEND,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw}, timeout=60,
    )
    resp.raise_for_status()
    print(f"  [post_purchase] Sent to {to} — {subject[:60]}")


def _first(host_name: str) -> str:
    return (host_name or "").split()[0] or "there"


def _photo_number_from_teardown(lid: str) -> str:
    """Extract a specific photo position from teardown for the D+3 email."""
    td_path = TEARDOWNS / f"teardown_{lid}.json"
    if not td_path.exists():
        return "the cover photo"
    try:
        td = json.loads(td_path.read_text())
        rec = td.get("analysis", {}).get("photo_order_rec", "")
        nums = re.findall(r"\b(\d{1,2})\b", rec)
        if nums:
            return f"photo {nums[0]}"
    except Exception:
        pass
    return "the cover photo"


def _d3_email(first: str, photo_ref: str) -> tuple[str, str]:
    subject = f"did you get a chance to swap the cover photo, {first}?"
    plain = f"""Hi {first},

Just checking in — did you get a chance to upload the new cover photo yet?

Hosts who swap it in the first few days tend to see calendar movement within 2 weeks. {photo_ref.capitalize()} is the one I'd put first — it's your strongest.

If you hit any snag uploading, just reply and I'll walk you through it.

— AL"""
    return subject, plain


def _d7_email(first: str) -> tuple[str, str]:
    subject = f"one more thing that might help, {first}"
    plain = f"""Hi {first},

Hope the listing changes are starting to show.

One thing I didn't include in the £29 package — a pricing audit. Your nightly rate vs open nights suggests there might be a sweet spot you're currently missing (either slightly too high for weekdays, or not taking advantage of weekend demand).

I can put together a quick pricing breakdown for £39. Reply 'pricing' and I'll get it to you within 48 hours.

— AL"""
    return subject, plain


def _d30_email(first: str) -> tuple[str, str]:
    subject = f"how did it go, {first}?"
    plain = f"""Hi {first},

It's been about a month since I sent the ListingBoost package.

Genuinely curious — did the changes move the needle? Even a small shift in bookings would be good to know about.

If it helped, I'd love to hear it (and would ask if I could share it anonymously). If it didn't, I want to know that too — reply and I'll look at what else might be going on.

Either way, thank you for trusting us with it.

— AL"""
    return subject, plain


def _days_since(date_str: str) -> int | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry",   action="store_true")
    parser.add_argument("--force", action="store_true", help="Ignore already-sent gate")
    args = parser.parse_args()

    rows = list(csv.DictReader(open(TRACKER)))
    fields = list(rows[0].keys()) if rows else []
    if "post_purchase_sent" not in fields:
        fields.append("post_purchase_sent")

    sent_count = 0
    for row in rows:
        if row.get("paid") != "yes":
            continue
        email = row.get("host_email", "")
        if not email:
            continue

        lid       = row.get("listing_id", "")
        first     = _first(row.get("host_name", ""))
        fulfilled = row.get("fulfilled_at") or row.get("paid_at", "")
        days      = _days_since(fulfilled)
        if days is None:
            continue

        sent_flags = set((row.get("post_purchase_sent") or "").split(","))
        sent_flags.discard("")

        to_send = []
        if 3 <= days <= 5   and (args.force or "d3"  not in sent_flags): to_send.append("d3")
        if 7 <= days <= 9   and (args.force or "d7"  not in sent_flags): to_send.append("d7")
        if 28 <= days <= 32 and (args.force or "d30" not in sent_flags): to_send.append("d30")

        for step in to_send:
            photo_ref = _photo_number_from_teardown(lid)
            if step == "d3":
                subj, body = _d3_email(first, photo_ref)
            elif step == "d7":
                subj, body = _d7_email(first)
            else:
                subj, body = _d30_email(first)

            print(f"[post_purchase] {lid} {first} D+{days}: {step} → {email}")
            if not args.dry:
                _send(email, subj, body)
                sent_flags.add(step)
                row["post_purchase_sent"] = ",".join(sorted(sent_flags))
                sent_count += 1
            else:
                print(f"  [dry] subject: {subj}")

    if not args.dry and sent_count > 0:
        tmp = Path(str(TRACKER) + ".tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        tmp.replace(TRACKER)

    print(f"[post_purchase] Done. {sent_count} email(s) sent.")


if __name__ == "__main__":
    main()
