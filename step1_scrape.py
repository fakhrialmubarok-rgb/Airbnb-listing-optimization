"""
Step 1 — Scrape & Qualify (LOCKED process v1)

Scrapes a market, qualifies leads, dedupes against the tracker, and emits
tracker-ready rows with contact channel resolved (email if found, else Airbnb DM).

Qualification floor (a lead must pass ALL):
  - revenue_at_stake_90d >= £2,000
  - entire home (no private/shared rooms)
  - host_review_count >= 5

Contact channel:
  - "email"     if enrich waterfall found one (bio regex -> website scrape)
  - "airbnb_dm" fallback — DM link is the listing URL (manual send)

Usage:
  python3 step1_scrape.py "Manchester, United Kingdom" 10
"""
import sys, json, csv, os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)
sys.path.insert(0, str(Path(__file__).parent))

from scraper import scrape_location

MIN_STAKE_GBP  = 2000
MIN_REVIEWS    = 5
MAX_REVIEWS    = 500          # above this = professional operator, not a $29 buyer
PRO_KEYWORDS   = ("ltd", "limited", "stays", "homes", "properties", "property",
                  "apartments", "aparthotel", "hotel", "suites", "serviced",
                  "group", "living", "lettings", "locke", "hosts", "management",
                  "collection", "residences", "accommodation")
CAL_MONTHS     = 3            # 90-day calendar so open_nights_90d is honest
TRACKER_CSV    = Path(__file__).parent / "work" / "leads_tracker.csv"


def load_seen_ids() -> set:
    if not TRACKER_CSV.exists():
        return set()
    with open(TRACKER_CSV) as f:
        return {row["listing_id"] for row in csv.DictReader(f)}


def qualify(l: dict) -> tuple[bool, str]:
    stake = (l.get("nightly_rate") or 0) * (l.get("open_nights_90d") or 0)
    if "entire" not in (l.get("room_type") or "").lower():
        return False, "not entire home"
    reviews = l.get("host_review_count") or 0
    if reviews < MIN_REVIEWS:
        return False, f"reviews < {MIN_REVIEWS}"
    if reviews > MAX_REVIEWS:
        return False, f"pro operator ({reviews} host reviews)"
    host = (l.get("host_name") or "").lower()
    hits = [k for k in PRO_KEYWORDS if k in host.split() or k in host]
    if hits:
        return False, f"pro operator (name: {hits[0]!r})"
    if stake < MIN_STAKE_GBP:
        return False, f"stake £{stake:,.0f} < £{MIN_STAKE_GBP:,}"
    return True, f"stake £{stake:,.0f}"


# Contact policy (stress-test 2026-07-15, legal + deliverability red-team):
#  - Cold email ONLY to business-subscriber addresses (custom domains) — PECR's
#    corporate exemption. Personal-mailbox hosts (gmail/hotmail/etc.) need
#    consent: route them to inbound channels, never cold email.
#  - Airbnb DMs from an identity-linked account = permanent-ban risk +
#    ToS breach: the DM channel is DEAD as a volume channel.
PERSONAL_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.co.uk", "outlook.com",
    "live.com", "live.co.uk", "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com",
    "aol.com", "btinternet.com", "sky.com", "talktalk.net", "protonmail.com",
    "proton.me", "mail.com", "gmx.com", "gmx.co.uk", "ymail.com", "msn.com",
}

def _contact_channel(email):
    if not email or "@" not in email:
        return "inbound_only"          # no cold contact — nurture via content/inbound
    domain = email.rsplit("@", 1)[1].lower()
    if domain in PERSONAL_MAIL_DOMAINS:
        return "inbound_only"          # PECR individual subscriber — no cold email
    return "email"                     # business-subscriber address — cold OK w/ LIA rules


PHOTO_SCORE_PROMPT = (
    "Rate how BAD this Airbnb listing cover photo is as marketing, 0-10: "
    "0 = professional (bright, straight, styled), 10 = terrible (dark, tilted, "
    "cluttered, phone-quality). Consider: lighting, verticals, clutter, framing, "
    "appeal. Return ONLY JSON: {\"badness\": <0-10>, \"issues\": \"<short>\"}"
)

def score_cover_photo(l: dict) -> int:
    """0-10 badness of the cover photo (10 = worst = highest lead priority)."""
    import base64, requests as rq
    url = (l.get("image_urls") or [None])[0]
    if not url:
        return 0
    try:
        img = rq.get(url, timeout=30).content
        r = rq.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [
                      {"text": PHOTO_SCORE_PROMPT},
                      {"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(img).decode()}}]}],
                  "generationConfig": {"responseMimeType": "application/json"}},
            timeout=60)
        r.raise_for_status()
        return int(json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]).get("badness", 0))
    except Exception:
        return 0


def to_row(l: dict) -> dict:
    stake = round((l.get("nightly_rate") or 0) * (l.get("open_nights_90d") or 0), 2)
    channel = _contact_channel(l.get("host_email"))
    return {
        "listing_id":            l.get("listing_id"),
        "url":                   (l.get("url") or "").split("?")[0],
        "title":                 (l.get("title") or "")[:80],
        "city":                  l.get("location") or "",
        "nightly_rate_gbp":      l.get("nightly_rate"),
        "occupancy_pct":         l.get("occupancy_pct"),
        "open_nights_90d":       l.get("open_nights_90d"),
        "revenue_at_stake_gbp":  stake,
        "host_name":             l.get("host_name"),
        "host_email":            l.get("host_email") or "",
        "email_source":          l.get("host_email_source") or "",
        "contact_channel":       channel,
        "superhost":             "YES" if l.get("host_is_superhost") else "no",
        "reviews":               l.get("host_review_count") or 0,
        "rating":                l.get("host_rating_avg") or "",
        "photo_count":           len(l.get("image_urls") or []),
        "cover_photo_url":       (l.get("image_urls") or [""])[0],
        "image_urls_json":       json.dumps(l.get("image_urls") or []),
        "status":                "Scraped",
        "date_scraped":          date.today().isoformat(),
        "notes":                 (f"photo_priority={l['photo_priority']}"
                                  if l.get("photo_priority") is not None else ""),
    }


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "Manchester, United Kingdom"
    n      = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    seen = load_seen_ids()
    print(f"[step1] {market} | max {n} | {len(seen)} already in tracker")

    listings = scrape_location(market, max_listings=n, calendar_months=CAL_MONTHS)

    qualified, rejected, dupes = [], [], []
    for l in listings:
        if l.get("listing_id") in seen:
            dupes.append(l); continue
        ok, why = qualify(l)
        (qualified if ok else rejected).append((l, why))

    # Cohort floor (brain rule 2026-07-15): market medians from thin cohorts
    # destroy credibility. <10 listings = hard stop; <20 = loud warning.
    if len(listings) < 10:
        print(f"\n[step1] HARD STOP: only {len(listings)} listings scraped — a market "
              f"median from <10 points is a guess. Scrape at least 20 (ask for more).")
        sys.exit(1)
    if len(listings) < 20:
        print(f"[step1] WARNING: cohort of {len(listings)} < 20 — Step 2 will suppress "
              f"market-median claims in hooks/copy.")

    # Photo-quality priority score (brain rule 2026-07-15): bad original photos
    # = biggest before/after delta = best conversion. Score cover photo 0-10
    # (10 = terrible photos = TOP priority). Cheap vision call, skip on failure.
    for l, _ in qualified:
        l["photo_priority"] = score_cover_photo(l)

    qualified.sort(key=lambda t: -(t[0].get("photo_priority") or 0))
    rows = [to_row(l) for l, _ in qualified]

    # Append to tracker CSV (source of truth for dedup; mirror to Google Sheet manually/via sync)
    TRACKER_CSV.parent.mkdir(exist_ok=True)
    write_header = not TRACKER_CSV.exists()
    if rows:
        # Use EXISTING header order when appending to avoid column-shift bugs
        if not write_header:
            with open(TRACKER_CSV, newline="") as rf:
                existing_fields = next(csv.reader(rf))
            # Add any new fields from new rows that aren't in the old header
            for k in rows[0].keys():
                if k not in existing_fields:
                    existing_fields.append(k)
            fieldnames = existing_fields
        else:
            fieldnames = list(rows[0].keys())
        with open(TRACKER_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerows(rows)

    out_json = Path(__file__).parent / "work" / "step1_qualified.json"
    with open(out_json, "w") as f:
        json.dump([l for l, _ in qualified], f, indent=2)

    # Full cohort (qualified + rejected + dupes) — the market benchmark pool
    # for Step 2. Rejected listings are still real market data points.
    cohort_json = Path(__file__).parent / "work" / "step1_cohort.json"
    with open(cohort_json, "w") as f:
        json.dump(listings, f, indent=2)

    print(f"\n[step1] RESULTS: {len(qualified)} qualified, {len(rejected)} rejected, {len(dupes)} dupes")
    for l, why in qualified:
        ch = "email:" + l.get("host_email", "") if l.get("host_email") else "airbnb_dm"
        print(f"  ✓ {l['listing_id']} | {l.get('host_name')} | {why} | contact={ch}")
    for l, why in rejected:
        print(f"  ✗ {l['listing_id']} | {l.get('host_name')} | {why}")
    print(f"\n[step1] Qualified leads -> {out_json}")
    print(f"[step1] Tracker -> {TRACKER_CSV}")


if __name__ == "__main__":
    main()
