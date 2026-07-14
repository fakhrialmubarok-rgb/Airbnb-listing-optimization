"""
outreach_email.py - ListingBoost cold outreach with hero image teaser + $29 CTA

Generates a personalized HTML email for each prospect:
  - Opens with one specific observation from their actual listing (no fake stats)
  - Shows the hero image inline (teaser: "this is what your cover could look like")
  - 3-bullet diagnosis (title / cover photo / top amenity gap)
  - $29 CTA with 4-week money-back guarantee
  - PDF attached (gap analysis)
  - Signs as AL

Product offer framing:
  - $29 PDF = full optimization report (title rewrites, description rewrite,
    amenity gap audit, photo order, AI-regraded cover image)
  - Value anchor: same outcome as a $5,000 professional photoshoot + copywriter
  - Guarantee: if search traffic doesn't increase in 4 weeks, full refund

Rules (from Scalr Outreach Constitution):
  - All numbers from their own scraped data — nothing invented
  - generate -> eyeball -> send (never auto-send)
  - Test-send to owner email first
  - Sign as AL, never Fakhri
  - One hero image inline, PDF attached

Usage:
  from outreach_email import build_outreach, send_outreach, preview_outreach

  # Build email (no send)
  email = build_outreach(listing, teardown_result, image_result)
  print(email.subject)
  print(email.text_body)   # eyeball before sending

  # Preview as HTML file
  preview_outreach(email)  # opens in browser

  # Send (test to yourself first)
  send_outreach(email, to="fakhrialmubarok@gmail.com")  # test
  send_outreach(email)                                   # real send to host

  # CLI
  python outreach_email.py --listing-json /tmp/listingboost_teardowns/teardown_20669368.json --preview
  python outreach_email.py --listing-json ... --test-send
  python outreach_email.py --listing-json ... --send --to host@email.com
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import smtplib
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 465))
SMTP_USER     = os.getenv("SMTP_USER", "hello@scalr-us.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_NAME     = "AL from ListingBoost"
FROM_EMAIL    = SMTP_USER
OWNER_EMAIL   = os.getenv("OWNER_EMAIL", "fakhrialmubarok@gmail.com")

OUTPUT_DIR = Path("/tmp/listingboost_teardowns")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class OutreachEmail:
    listing_id: str
    host_name: str
    host_email: str          # filled manually or from enrichment
    subject: str
    text_body: str
    html_body: str
    hero_image_path: str     # local path to 00_COVER_HERO photo
    pdf_path: str            # gap analysis PDF
    preview_path: str = ""   # local HTML preview file


# ---------------------------------------------------------------------------
# Email copy builder
# ---------------------------------------------------------------------------

PRODUCT_URL = "https://listingboost.co"   # placeholder — update when live


def _first_name(host_name: str) -> str:
    return (host_name or "there").split()[0].strip().title()


def _build_copy(listing: dict, teardown: dict, image_analysis: dict) -> dict:
    """
    Build all personalized copy from real listing data.
    Returns dict with subject, opener, bullet_1/2/3, hook, guarantee line.
    Never invents numbers — only uses what scraped data provides.
    """
    host_name   = listing.get("host_name", "there")
    fname       = _first_name(host_name)
    title       = listing.get("title") or listing.get("seo_title", "your listing")
    occupancy   = listing.get("occupancy_pct") or 0
    open_nights = teardown.get("occupancy_math", {}).get("open_nights_90d", 0)
    nightly     = listing.get("nightly_rate") or listing.get("price_per_night") or 0
    revenue     = teardown.get("occupancy_math", {}).get("revenue_at_stake_90d", 0)
    location    = listing.get("location_subtitle") or listing.get("location", "")
    title_score = teardown.get("scores", {}).get("title", 0)
    desc_score  = teardown.get("scores", {}).get("description", 0)
    diagnosis   = teardown.get("key_diagnosis", [])
    title_vars  = teardown.get("title_variants", [])
    best_title  = title_vars[0] if title_vars else ""

    # Image signals
    cover_is_wrong      = image_analysis.get("cover_recommendation", {}).get("cover_is_wrong", False)
    current_cover_room  = image_analysis.get("cover_recommendation", {}).get("current_room", "")
    recommended_room    = image_analysis.get("cover_recommendation", {}).get("recommended_room", "")
    image_key_finding   = image_analysis.get("key_finding", "")
    image_score         = image_analysis.get("overall_image_score", 0)

    # Choose the strongest opening hook (real data only)
    if cover_is_wrong and current_cover_room and recommended_room:
        opener = (
            f"Quick observation on your listing: your search thumbnail is showing "
            f"the {current_cover_room.lower()} — but your {recommended_room.lower()} photo "
            f"is significantly stronger and guests never see it."
        )
        hook_angle = "image"
    elif open_nights and nightly:
        opener = (
            f"I noticed your {location} listing has {open_nights} open nights in the next "
            f"90 days. Based on your rate, that's up to ${revenue:,.0f} sitting unbooked."
        ) if revenue else (
            f"I noticed your {location} listing has {open_nights} open nights in the next 90 days."
        )
        hook_angle = "occupancy"
    elif title_score and title_score <= 4:
        opener = (
            f"Quick note on your listing title — \"{title[:50]}\" is currently "
            f"{len(title)} characters, which pushes your best features past where "
            f"guests stop reading in search results."
        )
        hook_angle = "title"
    else:
        opener = (
            f"I ran a quick audit on your {location} listing and spotted "
            f"a few specific fixes that could lift your bookings."
        )
        hook_angle = "general"

    # 3-bullet diagnosis (use real Claude diagnosis if available, else build from data)
    bullets = []
    if diagnosis:
        bullets = diagnosis[:3]
    else:
        if title_score and title_score <= 5 and best_title:
            bullets.append(f"Title ({title_score}/10): \"{title[:40]}...\" → could be \"{best_title}\"")
        if cover_is_wrong:
            bullets.append(f"Cover photo: {current_cover_room} as #1 is losing clicks vs your {recommended_room} shot")
        amenity_gaps = teardown.get("top_amenity_gaps", [])
        if amenity_gaps:
            bullets.append(f"Amenity gap: {amenity_gaps[0]}")

    # Subject line (A/B variants — use first)
    if cover_is_wrong:
        subject = f"Your {recommended_room.lower()} photo is buried at the wrong position"
    elif open_nights > 20:
        subject = f"{open_nights} open nights — 3 fixes I'd make first"
    elif title_score and title_score <= 4:
        subject = f"Your listing title is cutting your search visibility"
    else:
        subject = f"Quick audit on your {location} listing"

    return {
        "fname": fname,
        "subject": subject,
        "opener": opener,
        "hook_angle": hook_angle,
        "bullets": bullets,
        "best_title": best_title,
        "cover_is_wrong": cover_is_wrong,
        "current_cover_room": current_cover_room,
        "recommended_room": recommended_room,
        "image_key_finding": image_key_finding,
        "revenue": revenue,
        "open_nights": open_nights,
        "nightly": nightly,
        "location": location,
        "title_score": title_score,
        "image_score": image_score,
    }


# ---------------------------------------------------------------------------
# Text body (plain-text version)
# ---------------------------------------------------------------------------

def _build_text(copy: dict) -> str:
    fname   = copy["fname"]
    opener  = copy["opener"]
    bullets = copy["bullets"]
    image_finding = copy.get("image_key_finding", "")

    bullet_lines = "\n".join(f"  {i+1}. {b}" for i, b in enumerate(bullets))

    image_line = ""
    if image_finding:
        image_line = f"\nImage audit:\n  {image_finding}\n"

    return f"""Hi {fname},

{opener}

I ran a full optimization audit on your listing. Here's what I found:

{bullet_lines}
{image_line}
I put everything — the title rewrites, full description rewrite, photo order, and the AI-regraded cover image — into a PDF report you can action in an afternoon.

It's $29.

If your search traffic doesn't increase within 4 weeks, I'll refund every dollar.

No software to install. No ongoing subscription. One PDF, everything you need.

→ Get your listing audit: {PRODUCT_URL}

[Hero image attached — this is what your cover photo could look like]

—
AL
ListingBoost
"""


# ---------------------------------------------------------------------------
# HTML body
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f5f5; color: #1a1a1a; line-height: 1.6; }}
  .wrap {{ max-width: 580px; margin: 32px auto; background: #fff;
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .header {{ background: #1a1a1a; padding: 24px 32px; }}
  .header .logo {{ color: #fff; font-size: 16px; font-weight: 700;
                   letter-spacing: 0.05em; }}
  .header .tagline {{ color: #888; font-size: 12px; margin-top: 2px; }}
  .hero-wrap {{ position: relative; background: #111; }}
  .hero-wrap img {{ width: 100%; display: block; opacity: 0.92; }}
  .hero-badge {{ position: absolute; bottom: 16px; left: 16px;
                 background: rgba(0,0,0,0.72); color: #fff;
                 font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
                 padding: 6px 12px; border-radius: 4px;
                 text-transform: uppercase; }}
  .body {{ padding: 32px; }}
  .greeting {{ font-size: 15px; color: #1a1a1a; margin-bottom: 16px; }}
  .opener {{ font-size: 15px; color: #333; margin-bottom: 24px;
             padding: 16px; background: #f8f8f8; border-left: 3px solid #1a1a1a;
             border-radius: 0 4px 4px 0; }}
  h3 {{ font-size: 13px; font-weight: 700; color: #888; letter-spacing: 0.08em;
        text-transform: uppercase; margin-bottom: 12px; }}
  .bullets {{ list-style: none; margin-bottom: 24px; }}
  .bullets li {{ display: flex; gap: 12px; padding: 12px 0;
                 border-bottom: 1px solid #f0f0f0; font-size: 14px; color: #333; }}
  .bullets li:last-child {{ border-bottom: none; }}
  .num {{ flex-shrink: 0; width: 24px; height: 24px; background: #1a1a1a;
          color: #fff; border-radius: 50%; font-size: 12px; font-weight: 700;
          display: flex; align-items: center; justify-content: center; }}
  .offer {{ background: #1a1a1a; color: #fff; border-radius: 8px;
            padding: 24px; margin: 24px 0; }}
  .offer .price {{ font-size: 36px; font-weight: 800; color: #fff; }}
  .offer .price span {{ font-size: 16px; font-weight: 400;
                        text-decoration: line-through; color: #888;
                        margin-left: 8px; }}
  .offer .value {{ font-size: 13px; color: #aaa; margin-top: 4px;
                   margin-bottom: 16px; }}
  .offer ul {{ list-style: none; margin-bottom: 20px; }}
  .offer ul li {{ font-size: 14px; color: #ccc; padding: 4px 0; }}
  .offer ul li::before {{ content: "✓ "; color: #fff; font-weight: 700; }}
  .cta {{ display: block; background: #fff; color: #1a1a1a;
          text-decoration: none; font-weight: 700; font-size: 15px;
          text-align: center; padding: 14px 24px; border-radius: 6px; }}
  .guarantee {{ font-size: 12px; color: #888; text-align: center;
                margin-top: 10px; }}
  .image-note {{ font-size: 13px; color: #888; font-style: italic;
                 text-align: center; margin: 16px 0; padding: 12px;
                 background: #f8f8f8; border-radius: 4px; }}
  .sig {{ font-size: 14px; color: #555; margin-top: 24px;
          padding-top: 24px; border-top: 1px solid #f0f0f0; }}
  .footer {{ background: #f8f8f8; padding: 16px 32px;
             font-size: 11px; color: #aaa; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="logo">ListingBoost</div>
    <div class="tagline">Airbnb listing optimization</div>
  </div>

  <!-- HERO IMAGE -->
  <div class="hero-wrap">
    <img src="cid:hero_image" alt="Your listing's strongest photo" />
    <div class="hero-badge">Your best photo — currently buried</div>
  </div>
  <div class="image-note">
    ↑ This is your strongest photo. It's not your cover image right now.
  </div>

  <div class="body">

    <div class="greeting">Hi {fname},</div>

    <div class="opener">{opener}</div>

    <h3>What I found in your listing</h3>
    <ul class="bullets">
      {bullet_html}
    </ul>

    <!-- OFFER BLOCK -->
    <div class="offer">
      <div class="price">$29 <span>$5,000</span></div>
      <div class="value">Same result as hiring a professional photographer + copywriter</div>
      <ul>
        <li>Rewritten title (3 variants, tested for search)</li>
        <li>Full description rewrite — same facts, converts better</li>
        <li>Amenity gap audit vs comparable listings</li>
        <li>Photo order recommendation + cover swap guide</li>
        <li>AI-regraded hero image (better light, same furniture)</li>
      </ul>
      <a href="{product_url}" class="cta">Get your listing audit →</a>
      <div class="guarantee">4-week guarantee — if search traffic doesn't increase, full refund.</div>
    </div>

    <div class="sig">
      — AL<br>
      <span style="color:#aaa; font-size:12px;">ListingBoost &nbsp;|&nbsp; hello@listingboost.co</span>
    </div>

  </div>

  <div class="footer">
    You received this because your listing was identified as a strong optimization candidate.<br>
    Reply to unsubscribe.
  </div>

</div>
</body>
</html>"""


def _build_html(copy: dict) -> str:
    bullets = copy.get("bullets", [])
    bullet_html = "\n".join(
        f'<li><div class="num">{i+1}</div><div>{b}</div></li>'
        for i, b in enumerate(bullets)
    )
    return _HTML_TEMPLATE.format(
        fname=copy["fname"],
        opener=copy["opener"],
        bullet_html=bullet_html,
        product_url=PRODUCT_URL,
    )


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------

def _build_mime(email: OutreachEmail, to: str) -> MIMEMultipart:
    msg = MIMEMultipart("related")
    msg["From"]    = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"]      = to
    msg["Subject"] = email.subject
    msg["Reply-To"] = FROM_EMAIL

    # Multipart/alternative: text + html
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(email.text_body, "plain", "utf-8"))
    alt.attach(MIMEText(email.html_body, "html", "utf-8"))
    msg.attach(alt)

    # Hero image inline (cid:hero_image)
    if email.hero_image_path and Path(email.hero_image_path).exists():
        with open(email.hero_image_path, "rb") as f:
            img = MIMEImage(f.read(), _subtype="jpeg")
        img.add_header("Content-ID", "<hero_image>")
        img.add_header("Content-Disposition", "inline",
                       filename=Path(email.hero_image_path).name)
        msg.attach(img)

    # PDF attachment
    if email.pdf_path and Path(email.pdf_path).exists():
        with open(email.pdf_path, "rb") as f:
            pdf = MIMEBase("application", "pdf")
            pdf.set_payload(f.read())
        from email.encoders import encode_base64
        encode_base64(pdf)
        pdf.add_header("Content-Disposition", "attachment",
                       filename=Path(email.pdf_path).name)
        msg.attach(pdf)

    return msg


def send_outreach(email: OutreachEmail, to: str | None = None) -> bool:
    """
    Send outreach email via SMTP.
    If to=None, sends to email.host_email (the actual host).
    Always test-send to owner first: send_outreach(email, to=OWNER_EMAIL)
    """
    recipient = to or email.host_email
    if not recipient:
        print("[outreach] No recipient email — set host_email or pass to= argument")
        return False

    msg = _build_mime(email, recipient)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[outreach] Sent to {recipient}")
        return True
    except Exception as e:
        print(f"[outreach] SMTP failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_outreach(
    listing: dict,
    teardown_json: dict,
    image_analysis_json: dict,
    host_email: str = "",
) -> OutreachEmail:
    """
    Build a fully personalized outreach email from real data.
    Does NOT send — call send_outreach() after eyeballing.
    """
    lid       = listing.get("listing_id", "unknown")
    host_name = listing.get("host_name", "Host")

    # Find hero image path — scan all matching dirs for this listing_id
    base = Path("/tmp/listingboost_photos")
    photo_dir = Path("")
    if base.exists():
        matches = sorted(base.glob(f"{lid}_*"))
        if matches:
            photo_dir = matches[0]
    hero_dir  = photo_dir / "00_COVER_HERO" if photo_dir else Path("/nonexistent")
    hero_path = ""
    if hero_dir.exists():
        heroes = sorted(hero_dir.glob("*.jpg"))
        if heroes:
            # Pick highest-scored hero (filename contains score)
            hero_path = str(sorted(heroes, key=lambda p: p.name, reverse=True)[0])

    # PDF path
    pdf_path = teardown_json.get("pdf_path", "")

    # Build copy
    copy = _build_copy(listing, teardown_json, image_analysis_json)

    text_body = _build_text(copy)
    html_body = _build_html(copy)

    email = OutreachEmail(
        listing_id=lid,
        host_name=host_name,
        host_email=host_email,
        subject=copy["subject"],
        text_body=text_body,
        html_body=html_body,
        hero_image_path=hero_path,
        pdf_path=pdf_path,
    )

    # Save preview HTML
    preview_path = OUTPUT_DIR / f"outreach_preview_{lid}.html"
    preview_path.write_text(html_body, encoding="utf-8")
    email.preview_path = str(preview_path)

    return email


def preview_outreach(email: OutreachEmail):
    """Open the HTML preview in default browser."""
    if email.preview_path and Path(email.preview_path).exists():
        subprocess.run(["open", email.preview_path])
        print(f"[outreach] Preview opened: {email.preview_path}")
    else:
        print("[outreach] No preview path — call build_outreach() first")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ListingBoost Outreach Email Builder")
    parser.add_argument("--listing-json", required=True,
                        help="Path to teardown JSON (/tmp/listingboost_teardowns/teardown_*.json)")
    parser.add_argument("--to", default="",
                        help="Recipient email (omit to default to test send to owner)")
    parser.add_argument("--preview", action="store_true",
                        help="Open HTML preview in browser (no send)")
    parser.add_argument("--test-send", action="store_true",
                        help=f"Send to owner email ({OWNER_EMAIL}) for review")
    parser.add_argument("--send", action="store_true",
                        help="Send to actual host (requires --to or host_email in data)")
    args = parser.parse_args()

    # Load teardown JSON
    teardown_json = json.loads(Path(args.listing_json).read_text())
    lid = teardown_json.get("listing_id", "")

    # Load image analysis JSON
    image_json_path = OUTPUT_DIR / f"image_analysis_{lid}.json"
    image_json = json.loads(image_json_path.read_text()) if image_json_path.exists() else {}

    # Reconstruct listing dict from teardown JSON
    occ_math = teardown_json.get("occupancy_math", {})
    outreach_meta = teardown_json.get("outreach", {})
    listing = {
        "listing_id": lid,
        "host_name": teardown_json.get("host_name", "") or outreach_meta.get("host_name", ""),
        "title": teardown_json.get("title_original", ""),
        "description": teardown_json.get("description_original", ""),
        "location_subtitle": teardown_json.get("location", ""),
        "occupancy_pct": occ_math.get("occupancy_pct", 0),
        "nightly_rate": occ_math.get("nightly_rate", 0),
        "images_by_room": {},   # not needed for email build
    }

    email = build_outreach(
        listing=listing,
        teardown_json=teardown_json,
        image_analysis_json=image_json,
        host_email=args.to,
    )

    print(f"\n{'='*60}")
    print("OUTREACH EMAIL READY")
    print(f"{'='*60}")
    print(f"Subject: {email.subject}")
    print(f"Hero image: {email.hero_image_path or 'NONE — run teardown with images first'}")
    print(f"PDF: {email.pdf_path or 'NONE'}")
    print(f"Preview: {email.preview_path}")
    print(f"\n--- TEXT PREVIEW ---")
    print(email.text_body)

    if args.preview:
        preview_outreach(email)

    elif args.test_send:
        print(f"\nTest-sending to {OWNER_EMAIL}...")
        ok = send_outreach(email, to=OWNER_EMAIL)
        print("Sent." if ok else "Failed — check SMTP settings.")

    elif args.send:
        if not args.to and not email.host_email:
            print("Need --to <email> to send to host.")
        else:
            recipient = args.to or email.host_email
            confirm = input(f"\nSend to {recipient}? [yes/no]: ").strip().lower()
            if confirm == "yes":
                ok = send_outreach(email, to=recipient)
                print("Sent." if ok else "Failed.")
            else:
                print("Cancelled.")

    else:
        print("\nRun with --preview to open in browser, --test-send to email yourself, or --send --to host@email.com")
