"""
Step 3 — Photo Recreation (process v1, pending lock)

For each Analyzed lead: select the photos that matter (selective mode),
recreate each as a bright, professionally-composed version of the SAME room
with IDENTICAL contents (no staging changes), QC-gate every output with a
vision check, and save originals + recreations per listing.

Chain (free-first):
  1. Gemini nano-banana (gemini-2.5-flash-image) — free tier, ~100 req/day
  2. HF router flux-kontext-dev — free credits (reset monthly)
  3. Replicate flux-kontext-dev — paid overflow (requires billing)

QC gate: Gemini 2.5 Flash (free) compares original vs recreation:
  same layout? same furniture/colors? no AI artifacts? straight verticals?
  FAIL -> one corrective retry -> still FAIL -> keep original (never ship bad).

Usage:
  python3 step3_photos.py                # all Analyzed leads
  python3 step3_photos.py <listing_id>   # one lead
  python3 step3_photos.py <listing_id> 3 # one lead, cap photos (testing)
"""
from __future__ import annotations
import sys, json, csv, base64, time, io
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)
import os

from perspective_fix import straighten

TRACKER_CSV  = HERE / "work" / "leads_tracker.csv"
LESSONS_FILE = HERE / "work" / "photo_lessons.json"
QUALIFIED    = HERE / "work" / "step1_qualified.json"
PHOTOS_DIR   = HERE / "work" / "photos"
MAX_PHOTOS   = 10          # selective mode: recreate only the photos that matter
ROOM_PRIORITY = ("living", "bedroom", "kitchen", "bathroom", "dining", "garden", "exterior")

# LOCKED PROMPT TEMPLATE (final — validated on Dorcas test 2026-07-14)
# The "freedom + pinned objects" fusion: magazine relight/staging language with
# hard object-conservation rules. Input is ALWAYS the OpenCV-straightened image.
PROMPT_TEMPLATE = (
    "Transform this into a bright, airy luxury interior-design magazine photograph: "
    "abundant soft natural daylight, crisp white balance, light and spacious feel, rich "
    "fresh color grading, deep clean contrast. Professionally presented: cushions plumped, "
    "fabrics smooth, no cables or clutter anywhere. "
    "ALL curtains and blinds are fully OPEN and neatly tied back at the window sides, "
    "letting maximum daylight in — strict requirement for every photo. "
    "Every lamp and ceiling light in the room is switched ON with a warm welcoming glow. "
    "Windows correctly exposed, never blown out — and windows stay WINDOWS (never turn a "
    "window into a door or balcony). "
    "{tv_rule}"
    "ABSOLUTE RULE — the room contains EXACTLY the objects in the original photo, no more, "
    "no less: do NOT add any throw, blanket, cushion, plant, tray or decor of any kind. "
    "Do not move, remove, resize or relocate anything. Same furniture, same wall art, same "
    "positions. Only lighting, curtain position, tidiness and camera geometry improve. "
    "Perfectly level camera, dead straight verticals, no tilt. Composition: main "
    "furniture in the lower two-thirds of frame with breathing room above, camera at "
    "about 110cm. "
    "BEDROOM STYLING (only when the photo shows a bed, using ONLY textiles already on "
    "it): white/cream duvet dominant and smooth, any colored bedspread folded into a "
    "neat flat runner across the FOOT of the bed with a soft cascade, pillows in "
    "hierarchy (sleeping pillows behind, accent cushions in front), everything in "
    "ordered relaxed-luxe drape — no chaotic wrinkles, no stretched-flat plastic look. "
    "Ultra-photorealistic editorial real-estate photography."
)

TV_RULE = ("If a television exists in the photo it stays EXACTLY where it is — same wall, "
           "same stand, same size — and displays a beautiful scenic photo of {attraction} "
           "with no text or writing on the screen. Never add a TV where none exists. ")

# HERO MODE — richest treatment for the listing's cover photo. SAME camera
# angle as the original (never relocate the camera — relocation experiments
# produced invented geometry). Layered light per Fakhri's reference standards.
HERO_SUFFIX = (
    " HERO TREATMENT for the cover photo: layered two-temperature light — airy bright "
    "daylight base with warm golden pools from the glowing lamps, gentle depth and falloff, "
    "luminous but never clinical. Textiles in relaxed luxe drape: smooth ordered folds, "
    "plumped layers, inviting not stretched. Palette harmonized around the room's own 2-3 "
    "colors. The single most beautiful, magazine-cover-worthy version of this exact view."
)

TV_DETECT_PROMPT = ("Is there a television/TV screen clearly visible in this photo? "
                    "Return ONLY JSON: {\"tv_visible\": true|false}")

# ---------------------------------------------------------------------------
# STAGED TIER — "virtual staging concept" (disclosed). Approved by Fakhri
# 2026-07-15: tasteful additions ALLOWED, architecture + furniture pinned.
# Output goes to staged/ with a deterministic PIL watermark for disclosure.
STAGING_PROMPT = (
    "Transform this photo into a page from a high-end interior design portfolio — "
    "the aspirational 'virtually staged' version of this exact room. "
    "KEEP: the room's architecture, window and door positions, all existing large "
    "furniture in their exact current positions and sizes, the same camera angle. "
    "YOU MAY ADD tasteful staging: an area rug grounding the main furniture, "
    "a throw draped on the sofa or bed, accent cushions, a coffee-table book or "
    "ceramic vase styling, a plant in a dead corner (never blocking doors, windows "
    "or radiators), upgraded wall art in the SAME frames/positions as existing art. "
    "Keep additions minimal and coherent — 2-3 new elements maximum, luxury-restraint "
    "aesthetic, palette matched to the room's existing 2-3 colors. "
    "LIGHTING: bright, airy, editorial — soft diffuse daylight flooding in, curtains "
    "fully open and tied, every lamp glowing warm, layered two-temperature light, "
    "high-key near-white walls, windows correctly exposed. "
    "GEOMETRY: perfectly level camera, dead straight verticals. "
    "Ultra-photorealistic, magazine-cover interior photography. "
    "Do NOT render any text, watermark, label or writing anywhere in the image."
)

QC_STAGED_PROMPT = (
    "You are a photo QC inspector for VIRTUAL STAGING. Photo 1 is the original room; "
    "photo 2 is a virtually staged version. Staging additions (rug, throw, cushions, "
    "plant, vase, books, upgraded art in existing frame positions) are ALLOWED and "
    "expected. Judge only these: "
    "Return ONLY JSON: {"
    "\"same_architecture\": bool,   # walls, windows, doors, radiators unchanged — window never becomes a door\n"
    "\"furniture_kept\": bool,      # every large furniture item from photo 1 still present, same position and size\n"
    "\"tasteful_restraint\": bool,  # additions look coherent and minimal, nothing blocking doors/windows/radiators\n"
    "\"photorealistic\": bool,      # no warped shapes, no CGI plastic look, no gibberish text\n"
    "\"dramatically_brighter\": bool,\n"
    "\"straight_verticals\": bool,\n"
    "\"verdict\": \"pass\"|\"fail\", \"reason\": \"<short>\"}. "
    "Verdict is pass ONLY if every check is true."
)


def watermark_staged(jpeg_bytes: bytes) -> bytes:
    """Deterministic disclosure watermark — same font, position, opacity every time."""
    from PIL import Image as PILImage, ImageDraw, ImageFont
    im = PILImage.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    w, h = im.size
    overlay = PILImage.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = max(18, int(w * 0.018))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        font = ImageFont.load_default()
    text = "VIRTUAL STAGING CONCEPT"
    pad = int(w * 0.015)
    tw = draw.textlength(text, font=font)
    # dark backing strip so the disclosure is legible on any background
    draw.rectangle([pad - 6, h - size - pad - 6, pad + tw + 6, h - pad + 4],
                   fill=(20, 28, 43, 175))
    draw.text((pad, h - size - pad), text, font=font, fill=(255, 255, 255, 235))
    im = PILImage.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def qc_check_staged(original: bytes, staged: bytes) -> dict:
    return _qc_vision(QC_STAGED_PROMPT, original, staged)
# ---------------------------------------------------------------------------

# City -> nearby tourist attraction shown on TVs (extend as new markets are scraped)
CITY_ATTRACTIONS = {
    "manchester": "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "middleton":  "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "whitefield": "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "london":     "Big Ben and the Houses of Parliament at golden hour",
    "leeds":      "the Leeds city skyline or Kirkstall Abbey",
    "liverpool":  "the Royal Liver Building on Liverpool's waterfront",
}

# ---------------------------------------------------------------------------
# LEARNING LOOP — persistent across runs. Every QC verdict is recorded in
# LESSONS_FILE; the most frequent failure modes are injected back into every
# future prompt as preemptive warnings, so each run starts smarter than the last.
LESSON_FIXES = {
    "no_added_objects":         "adding objects that do not exist in the original (throws, decor, curtains, blinds, doors, TVs) — add NOTHING",
    "nothing_removed_or_moved": "removing or relocating furniture/fixtures that exist in the original — everything stays exactly in place",
    "curtains_open":            "leaving curtains or blinds closed/covering the window — they must be fully open and tied back",
    "lights_on":                "leaving lamps or ceiling lights switched off — every light must glow warmly",
    "dramatically_brighter":    "output not bright enough — the room must be dramatically brighter, high-key, near-white walls",
    "straight_verticals":       "tilted camera / leaning verticals — all wall and frame edges must be perfectly vertical",
    "no_visible_cables":        "leaving visible cables or wires — remove them all",
    "window_not_blown_out":     "blowing out the window to pure white — keep the outside view correctly exposed",
    "no_ai_artifacts":          "warped shapes or gibberish text (especially on TV screens) — keep all geometry and text clean",
}
LESSON_MIN_COUNT = 3   # a failure mode must recur this often before it's injected
LESSON_TOP_N     = 3   # inject at most this many warnings (keep the prompt tight)

def _load_lessons() -> dict:
    try:
        return json.loads(LESSONS_FILE.read_text())
    except Exception:
        return {"fail_counts": {}, "candidates_seen": 0}

def record_lesson(verdict: dict) -> None:
    """Persist which QC checks failed for this candidate."""
    data = _load_lessons()
    data["candidates_seen"] = data.get("candidates_seen", 0) + 1
    for check in LESSON_FIXES:
        if verdict.get(check) is False:
            data["fail_counts"][check] = data["fail_counts"].get(check, 0) + 1
    LESSONS_FILE.write_text(json.dumps(data, indent=2))

def lesson_clause() -> str:
    """Preemptive warnings for the most frequent historical failure modes."""
    counts = _load_lessons().get("fail_counts", {})
    top = sorted(((c, n) for c, n in counts.items() if n >= LESSON_MIN_COUNT),
                 key=lambda t: -t[1])[:LESSON_TOP_N]
    if not top:
        return ""
    warnings = "; ".join(LESSON_FIXES[c] for c, _ in top)
    return (" LEARNED FROM PAST FAILURES — previous attempts were most often "
            f"rejected for: {warnings}. Do not repeat these mistakes. ")
# ---------------------------------------------------------------------------


def build_prompt(listing: dict, tv_visible: bool) -> str:
    city = (listing.get("location") or "").lower()
    attraction = next((a for c, a in CITY_ATTRACTIONS.items() if c in city),
                      "a famous local tourist attraction near the property")
    if tv_visible:
        return PROMPT_TEMPLATE.format(tv_rule=TV_RULE.format(attraction=attraction)) + lesson_clause()
    return PROMPT_TEMPLATE.format(tv_rule="") + lesson_clause()


def detect_tv(image_bytes: bytes) -> bool:
    """Cheap vision check so the TV rule is only sent when a TV really exists."""
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [
                      {"text": TV_DETECT_PROMPT},
                      {"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(image_bytes).decode()}}]}],
                  "generationConfig": {"responseMimeType": "application/json"}},
            timeout=60)
        r.raise_for_status()
        return bool(json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]).get("tv_visible"))
    except Exception:
        return False   # no TV rule when unsure — prevents hallucinated TVs

QC_PROMPT = (
    "You are a merciless photo QC inspector. Photo 1 is the original; photo 2 is an "
    "AI-recreated version that must show the SAME room with the SAME objects. "
    "ALLOWED differences in photo 2 (do NOT fail for these): much brighter lighting, lamps "
    "turned on, curtains OPENED and tied back, clutter and cables removed, tidier fabrics, "
    "scenic content shown on an EXISTING TV screen, straightened camera geometry, and "
    "bedding RESTYLED using the same textiles (spread refolded across the bed's foot, "
    "pillows rearranged — same colors, same items). "
    "Return ONLY JSON: {"
    "\"no_added_objects\": bool,        # NO new throws, blankets, decor, TVs, doors — nothing photo 1 lacks\n"
    "\"nothing_removed_or_moved\": bool, # every furniture item still present in its original spot; windows still windows\n"
    "\"no_ai_artifacts\": bool,          # no warped shapes, no gibberish text anywhere incl. TV screens\n"
    "\"straight_verticals\": bool,\n"
    "\"dramatically_brighter\": bool,\n"
    "\"lights_on\": bool,\n"
    "\"curtains_open\": bool,           # curtains/blinds open and tied back, not covering the window\n"
    "\"no_visible_cables\": bool,\n"
    "\"window_not_blown_out\": bool,\n"
    "\"verdict\": \"pass\"|\"fail\", \"reason\": \"<short, name every failed check>\"}. "
    "Verdict is pass ONLY if every single check is true. Be strict — added objects, moved "
    "furniture, or a window turned into a door are instant fails."
)


def _gemini_image(image_bytes: bytes, prompt: str) -> bytes:
    key = os.environ["NANO_BANANA_KEY"]
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
        params={"key": key},
        json={"contents": [{"parts": [
                  {"text": prompt},
                  {"inline_data": {"mime_type": "image/jpeg",
                                   "data": base64.b64encode(image_bytes).decode()}}]}],
              "generationConfig": {"responseModalities": ["IMAGE"]}},
        timeout=180)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    part = next(p for p in parts if "inlineData" in p)
    return base64.b64decode(part["inlineData"]["data"])


def _hf_kontext(image_url: str, prompt: str) -> bytes:
    r = requests.post(
        "https://router.huggingface.co/fal-ai/fal-ai/flux-kontext/dev",
        headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
        json={"prompt": prompt, "image_url": image_url, "output_format": "jpeg"},
        timeout=240)
    r.raise_for_status()
    out_url = r.json()["images"][0]["url"]
    return requests.get(out_url, timeout=60).content


def _replicate_kontext(image_url: str, prompt: str) -> bytes:
    r = requests.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-kontext-dev/predictions",
        headers={"Authorization": f"Bearer {os.environ['REPLICATE_API_TOKEN']}",
                 "Prefer": "wait=60"},
        json={"input": {"prompt": prompt, "input_image": image_url,
                        "aspect_ratio": "match_input_image", "output_format": "jpg"}},
        timeout=120)
    r.raise_for_status()
    pred = r.json()
    while pred["status"] not in ("succeeded", "failed", "canceled"):
        time.sleep(3)
        pred = requests.get(pred["urls"]["get"],
                            headers={"Authorization": f"Bearer {os.environ['REPLICATE_API_TOKEN']}"},
                            timeout=30).json()
    if pred["status"] != "succeeded":
        raise RuntimeError(pred.get("error", "replicate failed"))
    out = pred["output"] if isinstance(pred["output"], str) else pred["output"][0]
    return requests.get(out, timeout=60).content


IMG_CHAIN = [
    ("gemini nano-banana (free)", lambda b, u, p: _gemini_image(b, p)),
    ("hf kontext (free credits)", lambda b, u, p: _hf_kontext(u, p)),
    ("replicate kontext (paid)",  lambda b, u, p: _replicate_kontext(u, p)),
]
_CHAIN_START = 0


def recreate(image_bytes: bytes, image_url: str, prompt: str) -> tuple[bytes, str]:
    global _CHAIN_START
    order = IMG_CHAIN[_CHAIN_START:] + IMG_CHAIN[:_CHAIN_START]
    last = None
    for label, fn in order:
        try:
            out = fn(image_bytes, image_url, prompt)
            _CHAIN_START = next(i for i, (l, _) in enumerate(IMG_CHAIN) if l == label)
            return out, label
        except Exception as e:
            print(f"    {label} failed: {str(e)[:120]}")
            last = e
    raise RuntimeError(f"all image backends failed: {last}")


def qc_check(original: bytes, recreated: bytes) -> dict:
    return _qc_vision(QC_PROMPT, original, recreated)


def _qc_vision(prompt: str, original: bytes, recreated: bytes) -> dict:
    """Free vision QC via Gemini 2.5 Flash. On QC infra failure, pass-through
    with verdict 'unchecked' rather than blocking the batch."""
    try:
        key = os.environ["GEMINI_API_KEY"]
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [
                      {"text": prompt},
                      {"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(original).decode()}},
                      {"inline_data": {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(recreated).decode()}}]}],
                  "generationConfig": {"responseMimeType": "application/json"}},
            timeout=120)
        r.raise_for_status()
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)
    except Exception as e:
        return {"verdict": "unchecked", "reason": str(e)[:100]}


def select_photos(listing: dict) -> list[str]:
    """Selective mode: prioritize main rooms, cap at MAX_PHOTOS."""
    by_room = listing.get("images_by_room") or {}
    urls_in_priority = []
    seen = set()
    for kw in ROOM_PRIORITY:
        for room, urls in by_room.items():
            if kw in room.lower():
                for u in urls:
                    if u and u not in seen:
                        urls_in_priority.append(u); seen.add(u)
    for u in (listing.get("image_urls") or []):    # fill remainder in listing order
        if u and u not in seen:
            urls_in_priority.append(u); seen.add(u)
    return urls_in_priority[:MAX_PHOTOS]


def process_lead(listing: dict, cap=None) -> dict:
    lid = listing["listing_id"]
    out_dir = PHOTOS_DIR / lid
    (out_dir / "originals").mkdir(parents=True, exist_ok=True)
    (out_dir / "recreated").mkdir(parents=True, exist_ok=True)

    photos = select_photos(listing)
    if cap:
        photos = photos[:cap]
    print(f"[step3] {lid}: {len(photos)} photos selected (of {len(listing.get('image_urls') or [])})")

    manifest = []
    for n, url in enumerate(photos, 1):
        try:
            orig = requests.get(url, timeout=60).content
        except Exception as e:
            print(f"  {n}: download failed, skipped ({str(e)[:80]})")
            continue
        (out_dir / "originals" / f"{n:02d}.jpg").write_bytes(orig)

        # Deterministic geometry pre-pass: straighten verticals with OpenCV
        # BEFORE the AI pass. AI generation and QC both use the straightened base.
        base, geo_applied = straighten(orig)

        tv = detect_tv(base)
        prompt = build_prompt(listing, tv_visible=tv)
        if n == 1:   # first selected photo = cover -> hero treatment, same angle
            prompt += HERO_SUFFIX
        status, backend, verdict = "recreated", "", {}

        def qc_score(v):
            return sum(1 for x in v.values() if x is True)

        try:
            # BEST-OF-2: generate two candidates, QC both, keep the better one
            candidates = []
            for c in (1, 2):
                try:
                    cand, cb = recreate(base, url, prompt)
                    cv = qc_check(base, cand)
                    record_lesson(cv)
                    candidates.append((cand, cb, cv))
                    print(f"  {n}.{c}: QC {cv.get('verdict','?')} (score {qc_score(cv)}) "
                          f"{('- ' + cv.get('reason','')[:70]) if cv.get('verdict')=='fail' else ''}")
                except Exception as e:
                    print(f"  {n}.{c}: generation failed ({str(e)[:70]})")
            if not candidates:
                raise RuntimeError("both candidates failed to generate")
            candidates.sort(key=lambda t: (t[2].get("verdict") == "pass", qc_score(t[2])), reverse=True)
            rec, backend, verdict = candidates[0]

            # One corrective retry if even the best candidate fails
            if verdict.get("verdict") == "fail":
                print(f"  {n}: best candidate still fails — corrective retry")
                rec2, backend2 = recreate(base, url, prompt +
                    f" CORRECTION: the previous attempt failed review because: "
                    f"{verdict.get('reason','')}. You MUST fix exactly that while following all other rules.")
                verdict2 = qc_check(base, rec2)
                record_lesson(verdict2)
                if (verdict2.get("verdict") == "pass") or qc_score(verdict2) > qc_score(verdict):
                    rec, backend, verdict = rec2, backend2, verdict2
            if verdict.get("verdict") == "fail":
                print(f"  {n}: QC FAIL after best-of-2 + retry — shipping straightened original")
                rec, status = base, "original_kept"
        except Exception as e:
            print(f"  {n}: recreation failed ({str(e)[:80]}) — shipping original")
            rec, status = base, "original_kept"

        (out_dir / "recreated" / f"{n:02d}.jpg").write_bytes(rec)

        # STAGED TIER — best-of-2 with staging QC; skip silently on failure
        # (the staged set is a bonus deliverable, never blocks the true set)
        staged_status = "skipped"
        try:
            (out_dir / "staged").mkdir(exist_ok=True)
            s_cands = []
            from photo_grade import highkey_grade as _grade
            for _ in (1, 2):
                try:
                    s_img, _b = recreate(base, url, STAGING_PROMPT)
                    s_img = _grade(s_img)          # grade BEFORE QC — judge the shipping image
                    s_v = qc_check_staged(base, s_img)
                    s_cands.append((s_img, s_v))
                except Exception as e:
                    print(f"    staged gen failed: {str(e)[:70]}")
            s_cands.sort(key=lambda t: (t[1].get("verdict") == "pass",
                                        sum(1 for x in t[1].values() if x is True)),
                         reverse=True)
            if s_cands and s_cands[0][1].get("verdict") == "pass":
                (out_dir / "staged" / f"{n:02d}.jpg").write_bytes(
                    watermark_staged(s_cands[0][0]))
                staged_status = "staged"
            else:
                staged_status = "qc_fail"
        except Exception as e:
            print(f"    staged tier error: {str(e)[:70]}")

        manifest.append({"n": n, "url": url, "status": status,
                         "backend": backend, "qc": verdict,
                         "staged": staged_status, "tv": tv})
        print(f"  {n}: {status} via {backend or '-'} | QC: {verdict.get('verdict','-')} | staged: {staged_status}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"listing_id": lid, "photos": len(manifest),
            "recreated": sum(1 for m in manifest if m["status"] == "recreated"),
            "dir": str(out_dir)}


def main():
    only_id = sys.argv[1] if len(sys.argv) > 1 else None
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else None

    leads = json.loads(QUALIFIED.read_text())
    with open(TRACKER_CSV) as f:
        rows = list(csv.DictReader(f))
    by_id = {r["listing_id"]: r for r in rows}

    for l in leads:
        lid = l["listing_id"]
        if only_id and lid != only_id:
            continue
        row = by_id.get(lid)
        if row is None or row.get("status") != "Analyzed":
            continue
        res = process_lead(l, cap=cap)
        row["status"] = "Photos Done"
        print(f"[step3] {lid}: {res['recreated']}/{res['photos']} recreated -> {res['dir']}\n")

    fieldnames = list(rows[0].keys())
    with open(TRACKER_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
