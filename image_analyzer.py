"""
image_analyzer.py - Claude Vision photo audit for Airbnb listings

Vision analysis only — no pixel editing.
  Claude looks at every photo, scores it, picks the best cover photo,
  flags what to remove, what to retake, and gives the full recommended order.

  Download + organization is handled by image_organizer.py.
  AI regeneration (lighting/framing only, same furniture) happens separately.

Intra-process learning:
  - Reads strategy("cover_photo_preferred_room") before analysis
  - Emits image_cover_score, image_best_score, image_cover_is_wrong signals after

Inter-process learning:
  - outreach.image_hook emitted here -> teardown wires it into the outreach email
  - ml_image_quality_score written back to listing dict for sheet_writer

Usage:
  from image_analyzer import analyze_images
  result = analyze_images(listing)
  # result.cover_url, result.ranked_urls, result.outreach_hook

  python image_analyzer.py --json /tmp/listingboost_teardowns/teardown_20669368.json
  python image_analyzer.py --demo        # test on 20669368
"""
from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import concurrent.futures

import requests
from dotenv import load_dotenv

import learning_store as ls

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OUTPUT_DIR = Path("/tmp/listingboost_teardowns")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PhotoScore:
    url: str
    position: int              # original position (1 = current cover)
    room_type: str
    score_lighting: int        # 1-10
    score_composition: int     # 1-10
    score_cleanliness: int     # 1-10
    score_first_impression: int # 1-10
    overall_score: float
    verdict: str               # "hero" | "keep" | "retake" | "remove"
    reason: str                # one sentence why
    regen_prompt: str = ""     # AI regen prompt for this specific photo


@dataclass
class ImageAnalysisResult:
    listing_id: str

    # Vision output
    all_scores: list[PhotoScore] = field(default_factory=list)
    cover_url: str = ""            # recommended cover photo URL
    cover_room: str = ""           # room type of recommended cover
    current_cover_url: str = ""    # what they have now as #1
    current_cover_room: str = ""
    cover_is_wrong: bool = False   # True = they have the wrong photo as cover
    ranked_urls: list[str] = field(default_factory=list)   # full recommended order
    remove_urls: list[str] = field(default_factory=list)   # actively hurting CTR
    retake_rooms: list[str] = field(default_factory=list)  # missing/weak coverage
    key_finding: str = ""          # the single most actionable line
    outreach_hook: str = ""        # 1-sentence hook for cold email

    # ML
    ml_image_quality_score: int = 0   # 1-10 overall listing image quality


# ---------------------------------------------------------------------------
# Stage 1: Claude Vision analysis
# ---------------------------------------------------------------------------

VISION_SYSTEM = """You are a professional Airbnb photographer and conversion rate expert.
You've reviewed 10,000+ Airbnb listings. You know exactly which photos make guests click
"Book" and which make them bounce.

Rules:
- Be honest and specific. "Bathroom tile looks dated" beats "photo needs improvement"
- Cover photo is the ONLY thing visible in Airbnb search results. It must be the listing's
  single most aspirational, well-lit, uncluttered photo.
- Dark photos lose bookings. Clutter loses bookings. Toilets as cover photo = catastrophic.
- The best cover is almost always: pool, view, outdoor space, or the hero living/bedroom
  with natural light flooding in from the side.
- Score fairly. A 10/10 is rare and means "professional shoot, ready for magazine."
- Verdict guide: hero=best photo, keep=fine, retake=has potential but flawed, remove=actively hurts"""

def _build_vision_prompt(images: list[dict]) -> list[dict]:
    """Build the Claude messages payload with all images inline."""
    content = []

    content.append({
        "type": "text",
        "text": f"""I'm going to show you {len(images)} photos from an Airbnb listing in order (position 1 = current cover photo shown in search results).

For each photo, score it and give a verdict. Then give me your full recommendation.

Return ONLY this JSON (no markdown):
{{
  "photos": [
    {{
      "position": <1-based index>,
      "room_type": "<what room/area this shows>",
      "score_lighting": <1-10>,
      "score_composition": <1-10>,
      "score_cleanliness": <1-10>,
      "score_first_impression": <1-10>,
      "overall_score": <float, average of above>,
      "verdict": "<hero|keep|retake|remove>",
      "reason": "<one specific sentence why>",
      "regen_prompt": "<short img2img prompt for AI regeneration: describe ONLY the lighting and composition fix needed — e.g. 'warm afternoon window light from left, slightly wider angle, declutter counter'. Never change furniture or invent objects.>"
    }}
  ],
  "cover_recommendation": {{
    "position": <which position number should be the new cover>,
    "room_type": "<room type>",
    "reason": "<one sentence — specific to what you saw>"
  }},
  "ranked_order": [<position numbers in ideal order, e.g. [7, 3, 1, 5, ...]>],
  "remove_positions": [<position numbers to delete entirely>],
  "retake_rooms": ["<room type missing or needs complete reshoot>"],
  "key_finding": "<the single most actionable fix — specific to THIS listing's photos>",
  "outreach_hook": "<one sentence for a cold email to this host, using only what you actually saw — no fabricated stats>",
  "overall_image_score": <1-10, overall listing image quality>
}}

Here are the photos:"""
    })

    for img in images:
        # Add image
        content.append({
            "type": "image",
            "source": {
                "type": "url",
                "url": img["url"]
            }
        })
        content.append({
            "type": "text",
            "text": f"[Photo {img['position']} — {img['room_type']}]"
        })

    return content


def _run_vision_analysis(listing: dict) -> dict:
    """Call Claude Vision on all listing images. Returns raw analysis dict."""
    from anthropic import Anthropic

    images_by_room = listing.get("images_by_room") or {}

    # Flatten to ordered list, max 20 photos (token limit)
    flat_images = []
    pos = 1
    for room_type, urls in images_by_room.items():
        for url in urls[:4]:   # max 4 per room
            flat_images.append({"position": pos, "room_type": room_type, "url": url})
            pos += 1
            if pos > 20:
                break
        if pos > 20:
            break

    # Fallback: if images_by_room empty, try raw images list
    if not flat_images:
        raw_images = listing.get("raw_images") or []
        for i, img in enumerate(raw_images[:20]):
            url = img.get("imageUrl") or img if isinstance(img, str) else ""
            if url:
                flat_images.append({
                    "position": i + 1,
                    "room_type": img.get("caption", "Unknown") if isinstance(img, dict) else "Unknown",
                    "url": url
                })

    if not flat_images:
        return {"error": "no_images", "photos": [], "overall_image_score": 0}

    # Cap at 12 photos to keep response JSON well within token budget
    flat_images = flat_images[:12]

    print(f"  [image_analyzer] Sending {len(flat_images)} photos to Claude Vision...")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def _call_vision(images):
        content = _build_vision_prompt(images)
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4000,
            system=VISION_SYSTEM,
            messages=[{"role": "user", "content": content}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    # Try full batch; if JSON parse fails, retry with first 8
    try:
        result = _call_vision(flat_images)
    except json.JSONDecodeError:
        print(f"  [image_analyzer] JSON parse failed on {len(flat_images)} images, retrying with 8...")
        flat_images = flat_images[:8]
        result = _call_vision(flat_images)

    result["_flat_images"] = flat_images
    return result


# ---------------------------------------------------------------------------
# Stage 2: PIL image enhancement
# ---------------------------------------------------------------------------

def _download_image(url: str, timeout: int = 15) -> Optional[Image.Image]:
    """Download image from URL, return PIL Image or None."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  [enhance] Download failed for {url[:60]}...: {e}")
        return None


def _enhance_photo(img: Image.Image, preset: str = "standard") -> Image.Image:
    """
    Apply enhancement pipeline to a PIL image.

    presets:
      standard  — balanced lift: brightness +15%, contrast +20%, sharpness +30%
      sunset    — warm golden-hour grade: boost reds/yellows, lift shadows
      bright    — aggressive lift for dark/indoor shots: +30% brightness
      clean     — minimal: sharpen + slight contrast only
    """
    # Step 1: Resize to Airbnb's optimal upload size (1024x683 = 3:2 ratio)
    max_w, max_h = 1920, 1280
    img.thumbnail((max_w, max_h), Image.LANCZOS)

    # Step 2: Auto-crop to 4:3 (Airbnb displays 4:3 in listings)
    w, h = img.size
    target_ratio = 4 / 3
    current_ratio = w / h
    if current_ratio > target_ratio:
        # Too wide — crop sides
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif current_ratio < target_ratio:
        # Too tall — crop top/bottom (keep upper 2/3 — usually the interesting part)
        new_h = int(w / target_ratio)
        top = int((h - new_h) * 0.3)   # slight top bias
        img = img.crop((0, top, w, top + new_h))

    arr = np.array(img, dtype=np.float32)

    if preset == "sunset":
        # Warm grade: boost R channel, lift G slightly, keep B
        arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.12 + 8, 0, 255)   # reds +12% + lift
        arr[:, :, 1] = np.clip(arr[:, :, 1] * 1.05 + 4, 0, 255)   # greens +5%
        arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.92, 0, 255)        # blues -8%
        # Lift shadows (gamma on dark pixels)
        mask = arr < 80
        arr[mask] = arr[mask] * 1.3
        img = Image.fromarray(arr.astype(np.uint8))
        # Brightness +10%
        img = ImageEnhance.Brightness(img).enhance(1.10)
        # Contrast +15%
        img = ImageEnhance.Contrast(img).enhance(1.15)

    elif preset == "bright":
        # Aggressive lift for dark indoor shots
        arr = np.clip(arr * 1.25 + 15, 0, 255)
        img = Image.fromarray(arr.astype(np.uint8))
        img = ImageEnhance.Contrast(img).enhance(1.20)

    elif preset == "standard":
        # Balanced: lift shadows, moderate brightness + contrast
        mask = arr < 100
        arr[mask] = arr[mask] * 1.15
        img = Image.fromarray(arr.astype(np.uint8))
        img = ImageEnhance.Brightness(img).enhance(1.12)
        img = ImageEnhance.Contrast(img).enhance(1.18)

    elif preset == "clean":
        img = ImageEnhance.Contrast(img).enhance(1.10)

    # Sharpen slightly (unsharp mask feel)
    img = ImageEnhance.Sharpness(img).enhance(1.35)

    # Saturation boost — makes listing pop in search grid
    img = ImageEnhance.Color(img).enhance(1.15)

    return img


def _pick_preset(score_lighting: int, room_type: str) -> str:
    """Choose enhancement preset based on photo signals."""
    rt = room_type.lower()
    if score_lighting <= 4:
        return "bright"
    if any(x in rt for x in ["outdoor", "patio", "balcony", "pool", "garden", "view", "terrace"]):
        return "sunset"
    return "standard"


def _enhance_all(flat_images: list[dict], photo_scores: list[PhotoScore],
                 listing_id: str, skip_positions: list[int]) -> dict[int, str]:
    """
    Download + enhance all non-removed photos in parallel.
    Returns {position: enhanced_local_path}
    """
    enhanced_dir = OUTPUT_DIR / f"enhanced_{listing_id}"
    enhanced_dir.mkdir(exist_ok=True)

    score_map = {ps.position: ps for ps in photo_scores}

    def process(img_info: dict) -> tuple[int, str]:
        pos = img_info["position"]
        if pos in skip_positions:
            return pos, ""
        url = img_info["url"]
        room = img_info["room_type"]

        pil_img = _download_image(url)
        if pil_img is None:
            return pos, ""

        ps = score_map.get(pos)
        lighting_score = ps.score_lighting if ps else 5
        preset = _pick_preset(lighting_score, room)

        enhanced = _enhance_photo(pil_img, preset=preset)
        out_path = enhanced_dir / f"photo_{pos:02d}_{room.replace(' ','_')}_enhanced.jpg"
        enhanced.save(str(out_path), "JPEG", quality=92, optimize=True)
        print(f"  [enhance] Photo {pos} ({room}) → {preset} → {out_path.name}")
        return pos, str(out_path)

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(process, img): img["position"] for img in flat_images}
        for future in concurrent.futures.as_completed(futures):
            pos, path = future.result()
            if path:
                results[pos] = path

    return results, str(enhanced_dir)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_images(listing: dict) -> ImageAnalysisResult:
    """
    Vision audit pipeline. Scores photos, picks cover, generates regen prompts.
    Download + organization handled by image_organizer.py.
    """
    lid = listing.get("listing_id", "unknown")
    print(f"\n[image_analyzer] Auditing images for listing {lid}...")

    result = ImageAnalysisResult(listing_id=lid)

    # --- Stage 1: Vision analysis ---
    raw = _run_vision_analysis(listing)

    if raw.get("error"):
        print(f"  [image_analyzer] No images found for {lid}")
        return result

    flat_images = raw.get("_flat_images", [])
    url_map = {img["position"]: img["url"] for img in flat_images}

    # Build PhotoScore objects
    photo_scores = []
    for p in raw.get("photos", []):
        pos = p.get("position", 0)
        ps = PhotoScore(
            url=url_map.get(pos, ""),
            position=pos,
            room_type=p.get("room_type", "Unknown"),
            score_lighting=p.get("score_lighting", 5),
            score_composition=p.get("score_composition", 5),
            score_cleanliness=p.get("score_cleanliness", 5),
            score_first_impression=p.get("score_first_impression", 5),
            overall_score=p.get("overall_score", 5.0),
            verdict=p.get("verdict", "keep"),
            reason=p.get("reason", ""),
            regen_prompt=p.get("regen_prompt", ""),
        )
        photo_scores.append(ps)

    result.all_scores = photo_scores

    # Cover recommendation
    cover_rec = raw.get("cover_recommendation", {})
    cover_pos = cover_rec.get("position", 1)
    result.cover_url = url_map.get(cover_pos, "")
    result.cover_room = cover_rec.get("room_type", "")

    result.current_cover_url = url_map.get(1, "")
    result.current_cover_room = flat_images[0]["room_type"] if flat_images else ""
    result.cover_is_wrong = cover_pos != 1

    # Ranked order
    result.ranked_urls = [url_map[p] for p in raw.get("ranked_order", []) if p in url_map]

    # Remove + retake
    remove_positions = raw.get("remove_positions", [])
    result.remove_urls = [url_map[p] for p in remove_positions if p in url_map]
    result.retake_rooms = raw.get("retake_rooms", [])

    result.key_finding = raw.get("key_finding", "")
    result.outreach_hook = raw.get("outreach_hook", "")
    result.ml_image_quality_score = raw.get("overall_image_score", 5)

    # Print summary
    print(f"  [image_analyzer] Overall image score: {result.ml_image_quality_score}/10")
    print(f"  [image_analyzer] Cover photo: position 1 ({result.current_cover_room})")
    if result.cover_is_wrong:
        print(f"  [image_analyzer] *** WRONG COVER — should be position {cover_pos} ({result.cover_room}) ***")
    print(f"  [image_analyzer] Photos to remove: {len(result.remove_urls)}")
    print(f"  [image_analyzer] Rooms to retake: {result.retake_rooms}")
    print(f"  [image_analyzer] Key finding: {result.key_finding}")

    # Emit ML signals
    ls.emit("analyzer", "image_cover_score",
            next((ps.overall_score for ps in photo_scores if ps.position == 1), 0),
            {"listing_id": lid})
    ls.emit("analyzer", "image_best_score",
            max((ps.overall_score for ps in photo_scores), default=0),
            {"listing_id": lid})
    ls.emit("analyzer", "image_cover_is_wrong", 1 if result.cover_is_wrong else 0,
            {"listing_id": lid})
    ls.emit("outreach", "image_hook", None, {
        "listing_id": lid,
        "hook": result.outreach_hook,
        "cover_is_wrong": result.cover_is_wrong,
    })

    # Update listing ML column
    listing["ml_image_quality_score"] = result.ml_image_quality_score

    # Save full JSON
    out = OUTPUT_DIR / f"image_analysis_{lid}.json"
    out.write_text(json.dumps({
        "listing_id": lid,
        "generated_at": datetime.utcnow().isoformat(),
        "overall_image_score": result.ml_image_quality_score,
        "cover_recommendation": {
            "current_position": 1,
            "current_room": result.current_cover_room,
            "recommended_position": cover_pos,
            "recommended_room": result.cover_room,
            "cover_is_wrong": result.cover_is_wrong,
            "reason": cover_rec.get("reason", ""),
        },
        "key_finding": result.key_finding,
        "outreach_hook": result.outreach_hook,
        "photos": [
            {
                "position": ps.position,
                "room_type": ps.room_type,
                "url": ps.url,
                "scores": {
                    "lighting": ps.score_lighting,
                    "composition": ps.score_composition,
                    "cleanliness": ps.score_cleanliness,
                    "first_impression": ps.score_first_impression,
                    "overall": ps.overall_score,
                },
                "verdict": ps.verdict,
                "reason": ps.reason,
                "regen_prompt": ps.regen_prompt,
            }
            for ps in photo_scores
        ],
        "ranked_order_urls": result.ranked_urls,
        "remove_urls": result.remove_urls,
        "retake_rooms": result.retake_rooms,
    }, indent=2))
    print(f"  [image_analyzer] JSON saved: {out}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ListingBoost Image Analyzer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("url", nargs="?", help="Airbnb listing URL")
    group.add_argument("--json", dest="json_file", help="Existing scraped listing JSON")
    group.add_argument("--demo", action="store_true", help="Test on listing 20669368")
    args = parser.parse_args()

    if args.demo:
        from scraper import scrape_url
        listing = scrape_url("https://www.airbnb.com/rooms/20669368", calendar_months=1)
    elif args.json_file:
        data = json.loads(Path(args.json_file).read_text())
        listing = data[0] if isinstance(data, list) else data
    else:
        from scraper import scrape_url
        listing = scrape_url(args.url, calendar_months=1)

    result = analyze_images(listing)

    print(f"\n{'='*60}")
    print("IMAGE AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"Overall image score: {result.ml_image_quality_score}/10")
    print(f"\nCurrent cover: Position 1 ({result.current_cover_room})")
    if result.cover_is_wrong:
        print(f"RECOMMENDED COVER: {result.cover_room} (different position!)")
    print(f"\nKey finding: {result.key_finding}")
    print(f"\nOutreach hook: {result.outreach_hook}")
    if result.retake_rooms:
        print(f"\nRetake needed: {', '.join(result.retake_rooms)}")
    print(f"\nFull breakdown:")
    for ps in sorted(result.all_scores, key=lambda x: x.overall_score, reverse=True):
        flag = " <- RECOMMENDED COVER" if ps.url == result.cover_url else ""
        flag2 = " [REMOVE]" if ps.url in result.remove_urls else ""
        print(f"  #{ps.position:2d} {ps.room_type:25s} {ps.overall_score:.1f}/10  [{ps.verdict:6s}]  {flag}{flag2}")
        print(f"      {ps.reason}")
        if ps.regen_prompt:
            print(f"      Regen: {ps.regen_prompt}")
