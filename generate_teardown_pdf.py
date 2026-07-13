"""
ListingBoost Teardown PDF Generator
====================================
Reads manifest.csv + qc_report_free.json for a listing and produces a
professional client-facing teardown report PDF.

Usage:
    python3 generate_teardown_pdf.py \
        --listing-dir /tmp/listingboost_photos/20669368_Tanya \
        --results-dir /tmp/regen_results/20669368_Tanya \
        --host-name "Tanya" \
        --listing-title "Cozy Cabin with Hot Tub" \
        --listing-url "https://airbnb.com/rooms/20669368" \
        --out /tmp/regen_results/20669368_Tanya/teardown_report.pdf
"""

from __future__ import annotations
import argparse, csv, json, textwrap
from pathlib import Path
from fpdf import FPDF
from PIL import Image as PILImage

# ── Brand colours ─────────────────────────────────────────────────────────────
C_BLACK   = (18,  18,  18)
C_WHITE   = (255, 255, 255)
C_ACCENT  = (255, 90,  60)   # coral/red — action / hero
C_GOLD    = (200, 160,  40)  # amber    — warning / retake
C_GREEN   = (34,  139,  80)  # green    — keep / pass
C_DARK    = (40,  40,  40)
C_GRAY    = (120, 120, 120)
C_LIGHT   = (245, 245, 243)  # off-white sections

SCORE_COLORS = {
    "remove":  C_ACCENT,
    "retake":  C_GOLD,
    "hero":    (80, 140, 200),
    "keep":    C_GREEN,
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _score_bar(pdf: FPDF, score: float, x: float, y: float, w: float = 40, h: float = 4) -> None:
    """Draw a simple progress bar for a 0–10 score."""
    pdf.set_fill_color(*C_LIGHT)
    pdf.rect(x, y, w, h, "F")
    fill_w = (score / 10.0) * w
    if score >= 7.5:
        pdf.set_fill_color(*C_GREEN)
    elif score >= 6.0:
        pdf.set_fill_color(*C_GOLD)
    else:
        pdf.set_fill_color(*C_ACCENT)
    pdf.rect(x, y, fill_w, h, "F")


def _compress_thumb(img_path: Path, max_px: int = 320) -> "io.BytesIO":
    import io
    img = PILImage.open(img_path).convert("RGB")
    img.thumbnail((max_px, max_px), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70, optimize=True)
    buf.seek(0)
    return buf


def _thumb(pdf: FPDF, img_path: str | Path, x: float, y: float, w: float, h: float) -> None:
    import io
    p = Path(img_path)
    if not p.exists():
        pdf.set_fill_color(*C_LIGHT)
        pdf.rect(x, y, w, h, "F")
        return
    try:
        buf = _compress_thumb(p)
        pdf.image(buf, x=x, y=y, w=w, h=h)
    except Exception:
        pdf.set_fill_color(*C_LIGHT)
        pdf.rect(x, y, w, h, "F")


def _verdict_badge(pdf: FPDF, verdict: str, x: float, y: float) -> None:
    label = verdict.upper()
    color = SCORE_COLORS.get(verdict.lower(), C_GRAY)
    pdf.set_fill_color(*color)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x, y)
    pdf.cell(18, 5, label, align="C", fill=True)
    pdf.set_text_color(*C_BLACK)


def _section_header(pdf: FPDF, title: str) -> None:
    pdf.set_fill_color(*C_BLACK)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, f"  {title}", ln=True, fill=True)
    pdf.set_text_color(*C_BLACK)
    pdf.ln(3)


def _safe(text: str) -> str:
    """Sanitize string to Latin-1 safe characters for Helvetica."""
    replacements = {
        "—": "--", "–": "-", "‘": "'", "’": "'",
        "“": '"', "”": '"', "…": "...", "•": "*",
        "✦": "*", "→": "->", "•": "-",
    }
    for ch, repl in replacements.items():
        text = text.replace(ch, repl)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _wrap(text: str, width: int = 90) -> str:
    return "\n".join(textwrap.wrap(_safe(text), width))


# ── PDF class ─────────────────────────────────────────────────────────────────
class TeardownPDF(FPDF):
    def __init__(self, host_name: str, listing_title: str):
        super().__init__()
        self.host_name    = host_name
        self.listing_title = listing_title
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(auto=True, margin=16)

    def cell(self, w=0, h=0, txt="", **kwargs):
        return super().cell(w, h, _safe(str(txt)), **kwargs)

    def multi_cell(self, w, h, txt="", **kwargs):
        return super().multi_cell(w, h, _safe(str(txt)), **kwargs)


    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*C_BLACK)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 7, f"  ListingBoost · {self.listing_title} · Teardown Report", ln=False, fill=True)
        self.set_text_color(*C_ACCENT)
        self.cell(0, 7, "scalr-us.com  ", align="R", ln=True, fill=True)
        self.set_text_color(*C_BLACK)
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*C_GRAY)
        self.cell(0, 5, f"Confidential · Prepared for {self.host_name} · ListingBoost by Scalr", align="C")
        self.set_text_color(*C_BLACK)


# ── Pages ─────────────────────────────────────────────────────────────────────
def cover_page(pdf: TeardownPDF, host_name: str, listing_title: str,
               listing_url: str, cover_thumb: Path | None) -> None:
    pdf.add_page()

    # Black top strip
    pdf.set_fill_color(*C_BLACK)
    pdf.rect(0, 0, 210, 55, "F")

    # Logo text
    pdf.set_xy(14, 12)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 10, "ListingBoost", ln=True)
    pdf.set_xy(14, 23)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_ACCENT)
    pdf.cell(0, 6, "by Scalr · scalr-us.com", ln=True)

    # Report label
    pdf.set_xy(14, 33)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 8, "LISTING TEARDOWN REPORT", ln=True)

    pdf.set_text_color(*C_BLACK)

    # Cover thumbnail
    if cover_thumb and cover_thumb.exists():
        _thumb(pdf, cover_thumb, x=14, y=58, w=80, h=55)

    # Listing info block
    pdf.set_xy(100, 60)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*C_DARK)
    pdf.multi_cell(95, 8, listing_title)

    pdf.set_xy(100, 80)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_GRAY)
    pdf.cell(95, 6, f"Prepared for: {host_name}", ln=True)
    if listing_url:
        pdf.set_xy(100, 87)
        pdf.set_text_color(*C_ACCENT)
        pdf.cell(95, 6, listing_url, ln=True)

    pdf.set_text_color(*C_BLACK)

    # Divider
    pdf.set_draw_color(*C_ACCENT)
    pdf.set_line_width(0.8)
    pdf.line(14, 118, 196, 118)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)

    # What's inside
    pdf.set_xy(14, 122)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*C_DARK)
    pdf.cell(0, 7, "What's inside this report:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_GRAY)
    items = [
        "->  Executive summary - 3 highest-impact fixes",
        "->  Photo-by-photo audit with scores and action notes",
        "->  AI-upgraded cover photo analysis",
        "->  Priority action checklist",
        "->  28 upgraded photos delivered in a separate ZIP",
    ]
    for item in items:
        pdf.set_x(14)
        pdf.cell(0, 6, item, ln=True)

    pdf.set_text_color(*C_BLACK)

    # Footer note on cover
    pdf.set_xy(14, 260)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*C_GRAY)
    pdf.multi_cell(180, 5,
        "This report is confidential and prepared exclusively for the host named above. "
        "Data sourced from Airbnb public listing, AI photo analysis, and Scalr benchmarks.")
    pdf.set_text_color(*C_BLACK)


def exec_summary_page(pdf: TeardownPDF, manifest_rows: list[dict],
                      top10: list[dict], winner_variant: str) -> None:
    pdf.add_page()
    _section_header(pdf, "Executive Summary")

    remove_rows = [r for r in manifest_rows if r["verdict"].lower() == "remove"]
    retake_rows = [r for r in manifest_rows if r["verdict"].lower() == "retake"]
    hero_rows   = [r for r in manifest_rows if r["verdict"].lower() == "hero"]
    keep_rows   = [r for r in manifest_rows if r["verdict"].lower() == "keep"]
    scored_rows = [r for r in manifest_rows if float(r["overall_score"] or 0) > 0]
    avg_score   = sum(float(r["overall_score"]) for r in scored_rows) / len(scored_rows) if scored_rows else 0

    # Stat tiles
    tiles = [
        ("Total photos",    str(len(manifest_rows)), C_DARK),
        ("Avg photo score", f"{avg_score:.1f}/10",   C_GOLD if avg_score < 7.5 else C_GREEN),
        ("Photos to remove", str(len(remove_rows)),  C_ACCENT if remove_rows else C_GREEN),
        ("Photos to retake", str(len(retake_rows)),  C_GOLD if retake_rows else C_GREEN),
    ]
    tile_w, tile_h = 42, 24
    for i, (label, val, color) in enumerate(tiles):
        tx = 14 + i * (tile_w + 3)
        ty = pdf.get_y()
        pdf.set_fill_color(*C_LIGHT)
        pdf.rect(tx, ty, tile_w, tile_h, "F")
        pdf.set_fill_color(*color)
        pdf.rect(tx, ty, 3, tile_h, "F")
        pdf.set_xy(tx + 5, ty + 3)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*color)
        pdf.cell(tile_w - 6, 9, val, ln=True)
        pdf.set_xy(tx + 5, ty + 14)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(tile_w - 6, 5, label, ln=False)
    pdf.set_text_color(*C_BLACK)
    pdf.ln(tile_h + 6)

    # Cover recommendation
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*C_DARK)
    pdf.cell(0, 7, "Cover photo recommendation", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_GRAY)
    if hero_rows:
        hr = hero_rows[0]
        txt = (f"Photo #{hr['position']} ({hr['room_type']}) scored {hr['overall_score']}/10 and is "
               f"the strongest image in this listing. It has been set as the recommended cover. "
               f"An AI-enhanced version was generated using the '{winner_variant}' treatment and is "
               f"included in the delivered photo set.")
    else:
        txt = "No clear hero image identified. See photo-by-photo breakdown for enhancement recommendations."
    pdf.multi_cell(0, 5, _wrap(txt, 100))
    pdf.ln(4)

    # Top 3 impact fixes
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*C_DARK)
    pdf.cell(0, 7, "Top 3 highest-impact fixes", ln=True)

    fixes = []
    if remove_rows:
        reasons = "; ".join(r["reason"] for r in remove_rows if r["reason"])
        fixes.append(("Remove weak photos",
                      f"{len(remove_rows)} photo(s) score below 5.5 and actively harm conversion. "
                      f"Detail: {reasons[:120]}"))
    if retake_rows:
        fixes.append(("Retake / upgrade key photos",
                      f"{len(retake_rows)} photo(s) need a better angle or composition. "
                      "AI-upgraded replacements are included in your delivered set."))

    low_scored = [r for r in scored_rows if float(r["overall_score"]) < 6.5]
    if low_scored:
        fixes.append(("Improve interior lighting in weak shots",
                      f"{len(low_scored)} interior photo(s) score below 6.5. Brighter, balanced "
                      "natural light is the single highest-leverage improvement for interior shots."))
    if len(fixes) < 3:
        fixes.append(("Reorder photo sequence for max CTR",
                      "Lead with the strongest aspirational exterior/patio shot, then hero interior, "
                      "then room-by-room. Airbnb search grids show only the cover — it must FOMO."))

    for n, (title, detail) in enumerate(fixes[:3], 1):
        y_start = pdf.get_y()
        pdf.set_fill_color(*C_ACCENT)
        pdf.rect(14, y_start, 6, 14, "F")
        pdf.set_xy(22, y_start + 1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*C_DARK)
        pdf.cell(0, 5, f"{n}. {title}", ln=True)
        pdf.set_xy(22, pdf.get_y())
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_GRAY)
        pdf.multi_cell(160, 4, _wrap(detail, 100))
        pdf.ln(2)

    pdf.set_text_color(*C_BLACK)

    # AI upgrade summary
    pdf.ln(2)
    pdf.set_fill_color(*C_LIGHT)
    pdf.set_xy(14, pdf.get_y())
    box_y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*C_DARK)
    pdf.cell(0, 7, "  AI photo upgrades delivered with this report:", ln=True)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*C_GRAY)
    if top10:
        best = top10[0]
        pdf.set_x(14)
        pdf.multi_cell(0, 5,
            f"  Best regen: Photo #{best['photo'].split('_')[0]} · {best['variant']} treatment · "
            f"score {best['total']}/10 (preserve {best['preserve']}, light {best['light']}, "
            f"appeal {best['appeal']})\n"
            f"  Reasoning: {best['reasoning'][:160]}...")
    pdf.set_text_color(*C_BLACK)


def photo_audit_pages(pdf: TeardownPDF, manifest_rows: list[dict]) -> None:
    pdf.add_page()
    _section_header(pdf, "Photo-by-Photo Audit")

    col_w = 86
    row_h = 48
    thumb_w = 32
    thumb_h = 24
    cols = [14, 14 + col_w + 4]
    col_idx = 0

    for row in manifest_rows:
        verdict = row["verdict"].lower()
        score   = float(row["overall_score"] or 0)
        reason  = row["reason"] or ""
        regen   = row["regen_prompt"] or ""
        pos     = row["position"]
        room    = row["room_type"]
        img     = row["local_path"]

        # Check page space
        if pdf.get_y() + row_h > 270:
            if col_idx == 0:
                col_idx = 1
            else:
                pdf.add_page()
                _section_header(pdf, "Photo-by-Photo Audit (continued)")
                col_idx = 0

        x = cols[col_idx]
        y = pdf.get_y()

        # Card background
        pdf.set_fill_color(*C_LIGHT)
        pdf.rect(x, y, col_w, row_h, "F")

        # Verdict accent strip
        strip_color = SCORE_COLORS.get(verdict, C_GRAY)
        pdf.set_fill_color(*strip_color)
        pdf.rect(x, y, 3, row_h, "F")

        # Thumbnail
        _thumb(pdf, img, x=x + 5, y=y + 4, w=thumb_w, h=thumb_h)

        # Badge
        _verdict_badge(pdf, verdict, x=x + 5, y=y + 29)

        # Score bar
        if score > 0:
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*C_GRAY)
            pdf.set_xy(x + 5, y + 36)
            pdf.cell(20, 4, f"{score:.1f}/10")
            _score_bar(pdf, score, x=x + 5, y=y + 41, w=28)

        # Text content
        tx = x + thumb_w + 8
        pdf.set_xy(tx, y + 3)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*C_DARK)
        pdf.cell(col_w - thumb_w - 10, 5, f"#{pos}  {room}", ln=True)

        if reason:
            pdf.set_xy(tx, pdf.get_y())
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*C_GRAY)
            pdf.multi_cell(col_w - thumb_w - 12, 3.5, _wrap(reason, 55))

        if regen and regen.lower() not in ("n/a", "none needed", ""):
            pdf.set_xy(tx, pdf.get_y() + 1)
            pdf.set_font("Helvetica", "I", 6.5)
            pdf.set_text_color(*C_ACCENT)
            pdf.multi_cell(col_w - thumb_w - 12, 3.5,
                           f"Fix: {_wrap(regen, 55)}")

        pdf.set_text_color(*C_BLACK)

        # Advance position
        if col_idx == 0:
            col_idx = 1
            # Don't advance Y yet — next card fills right column
        else:
            col_idx = 0
            pdf.set_y(y + row_h + 3)

    # If we ended on left column, advance
    if col_idx == 1:
        pdf.ln(row_h + 3)


def ai_upgrades_page(pdf: TeardownPDF, top10: list[dict], winner_variant: str) -> None:
    pdf.add_page()
    _section_header(pdf, "AI Photo Upgrades — Top Results")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_GRAY)
    pdf.multi_cell(0, 5,
        f"The AI upgrade engine tested {len(top10)} scored variants across multiple treatments. "
        f"Best overall treatment: '{winner_variant}'. Top results are shown below. "
        "All upgraded photos are included in the delivered ZIP at full resolution.")
    pdf.set_text_color(*C_BLACK)
    pdf.ln(3)

    for item in top10[:6]:
        img_path = item.get("output", "")
        score    = item["total"]
        variant  = item["variant"]
        photo    = item["photo"]
        reasoning = item.get("reasoning", "")

        y = pdf.get_y()
        if y + 30 > 270:
            pdf.add_page()
            _section_header(pdf, "AI Photo Upgrades (continued)")
            y = pdf.get_y()

        _thumb(pdf, img_path, x=14, y=y, w=42, h=30)

        # Score bar
        _score_bar(pdf, score, x=14, y=y + 32, w=42)
        pdf.set_xy(14, y + 37)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*C_GREEN if score >= 7.5 else C_GOLD)
        pdf.cell(42, 4, f"{score:.1f}/10", align="C")

        # Details
        pdf.set_xy(60, y + 1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*C_DARK)
        pdf.cell(0, 5, f"{photo}  ·  treatment: {variant}", ln=True)

        pdf.set_xy(60, pdf.get_y())
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*C_GRAY)
        pdf.multi_cell(128, 4, _wrap(reasoning, 110) if reasoning else "")

        pdf.set_text_color(*C_BLACK)
        pdf.ln(4)


def action_checklist_page(pdf: TeardownPDF, manifest_rows: list[dict]) -> None:
    pdf.add_page()
    _section_header(pdf, "Priority Action Checklist")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_GRAY)
    pdf.multi_cell(0, 5,
        "Complete these in order. Each step is ranked by impact on your listing's "
        "click-through rate and conversion. Your upgraded photos (delivered in the ZIP) "
        "are ready to upload once you complete step 1.")
    pdf.set_text_color(*C_BLACK)
    pdf.ln(4)

    remove_rows = [r for r in manifest_rows if r["verdict"].lower() == "remove"]
    retake_rows = [r for r in manifest_rows if r["verdict"].lower() == "retake"]
    hero_rows   = [r for r in manifest_rows if r["verdict"].lower() == "hero"]

    tasks = []

    # Step 1: upload new cover
    if hero_rows:
        hr = hero_rows[0]
        tasks.append((
            "CRITICAL",
            f"Replace cover photo with photo #{hr['position']} ({hr['room_type']}, score {hr['overall_score']}/10)",
            "Cover photo is the #1 CTR lever. An aspirational exterior/unique feature shot "
            "outperforms interiors on Airbnb search grids by 30–40%.",
            C_ACCENT
        ))

    # Step 2: upload full upgraded set
    tasks.append((
        "HIGH",
        "Upload all 28 upgraded photos from the delivered ZIP (replace current set in order)",
        "The upgraded set is matched to your listing count (28 photos) and pre-ordered with "
        "the hero cover first. Upload in sequence to Airbnb's photo manager.",
        C_ACCENT
    ))

    # Step 3: remove bad photos
    if remove_rows:
        pos_list = ", ".join(f"#{r['position']}" for r in remove_rows)
        tasks.append((
            "HIGH",
            f"Delete photos {pos_list} — they score below 5.5 and harm conversion",
            "; ".join(r["reason"] for r in remove_rows if r["reason"])[:200],
            C_GOLD
        ))

    # Step 4: retakes
    if retake_rows:
        for r in retake_rows:
            tasks.append((
                "MEDIUM",
                f"Retake photo #{r['position']} ({r['room_type']}) — AI version included in ZIP",
                r["regen_prompt"] or r["reason"],
                C_GOLD
            ))

    # Step 5: sequence optimisation
    tasks.append((
        "MEDIUM",
        "Reorder Airbnb photo sequence: cover → best patio/exterior → hero interior → room-by-room",
        "Airbnb's algorithm favors listings where early swipes match guest search intent. "
        "Exterior and unique features first, details last.",
        C_GREEN
    ))

    # Step 6: title/description
    tasks.append((
        "LOW",
        "Update listing title to call out the hot tub and private outdoor space explicitly",
        "Amenity callouts in the title outperform generic titles in search relevance. "
        "Example: 'Cozy Cabin · Private Hot Tub · Chiminea + Patio'",
        C_GREEN
    ))

    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    tasks.sort(key=lambda t: priority_order.get(t[0], 9))

    for i, (priority, task, detail, color) in enumerate(tasks, 1):
        y = pdf.get_y()
        if y + 22 > 270:
            pdf.add_page()
            _section_header(pdf, "Action Checklist (continued)")
            y = pdf.get_y()

        # Checkbox
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(14, y + 2, 6, 6)

        # Priority badge
        pdf.set_fill_color(*color)
        pdf.set_text_color(*C_WHITE)
        pdf.set_font("Helvetica", "B", 6)
        pdf.set_xy(22, y + 2)
        pdf.cell(16, 5, priority, fill=True)

        # Task text
        pdf.set_xy(40, y + 2)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*C_DARK)
        pdf.multi_cell(152, 5, task)

        if detail:
            pdf.set_x(40)
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(*C_GRAY)
            pdf.multi_cell(152, 4, _wrap(detail, 110))

        pdf.set_text_color(*C_BLACK)
        pdf.ln(2)
        pdf.set_draw_color(220, 220, 220)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.set_draw_color(0, 0, 0)
        pdf.ln(2)


def closing_page(pdf: TeardownPDF, host_name: str) -> None:
    pdf.add_page()
    pdf.set_fill_color(*C_BLACK)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_xy(14, 80)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 14, "Your listing, upgraded.", ln=True, align="C")

    pdf.set_xy(14, 100)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*C_GRAY)
    pdf.multi_cell(0, 7,
        "The 28 upgraded photos in your ZIP are ready to upload.\n"
        "Follow the checklist in Section 4 to complete the upgrade.", align="C")

    pdf.set_xy(14, 135)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*C_ACCENT)
    pdf.cell(0, 8, "Questions? Reach us at hello@scalr-us.com", ln=True, align="C")

    pdf.set_xy(14, 270)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*C_GRAY)
    pdf.cell(0, 6, f"ListingBoost by Scalr · Prepared for {host_name}", align="C")


# ── Main ──────────────────────────────────────────────────────────────────────
def generate_teardown(
    listing_dir: Path,
    results_dir: Path,
    host_name: str,
    listing_title: str,
    listing_url: str,
    out_path: Path,
) -> None:
    manifest_path = listing_dir / "manifest.csv"
    qc_path       = results_dir / "qc_report_free.json"

    with open(manifest_path) as f:
        manifest_rows = list(csv.DictReader(f))

    top10, winner_variant = [], "wider_angle"
    if qc_path.exists():
        qc = json.loads(qc_path.read_text())
        top10 = qc.get("top_10", [])
        winner_variant = qc.get("winner", "wider_angle")

    # Find cover thumbnail (hero or position 12)
    cover_thumb: Path | None = None
    for r in manifest_rows:
        if r["verdict"].lower() == "hero" and r["local_path"] and Path(r["local_path"]).exists():
            cover_thumb = Path(r["local_path"])
            break

    pdf = TeardownPDF(host_name=host_name, listing_title=listing_title)

    cover_page(pdf, host_name, listing_title, listing_url, cover_thumb)
    exec_summary_page(pdf, manifest_rows, top10, winner_variant)
    photo_audit_pages(pdf, manifest_rows)
    ai_upgrades_page(pdf, top10, winner_variant)
    action_checklist_page(pdf, manifest_rows)
    closing_page(pdf, host_name)

    pdf.output(str(out_path))
    size_kb = out_path.stat().st_size // 1024
    print(f"[pdf] Generated: {out_path}  ({size_kb} KB, {pdf.page_no()} pages)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-dir",    required=True)
    parser.add_argument("--results-dir",    required=True)
    parser.add_argument("--host-name",      default="Host")
    parser.add_argument("--listing-title",  default="Airbnb Listing")
    parser.add_argument("--listing-url",    default="")
    parser.add_argument("--out",            default=None)
    args = parser.parse_args()

    listing_dir = Path(args.listing_dir)
    results_dir = Path(args.results_dir)
    out_path = Path(args.out) if args.out else results_dir / "teardown_report.pdf"

    generate_teardown(
        listing_dir, results_dir,
        args.host_name, args.listing_title, args.listing_url,
        out_path,
    )


if __name__ == "__main__":
    main()
