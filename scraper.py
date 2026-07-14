"""
scraper.py — Airbnb data harvester (Apify-backed, ML-aware)

Intra-process learning:
  - After each scrape, emits signals about what it found
    (title length, amenity richness, image count, rating sub-scores)
  - Reads strategy to know which fields to prioritize / validate harder

Inter-process contributions:
  - Emits high_rated_title_length → Generator learns preferred title length
  - Emits top_amenity_category → Generator learns what amenities to recommend
  - Emits occupancy_signal → Analyzer uses as ground truth for "success"
  - Emits scrape_cost → System learns cost per field to optimize future runs

Usage:
  python scraper.py <airbnb_url>            # single listing
  python scraper.py --location "Bali" --max 10  # market scan
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import re
import urllib.parse

import requests
from dotenv import load_dotenv

import learning_store as ls

# ---------------------------------------------------------------------------
# Email enrichment — 100% free, no API keys
# ---------------------------------------------------------------------------

_EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.I)
_URL_RE    = re.compile(r"https?://[^\s\"'<>]+", re.I)
_SCRAPE_TIMEOUT = 8   # seconds per HTTP request

_CONTACT_PATHS = [
    "", "/contact", "/contact-us", "/about", "/about-us",
    "/get-in-touch", "/reach-us", "/info",
]


def _emails_from_text(text: str) -> list[str]:
    """Return all email addresses found in a string, lower-cased and deduped."""
    return list({m.lower() for m in _EMAIL_RE.findall(text or "")})


def _emails_from_url(url: str) -> list[str]:
    """
    Fetch a URL and up to a few contact sub-paths; return all emails found.
    Skips social-media domains — they never expose host emails.
    """
    skip_domains = {
        "facebook.com", "instagram.com", "twitter.com", "x.com",
        "tiktok.com", "linkedin.com", "youtube.com", "airbnb.com",
        "google.com", "pinterest.com",
    }
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
        if any(domain == s or domain.endswith("." + s) for s in skip_domains):
            return []

        base = f"{parsed.scheme}://{parsed.netloc}"
        found: set[str] = set()

        headers = {"User-Agent": "Mozilla/5.0 (compatible; ListingBoost/1.0)"}
        for path in _CONTACT_PATHS:
            try:
                resp = requests.get(base + path, headers=headers,
                                    timeout=_SCRAPE_TIMEOUT, allow_redirects=True)
                if resp.ok:
                    found.update(m.lower() for m in _EMAIL_RE.findall(resp.text))
                if found:          # stop as soon as we find something
                    break
            except Exception:
                continue

        # Filter out common false positives (image filenames, CSS vars, etc.)
        noise = {"example.com", "domain.com", "email.com", "sentry.io",
                 "noreply", "no-reply", "support@airbnb", "help@"}
        return [e for e in found
                if not any(n in e for n in noise) and len(e) < 80]

    except Exception:
        return []


def _apollo_find_email(host_name: str, location: str) -> str | None:
    """
    Apollo People Match — burns 1 export credit per hit.
    Only called when free methods fail AND caller explicitly passes use_apollo=True.
    Requires APOLLO_API_KEY in env.
    """
    api_key = os.environ.get("APOLLO_API_KEY", "")
    if not api_key:
        return None

    first, *rest = host_name.strip().split(" ", 1)
    last = rest[0] if rest else ""

    try:
        resp = requests.post(
            "https://api.apollo.io/v1/people/match",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={
                "first_name": first,
                "last_name":  last,
                "location":   location,
                "reveal_personal_emails": True,
            },
            timeout=15,
        )
        if not resp.ok:
            return None
        data = resp.json()
        person = data.get("person") or {}
        email = person.get("email")
        if email and "@" in email and "apollo.io" not in email:
            return email.lower()
    except Exception:
        pass
    return None


def enrich_host_email(listing: dict, use_apollo: bool = False) -> dict:
    """
    Find the host's email address via a 3-tier waterfall:
      1. Regex the host bio directly                 (free, instant)
      2. Scrape their website if URL in bio          (free, ~2–5s)
      3. Apollo People Match                         (costs 1 credit — only if use_apollo=True)

    Adds to listing:
      host_email          — best email found (or None)
      host_email_source   — 'bio_direct' | 'website_scraped' | 'apollo' | None
      host_website        — first website URL found in bio (or None)

    Never overwrites an existing host_email.
    """
    if listing.get("host_email"):
        return listing

    bio      = listing.get("host_about") or ""
    location = listing.get("location") or ""

    # Tier 1: email directly in bio
    bio_emails = _emails_from_text(bio)
    if bio_emails:
        listing["host_email"]        = bio_emails[0]
        listing["host_email_source"] = "bio_direct"
        listing.setdefault("host_website", None)
        print(f"  [enrich] email from bio: {bio_emails[0]}")
        return listing

    # Tier 2: URL in bio → scrape for contact email
    urls = _URL_RE.findall(bio)
    if urls:
        listing["host_website"] = urls[0]
        for url in urls[:3]:
            site_emails = _emails_from_url(url)
            if site_emails:
                listing["host_email"]        = site_emails[0]
                listing["host_email_source"] = "website_scraped"
                print(f"  [enrich] email from website ({url}): {site_emails[0]}")
                return listing
    else:
        listing.setdefault("host_website", None)

    # Tier 3: Apollo fallback — only when explicitly requested
    if use_apollo:
        host_name = listing.get("host_name") or ""
        if host_name:
            email = _apollo_find_email(host_name, location)
            if email:
                listing["host_email"]        = email
                listing["host_email_source"] = "apollo"
                print(f"  [enrich] email from Apollo: {email}  (1 credit used)")
                return listing
            print(f"  [enrich] Apollo: no match for {host_name!r} in {location!r}")

    listing["host_email"]        = None
    listing["host_email_source"] = None
    print(f"  [enrich] no email found for host: {listing.get('host_name', '?')}")
    return listing

load_dotenv()

APIFY_KEY = os.getenv("APIFY_API_KEY", "")
ACTOR_ID  = "automation-lab~airbnb-listing"
APIFY_BASE = "https://api.apify.com/v2"


# ---------------------------------------------------------------------------
# Apify helpers
# ---------------------------------------------------------------------------

def _run_actor(input_payload: dict, timeout_secs: int = 120) -> dict:
    """Fire Apify actor, poll until done, return raw dataset items."""
    headers = {"Authorization": f"Bearer {APIFY_KEY}", "Content-Type": "application/json"}

    # Start run
    r = requests.post(
        f"{APIFY_BASE}/acts/{ACTOR_ID}/runs",
        headers=headers,
        json=input_payload,
        timeout=30
    )
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    print(f"  [scraper] Apify run started: {run_id}")

    # Poll until terminal
    deadline = time.time() + max(timeout_secs, 900)   # min 15min; large city batches need it
    while time.time() < deadline:
        time.sleep(4)
        status_r = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}", headers=headers, timeout=10)
        status_r.raise_for_status()
        status = status_r.json()["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify run {run_id} ended with status {status}")
    else:
        # Loop exhausted without SUCCEEDED — never return a partial dataset
        raise RuntimeError(f"Apify run {run_id} still {status} after {timeout_secs}s — "
                           "raise timeout_secs or check the run in Apify console")

    # Fetch dataset — paginated, never silently capped
    dataset_id = status_r.json()["data"]["defaultDatasetId"]
    items, offset = [], 0
    while True:
        items_r = requests.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items?clean=true&limit=500&offset={offset}",
            headers=headers, timeout=30)
        items_r.raise_for_status()
        page = items_r.json()
        items.extend(page)
        if len(page) < 500:
            break
        offset += 500

    cost_usd = 0.00009 + len(items) * 0.0045  # actor start + per listing
    ls.emit("scraper", "scrape_cost_usd", cost_usd, {"run_id": run_id, "items": len(items)})

    return items


# ---------------------------------------------------------------------------
# Signal extraction — this is the intra-process ML layer
# ---------------------------------------------------------------------------

def _emit_listing_signals(listing: dict):
    """After scraping, emit signals that the rest of the pipeline can learn from."""
    lid = listing.get("id", "unknown")
    rating_avg = (listing.get("rating") or {}).get("guestSatisfaction")

    # Title quality signal
    title = listing.get("title", "") or ""
    if title and rating_avg and rating_avg >= 4.8:
        ls.emit("scraper", "high_rated_title_length", len(title),
                {"listing_id": lid, "rating": rating_avg})

    # Amenity richness
    amenities = listing.get("amenities") or []
    available_count = sum(
        1 for cat in amenities for v in (cat.get("values") or []) if v.get("available")
    )
    missing_count = sum(
        1 for cat in amenities for v in (cat.get("values") or []) if not v.get("available")
    )
    ls.emit("scraper", "amenity_available_count", available_count, {"listing_id": lid})
    ls.emit("scraper", "amenity_missing_count", missing_count, {"listing_id": lid})

    # Top amenity categories in high-rated listings
    if rating_avg and rating_avg >= 4.7:
        for cat in amenities:
            cat_title = cat.get("title", "")
            has_any = any(v.get("available") for v in (cat.get("values") or []))
            if has_any and cat_title not in ("Not included",):
                ls.emit("scraper", "top_amenity_category", None, {"category": cat_title})

    # Image richness signal
    images = listing.get("images") or []
    ls.emit("scraper", "image_count", len(images), {"listing_id": lid})
    room_types = list({img.get("caption", "").split(" image")[0] for img in images})
    ls.emit("scraper", "image_room_type_count", len(room_types),
            {"listing_id": lid, "room_types": room_types})

    # Occupancy signal (from calendar — booked days / total days)
    calendar = listing.get("calendar") or []
    if calendar:
        booked = sum(1 for d in calendar if not d.get("available"))
        occ_rate = booked / len(calendar)
        ls.emit("scraper", "occupancy_rate", occ_rate, {"listing_id": lid})

    # Description length
    desc = listing.get("description") or ""
    ls.emit("scraper", "description_length", len(desc), {"listing_id": lid})

    # Superhost signal
    is_super = listing.get("isSuperHost", False)
    ls.emit("scraper", "is_superhost", 1 if is_super else 0, {"listing_id": lid})


# ---------------------------------------------------------------------------
# Parsed listing — clean structured output
# ---------------------------------------------------------------------------

def parse_listing(raw: dict) -> dict:
    """Normalize raw Apify output into clean listing dict. Read strategy to know what to prioritize."""
    priority_fields = ls.get_strategy("scraper", "priority_fields",
                                      default=["title", "description", "amenities", "images", "rating"])

    amenities = raw.get("amenities") or []
    available_amenities = [
        {"category": cat.get("title"), "name": v.get("title"), "subtitle": v.get("subtitle", "")}
        for cat in amenities for v in (cat.get("values") or []) if v.get("available")
    ]
    missing_amenities = [
        {"category": cat.get("title"), "name": v.get("title")}
        for cat in amenities for v in (cat.get("values") or []) if not v.get("available")
        and cat.get("title") == "Not included"
    ]

    images = raw.get("images") or []
    images_by_room: dict[str, list[str]] = {}
    for img in images:
        caption = img.get("caption", "Additional photos")
        room = caption.split(" image")[0].strip().title()
        images_by_room.setdefault(room, []).append(img.get("imageUrl", ""))

    rating = raw.get("rating") or {}
    host   = raw.get("host") or {}
    coords = raw.get("coordinates") or {}

    calendar = raw.get("calendar") or []
    booked_days   = sum(1 for d in calendar if not d.get("available"))
    occupancy_pct = round(booked_days / len(calendar) * 100, 1) if calendar else None
    # Extrapolate open nights over the next 90 days from the scraped calendar window.
    # Honest only with calendar_months>=3 (90d window); with 1 month it's a projection.
    open_nights_90d = round((1 - occupancy_pct / 100) * 90) if occupancy_pct is not None else None

    # Nightly rate — extract from automation-lab/airbnb-listing output.
    # The actor returns price as a dict with string values (e.g. "£1,209.20").
    # Primary source: price.breakDown.basePrice.description = "N nights x £X.XX"
    # Fallback: calendar daily prices (when available).
    # Never fall back to a default — leave as None if unverifiable.
    nightly_rate = None
    _price_dict = raw.get("price") or {}
    if isinstance(_price_dict, (int, float)):
        nightly_rate = float(_price_dict)
    elif isinstance(_price_dict, dict):
        # Try "N nights x £X.XX" description first (most reliable)
        _bp_desc = ((_price_dict.get("breakDown") or {})
                    .get("basePrice") or {}).get("description", "")
        _per_night_match = re.search(r"x\s*[£$€]?([\d,]+(?:\.\d+)?)", _bp_desc)
        if _per_night_match:
            nightly_rate = float(_per_night_match.group(1).replace(",", ""))
        else:
            # Try calendar daily prices (null when no checkin/checkout given)
            _cal_prices = [
                float(re.sub(r"[^\d.]", "", str(d["price"])))
                for d in (raw.get("calendar") or [])
                if d.get("price") and d.get("available")
            ]
            if _cal_prices:
                nightly_rate = round(sum(_cal_prices) / len(_cal_prices), 2)
            else:
                # Last resort: strip currency symbol from price.price string
                _price_str = _price_dict.get("price") or ""
                _nights_match = re.search(r"for\s+(\d+)\s+night", _price_str, re.I)
                _amt_match = re.search(r"[£$€]?([\d,]+(?:\.\d+)?)", _price_str)
                if _amt_match and _nights_match:
                    nightly_rate = round(
                        float(_amt_match.group(1).replace(",", "")) /
                        int(_nights_match.group(1)), 2
                    )

    listing = {
        # Identity
        "listing_id":         raw.get("id"),
        "url":                raw.get("url"),
        "scraped_at":         datetime.utcnow().isoformat(),

        # Content
        "title":              raw.get("title") or raw.get("seoTitle", ""),
        "description":        raw.get("description", ""),
        "seo_title":          raw.get("seoTitle", ""),
        "meta_description":   raw.get("metaDescription", ""),
        "sub_description":    raw.get("subDescription", {}).get("title", ""),

        # Property
        "property_type":      raw.get("propertyType", ""),
        "room_type":          raw.get("roomType", ""),
        "person_capacity":    raw.get("personCapacity"),
        "min_nights":         raw.get("minNights"),
        "max_nights":         raw.get("maxNights"),

        # Location
        "location":           raw.get("location", ""),
        "location_subtitle":  raw.get("locationSubtitle", ""),
        "latitude":           coords.get("latitude"),
        "longitude":          coords.get("longitude"),

        # Ratings
        "rating_overall":     rating.get("guestSatisfaction"),
        "rating_accuracy":    rating.get("accuracy"),
        "rating_checkin":     rating.get("checking"),
        "rating_cleanliness": rating.get("cleanliness"),
        "rating_communication": rating.get("communication"),
        "rating_location":    rating.get("location"),
        "rating_value":       rating.get("value"),
        "review_count":       rating.get("reviewsCount"),

        # Host
        "host_id":            host.get("id"),
        "host_name":          host.get("name"),
        "host_is_superhost":  host.get("isSuperHost"),
        "host_is_verified":   host.get("isVerified"),
        "host_rating_avg":    host.get("ratingAverage"),
        "host_review_count":  host.get("ratingCount"),
        "host_years":         host.get("timeAsHost", {}).get("years"),
        "host_about":         host.get("about", ""),

        # Amenities
        "amenities_available":        available_amenities,
        "amenities_missing":          missing_amenities,
        "amenities_available_count":  len(available_amenities),
        "amenities_missing_count":    len(missing_amenities),

        # Images
        "images_by_room":     images_by_room,
        "image_urls":         [img.get("imageUrl", "") for img in images if img.get("imageUrl")],
        "image_total_count":  len(images),
        "thumbnail":          raw.get("thumbnail", ""),

        # Availability / occupancy
        "occupancy_pct":      occupancy_pct,
        "open_nights_90d":    open_nights_90d,
        "nightly_rate":       nightly_rate,   # None if Apify didn't return a price
        "calendar_days":      len(calendar),
        "check_in_time":      raw.get("checkIn"),
        "check_out_time":     raw.get("checkOut"),

        # House rules
        "house_rules":        raw.get("houseRules", {}),

        # ML columns (pre-wired, populated by downstream processes)
        "ml_title_score":          None,  # Generator fills
        "ml_desc_score":           None,  # Analyzer fills
        "ml_amenity_gap_score":    None,  # Analyzer fills
        "ml_image_quality_score":  None,  # Analyzer fills
        "ml_occupancy_predicted":  None,  # Generator fills after optimization
        "ml_generated_title":      None,  # Generator fills
        "ml_generated_desc":       None,  # Generator fills
        "ml_outcome_delta":        None,  # Outcome fills (actual improvement)
        "ml_client_feedback":      None,  # Delivery fills
        "ml_version":              1,

        # Strategy snapshot — what rules were applied this run
        "strategy_snapshot": {
            "priority_fields": priority_fields,
            "preferred_title_length": ls.get_strategy("generator", "preferred_title_length"),
            "high_value_amenities": ls.get_strategy("generator", "high_value_amenity_categories"),
        }
    }

    # Emit signals for inter-process learning
    _emit_listing_signals(raw)

    return listing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_url(url: str, calendar_months: int = 3,
               currency: str = "GBP", locale: str = "en-GB") -> dict:
    """Scrape a single Airbnb listing URL. Returns parsed listing dict."""
    print(f"[scraper] Scraping: {url}")
    items = _run_actor({
        "startUrls": [{"url": url}],
        "skipDetailPages": False,
        "calendarMonths": calendar_months,
        "maxListings": 1,
        "locale": locale,
        "currency": currency,
    })
    if not items:
        raise ValueError(f"No data returned for {url}")

    listing = parse_listing(items[0])
    enrich_host_email(listing)
    print(f"[scraper] Done: {listing['listing_id']} — {listing['title'][:60]}")
    return listing


def scrape_location(location: str, max_listings: int = 50,
                    calendar_months: int = 1,
                    currency: str = "GBP", locale: str = "en-GB") -> list[dict]:
    """Scrape all listings for a market/location. Returns list of parsed listings."""
    print(f"[scraper] Market scan: {location} (max {max_listings})")
    items = _run_actor({
        "locationQueries": [location],
        "skipDetailPages": False,
        "calendarMonths": calendar_months,
        "maxListings": max_listings,
        "locale": locale,
        "currency": currency,
    })
    listings = [parse_listing(item) for item in items]
    for listing in listings:
        enrich_host_email(listing)

    # After batch scrape, recompute strategies from accumulated signals
    ls.recompute_all_strategies()
    print(f"[scraper] Market scan complete: {len(listings)} listings. Strategies updated.")
    return listings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ListingBoost Airbnb Scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("url", nargs="?", help="Single Airbnb listing URL")
    group.add_argument("--location", help="Market location to scan (e.g. 'Bali')")
    parser.add_argument("--max", type=int, default=10, help="Max listings for market scan")
    parser.add_argument("--calendar", type=int, default=3, help="Months of calendar data")
    parser.add_argument("--out", default="scraped_listing.json", help="Output JSON path")
    args = parser.parse_args()

    if args.url:
        result = scrape_url(args.url, calendar_months=args.calendar)
        results = [result]
    else:
        results = scrape_location(args.location, max_listings=args.max,
                                  calendar_months=args.calendar)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n[scraper] Saved {len(results)} listing(s) → {out_path}")
