"""
image_organizer.py — Download + organize Airbnb listing photos

Downloads all photos from a scraped listing into a structured folder:
  /tmp/listingboost_photos/{listing_id}/
    00_COVER_HERO/         <- recommended cover photo (Vision-picked)
    01_keep/               <- photos to keep, ordered by score
    02_retake/             <- verdict = retake (weak but fixable)
    03_REMOVE/             <- verdict = remove (actively hurts CTR)
    manifest.csv           <- full spreadsheet: position, room, score, verdict, regen_prompt, url, local_path

The manifest.csv is the "ready to process" sheet — paste into Google Sheets,
then use regen_prompt column to drive the AI regeneration step.

AI regeneration rules (enforced in regen_prompt):
  - Same furniture, same layout, same objects — nothing invented or removed
  - Only fix: lighting direction, brightness, composition/framing (crop/angle)
  - No style transfer, no new decor, no virtual staging
  - Output must look like the same room shot by a professional photographer

Usage:
  python image_organizer.py --listing-json /tmp/listingboost_teardowns/teardown_20669368.json
  python image_organizer.py --demo

  from image_organizer import organize_listing_photos
  manifest_path, photo_dir = organize_listing_photos(listing, image_analysis_result)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path("/tmp/listingboost_photos")
BASE_DIR.mkdir(exist_ok=True)

DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.airbnb.com/",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}

SUBFOLDER_MAP = {
    "hero":   "00_COVER_HERO",
    "keep":   "01_keep",
    "retake": "02_retake",
    "remove": "03_REMOVE",
}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path, timeout: int = 20) -> bool:
    """Download image URL to dest path. Returns True on success."""
    try:
        r = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=timeout, stream=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"  [organizer] FAIL {url[:70]}... : {e}")
        return False


def _safe_room(room_type: str) -> str:
    """Sanitize room type for use as a filename component."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in room_type)[:30]


# ---------------------------------------------------------------------------
# Main organizer
# ---------------------------------------------------------------------------

def organize_listing_photos(
    listing: dict,
    image_result=None,  # ImageAnalysisResult from image_analyzer.py (optional)
) -> tuple[str, str]:
    """
    Download all photos, organize into subfolders, write manifest.csv.

    Returns (manifest_csv_path, photo_dir_path)
    """
    lid = listing.get("listing_id", "unknown")
    host = listing.get("host_name", "host")
    photo_dir = BASE_DIR / f"{lid}_{_safe_room(host)}"
    photo_dir.mkdir(exist_ok=True)

    # Build flat photo list from listing
    images_by_room = listing.get("images_by_room") or {}
    flat: list[dict] = []
    pos = 1
    for room_type, urls in images_by_room.items():
        for url in urls:
            flat.append({"position": pos, "room_type": room_type, "url": url})
            pos += 1

    if not flat:
        print(f"  [organizer] No images found for listing {lid}")
        return "", str(photo_dir)

    # Build lookup from image_analysis if available
    verdict_map: dict[str, str] = {}     # url -> verdict
    reason_map: dict[str, str] = {}      # url -> reason
    regen_map: dict[str, str] = {}       # url -> regen_prompt
    score_map: dict[str, float] = {}     # url -> overall_score
    cover_url = ""
    recommended_cover_position = 1

    if image_result:
        for ps in image_result.all_scores:
            verdict_map[ps.url] = ps.verdict
            reason_map[ps.url] = ps.reason
            regen_map[ps.url] = ps.regen_prompt
            score_map[ps.url] = ps.overall_score
        cover_url = image_result.cover_url
        if cover_url:
            for img in flat:
                if img["url"] == cover_url:
                    recommended_cover_position = img["position"]
                    break

    # Create subfolders
    for sub in SUBFOLDER_MAP.values():
        (photo_dir / sub).mkdir(exist_ok=True)

    # Download in parallel
    print(f"\n[organizer] Downloading {len(flat)} photos for listing {lid}...")

    def download_one(img: dict) -> dict:
        url = img["url"]
        pos = img["position"]
        room = img["room_type"]

        verdict = verdict_map.get(url, "keep")
        # Override: hero subfolder only for the single recommended cover
        if url == cover_url:
            verdict = "hero"

        subfolder = SUBFOLDER_MAP.get(verdict, "01_keep")
        score = score_map.get(url, 0.0)
        filename = f"{pos:02d}_{_safe_room(room)}_score{score:.1f}.jpg"
        dest = photo_dir / subfolder / filename

        ok = _download(url, dest)
        local_path = str(dest) if ok else ""

        print(f"  [organizer] #{pos:2d} {room[:25]:25s} [{verdict:6s}] {'OK' if ok else 'FAIL'} → {subfolder}/{filename}")

        return {
            "position": pos,
            "room_type": room,
            "verdict": verdict,
            "overall_score": score,
            "local_path": local_path,
            "subfolder": subfolder,
            "url": url,
            "reason": reason_map.get(url, ""),
            "regen_prompt": regen_map.get(url, ""),
            "is_recommended_cover": "YES" if url == cover_url else "",
            "is_current_cover": "YES" if pos == 1 else "",
        }

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(download_one, img) for img in flat]
        for f in concurrent.futures.as_completed(futures):
            rows.append(f.result())

    # Sort by original position
    rows.sort(key=lambda r: r["position"])

    # Write manifest.csv
    manifest_path = photo_dir / "manifest.csv"
    fieldnames = [
        "position", "room_type", "verdict", "overall_score",
        "is_recommended_cover", "is_current_cover",
        "reason", "regen_prompt",
        "local_path", "subfolder", "url",
    ]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if r["local_path"])
    print(f"\n[organizer] Done. {ok_count}/{len(rows)} photos downloaded.")
    print(f"  Folder:   {photo_dir}/")
    print(f"  Manifest: {manifest_path}")
    print(f"\n  Subfolders:")
    for sub in SUBFOLDER_MAP.values():
        count = len(list((photo_dir / sub).glob("*.jpg")))
        print(f"    {sub}/  ({count} photos)")

    return str(manifest_path), str(photo_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ListingBoost Image Organizer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--listing-json", help="Path to scraped listing JSON")
    group.add_argument("--demo", action="store_true", help="Test on listing 20669368")
    parser.add_argument("--with-vision", action="store_true",
                        help="Run Vision analysis first, then organize (costs ~$0.10)")
    args = parser.parse_args()

    if args.demo:
        from scraper import scrape_url
        listing = scrape_url("https://www.airbnb.com/rooms/20669368", calendar_months=1)
    else:
        data = json.loads(Path(args.listing_json).read_text())
        listing = data[0] if isinstance(data, list) else data

    image_result = None
    if args.with_vision:
        from image_analyzer import analyze_images
        image_result = analyze_images(listing)

    manifest_path, photo_dir = organize_listing_photos(listing, image_result)

    print(f"\n{'='*60}")
    print("READY FOR REGENERATION")
    print(f"{'='*60}")
    print(f"Manifest CSV: {manifest_path}")
    print(f"Photo folder: {photo_dir}/")
    print()
    print("Next steps:")
    print("  1. Open manifest.csv — paste into Google Sheets")
    print("  2. Use 00_COVER_HERO/ photo as the teaser in outreach email")
    print("  3. Send photos from 01_keep/ + 02_retake/ to AI regeneration")
    print("     Rule: same furniture/layout/objects. Fix lighting + framing only.")
    print("  4. Upload regenerated photos to Google Drive → share with host")
    print("  5. Send outreach with hero image teaser + $29 PDF CTA")
