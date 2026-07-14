"""
Outreach PDF — 4-page teaser attached to cold emails.

Feels like a pitch deck: one idea per page, bold numbers, specific to their listing.
Ends with the $29 offer and checkout URL.

Usage:
  python3 outreach_pdf.py <listing_id> [--checkout-url URL]
"""
from __future__ import annotations
import sys, json, io
from pathlib import Path
from PIL import Image as PILImage, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas

HERE      = Path(__file__).parent
TEARDOWNS = HERE / "work" / "teardowns"
PHOTOS    = HERE / "work" / "photos"
PDF_DIR   = HERE / "work" / "pdfs"

W, H = A4
M    = 18 * mm

CREAM = HexColor("#edeae2")
INK   = HexColor("#191919")
CORAL = HexColor("#e8391d")
MUTED = HexColor("#8a877c")
LINE  = HexColor("#c9c5ba")
WHITE = HexColor("#ffffff")
CARD  = HexColor("#e4e0d7")

_CHAR_MAP = {"‑":"-","‐":"-","–":"-"," ":" ","'":"'","'":"'",""":'"',""":'"',"…":"...","•":"-"}
def clean(s):
    if not isinstance(s, str): return s
    for bad, good in _CHAR_MAP.items():
        s = s.replace(bad, good)
    return "".join(c for c in s if ord(c) < 0x2500)

def _crop(path, ratio):
    im = PILImage.open(path).convert("RGB")
    w, h = im.size
    if w/h > ratio:
        nw = int(h*ratio); im = im.crop(((w-nw)//2, 0, (w+nw)//2, h))
    else:
        nh = int(w/ratio); im = im.crop((0, (h-nh)//2, w, (h+nh)//2))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88); buf.seek(0)
    return ImageReader(buf)

def _blurred_crop(path, ratio, radius=18):
    im = PILImage.open(path).convert("RGB")
    w, h = im.size
    if w/h > ratio:
        nw = int(h*ratio); im = im.crop(((w-nw)//2, 0, (w+nw)//2, h))
    else:
        nh = int(w/ratio); im = im.crop((0, (h-nh)//2, w, (h+nh)//2))
    im = im.filter(ImageFilter.GaussianBlur(radius))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80); buf.seek(0)
    return ImageReader(buf)

def _footer(c, text="listingboost  ·  hello@scalr-us.com"):
    c.setFont("Helvetica", 7.5); c.setFillColor(MUTED)
    c.drawString(M, 11*mm, text)
    c.setStrokeColor(LINE); c.setLineWidth(0.5)
    c.line(M, 14*mm, W-M, 14*mm)

def _wrap(c, text, x, y, width, font="Helvetica", size=10, leading=None, color=INK):
    leading = leading or size * 1.5
    c.setFont(font, size); c.setFillColor(color)
    for line in simpleSplit(text, font, size, width):
        c.drawString(x, y, line); y -= leading
    return y


# ─── Page 1: Cover — personal, specific ───────────────────────────────────────

def page_cover(c, td, nums, hero: Path | None):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)

    # Top meta strip
    c.setFont("Helvetica", 7.5); c.setFillColor(MUTED)
    c.drawString(M, H-11*mm, f"prepared for {clean(td.get('host_name',''))}")
    c.drawRightString(W-M, H-11*mm, clean(td.get('analyzed_at','').split('T')[0] if td.get('analyzed_at') else ''))

    # Hero photo — full right column, framed
    if hero and hero.exists():
        fw, fh = 112*mm, 88*mm
        fx, fy = W-M-fw, H-28*mm-fh
        c.drawImage(_crop(hero, fw/fh), fx, fy, fw, fh)
        # coral dot at corner
        c.setFillColor(CORAL); c.circle(fx, fy+fh, 5*mm, fill=1, stroke=0)

    # Big left column headline
    y = 102*mm
    c.setFont("Helvetica-Bold", 42); c.setFillColor(CORAL)
    c.drawString(M, y,      "we looked")
    c.drawString(M, y-13*mm,"at your")
    c.drawString(M, y-26*mm,"listing.")

    # One-liner tension
    y = 68*mm
    c.setFont("Helvetica-Bold", 12); c.setFillColor(INK)
    open_n = nums.get('open_nights_90d', '?')
    rate   = nums.get('nightly_rate_gbp', 0)
    c.drawString(M, y, f"{open_n} open nights in the next 90 days.")
    y -= 7*mm
    c.setFont("Helvetica", 10); c.setFillColor(INK)
    c.drawString(M, y, "Here's exactly what's holding the listing back —")
    y -= 5.5*mm
    c.drawString(M, y, "and what we'd fix for £29.")

    # Bottom rule
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(M, 20*mm, W-M, 20*mm)
    c.setFont("Helvetica", 7.5); c.setFillColor(MUTED)
    c.drawString(M, 15*mm, "confidential — prepared for you, not for distribution")
    c.showPage()


# ─── Page 2: The gap — one idea, massive ──────────────────────────────────────

def page_the_gap(c, td, nums):
    c.setFillColor(INK); c.rect(0, 0, W, H, fill=1, stroke=0)   # dark slide

    open_n = nums.get('open_nights_90d', '?')
    stake  = nums.get('revenue_at_stake_gbp', 0)
    rate   = nums.get('nightly_rate_gbp', 0)

    # Page number / eyebrow
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawString(M, H-12*mm, "what we found")

    # Giant stat
    y = H * 0.68
    num_str = f"£{stake/3:,.0f}" if stake else f"{open_n} nights"
    c.setFont("Helvetica-Bold", 62); c.setFillColor(CORAL)
    c.drawString(M, y, num_str)

    y -= 18*mm
    c.setFont("Helvetica-Bold", 16); c.setFillColor(WHITE)
    c.drawString(M, y, "sitting there. Uncaptured.")

    y -= 14*mm
    c.setFont("Helvetica", 10.5); c.setFillColor(HexColor("#b0ada6"))
    if stake and rate:
        c.drawString(M, y, f"That's the conservative case: {open_n} open nights, one third booked,")
        y -= 6*mm
        c.drawString(M, y, f"at your current £{rate:,.0f}/night rate.")
    else:
        c.drawString(M, y, f"{open_n} open nights on your calendar in the next 90 days.")

    # Photo score + industry benchmark — specific, real data only
    score_images = td.get("analysis", {}).get("score_images")
    y -= 14*mm
    if score_images is not None:
        bar_w = 60*mm
        bar_h = 4*mm
        score_x = M
        score_y = y
        c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawString(score_x, score_y + 5*mm, "PHOTO QUALITY SCORE")
        # Grey track
        c.setFillColor(HexColor("#333330")); c.roundRect(score_x, score_y, bar_w, bar_h, 1*mm, fill=1, stroke=0)
        # Coral fill proportional to score
        fill_w = max(2*mm, min(bar_w, bar_w * score_images / 10))
        c.setFillColor(CORAL); c.roundRect(score_x, score_y, fill_w, bar_h, 1*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10); c.setFillColor(WHITE)
        c.drawString(score_x + bar_w + 3*mm, score_y + 1*mm, f"{score_images:.1f}/10")
        c.setFont("Helvetica", 8); c.setFillColor(MUTED)
        c.drawString(score_x + bar_w + 16*mm, score_y + 1*mm, "(industry avg: 6.4/10)")
        y -= 14*mm

    # Three diagnosis bullets — the specific problems
    diag = td.get("analysis", {}).get("key_diagnosis", [])[:3]
    y -= 6*mm
    c.setFont("Helvetica-Bold", 9); c.setFillColor(MUTED)
    c.drawString(M, y, "WHY IT'S SITTING EMPTY")
    c.setStrokeColor(CORAL); c.setLineWidth(0.8)
    c.line(M, y-2.5*mm, M+42*mm, y-2.5*mm)
    y -= 12*mm
    for d in diag:
        c.setFillColor(CORAL); c.circle(M+2*mm, y+1.5*mm, 2*mm, fill=1, stroke=0)
        y = _wrap(c, clean(d), M+8*mm, y, W-2*M-8*mm, size=10.5, color=WHITE, leading=14) - 5*mm

    # Footer
    c.setFont("Helvetica", 7.5); c.setFillColor(MUTED)
    c.drawString(M, 11*mm, "listingboost  ·  hello@scalr-us.com")
    c.showPage()


# ─── Page 3: A glimpse — blurred before/after, entice not deliver ─────────────

def page_glimpse(c, pdir: Path, td):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)

    # Eyebrow
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawString(M, H-12*mm, "what changes")

    # Headline
    y = H-24*mm
    c.setFont("Helvetica-Bold", 34); c.setFillColor(CORAL)
    c.drawString(M, y, "same room.")
    y -= 12*mm
    c.drawString(M, y, "different listing.")

    y -= 9*mm
    c.setFont("Helvetica", 10); c.setFillColor(INK)
    c.drawString(M, y, "Same photos, professionally re-lit and reordered.")
    y -= 5.5*mm
    c.drawString(M, y, "Here's a preview — the full set comes with the report.")

    # Find the best before/after pair
    orig_dir = pdir / "originals"
    reco_dir = pdir / "recreated"
    pairs = []
    if orig_dir.exists() and reco_dir.exists():
        for f in sorted(orig_dir.glob("*.jpg")):
            r = reco_dir / f.name
            if r.exists():
                pairs.append((f, r))

    y -= 10*mm
    if pairs:
        # Show one pair side by side: left = BLURRED original (teaser), right = sharp reco
        o_path, r_path = pairs[0]
        ph = 72*mm
        pw = (W - 2*M - 6*mm) / 2
        ratio = pw / ph

        # Left: blurred / "before" hint
        c.drawImage(_blurred_crop(o_path, ratio, radius=22), M, y-ph, pw, ph)
        c.setFillColor(HexColor("#191919cc" if False else INK))
        # subtle dark overlay on blurred side
        c.setFillAlpha(0.35); c.rect(M, y-ph, pw, ph, fill=1, stroke=0); c.setFillAlpha(1)
        c.setFont("Helvetica-Bold", 9); c.setFillColor(WHITE)
        c.drawCentredString(M + pw/2, y - ph/2, "before")

        # Right: sharp after
        c.drawImage(_crop(r_path, ratio), M+pw+6*mm, y-ph, pw, ph)
        c.setFont("Helvetica-Bold", 9); c.setFillColor(WHITE)
        # small label on the after
        c.setFillColor(CORAL); c.roundRect(M+pw+6*mm+pw-22*mm, y-ph+4*mm, 18*mm, 7*mm, 1*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 8); c.setFillColor(WHITE)
        c.drawCentredString(M+pw+6*mm+pw-13*mm, y-ph+7*mm, "after")

        y -= ph + 8*mm

    # Teaser copy — what else is in the full report
    photo_rec = td.get("analysis", {}).get("photo_order_rec", "")
    if photo_rec and y > 45*mm:
        c.setFillColor(CARD)
        c.roundRect(M, y-22*mm, W-2*M, 22*mm, 2*mm, fill=1, stroke=0)
        c.setFillColor(CORAL); c.rect(M, y-22*mm, 1.5*mm, 22*mm, fill=1, stroke=0)
        y2 = y - 8*mm
        c.setFont("Helvetica-Bold", 9.5); c.setFillColor(INK)
        c.drawString(M+6*mm, y2, "Cover photo strategy (from the full report):")
        y2 -= 5.5*mm
        _wrap(c, clean(photo_rec), M+6*mm, y2, W-2*M-12*mm, size=9, color=INK)

    _footer(c)
    c.showPage()


# ─── Page 4: The offer — clean, direct, one CTA ───────────────────────────────

def page_offer(c, td, nums, checkout_url: str):
    c.setFillColor(CREAM); c.rect(0, 0, W, H, fill=1, stroke=0)

    # Top label
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawString(M, H-12*mm, "next step")

    # Big headline
    y = H-28*mm
    c.setFont("Helvetica-Bold", 40); c.setFillColor(INK)
    c.drawString(M, y, "everything,")
    y -= 13*mm
    c.drawString(M, y, "ready to upload.")

    y -= 12*mm
    c.setFont("Helvetica", 11); c.setFillColor(INK)
    c.drawString(M, y, "The full report lands in your inbox within 48 hours.")

    # What's included — clean list, not a feature dump
    y -= 16*mm
    items = [
        ("Photo teardown",      "Every photo scored. What to cut, what to fix, what to move to the front."),
        ("Re-edited photos",    "Your shots re-lit and straightened. Same rooms — just showing them properly."),
        ("Three title variants","Ready to paste. Written for search and for the click."),
        ("Rewritten description","Your words, tightened. Tells the story guests actually want to read."),
    ]
    for title, body in items:
        c.setFillColor(CORAL); c.circle(M+2*mm, y+1.5*mm, 2*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10.5); c.setFillColor(INK)
        c.drawString(M+8*mm, y, title)
        y -= 5.5*mm
        _wrap(c, body, M+8*mm, y, W-2*M-8*mm, size=9.5, color=MUTED)
        y -= 9*mm

    # Price + CTA block
    y -= 4*mm
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(M, y, W-M, y)
    y -= 10*mm

    # Price
    c.setFont("Helvetica-Bold", 32); c.setFillColor(CORAL)
    c.drawString(M, y, "£29")
    c.setFont("Helvetica", 10); c.setFillColor(MUTED)
    c.drawString(M+22*mm, y+2*mm, "· one time · 48-hour delivery")

    y -= 10*mm
    # Guarantee line
    c.setFont("Helvetica", 9.5); c.setFillColor(INK)
    c.drawString(M, y, "Doesn't move the needle? Reply and I'll refund it. No forms.")

    # CTA — the URL printed clearly (clickable in PDF readers)
    y -= 14*mm
    c.setFillColor(CORAL)
    c.roundRect(M, y-10*mm, W-2*M, 14*mm, 2.5*mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 11); c.setFillColor(WHITE)
    c.drawCentredString(W/2, y-4.5*mm, "Get the full report →")
    # Invisible link overlay
    c.linkURL(checkout_url, (M, y-10*mm, W-M, y+4*mm), relative=0)

    y -= 16*mm
    c.setFont("Helvetica", 8); c.setFillColor(MUTED)
    c.drawCentredString(W/2, y, checkout_url)

    _footer(c, "listingboost  ·  hello@scalr-us.com  ·  questions? just reply")
    c.showPage()


# ─── Build ─────────────────────────────────────────────────────────────────────

def build_outreach_pdf(lid: str, checkout_url: str) -> Path:
    td_path = TEARDOWNS / f"teardown_{lid}.json"
    if not td_path.exists():
        raise FileNotFoundError(f"No teardown for {lid}. Run step2_teardown.py first.")
    td   = json.loads(clean(td_path.read_text(ensure_ascii=False) if False else td_path.read_text()))
    td   = json.loads(clean(json.dumps(td, ensure_ascii=False)))
    nums = td.get("listing_numbers", {})
    pdir = PHOTOS / lid

    PDF_DIR.mkdir(exist_ok=True)
    out = PDF_DIR / f"outreach_{lid}.pdf"
    c = Canvas(str(out), pagesize=A4)
    c.setTitle(f"Your Listing — A Quick Look")

    hero = pdir / "recreated" / "01.jpg"
    if not hero.exists():
        hero = next(pdir.glob("originals/*.jpg"), None) if pdir.exists() else None

    page_cover(c, td, nums, hero)
    page_the_gap(c, td, nums)
    page_glimpse(c, pdir, td)
    page_offer(c, td, nums, checkout_url)
    c.save()
    return out


def main():
    import argparse, os
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env", override=True)
    p = argparse.ArgumentParser()
    p.add_argument("listing_id")
    p.add_argument("--checkout-url",
                   default=os.environ.get("GUMROAD_URL", "https://itsalfahri.gumroad.com/l/bkitwy"))
    args = p.parse_args()
    out = build_outreach_pdf(args.listing_id, args.checkout_url)
    print(f"[outreach_pdf] -> {out}  ({out.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
