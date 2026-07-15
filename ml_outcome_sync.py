"""
ML Outcome Sync — closes the Thompson Sampling feedback loop.

Reads Gmail for replies to outreach emails and matches them to listing_ids
in the send log. Records 'replied' and 'paid' outcomes back to ml_variants.

Run daily via cron (after the main cron batch).

Usage:
  python3 ml_outcome_sync.py          # sync outcomes
  python3 ml_outcome_sync.py --dry    # report without writing
"""
from __future__ import annotations
import argparse, base64, csv, json, os, re
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)

TRACKER = HERE / "work" / "leads_tracker.csv"
LOG     = HERE / "work" / "ml_send_log.jsonl"
SYNCED  = HERE / "work" / "ml_outcome_synced.json"

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _token() -> str:
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     os.environ["GMAIL_CLIENT_ID"],
        "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _list_threads(token: str, query: str) -> list[str]:
    r = requests.get(f"{GMAIL_API}/threads", params={"q": query, "maxResults": 100},
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return [t["id"] for t in r.json().get("threads", [])]


def _thread_emails(token: str, thread_id: str) -> list[str]:
    """Return list of sender emails in the thread."""
    r = requests.get(f"{GMAIL_API}/threads/{thread_id}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    senders = []
    for msg in r.json().get("messages", []):
        for h in msg.get("payload", {}).get("headers", []):
            if h["name"].lower() == "from":
                m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", h["value"])
                if m:
                    senders.append(m.group().lower())
    return senders


def _load_send_log() -> dict[str, dict]:
    """email -> {listing_id, variants}"""
    if not LOG.exists():
        return {}
    mapping = {}
    for line in LOG.read_text().splitlines():
        try:
            e = json.loads(line)
            mapping[e["listing_id"]] = e
        except Exception:
            pass
    return mapping


def _load_synced() -> set:
    if SYNCED.exists():
        return set(json.loads(SYNCED.read_text()))
    return set()


def _save_synced(done: set) -> None:
    SYNCED.write_text(json.dumps(sorted(done)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    from ml_variants import record_outcome

    rows = list(csv.DictReader(open(TRACKER)))
    email_to_lid = {r["host_email"].lower(): r["listing_id"]
                    for r in rows if r.get("host_email")}
    synced = _load_synced()

    try:
        token = _token()
    except Exception as e:
        print(f"[ml_outcome_sync] Gmail auth failed: {e}")
        return

    # Check for replies to our outreach emails
    reply_threads = _list_threads(token, 'in:inbox subject:"your listing" OR subject:"listing teardown" OR subject:"open nights" newer_than:60d')
    paid_threads  = _list_threads(token, 'from:gumroad.com OR from:creem.io newer_than:60d')

    outcomes_recorded = 0

    for tid in reply_threads:
        if f"reply:{tid}" in synced:
            continue
        senders = _thread_emails(token, tid)
        for sender in senders:
            lid = email_to_lid.get(sender)
            if lid:
                print(f"[ml_outcome_sync] Reply detected: {sender} -> listing {lid}")
                if not args.dry:
                    record_outcome(lid, "replied")
                    # Update tracker
                    for r in rows:
                        if r["listing_id"] == lid:
                            r["replied"] = "yes"
                synced.add(f"reply:{tid}")
                outcomes_recorded += 1

    for tid in paid_threads:
        if f"paid:{tid}" in synced:
            continue
        # Extract listing_id from email body if possible
        r = requests.get(f"{GMAIL_API}/threads/{tid}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        body_text = json.dumps(r.json())
        # Look for any listing_id that appears in our send log
        for lid in email_to_lid.values():
            if lid in body_text:
                print(f"[ml_outcome_sync] Payment detected for listing {lid}")
                if not args.dry:
                    record_outcome(lid, "paid")
                    for row in rows:
                        if row["listing_id"] == lid:
                            row["paid"] = "yes"
                synced.add(f"paid:{tid}")
                outcomes_recorded += 1
                break

    if not args.dry:
        tmp = Path(str(TRACKER) + ".tmp")
        with open(tmp, "w", newline="") as f:
            import csv as _csv
            fields = list(rows[0].keys()) if rows else []
            w = _csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        tmp.replace(TRACKER)
        _save_synced(synced)

    print(f"[ml_outcome_sync] Done. {outcomes_recorded} outcome(s) recorded.")


if __name__ == "__main__":
    main()
