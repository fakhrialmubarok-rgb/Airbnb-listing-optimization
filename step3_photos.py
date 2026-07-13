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
import sys, json, csv, base64, time
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)
import os

TRACKER_CSV  = HERE / "work" / "leads_tracker.csv"
QUALIFIED    = HERE / "work" / "step1_qualified.json"
PHOTOS_DIR   = HERE / "work" / "photos"
MAX_PHOTOS   = 10          # selective mode: recreate only the photos that matter
ROOM_PRIORITY = ("living", "bedroom", "kitchen", "bathroom", "dining", "garden", "exterior")

# LOCKED PROMPT TEMPLATE — numbered checklist; every item is mandatory
PROMPT_TEMPLATE = (
    "Recreate this photo as a flawless professional real-estate photograph of the SAME room. "
    "Apply EVERY numbered requirement — each one must be clearly visible in the result:\n"
    "1. BRIGHTNESS: the whole room including the ceiling and corners is DRAMATICALLY brighter "
    "than the original — professional HDR real-estate exposure, no dark or murky areas anywhere.\n"
    "2. LIGHTS ON: every ceiling light, chandelier and lamp visible in the room is switched ON "
    "and clearly GLOWING warm light. Not one fixture stays off.\n"
    "3. WINDOWS: windows are correctly exposed — the view outside is visible and natural, "
    "NEVER a blown-out white overexposed rectangle.\n"
    "4. CABLES: every visible cable, wire, cord and plug is completely removed. Zero cables "
    "in the final image.\n"
    "5. NEATNESS: curtains hang in smooth tidy folds, sofa cushions are plumped and perfectly "
    "arranged, throws folded neatly, all fabrics smooth. The room looks hotel-housekeeping neat.\n"
    "6. FRAMING (MANDATORY — re-shoot, do not copy the original camera): the original photo "
    "was taken carelessly with a tilted handheld phone. You are RE-SHOOTING the room from a "
    "proper tripod: camera perfectly level at chest height, every wall edge and door frame "
    "exactly vertical, floor line level. The perspective MUST visibly differ from the "
    "original's tilt — a clean, balanced, wide professional real-estate composition.\n"
    "{tv_rule}"
    "7. ABSOLUTE CONTENT RULE: do NOT add any new furniture or objects that are not in the "
    "original. Do NOT remove, move, resize or recolor any furniture, plants, textiles, "
    "curtains, cushions, wall art or decor. Same items, same colors, same positions, same "
    "sizes. Only lighting, tidiness, cable removal{tv_clause} and camera geometry change.\n"
    "Ultra-photorealistic. Magazine-grade editorial interior photography."
)

TV_RULE = ("8. TV SCREEN: the television that exists in this photo displays a beautiful, "
           "photorealistic scenic image of {attraction} — like a premium tourism advert.\n")

TV_DETECT_PROMPT = ("Is there a television/TV screen clearly visible in this photo? "
                    "Return ONLY JSON: {\"tv_visible\": true|false}")

# City -> nearby tourist attraction shown on TVs (extend as new markets are scraped)
CITY_ATTRACTIONS = {
    "manchester": "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "middleton":  "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "whitefield": "a famous Manchester landmark (Old Trafford stadium or the Manchester city skyline)",
    "london":     "Big Ben and the Houses of Parliament at golden hour",
    "leeds":      "the Leeds city skyline or Kirkstall Abbey",
    "liverpool":  "the Royal Liver Building on Liverpool's waterfront",
}

def build_prompt(listing: dict, tv_visible: bool) -> str:
    city = (listing.get("location") or "").lower()
    attraction = next((a for c, a in CITY_ATTRACTIONS.items() if c in city),
                      "a famous local tourist attraction near the property")
    if tv_visible:
        return PROMPT_TEMPLATE.format(
            tv_rule=TV_RULE.format(attraction=attraction),
            tv_clause=", the TV screen content")
    return PROMPT_TEMPLATE.format(tv_rule="", tv_clause="")


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
    "AI-recreated version that must show the SAME room with IDENTICAL furniture. "
    "EXPECTED and ALLOWED differences in photo 2 (do NOT fail for these): much brighter "
    "lighting, lamps turned on, clutter and cables removed, tidier fabrics, different "
    "content shown on an EXISTING TV screen, straightened camera geometry. "
    "Return ONLY JSON: {"
    "\"no_added_objects\": bool,        # NOTHING new — no TVs, furniture or decor that photo 1 lacks\n"
    "\"same_furniture_and_colors\": bool,\n"
    "\"no_ai_artifacts\": bool,\n"
    "\"straight_verticals\": bool,\n"
    "\"dramatically_brighter\": bool,   # whole room incl. ceiling clearly brighter, no murky areas\n"
    "\"lights_on\": bool,               # fixtures/lamps present in the room are visibly glowing\n"
    "\"no_visible_cables\": bool,\n"
    "\"window_not_blown_out\": bool,    # windows show detail, not pure white\n"
    "\"fabrics_neat\": bool,            # curtains/sofa/throws look tidy\n"
    "\"verdict\": \"pass\"|\"fail\", \"reason\": \"<short, name every failed check>\"}. "
    "Verdict is pass ONLY if every single check is true. Be strict."
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
    """Free vision QC via Gemini 2.5 Flash. On QC infra failure, pass-through
    with verdict 'unchecked' rather than blocking the batch."""
    try:
        key = os.environ["GEMINI_API_KEY"]
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [
                      {"text": QC_PROMPT},
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

        tv = detect_tv(orig)
        prompt = build_prompt(listing, tv_visible=tv)
        status, backend, verdict = "recreated", "", {}

        def qc_score(v):
            return sum(1 for x in v.values() if x is True)

        try:
            # BEST-OF-2: generate two candidates, QC both, keep the better one
            candidates = []
            for c in (1, 2):
                try:
                    cand, cb = recreate(orig, url, prompt)
                    cv = qc_check(orig, cand)
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
                rec2, backend2 = recreate(orig, url, prompt +
                    f" CORRECTION: the previous attempt failed review because: "
                    f"{verdict.get('reason','')}. You MUST fix exactly that while following all other rules.")
                verdict2 = qc_check(orig, rec2)
                if (verdict2.get("verdict") == "pass") or qc_score(verdict2) > qc_score(verdict):
                    rec, backend, verdict = rec2, backend2, verdict2
            if verdict.get("verdict") == "fail":
                print(f"  {n}: QC FAIL after best-of-2 + retry — shipping original")
                rec, status = orig, "original_kept"
        except Exception as e:
            print(f"  {n}: recreation failed ({str(e)[:80]}) — shipping original")
            rec, status = orig, "original_kept"

        (out_dir / "recreated" / f"{n:02d}.jpg").write_bytes(rec)
        manifest.append({"n": n, "url": url, "status": status,
                         "backend": backend, "qc": verdict})
        print(f"  {n}: {status} via {backend or '-'} | QC: {verdict.get('verdict','-')}")

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
