"""
teardown.py - ListingBoost core product engine

Given a scraped listing dict (from scraper.py), produces:
  1. Scored teardown  - title/desc/amenity/image/occupancy scores (1-10 each)
  2. Rewritten title  - 3 variants, optimized for Airbnb search + conversion
  3. Rewritten desc   - full rewrite using learned strategy params
  4. Amenity gaps     - top missing amenities vs. comparable high-performers
  5. Photo order rec  - which room type should lead and why
  6. Occupancy math   - their own data: rate x open nights = $ at stake
  7. PDF report       - via gap_analysis_pdf_generator.py

One Claude call does the whole analysis + generation (cost: ~$0.01-0.03 per listing).
ML signals emitted after every run - outreach angle used, scores, variants tried.

Intra-process learning:
  - Reads strategy("preferred_title_length") and ("high_value_amenity_categories")
    from learning_store before generating
  - Emits title_score, desc_score, amenity_gap_score after each run

Inter-process learning:
  - outreach.angle emitted here -> reply_tracker reads it to correlate with reply rate
  - ml_title_score written to listing dict -> sheet_writer stores for future correlation

Usage:
  python teardown.py <airbnb_url>                    # scrape + teardown + PDF
  python teardown.py --json scraped_listing.json     # teardown from existing scrape
  python teardown.py --demo                          # run on test listing 20669368

  from teardown import run_teardown
  result = run_teardown(listing_dict)
  # result.pdf_path, result.scores, result.rewritten_title, result.rewritten_desc
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import learning_store as ls

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OUTPUT_DIR        = Path("/tmp/listingboost_teardowns")
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class TeardownResult:
    listing_id: str
    listing_url: str
    title_original: str
    desc_original: str

    score_title: int = 0
    score_desc: int = 0
    score_amenities: int = 0
    score_images: int = 0
    score_occupancy_signal: int = 0

    title_variants: list = field(default_factory=list)
    rewritten_desc: str = ""
    top_amenity_gaps: list = field(default_factory=list)
    photo_order_rec: str = ""
    key_diagnosis: list = field(default_factory=list)

    occupancy_pct: float = 0.0
    nightly_rate: float = 0.0
    open_nights_90d: int = 0
    revenue_at_stake_90d: float = 0.0

    outreach_angle: str = ""
    pdf_path: str = ""
    json_path: str = ""
    raw_analysis: dict = field(default_factory=dict)


SYSTEM_PROMPT = """You are an elite Airbnb listing optimization expert.
You analyze listings with surgical precision - finding the 3 specific, concrete
fixes that will have the biggest impact on bookings.

Rules:
- Every diagnosis must be specific and verifiable from the data provided
- Never invent stats or claim market benchmarks you don't have
- Scores are honest: a 4.9-rated Superhost listing might still score 4/10 on title
- Title variants must be under 50 characters each
- Rewritten description must keep all factual information intact
- Revenue estimates use ONLY the host's own nightly rate x open calendar days"""

ANALYSIS_PROMPT = """Analyze this Airbnb listing and return a JSON object with exactly this structure.

LISTING DATA:
Title: {title}
Description: {description}
Property type: {property_type}
Location: {location}
Rating: {rating_overall} ({review_count} reviews)
Nightly rate: ${nightly_rate}
Capacity: {person_capacity} guests
Superhost: {is_superhost}
Occupancy (next 90 days): {occupancy_pct}% booked ({open_nights} open nights)

AMENITIES AVAILABLE: {amenities_available}
AMENITIES MISSING: {amenities_missing}

IMAGES (labeled by room type): {image_rooms}

HOST: {host_name}, {host_years} years hosting, {host_rating_avg} avg rating

LEARNED STRATEGY (apply this):
- Preferred title length: {preferred_title_length} chars
- High-value amenity categories: {high_value_amenity_categories}

Return ONLY this JSON (no markdown, no explanation):
{{
  "score_title": <1-10, be honest>,
  "score_desc": <1-10>,
  "score_amenities": <1-10, based on available vs missing>,
  "score_images": <1-10, based on room coverage and lead photo>,
  "score_occupancy_signal": <1-10, where 10 means huge room to improve occupancy>,
  "title_variants": [
    "<variant 1, under 50 chars, leads with strongest differentiator>",
    "<variant 2, under 50 chars, different angle>",
    "<variant 3, under 50 chars, different angle>"
  ],
  "rewritten_desc": "<full rewritten description, same facts, much more compelling, 200-300 words>",
  "top_amenity_gaps": [
    "<most impactful missing or under-presented amenity>",
    "<second>",
    "<third>"
  ],
  "photo_order_rec": "<which room type should be the cover photo and why, 1-2 sentences>",
  "key_diagnosis": [
    "<specific fix #1 - concrete, actionable, tied to this listing's actual data>",
    "<specific fix #2>",
    "<specific fix #3>"
  ],
  "outreach_angle": "<one of: occupancy | amenity_gap | title_seo | image_order>",
  "outreach_hook": "<one sentence that leads outreach email - uses their own numbers, no fabricated stats>"
}}"""


def _call_claude(prompt: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _call_openai(prompt: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _analyze(listing: dict) -> dict:
    preferred_title_length = ls.get_strategy("generator", "preferred_title_length", default=50)
    high_value_amenity_categories = ls.get_strategy(
        "generator", "high_value_amenity_categories",
        default=["Outdoor", "Parking and facilities", "Entertainment"]
    )

    occupancy_pct = listing.get("occupancy_pct") or 0
    nightly_rate  = listing.get("nightly_rate") or listing.get("price_per_night") or 0
    calendar_days = listing.get("calendar_days") or 90
    open_nights   = round(calendar_days * (1 - occupancy_pct / 100)) if occupancy_pct else None

    amenities_available = listing.get("amenities_available") or []
    amenities_missing   = listing.get("amenities_missing") or []
    avail_names = [a.get("name", "") for a in amenities_available if isinstance(a, dict)][:20]
    miss_names  = [a.get("name", "") for a in amenities_missing  if isinstance(a, dict)][:10]

    images_by_room = listing.get("images_by_room") or {}
    image_rooms = list(images_by_room.keys())

    title = listing.get("title") or listing.get("seo_title") or ""

    prompt = ANALYSIS_PROMPT.format(
        title=title,
        description=(listing.get("description") or "")[:1500],
        property_type=listing.get("property_type", ""),
        location=listing.get("location_subtitle") or listing.get("location", ""),
        rating_overall=listing.get("rating_overall", "N/A"),
        review_count=listing.get("review_count", 0),
        nightly_rate=nightly_rate or "unknown",
        person_capacity=listing.get("person_capacity", ""),
        is_superhost=listing.get("host_is_superhost", False),
        occupancy_pct=round(occupancy_pct, 1),
        open_nights=open_nights or "unknown",
        amenities_available=", ".join(avail_names) or "none listed",
        amenities_missing=", ".join(miss_names) or "none listed",
        image_rooms=", ".join(image_rooms) or "unknown",
        host_name=listing.get("host_name", ""),
        host_years=listing.get("host_years", ""),
        host_rating_avg=listing.get("host_rating_avg", ""),
        preferred_title_length=preferred_title_length,
        high_value_amenity_categories=", ".join(high_value_amenity_categories),
    )

    try:
        return _call_claude(prompt)
    except Exception as e:
        print(f"  [teardown] Claude failed ({e}), trying OpenAI fallback...")
        return _call_openai(prompt)


def _render_pdf(listing: dict, result: TeardownResult, image_result=None) -> str:
    try:
        from gap_analysis_pdf_generator import GapAnalysisPDFGenerator

        nightly_rate = listing.get("nightly_rate") or listing.get("price_per_night") or 0
        occupancy_pct = listing.get("occupancy_pct") or 0
        calendar_days = listing.get("calendar_days") or 90
        open_nights   = round(calendar_days * (1 - occupancy_pct / 100))
        revenue_at_stake = round(open_nights * nightly_rate)

        property_data = {
            "name": result.title_original or listing.get("seo_title", f"Listing {result.listing_id}"),
            "location": listing.get("location_subtitle") or listing.get("location", ""),
            "price_per_night": nightly_rate,
            "current_amenities": [
                a.get("name") for a in (listing.get("amenities_available") or [])
                if isinstance(a, dict)
            ],
        }

        image_section = {}
        if image_result:
            image_section = {
                "image_score": image_result.ml_image_quality_score,
                "cover_is_wrong": image_result.cover_is_wrong,
                "current_cover_room": image_result.current_cover_room,
                "recommended_cover_room": image_result.cover_room,
                "image_key_finding": image_result.key_finding,
                "retake_rooms": image_result.retake_rooms,
                "remove_count": len(image_result.remove_urls),
                "photo_dir": analysis.get("photo_dir", ""),
                "manifest_csv": analysis.get("manifest_path", ""),
            }

        analysis_data = {
            "missing_amenities": [
                {"amenity": gap, "booking_increase": 0, "annual_loss": 0}
                for gap in result.top_amenity_gaps
            ],
            "estimated_annual_loss": revenue_at_stake,
            "booking_increase_potential": max(0, round((100 - occupancy_pct) * 0.3)),
            "recommendations": result.key_diagnosis,
            "title_score": result.score_title,
            "desc_score": result.score_desc,
            "title_variants": result.title_variants,
            "rewritten_desc": result.rewritten_desc,
            "photo_order_rec": result.photo_order_rec,
            "open_nights": open_nights,
            "revenue_at_stake": revenue_at_stake,
            **image_section,
        }

        gen = GapAnalysisPDFGenerator(output_dir=str(OUTPUT_DIR))
        host_name = listing.get("host_name", "Host")
        pdf_path = gen.generate(host_name, property_data, analysis_data)
        return pdf_path or ""

    except ImportError as e:
        print(f"  [teardown] PDF skipped - reportlab not installed: {e}")
        return ""
    except Exception as e:
        print(f"  [teardown] PDF generation failed: {e}")
        return ""


def _emit_signals(listing: dict, result: TeardownResult):
    lid = result.listing_id
    ls.emit("analyzer", "title_score",       result.score_title,      {"listing_id": lid})
    ls.emit("analyzer", "desc_score",        result.score_desc,       {"listing_id": lid})
    ls.emit("analyzer", "amenity_gap_score", result.score_amenities,  {"listing_id": lid})
    ls.emit("analyzer", "image_score",       result.score_images,     {"listing_id": lid})
    ls.emit("generator", "title_variant_count", len(result.title_variants), {"listing_id": lid})
    ls.emit("generator", "outreach_angle", None, {
        "listing_id": lid,
        "angle": result.outreach_angle,
        "occupancy_pct": result.occupancy_pct,
    })
    ls.emit("outreach", "teardown_ready", 1, {
        "listing_id": lid,
        "outreach_angle": result.outreach_angle,
        "outreach_hook": result.raw_analysis.get("outreach_hook", ""),
        "title_score": result.score_title,
        "desc_score": result.score_desc,
    })


def run_teardown(listing: dict, analyze_images: bool = True) -> TeardownResult:
    """
    Main entry point. Takes a parsed listing dict (from scraper.py)
    and returns a fully populated TeardownResult.

    analyze_images=True runs image_analyzer.py as a second Claude Vision call
    and wires the image outreach hook + enhanced photos into the result.
    """
    lid = listing.get("listing_id", "unknown")
    print(f"\n[teardown] Analyzing listing {lid}...")

    print("  [teardown] Calling Claude for analysis + rewrite...")
    analysis = _analyze(listing)

    occupancy_pct = listing.get("occupancy_pct") or 0
    nightly_rate  = listing.get("nightly_rate") or listing.get("price_per_night") or 0
    calendar_days = listing.get("calendar_days") or 90
    open_nights   = round(calendar_days * (1 - occupancy_pct / 100))
    revenue_at_stake = round(open_nights * nightly_rate)

    title_original = listing.get("title") or listing.get("seo_title") or ""

    result = TeardownResult(
        listing_id=lid,
        listing_url=listing.get("url", ""),
        title_original=title_original,
        desc_original=listing.get("description", ""),
        score_title=analysis.get("score_title", 0),
        score_desc=analysis.get("score_desc", 0),
        score_amenities=analysis.get("score_amenities", 0),
        score_images=analysis.get("score_images", 0),
        score_occupancy_signal=analysis.get("score_occupancy_signal", 0),
        title_variants=analysis.get("title_variants", []),
        rewritten_desc=analysis.get("rewritten_desc", ""),
        top_amenity_gaps=analysis.get("top_amenity_gaps", []),
        photo_order_rec=analysis.get("photo_order_rec", ""),
        key_diagnosis=analysis.get("key_diagnosis", []),
        occupancy_pct=occupancy_pct,
        nightly_rate=nightly_rate,
        open_nights_90d=open_nights,
        revenue_at_stake_90d=revenue_at_stake,
        outreach_angle=analysis.get("outreach_angle", ""),
        raw_analysis=analysis,
    )

    # Stage 2: Image Vision audit + download + organize
    image_result = None
    if analyze_images and listing.get("images_by_room"):
        try:
            from image_analyzer import analyze_images as _analyze_images
            from image_organizer import organize_listing_photos
            image_result = _analyze_images(listing)
            result.score_images = image_result.ml_image_quality_score
            # Wire image hook into outreach if cover is wrong (most actionable)
            if image_result.cover_is_wrong and image_result.outreach_hook:
                analysis["image_outreach_hook"] = image_result.outreach_hook
                analysis["image_key_finding"] = image_result.key_finding
                analysis["cover_is_wrong"] = True
                analysis["recommended_cover_room"] = image_result.cover_room
                analysis["current_cover_room"] = image_result.current_cover_room
            # Download + organize photos (no editing)
            manifest_path, photo_dir = organize_listing_photos(listing, image_result)
            analysis["manifest_path"] = manifest_path
            analysis["photo_dir"] = photo_dir
        except Exception as e:
            print(f"  [teardown] Image analysis failed (non-fatal): {e}")

    print("  [teardown] Generating PDF report...")
    result.pdf_path = _render_pdf(listing, result, image_result=image_result)

    json_path = OUTPUT_DIR / f"teardown_{lid}.json"
    json_path.write_text(json.dumps({
        "listing_id": lid,
        "listing_url": result.listing_url,
        "generated_at": datetime.utcnow().isoformat(),
        "host_name": listing.get("host_name", ""),
        "location": listing.get("location_subtitle") or listing.get("location", ""),
        "scores": {
            "title": result.score_title,
            "description": result.score_desc,
            "amenities": result.score_amenities,
            "images": result.score_images,
            "occupancy_improvement_potential": result.score_occupancy_signal,
        },
        "title_original": result.title_original,
        "title_variants": result.title_variants,
        "description_original": (result.desc_original or "")[:300] + "...",
        "rewritten_desc": result.rewritten_desc,
        "top_amenity_gaps": result.top_amenity_gaps,
        "photo_order_rec": result.photo_order_rec,
        "key_diagnosis": result.key_diagnosis,
        "occupancy_math": {
            "occupancy_pct": occupancy_pct,
            "nightly_rate": nightly_rate,
            "open_nights_90d": open_nights,
            "revenue_at_stake_90d": revenue_at_stake,
            "note": "Derived from host's own calendar data - not a market estimate"
        },
        "outreach": {
            "angle": result.outreach_angle,
            "hook": analysis.get("outreach_hook", ""),
            "image_hook": analysis.get("image_outreach_hook", ""),
            "cover_is_wrong": analysis.get("cover_is_wrong", False),
            "recommended_cover_room": analysis.get("recommended_cover_room", ""),
            "current_cover_room": analysis.get("current_cover_room", ""),
        },
        "image_analysis_path": str(OUTPUT_DIR / f"image_analysis_{lid}.json") if image_result else "",
        "photo_dir": analysis.get("photo_dir", ""),
        "manifest_csv": analysis.get("manifest_path", ""),
        "pdf_path": result.pdf_path,
    }, indent=2))
    result.json_path = str(json_path)

    _emit_signals(listing, result)

    listing["ml_title_score"]         = result.score_title
    listing["ml_desc_score"]          = result.score_desc
    listing["ml_amenity_gap_score"]   = result.score_amenities
    listing["ml_image_quality_score"] = result.score_images
    listing["ml_generated_title"]     = result.title_variants[0] if result.title_variants else ""
    listing["ml_generated_desc"]      = result.rewritten_desc[:500]

    print(f"  [teardown] Done.")
    print(f"    Title score:     {result.score_title}/10")
    print(f"    Desc score:      {result.score_desc}/10")
    print(f"    Amenity score:   {result.score_amenities}/10")
    print(f"    Image score:     {result.score_images}/10")
    print(f"    Revenue at stake (90d): ${revenue_at_stake:,}")
    if result.title_variants:
        print(f"    Best title variant: {result.title_variants[0]}")
    print(f"    Outreach angle:  {result.outreach_angle}")
    if image_result:
        print(f"    Image score:     {result.score_images}/10")
        if image_result.cover_is_wrong:
            print(f"    *** COVER SWAP: {image_result.current_cover_room} → {image_result.cover_room} ***")
        if analysis.get("photo_dir"):
            print(f"    Photos:          {analysis['photo_dir']}/")
        if analysis.get("manifest_path"):
            print(f"    Manifest CSV:    {analysis['manifest_path']}")
    if result.pdf_path:
        print(f"    PDF:  {result.pdf_path}")
    print(f"    JSON: {result.json_path}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ListingBoost Teardown Engine")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("url", nargs="?", help="Airbnb listing URL to scrape + teardown")
    group.add_argument("--json", dest="json_file", help="Path to existing scraped JSON")
    group.add_argument("--demo", action="store_true",
                       help="Run on test listing (20669368)")
    parser.add_argument("--no-images", action="store_true",
                       help="Skip image Vision analysis (faster, cheaper)")
    args = parser.parse_args()

    if args.demo:
        url = "https://www.airbnb.com/rooms/20669368"
        print(f"[teardown] Demo mode - scraping test listing...")
        from scraper import scrape_url
        listing = scrape_url(url, calendar_months=3)
    elif args.json_file:
        data = json.loads(Path(args.json_file).read_text())
        listing = data[0] if isinstance(data, list) else data
        print(f"[teardown] Loaded listing {listing.get('listing_id')} from {args.json_file}")
    else:
        from scraper import scrape_url
        listing = scrape_url(args.url, calendar_months=3)

    result = run_teardown(listing, analyze_images=not args.no_images)

    print(f"\n{'='*60}")
    print("OUTREACH HOOK:")
    print(f"{'='*60}")
    print(result.raw_analysis.get("outreach_hook", "No hook generated"))
    print(f"\nKEY DIAGNOSIS:")
    for i, d in enumerate(result.key_diagnosis, 1):
        print(f"  {i}. {d}")
    print(f"\nTITLE VARIANTS:")
    for i, t in enumerate(result.title_variants, 1):
        print(f"  {i}. {t} ({len(t)} chars)")
