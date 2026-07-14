"""
photo_regen.py — Multi-platform AI photo enhancement tester + QC scoring

Tests OpenAI gpt-image-1 across 30+ prompt variations on listing photos.
QC agent (Claude Vision) scores each output against the reference aesthetic
(warm natural light, professional composition, preserved furniture/layout).

Usage:
  python photo_regen.py --listing-dir /tmp/listingboost_photos/20669368_Tanya
  python photo_regen.py --listing-dir ... --max-photos 5 --max-variants 6
  python photo_regen.py --qc-only --results-dir /tmp/regen_results/...

Output:
  /tmp/regen_results/{listing_id}/
    {photo}_{variant}/output.png
    scores.json  <- QC scores for all variants
    winner.json  <- best variant per photo + overall winner strategy
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import anthropic
from openai import OpenAI

load_dotenv()

RESULTS_DIR = Path("/tmp/regen_results")
RESULTS_DIR.mkdir(exist_ok=True)

anthropic_client = anthropic.Anthropic()
openai_client = OpenAI()

# ---------------------------------------------------------------------------
# Reference aesthetic (from user's inspiration images)
# ---------------------------------------------------------------------------
REFERENCE_AESTHETIC = """
The target aesthetic for high-converting Airbnb listing photos:
- Warm natural light (golden hour / soft window light), not harsh artificial lighting
- Clean, uncluttered surfaces — nothing distracting in frame
- Professional real estate / hospitality photography framing
- Colors: warm whites, natural wood tones, soft neutrals — cozy Alpine chalet feel
- Bedrooms: crisp white/beige linens, warm ambient bedside lamps
- Living rooms: inviting with fireplace/mountain view hero if available
- Exteriors: vivid green grass, bright flowers, warm wood chalet, blue sky
- Consistent color grading across all photos (unified style)
- NO: HDR oversaturation, harsh flash, flat overcast light, busy backgrounds
"""

# ---------------------------------------------------------------------------
# Prompt variants to test
# ---------------------------------------------------------------------------
PROMPT_VARIANTS = [
    # --- Lighting focus ---
    {
        "id": "warm_window",
        "category": "lighting",
        "prompt": "Professional Airbnb listing photo. Same room, same furniture, same layout. "
                  "Fix lighting only: warm soft natural light streaming from left window, "
                  "golden afternoon glow. Keep all furniture exactly as-is. No virtual staging.",
    },
    {
        "id": "golden_hour",
        "category": "lighting",
        "prompt": "Professional real estate photo of this room. Preserve all furniture and objects exactly. "
                  "Change only lighting to warm golden hour sunlight, soft shadows. "
                  "Hospitality photography quality, magazine-worthy.",
    },
    {
        "id": "overcast_clean",
        "category": "lighting",
        "prompt": "Professional interior photo, same room, same furniture. "
                  "Soft diffused natural light, bright and airy, no harsh shadows. "
                  "Clean white balance. Do not move or add any furniture.",
    },
    {
        "id": "candlelight_evening",
        "category": "lighting",
        "prompt": "Cozy evening ambiance, same room same furniture. "
                  "Warm lamp light, soft shadows, intimate atmosphere. "
                  "Alpine chalet feel. No new furniture or objects.",
    },
    {
        "id": "blue_hour",
        "category": "lighting",
        "prompt": "Professional architectural photo, blue hour lighting, "
                  "warm interior lights visible, crisp shadows. "
                  "Same room layout preserved exactly.",
    },
    # --- Composition focus ---
    {
        "id": "wider_angle",
        "category": "composition",
        "prompt": "Professional real estate wide-angle shot of this room. "
                  "Show more of the room for better spatial sense. "
                  "Same furniture, warm natural light, clean composition.",
    },
    {
        "id": "rule_of_thirds",
        "category": "composition",
        "prompt": "Reframe using rule of thirds photography composition. "
                  "Same room, same furniture. Warm natural window light. "
                  "Professional Airbnb listing quality.",
    },
    {
        "id": "symmetry",
        "category": "composition",
        "prompt": "Architectural symmetrical composition of this room. "
                  "Centered framing, same furniture layout, warm diffused natural light. "
                  "Magazine-quality interior photography.",
    },
    # --- Style fusion ---
    {
        "id": "alpine_luxury",
        "category": "style",
        "prompt": "Swiss Alpine luxury chalet interior photography style. "
                  "Same furniture and room layout preserved. "
                  "Warm wood tones enhanced, soft natural window light, "
                  "cozy premium feel. Like a 5-star Zermatt chalet brochure photo.",
    },
    {
        "id": "nordic_minimal",
        "category": "style",
        "prompt": "Scandinavian minimal interior photography. Same room, same furniture. "
                  "Clean bright light, white balance slightly cool, "
                  "airy and spacious feel. No clutter.",
    },
    {
        "id": "boutique_hotel",
        "category": "style",
        "prompt": "Boutique hotel photography quality for this room. "
                  "Same furniture preserved. Professional hospitality lighting, "
                  "warm and inviting. The Airbnb guest should feel they must book this.",
    },
    {
        "id": "airbnb_plus",
        "category": "style",
        "prompt": "Airbnb Plus listing photo quality — their highest tier. "
                  "Same furniture and room exactly. Professional lighting, "
                  "editorial composition, luxury short-term rental aesthetic.",
    },
    # --- Technical enhancement ---
    {
        "id": "hdr_natural",
        "category": "technical",
        "prompt": "Natural HDR interior photo, balanced exposure, "
                  "no blown highlights, deep shadows lifted. "
                  "Same room furniture preserved. Warm color grade.",
    },
    {
        "id": "moody_warm",
        "category": "technical",
        "prompt": "Moody warm-toned interior photography. "
                  "Same room, same furniture. Slightly underexposed shadows, "
                  "warm highlights, cinematic feel. Cozy and intimate.",
    },
    {
        "id": "bright_airy",
        "category": "technical",
        "prompt": "Bright airy interior photo, lifted shadows, "
                  "warm whites, clean and fresh feel. "
                  "Same room layout and furniture exactly preserved. "
                  "Professional real estate photography.",
    },
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class RegenResult:
    photo_name: str
    variant_id: str
    category: str
    prompt: str
    output_path: str
    success: bool
    error: str = ""
    qc_score: float = 0.0
    qc_reasoning: str = ""
    qc_preserve_score: float = 0.0  # did it preserve furniture?
    qc_light_score: float = 0.0     # lighting quality
    qc_appeal_score: float = 0.0    # booking appeal


# ---------------------------------------------------------------------------
# OpenAI image generation
# ---------------------------------------------------------------------------
def _img_to_b64(path: Path) -> tuple[bytes, str]:
    """Read image and return (bytes, base64_str)."""
    data = path.read_bytes()
    return data, base64.b64encode(data).decode()


def _prep_image_for_openai(src: Path, out: Path) -> bool:
    """
    Convert to PNG and resize to max 1536px for gpt-image-1.
    Returns True if successful.
    """
    try:
        from PIL import Image as PILImage
        img = PILImage.open(src)
        # Convert to RGBA for PNG
        if img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGB")
        # Resize if too large (gpt-image-1 works best at 1024 or 1536)
        max_size = 1536
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), PILImage.LANCZOS)
        img.save(out, "PNG")
        return True
    except ImportError:
        # PIL not available, just copy as-is
        shutil.copy(src, out)
        return True
    except Exception as e:
        print(f"  [prep] Error preparing {src.name}: {e}")
        return False


def generate_variant(
    photo_path: Path,
    variant: dict,
    results_dir: Path,
    dry_run: bool = False,
) -> RegenResult:
    """Generate one variant of a photo using OpenAI gpt-image-1."""
    variant_id = variant["id"]
    photo_name = photo_path.stem
    out_dir = results_dir / f"{photo_name}__{variant_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "output.png"

    # Save metadata
    (out_dir / "meta.json").write_text(json.dumps({
        "photo_name": photo_name,
        "source_path": str(photo_path),
        "variant_id": variant_id,
        "category": variant["category"],
        "prompt": variant["prompt"],
    }, indent=2))

    if dry_run:
        print(f"  [dry] Would generate: {photo_name} × {variant_id}")
        return RegenResult(
            photo_name=photo_name, variant_id=variant_id,
            category=variant["category"], prompt=variant["prompt"],
            output_path=str(output_path), success=False, error="dry_run"
        )

    try:
        # Prepare PNG version
        png_path = out_dir / "input.png"
        _prep_image_for_openai(photo_path, png_path)

        print(f"  [regen] {photo_name} × {variant_id} ... ", end="", flush=True)
        t0 = time.time()

        # Use gpt-image-1 with image edit (retry once on 429)
        for attempt in range(2):
            try:
                with open(png_path, "rb") as img_file:
                    response = openai_client.images.edit(
                        model="gpt-image-1",
                        image=img_file,
                        prompt=variant["prompt"],
                        size="1024x1024",
                        quality="high",
                        n=1,
                    )
                break
            except Exception as e:
                if "429" in str(e) and attempt == 0:
                    print(f"rate-limited, sleeping 20s... ", end="", flush=True)
                    time.sleep(20)
                else:
                    raise

        elapsed = time.time() - t0

        # Save output
        img_data = base64.b64decode(response.data[0].b64_json)
        output_path.write_bytes(img_data)

        print(f"OK ({elapsed:.1f}s) → {out_dir.name}/output.png")
        return RegenResult(
            photo_name=photo_name, variant_id=variant_id,
            category=variant["category"], prompt=variant["prompt"],
            output_path=str(output_path), success=True
        )

    except Exception as e:
        print(f"FAIL: {e}")
        return RegenResult(
            photo_name=photo_name, variant_id=variant_id,
            category=variant["category"], prompt=variant["prompt"],
            output_path="", success=False, error=str(e)
        )


# ---------------------------------------------------------------------------
# QC scoring (Claude Vision)
# ---------------------------------------------------------------------------
def _detect_mime(path: Path) -> str:
    """Detect actual image mime type from magic bytes."""
    header = path.read_bytes()[:12]
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return "image/webp"
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if header[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    return "image/jpeg"  # default


def score_variant(original_path: Path, result: RegenResult) -> RegenResult:
    """Score a variant with Claude Vision against the target aesthetic."""
    if not result.success or not result.output_path:
        return result

    output_path = Path(result.output_path)
    if not output_path.exists():
        result.error = "output file missing"
        return result

    try:
        orig_mime = _detect_mime(original_path)
        orig_b64 = base64.b64encode(original_path.read_bytes()).decode()
        out_b64 = base64.b64encode(output_path.read_bytes()).decode()

        prompt = f"""You are a professional Airbnb listing photo quality judge.

Compare ORIGINAL photo (Image 1) with AI-REGENERATED photo (Image 2).

The regeneration variant was: "{result.variant_id}" — prompt: "{result.prompt[:200]}..."

Target aesthetic:
{REFERENCE_AESTHETIC}

CRITICAL PLATFORM RULES (learned from QC sessions):
1. Airbnb uses a white/bright background throughout its app. Photos that appear DARK will look empty
   against this white context and guests will skip them immediately. ANY dark or moody output scores
   light_score ≤ 3 regardless of artistic merit.
2. preserve_score MUST reach 8.1 or higher to be usable. Furniture positions, wall colors, fixtures,
   layout must match the original closely. Score strictly — minor differences = 7, clear layout drift = 5.
3. Bright, airy, natural light is the gold standard. Wider angles that show more room = bonus.

Score the REGENERATED photo on these dimensions (0-10):
1. preserve_score: Strict furniture/layout preservation. (10=pixel-perfect, 8.1+=acceptable, <8.1=reject)
2. light_score: Brightness for Airbnb context. DARK/moody=1-3. Flat/harsh=4-5. Natural bright=7-8. Warm+bright=9-10.
3. appeal_score: Booking appeal on Airbnb's white background. Dark images score ≤3 here.
4. total_score: preserve×0.4 + light×0.35 + appeal×0.25. If preserve_score < 8.1, cap total at 5.0.

Return ONLY valid JSON:
{{
  "preserve_score": <0-10>,
  "light_score": <0-10>,
  "appeal_score": <0-10>,
  "total_score": <0-10>,
  "reasoning": "<2 sentences: what worked, what didn't>",
  "usable": <true if total_score >= 6.5 AND preserve_score >= 8.1>
}}"""

        resp = anthropic_client.messages.create(
            model="claude-opus-4-8",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": orig_mime, "data": orig_b64}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": out_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        text = resp.content[0].text.strip()
        # Extract JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        scores = json.loads(text[start:end])

        result.qc_score = scores.get("total_score", 0)
        result.qc_preserve_score = scores.get("preserve_score", 0)
        result.qc_light_score = scores.get("light_score", 0)
        result.qc_appeal_score = scores.get("appeal_score", 0)
        result.qc_reasoning = scores.get("reasoning", "")

        print(f"  [qc] {result.photo_name} × {result.variant_id}: "
              f"total={result.qc_score:.1f} preserve={result.qc_preserve_score:.1f} "
              f"light={result.qc_light_score:.1f} appeal={result.qc_appeal_score:.1f}")

    except Exception as e:
        print(f"  [qc] Error scoring {result.variant_id}: {e}")
        result.error = f"qc_error: {e}"

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(results: list[RegenResult], results_dir: Path) -> dict:
    """Generate a summary report ranking variants and picking winners."""
    successful = [r for r in results if r.success and r.qc_score > 0]

    if not successful:
        return {"error": "No successful results to rank"}

    # Sort by QC score
    ranked = sorted(successful, key=lambda r: r.qc_score, reverse=True)

    # Best per category
    categories = {}
    for r in ranked:
        if r.category not in categories:
            categories[r.category] = r

    # Best per variant across all photos
    variant_scores: dict[str, list[float]] = {}
    for r in successful:
        variant_scores.setdefault(r.variant_id, []).append(r.qc_score)
    avg_by_variant = {
        vid: sum(scores) / len(scores)
        for vid, scores in variant_scores.items()
    }
    best_variants = sorted(avg_by_variant.items(), key=lambda x: x[1], reverse=True)

    report = {
        "summary": {
            "total_tests": len(results),
            "successful": len(successful),
            "usable": len([r for r in successful if r.qc_score >= 6.5 and r.qc_preserve_score >= 5.0]),
            "avg_score": round(sum(r.qc_score for r in successful) / len(successful), 2),
        },
        "top_10_overall": [
            {
                "rank": i + 1,
                "photo": r.photo_name,
                "variant": r.variant_id,
                "category": r.category,
                "total": round(r.qc_score, 1),
                "preserve": round(r.qc_preserve_score, 1),
                "light": round(r.qc_light_score, 1),
                "appeal": round(r.qc_appeal_score, 1),
                "reasoning": r.qc_reasoning,
                "output": r.output_path,
            }
            for i, r in enumerate(ranked[:10])
        ],
        "best_variant_strategy": [
            {"variant_id": vid, "avg_score": round(avg, 2)}
            for vid, avg in best_variants[:5]
        ],
        "best_per_category": {
            cat: {
                "variant": r.variant_id,
                "score": round(r.qc_score, 1),
                "reasoning": r.qc_reasoning,
                "output": r.output_path,
            }
            for cat, r in categories.items()
        },
        "recommendation": {
            "winner_variant": best_variants[0][0] if best_variants else "unknown",
            "winner_avg_score": round(best_variants[0][1], 2) if best_variants else 0,
            "use_for_production": best_variants[0][0] if best_variants and best_variants[0][1] >= 6.5 else None,
        },
        "all_results": [
            {
                "photo": r.photo_name,
                "variant": r.variant_id,
                "total": round(r.qc_score, 1),
                "preserve": round(r.qc_preserve_score, 1),
                "light": round(r.qc_light_score, 1),
                "appeal": round(r.qc_appeal_score, 1),
                "output": r.output_path,
            }
            for r in ranked
        ],
    }

    # Save report
    report_path = results_dir / "qc_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    return report


def print_report(report: dict) -> None:
    """Print a human-readable summary."""
    s = report.get("summary", {})
    print(f"\n{'='*65}")
    print("PHOTO REGEN QC REPORT")
    print(f"{'='*65}")
    print(f"Tests run:     {s.get('total_tests', 0)}")
    print(f"Successful:    {s.get('successful', 0)}")
    print(f"Usable (≥6.5): {s.get('usable', 0)}")
    print(f"Avg QC score:  {s.get('avg_score', 0)}")

    rec = report.get("recommendation", {})
    winner = rec.get("winner_variant", "N/A")
    winner_score = rec.get("winner_avg_score", 0)
    print(f"\n{'─'*65}")
    print(f"WINNER STRATEGY: {winner}  (avg score {winner_score})")
    use = rec.get("use_for_production")
    if use:
        print(f"✓ READY FOR PRODUCTION: Use '{use}' prompt for all photos")
    else:
        print("✗ No variant scored high enough consistently — iterate prompts")

    print(f"\n{'─'*65}")
    print("TOP 10 RESULTS:")
    for item in report.get("top_10_overall", []):
        print(f"  #{item['rank']} {item['total']:4.1f}  {item['photo'][:30]:30s}  [{item['variant']}]")
        print(f"      preserve={item['preserve']} light={item['light']} appeal={item['appeal']}")
        print(f"      {item['reasoning']}")

    print(f"\n{'─'*65}")
    print("BEST VARIANT PER CATEGORY:")
    for cat, info in report.get("best_per_category", {}).items():
        print(f"  [{cat:12s}] {info['variant']:20s}  score={info['score']}")

    print(f"\n{'─'*65}")
    print("BEST VARIANTS RANKED (avg across all photos):")
    for item in report.get("best_variant_strategy", []):
        print(f"  {item['avg_score']:4.1f}  {item['variant_id']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ListingBoost Photo Regen Tester")
    parser.add_argument("--listing-dir", help="Path to organized photo dir (contains 00_COVER_HERO, 01_keep, etc.)")
    parser.add_argument("--max-photos", type=int, default=5, help="Max photos to test (default 5)")
    parser.add_argument("--max-variants", type=int, default=15, help="Max prompt variants per photo (default all)")
    parser.add_argument("--qc-only", action="store_true", help="Only run QC on existing results")
    parser.add_argument("--results-dir", help="Results dir (for --qc-only)")
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no API calls")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers (default 3)")
    parser.add_argument("--categories", nargs="+",
                        choices=["lighting", "composition", "style", "technical"],
                        help="Only test specific categories")
    args = parser.parse_args()

    # Collect photos to test
    if args.listing_dir:
        listing_dir = Path(args.listing_dir)
        photos = []
        # Prefer cover hero, then keep, then retake
        for subfolder in ["00_COVER_HERO", "01_keep", "02_retake"]:
            sub = listing_dir / subfolder
            if sub.exists():
                photos.extend(sorted(sub.glob("*.jpg"))[:args.max_photos])
        # Deduplicate by stem (multiple scores same room)
        seen_stems = set()
        unique_photos = []
        for p in photos:
            # Use just room name prefix for dedup
            room_key = "_".join(p.stem.split("_")[:2])
            if room_key not in seen_stems:
                seen_stems.add(room_key)
                unique_photos.append(p)
        photos = unique_photos[:args.max_photos]

        listing_id = listing_dir.name
        results_dir = RESULTS_DIR / listing_id
        results_dir.mkdir(parents=True, exist_ok=True)
    elif args.qc_only and args.results_dir:
        results_dir = Path(args.results_dir)
        photos = []
    else:
        parser.error("Provide --listing-dir or --qc-only + --results-dir")
        return

    # Filter variants — respect ML kill list from learning.db
    try:
        import sys as _sys; _sys.path.insert(0, str(Path(__file__).parent))
        from learning_store import get_strategy as _gs
        import json as _json
        kill_list = _json.loads(_gs("regen", "variant_kill_list") or "[]")
        if kill_list:
            print(f"[ml] Skipping killed variants: {kill_list}")
    except Exception:
        kill_list = []

    variants = PROMPT_VARIANTS[: args.max_variants]
    variants = [v for v in variants if v["id"] not in kill_list]
    if args.categories:
        variants = [v for v in variants if v["category"] in args.categories]

    if not args.qc_only:
        total = len(photos) * len(variants)
        print(f"\n[regen] Testing {len(photos)} photos × {len(variants)} variants = {total} generations")
        print(f"[regen] Results dir: {results_dir}/")
        print(f"[regen] Estimated cost: ~${total * 0.04:.2f} (OpenAI gpt-image-1)")
        print()
        for p in photos:
            print(f"  {p.relative_to(p.parent.parent)}")
        print()

        if args.dry_run:
            for photo in photos:
                for variant in variants:
                    generate_variant(photo, variant, results_dir, dry_run=True)
            print(f"\n[dry-run] Would run {total} generations. Remove --dry-run to execute.")
            return

        # Generate all variants
        results: list[RegenResult] = []
        tasks = [(photo, variant) for photo in photos for variant in variants]

        def run_task(task):
            photo, variant = task
            return generate_variant(photo, variant, results_dir)

        print(f"[regen] Starting {total} generations with {args.workers} workers...\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(run_task, task) for task in tasks]
            for f in concurrent.futures.as_completed(futures):
                try:
                    results.append(f.result())
                except Exception as e:
                    print(f"  [regen] Task error: {e}")

        # Save raw results
        raw_path = results_dir / "raw_results.json"
        raw_path.write_text(json.dumps(
            [asdict(r) for r in results], indent=2
        ))
        print(f"\n[regen] Done. {sum(1 for r in results if r.success)}/{total} successful.")
    else:
        # Load existing results
        raw_path = results_dir / "raw_results.json"
        if not raw_path.exists():
            print(f"No raw_results.json found in {results_dir}")
            return
        raw = json.loads(raw_path.read_text())
        from dataclasses import fields
        result_fields = {f.name for f in fields(RegenResult)}
        results = [RegenResult(**{k: v for k, v in r.items() if k in result_fields}) for r in raw]
        print(f"[qc] Loaded {len(results)} results from {results_dir}")
        photos_map = {}
        for r in results:
            meta_path = results_dir / f"{r.photo_name}__{r.variant_id}" / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                photos_map[r.photo_name] = Path(meta["source_path"])

    # QC scoring
    successful = [r for r in results if r.success and r.qc_score == 0]
    print(f"\n[qc] Scoring {len(successful)} variants with Claude Vision...")

    # Build photo path map for QC
    photos_map: dict[str, Path] = {}
    for photo in photos:
        photos_map[photo.stem] = photo
    # Also from metadata
    for r in results:
        if r.photo_name not in photos_map:
            meta_path = results_dir / f"{r.photo_name}__{r.variant_id}" / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                photos_map[r.photo_name] = Path(meta["source_path"])

    def score_task(result: RegenResult) -> RegenResult:
        orig = photos_map.get(result.photo_name)
        if orig and orig.exists():
            return score_variant(orig, result)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(score_task, r): i for i, r in enumerate(results)}
        for f in concurrent.futures.as_completed(futures):
            i = futures[f]
            try:
                results[i] = f.result()
            except Exception as e:
                print(f"  [qc] Score error: {e}")

    # Save updated results
    raw_path.write_text(json.dumps([asdict(r) for r in results], indent=2))

    # Generate report
    report = generate_report(results, results_dir)
    print_report(report)

    print(f"\n[done] Full report: {results_dir}/qc_report.json")
    print(f"[done] View outputs: open {results_dir}/")


if __name__ == "__main__":
    main()
