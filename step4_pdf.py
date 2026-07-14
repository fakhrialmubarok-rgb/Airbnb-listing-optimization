"""
Step 4 — PDF Report Assembly (process v2, pending lock)

Canvas-drawn premium report: full-bleed cover, dark stat band, scorecard,
rewritten copy, large before/after pairs. Design bar: something a host would
believe cost $500, delivered for $29.

Usage:
  python3 step4_pdf.py                # all leads with Photos Done
  python3 step4_pdf.py <listing_id>   # one lead
"""
from __future__ import annotations
import sys, json, csv, io
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas

HERE        = Path(__file__).parent
TRACKER_CSV = HERE / "work" / "leads_tracker.csv"
TEARDOWNS   = HERE / "work" / "teardowns"
PHOTOS_DIR  = HERE / "work" / "photos"
PDF_DIR     = HERE / "work" / "pdfs"

W, H = A4
M = 16 * mm                     # page margin

NAVY   = HexColor("#141c2b")
NAVY2  = HexColor("#1e2a40")
CORAL  = HexColor("#ff6b52")
CREAM  = HexColor("#faf7f2")
INK    = HexColor("#20293a")
MUTED  = HexColor("#8a93a5")
LINE   = HexColor("#e3ddd2")
WHITE  = HexColor("#ffffff")

_CHAR_MAP = {"‑": "-", "‐": "-", "–": "-", " ": " ", "‘": "'", "’": "'",
             "“": '"', "”": '"', "…": "...", "•": "-"}

def clean(s):
    if not isinstance(s, str):
        return s
    for bad, good in _CHAR_MAP.items():
        s = s.replace(bad, good)
    return "".join(c for c in s if ord(c) < 0x2500)


def _cover_crop(path: Path, target_ratio: float) -> ImageReader:
    """Center-crop an image to exactly target_ratio (w/h) so it fills its box."""
    im = PILImage.open(path).convert("RGB")
    w, h = im.size
    if w / h > target_ratio:              # too wide -> crop sides
        nw = int(h * target_ratio)
        im = im.crop(((w - nw)//2, 0, (w + nw)//2, h))
    else:                                  # too tall -> crop top/bottom
        nh = int(w / target_ratio)
        im = im.crop((0, (h - nh)//2, w, (h + nh)//2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return ImageReader(buf)


def _fit(path: Path, max_w, max_h):
    iw, ih = ImageReader(str(path)).getSize()
    s = min(max_w / iw, max_h / ih)
    return iw * s, ih * s


def _wrap_text(c: Canvas, text, x, y, width, font="Helvetica", size=10,
               leading=None, color=INK) -> float:
    """Draw wrapped text, return y after the last line."""
    leading = leading or size * 1.45
    c.setFont(font, size); c.setFillColor(color)
    for line in simpleSplit(text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def _footer(c: Canvas, page_no: int):
    c.setFont("Helvetica", 7.5); c.setFillColor(MUTED)
    c.drawString(M, 10*mm, "LISTINGBOOST")
    c.drawRightString(W - M, 10*mm, f"{page_no:02d}")
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(M, 13.5*mm, W - M, 13.5*mm)


def _eyebrow(c, x, y, text):
    c.setFont("Helvetica-Bold", 8.5); c.setFillColor(CORAL)
    c.drawString(x, y, text.upper())


def _h1(c, x, y, text, color=INK, size=24):
    c.setFont("Helvetica-Bold", size); c.setFillColor(color)
    c.drawString(x, y, text)


# ---------------------------------------------------------------- pages ----

def page_cover(c, td, nums, hero: Path | None):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    # full-bleed hero, top 58%
    img_h = H * 0.58
    if hero and hero.exists():
        c.drawImage(_cover_crop(hero, W / img_h), 0, H - img_h, W, img_h)
    # navy band
    band_h = H - img_h
    c.setFillColor(NAVY); c.rect(0, 0, W, band_h, fill=1, stroke=0)
    # coral rule across the seam
    c.setFillColor(CORAL); c.rect(0, band_h - 1.2*mm, W, 1.2*mm, fill=1, stroke=0)

    y = band_h - 16*mm
    _eyebrow(c, M, y, "ListingBoost  ·  Professional Airbnb Teardown")
    y -= 13*mm
    c.setFont("Helvetica-Bold", 34); c.setFillColor(WHITE)
    c.drawString(M, y, "Your listing, rebuilt.")
    y -= 8.5*mm
    c.setFont("Helvetica", 11.5); c.setFillColor(HexColor("#aab4c8"))
    c.drawString(M, y, f"Prepared for {td.get('host_name','')}  ·  {td.get('analyzed_at','')}")

    stake = nums.get("revenue_at_stake_gbp")
    if stake:
        y -= 19*mm
        c.setFont("Helvetica-Bold", 30); c.setFillColor(CORAL)
        c.drawString(M, y, f"£{stake:,.0f}")
        c.setFont("Helvetica", 11.5); c.setFillColor(WHITE)
        c.drawString(M + c.stringWidth(f"£{stake:,.0f}", "Helvetica-Bold", 30) + 4*mm,
                     y + 1, "of bookings are open in your next 90 days.")
        y -= 8*mm
        c.setFont("Helvetica", 10); c.setFillColor(HexColor("#aab4c8"))
        c.drawString(M, y, f"{nums.get('open_nights_90d','?')} unbooked nights at "
                           f"£{nums.get('nightly_rate_gbp',0):,.0f}/night "
                           f"({nums.get('occupancy_pct','?')}% occupancy). "
                           "This report shows exactly why — and how to fix it.")
    c.showPage()


def _stat_card(c, x, y, w, h, value, label):
    c.setFillColor(NAVY2)
    c.roundRect(x, y, w, h, 2.5*mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 17); c.setFillColor(WHITE)
    c.drawString(x + 5*mm, y + h - 11*mm, value)
    c.setFont("Helvetica", 8); c.setFillColor(HexColor("#8fa0bd"))
    c.drawString(x + 5*mm, y + 5*mm, label.upper())


def page_scorecard(c, a, nums, page_no):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    y = H - M - 6*mm
    _eyebrow(c, M, y, "01 — Diagnosis")
    y -= 11*mm
    _h1(c, M, y, "Where the listing stands")

    # stat cards (navy strip)
    y -= 34*mm
    cards = [
        (f"£{nums.get('nightly_rate_gbp',0):,.0f}", "your nightly rate"),
        (f"{nums.get('occupancy_pct','?')}%",       "occupancy next 90d"),
        (f"{nums.get('open_nights_90d','?')}",      "open nights"),
        (f"£{nums.get('revenue_at_stake_gbp',0):,.0f}", "revenue at stake"),
    ]
    cw = (W - 2*M - 3*4.5*mm) / 4
    for i, (v, l) in enumerate(cards):
        _stat_card(c, M + i*(cw + 4.5*mm), y, cw, 24*mm, v, l)

    # score bars
    y -= 14*mm
    scores = [("Title", a.get("score_title", 0)), ("Description", a.get("score_desc", 0)),
              ("Amenities", a.get("score_amenities", 0)), ("Photos", a.get("score_images", 0)),
              ("Demand signal", a.get("score_occupancy_signal", 0))]
    bar_x, bar_w = M + 42*mm, W - 2*M - 42*mm - 16*mm
    for label, s in scores:
        y -= 9.5*mm
        c.setFont("Helvetica-Bold", 9.5); c.setFillColor(INK)
        c.drawString(M, y, label)
        c.setFillColor(HexColor("#eee8dd"))
        c.roundRect(bar_x, y - 1, bar_w, 4.2*mm, 2.1*mm, fill=1, stroke=0)
        if s > 0:
            c.setFillColor(CORAL if s <= 4 else (HexColor("#f0a03c") if s <= 6 else HexColor("#3fae6a")))
            c.roundRect(bar_x, y - 1, bar_w * min(s,10)/10, 4.2*mm, 2.1*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10); c.setFillColor(INK)
        c.drawRightString(W - M, y, f"{s}/10")

    # diagnosis
    y -= 17*mm
    _eyebrow(c, M, y, "What's holding you back")
    y -= 8*mm
    for i, d in enumerate(a.get("key_diagnosis", [])[:3], 1):
        c.setFillColor(CORAL)
        c.circle(M + 2.6*mm, y + 1.2*mm, 2.6*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9); c.setFillColor(WHITE)
        c.drawCentredString(M + 2.6*mm, y - 0.9*mm, str(i))
        y = _wrap_text(c, d, M + 9*mm, y, W - 2*M - 9*mm, size=10.5) - 4.5*mm
    _footer(c, page_no)
    c.showPage()


def page_copy(c, a, page_no):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
    y = H - M - 6*mm
    _eyebrow(c, M, y, "02 — The Fixes")
    y -= 11*mm
    _h1(c, M, y, "Copy that sells the place")

    y -= 12*mm
    c.setFont("Helvetica-Bold", 11.5); c.setFillColor(INK)
    c.drawString(M, y, "Three titles, ready to paste")
    y -= 8*mm
    for i, v in enumerate(a.get("title_variants", [])[:3], 1):
        c.setFillColor(WHITE)
        c.roundRect(M, y - 4.5*mm, W - 2*M, 10.5*mm, 2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10); c.setFillColor(CORAL)
        c.drawString(M + 4*mm, y - 1*mm, f"{i:02d}")
        c.setFont("Helvetica", 10.5); c.setFillColor(INK)
        c.drawString(M + 12*mm, y - 1*mm, clean(v))
        y -= 13.5*mm

    y -= 5*mm
    c.setFont("Helvetica-Bold", 11.5); c.setFillColor(INK)
    c.drawString(M, y, "Your description, rewritten")
    y -= 7*mm
    desc = clean(a.get("rewritten_desc", ""))
    lines = simpleSplit(desc, "Helvetica", 9.5, W - 2*M - 10*mm)
    box_h = len(lines) * 13.5 + 16
    c.setFillColor(WHITE)
    c.roundRect(M, y - box_h, W - 2*M, box_h, 2.5*mm, fill=1, stroke=0)
    c.setFillColor(CORAL); c.rect(M, y - box_h, 1.4*mm, box_h, fill=1, stroke=0)
    ty = y - 12
    c.setFont("Helvetica", 9.5); c.setFillColor(INK)
    for ln in lines:
        c.drawString(M + 6*mm, ty, ln); ty -= 13.5
    y -= box_h + 10*mm

    gaps = a.get("top_amenity_gaps", [])
    if gaps and y > 45*mm:
        c.setFont("Helvetica-Bold", 11.5); c.setFillColor(INK)
        c.drawString(M, y, "Amenity gaps guests filter for")
        y -= 7.5*mm
        for g in gaps[:3]:
            c.setFillColor(CORAL); c.circle(M + 1.5*mm, y + 1.4*mm, 1.3*mm, fill=1, stroke=0)
            y = _wrap_text(c, clean(g), M + 6*mm, y, W - 2*M - 6*mm, size=10) - 3*mm
    if a.get("photo_order_rec") and y > 30*mm:
        y -= 4*mm
        c.setFont("Helvetica-Bold", 11.5); c.setFillColor(INK)
        c.drawString(M, y, "Cover photo strategy")
        y -= 7*mm
        _wrap_text(c, clean(a["photo_order_rec"]), M, y, W - 2*M, size=10)
    _footer(c, page_no)
    c.showPage()


def pages_photos(c, pdir: Path, manifest: list, page_no: int) -> int:
    pairs = [m["n"] for m in manifest
             if (pdir/"originals"/f"{m['n']:02d}.jpg").exists()
             and (pdir/"recreated"/f"{m['n']:02d}.jpg").exists()]
    first = True
    per_page = 2
    for idx in range(0, len(pairs), per_page):
        c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
        y = H - M - 6*mm
        if first:
            _eyebrow(c, M, y, "03 — Your Photos, Re-shot")
            y -= 11*mm
            _h1(c, M, y, "Before & after")
            y -= 7*mm
            c.setFont("Helvetica", 9.5); c.setFillColor(MUTED)
            c.drawString(M, y, "Same rooms, same furniture — re-lit, straightened and staged. "
                               "Full-resolution files come with this report.")
            y -= 8*mm
            first = False
        half = (W - 2*M - 6*mm) / 2
        slot_h = (y - 20*mm) / per_page
        for n in pairs[idx:idx + per_page]:
            o, r = pdir/"originals"/f"{n:02d}.jpg", pdir/"recreated"/f"{n:02d}.jpg"
            img_h = slot_h - 12*mm
            ratio = half / img_h
            top = y - 5*mm
            c.setFont("Helvetica-Bold", 8); c.setFillColor(MUTED)
            c.drawString(M, top, "BEFORE")
            c.setFillColor(CORAL)
            c.drawString(M + half + 6*mm, top, "AFTER")
            c.drawImage(_cover_crop(o, ratio), M, top - 3*mm - img_h, half, img_h)
            c.drawImage(_cover_crop(r, ratio), M + half + 6*mm, top - 3*mm - img_h, half, img_h)
            y -= slot_h
        _footer(c, page_no); page_no += 1
        c.showPage()
    return page_no


def pages_staged(c, pdir: Path, page_no: int) -> int:
    """Virtual staging concept pages — the money section. Full-width images."""
    staged = sorted((pdir / "staged").glob("*.jpg")) if (pdir / "staged").exists() else []
    if not staged:
        return page_no
    first = True
    per_page = 2
    for idx in range(0, len(staged), per_page):
        c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)
        y = H - M - 6*mm
        if first:
            _eyebrow(c, M, y, "04 — The Vision")
            y -= 11*mm
            _h1(c, M, y, "What this place could look like")
            y -= 7*mm
            c.setFont("Helvetica", 9.5); c.setFillColor(MUTED)
            y = _wrap_text(c, "Virtual staging concepts — same rooms, same furniture, "
                              "plus the styling a design studio would add. Use them as "
                              "your shopping list: every added item is affordable and "
                              "shown in your actual space.",
                           M, y, W - 2*M, size=9.5, color=MUTED) - 3*mm
            first = False
        slot_h = (y - 18*mm) / per_page
        for p in staged[idx:idx + per_page]:
            img_h = slot_h - 8*mm
            ratio = (W - 2*M) / img_h
            c.drawImage(_cover_crop(p, ratio), M, y - img_h - 3*mm, W - 2*M, img_h)
            y -= slot_h
        _footer(c, page_no); page_no += 1
        c.showPage()
    return page_no


def page_close(c, page_no):
    c.setFillColor(NAVY); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CORAL); c.rect(0, H - 1.2*mm, W, 1.2*mm, fill=1, stroke=0)
    y = H * 0.62
    _eyebrow(c, M, y, "Next step")
    y -= 12*mm
    c.setFont("Helvetica-Bold", 26); c.setFillColor(WHITE)
    c.drawString(M, y, "Paste it in. Watch what happens.")
    y -= 12*mm
    c.setFont("Helvetica", 11); c.setFillColor(HexColor("#aab4c8"))
    for ln in ["Everything in this report is ready to use today: titles, description,",
               "photo files and the exact order to arrange them in.",
               "", "Questions? Just reply to the email this came with."]:
        c.drawString(M, y, ln); y -= 6.5*mm
    y -= 8*mm
    c.setFont("Helvetica-Bold", 12); c.setFillColor(WHITE)
    c.drawString(M, y, "— AL, ListingBoost")
    c.showPage()


# ---------------------------------------------------------------- build ----

def build_pdf(lid: str) -> Path:
    td = json.loads(clean((TEARDOWNS / f"teardown_{lid}.json").read_text()))
    a, nums = td["analysis"], td.get("listing_numbers", {})
    pdir = PHOTOS_DIR / lid
    manifest = json.loads((pdir / "manifest.json").read_text()) if (pdir/"manifest.json").exists() else []

    PDF_DIR.mkdir(exist_ok=True)
    out = PDF_DIR / f"listingboost_{lid}.pdf"
    c = Canvas(str(out), pagesize=A4)
    c.setTitle(f"ListingBoost Teardown — {td.get('host_name','')}")

    page_cover(c, td, nums, pdir / "recreated" / "01.jpg")
    page_scorecard(c, a, nums, 2)
    page_copy(c, a, 3)
    next_no = pages_photos(c, pdir, manifest, 4)
    next_no = pages_staged(c, pdir, next_no)
    page_close(c, next_no)
    c.save()
    return out


def main():
    only_id = sys.argv[1] if len(sys.argv) > 1 else None
    rows = list(csv.DictReader(open(TRACKER_CSV)))
    touched = False
    for row in rows:
        lid = row["listing_id"]
        if only_id and lid != only_id:
            continue
        if not only_id and row.get("status") != "Photos Done":
            continue
        if not (TEARDOWNS / f"teardown_{lid}.json").exists():
            print(f"[step4] {lid}: no teardown, skipped"); continue
        out = build_pdf(lid)
        row["status"] = "PDF Done"; touched = True
        print(f"[step4] {lid}: -> {out} ({out.stat().st_size//1024} KB)")
    if touched:
        with open(TRACKER_CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
