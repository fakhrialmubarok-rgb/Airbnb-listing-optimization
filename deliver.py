"""
ListingBoost Delivery Script
=============================
Packages the teardown PDF + upgraded photos into a ZIP and emails it
directly to the host (or a test address).

Usage:
    python3 deliver.py \
        --listing-dir /tmp/listingboost_photos/20669368_Tanya \
        --results-dir /tmp/regen_results/20669368_Tanya \
        --host-email "tanya@example.com" \
        --host-name "Tanya" \
        --listing-title "Cozy Cabin with Hot Tub and Patio" \
        --listing-url "https://airbnb.com/rooms/20669368" \
        [--test]   # sends to OWNER_EMAIL instead of host

Flow:
    1. Generate teardown_report.pdf (if not already there)
    2. Zip FINAL_EXPORT/ photos + PDF -> delivery.zip
    3. Send email with ZIP attached via Gmail API
"""

from __future__ import annotations
import argparse, base64, io, json, os, sys, zipfile
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

import requests
from dotenv import load_dotenv
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent

_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


# ── Auth ──────────────────────────────────────────────────────────────────────
def _access_token() -> str:
    resp = requests.post(_TOKEN_URL, data={
        "client_id":     os.environ["GMAIL_CLIENT_ID"],
        "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
        "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Email body ─────────────────────────────────────────────────────────────────
def _build_body(host_name: str, listing_title: str, photo_count: int,
                listing_id: str = "") -> tuple[str, str]:
    """Return (plain, html) email bodies."""
    first = host_name.split()[0] if host_name else "there"
    plain = f"""Hi {first},

Your package is attached — everything's in the ZIP.

What's inside:
  - teardown_report.pdf — your photo scores, what's costing you clicks, and a priority checklist
  - {photo_count} edited photos (01.jpg through {str(photo_count).zfill(2)}.jpg) — ready to upload, cover-first

Three things to do right now (takes about 10 minutes):
  1. Open teardown_report.pdf — skip to page 2, the top 3 fixes are listed there
  2. Upload all photos from the ZIP in order, replacing what's on Airbnb now
  3. Make sure photo 01 is your cover — it was pulled forward specifically for click-through

Your listing: {listing_title}

Any questions, just hit reply.

AL
hello@scalr-us.com
"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; color: #1a1a1a;
          max-width: 580px; margin: 0 auto; padding: 24px 16px; }}
  .logo {{ font-size: 20px; font-weight: 700; color: #1a1a1a; }}
  .logo span {{ color: #ff5a3c; }}
  h2 {{ font-size: 18px; font-weight: 600; margin: 24px 0 8px; }}
  .box {{ background: #f5f5f3; border-radius: 8px; padding: 16px 20px; margin: 16px 0; }}
  .box ul {{ margin: 8px 0; padding-left: 18px; }}
  .box li {{ margin: 6px 0; font-size: 14px; line-height: 1.5; }}
  .steps {{ counter-reset: step; }}
  .step {{ display: flex; gap: 12px; margin: 12px 0; align-items: flex-start; }}
  .step-n {{ background: #ff5a3c; color: #fff; border-radius: 50%;
              width: 22px; height: 22px; display: flex; align-items: center;
              justify-content: center; font-weight: 700; font-size: 12px;
              flex-shrink: 0; margin-top: 1px; }}
  .step-text {{ font-size: 14px; line-height: 1.5; }}
  .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0;
              font-size: 12px; color: #888; }}
  a {{ color: #ff5a3c; }}
</style>
</head>
<body>
<div class="logo">Listing<span>Boost</span></div>
<p style="color:#888;font-size:13px;margin:4px 0 0;">by Scalr</p>

<h2>Here's your package, {first}.</h2>

<p style="font-size:14px;color:#555;">
  ZIP is attached. Open it and you'll find the teardown report and
  {photo_count} edited photos ready to drop straight into your listing.
</p>

<div class="box">
  <strong style="font-size:13px;">What's in the ZIP:</strong>
  <ul>
    <li><strong>teardown_report.pdf</strong> &mdash; photo scores, what's costing you clicks,
        priority checklist</li>
    <li><strong>{photo_count} edited photos</strong> (01 &ndash; {str(photo_count).zfill(2)})
        &mdash; reordered, cover-first, upload-ready</li>
  </ul>
</div>

<h2>Do these three things first (10 min)</h2>
<div class="steps">
  <div class="step">
    <div class="step-n">1</div>
    <div class="step-text">Open <strong>teardown_report.pdf</strong> and jump to page 2 &mdash;
      your top 3 fixes are right there.</div>
  </div>
  <div class="step">
    <div class="step-n">2</div>
    <div class="step-text">Upload all photos from the ZIP in order, replacing
      what's on your listing now.</div>
  </div>
  <div class="step">
    <div class="step-n">3</div>
    <div class="step-text">Make sure <strong>photo 01</strong> is your cover &mdash;
      it was pulled forward specifically for click-through.</div>
  </div>
  <div class="step">
    <div class="step-n">4</div>
    <div class="step-text">Work through the rest of the checklist in the PDF when you
      get a chance &mdash; those are your next-biggest levers.</div>
  </div>
</div>

<p style="font-size:14px;margin-top:20px;">
  Your listing: <a href="#">{listing_title}</a>
</p>

<div class="footer">
  AL &mdash; <a href="mailto:hello@scalr-us.com">hello@scalr-us.com</a><br>
  ListingBoost by Scalr &bull; Questions? Just reply to this email.
</div>
{_tracking_pixel_tag(listing_id)}
</body>
</html>"""

    return plain, html


def _tracking_pixel_tag(listing_id: str) -> str:
    """Return a 1×1 tracking pixel img tag, or '' if WEBHOOK_BASE not set."""
    base = os.environ.get("WEBHOOK_BASE", "").rstrip("/")
    if not base or not listing_id:
        return ""
    return f'<img src="{base}/t/{listing_id}" width="1" height="1" style="display:none" alt="">'


# ── ZIP builder ───────────────────────────────────────────────────────────────
MAX_ATTACH_BYTES = 20 * 1024 * 1024   # Gmail hard cap is 25MB; keep margin

def build_zip(export_dir: Path, pdf_path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, arcname="teardown_report.pdf")
        photos = sorted(export_dir.glob("*"))
        for p in photos:
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                zf.write(p, arcname=f"photos/{p.name}")
    buf.seek(0)
    return buf.read()


# ── Gmail send with attachment ─────────────────────────────────────────────────
def send_with_attachment(
    to: str,
    subject: str,
    plain: str,
    html: str,
    zip_bytes: bytes,
    zip_filename: str,
    from_addr: str = "hello@scalr-us.com",
    from_name: str = "AL",
) -> None:
    token = _access_token()

    msg = MIMEMultipart("mixed")
    msg["To"]      = to
    msg["From"]    = f"{from_name} <{from_addr}>"
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain"))
    alt.attach(MIMEText(html,  "html"))
    msg.attach(alt)

    part = MIMEBase("application", "zip")
    part.set_payload(zip_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{zip_filename}"')
    msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = requests.post(
        _GMAIL_SEND,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=60,
    )
    resp.raise_for_status()
    print(f"  [gmail] Sent to {to}  (msg id: {resp.json().get('id', '?')})")


# ── Offer email variant engine ────────────────────────────────────────────────

def _variant(seed: str, n: int) -> int:
    """Deterministic 0..n-1 selector so the same listing always gets the same copy."""
    import hashlib
    return int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % n


_SUBJECTS = [
    lambda first, nights, _title: f"{nights} nights sitting empty — something I found on your listing",
    lambda first, nights, _title: f"quick thing I noticed about your listing, {first}",
    lambda first, nights, _title: f"your calendar has {nights} gaps — found something specific",
    lambda first, nights, _title: f"honest question about your Airbnb bookings, {first}",
    lambda first, nights, _title: f"{first} — {nights} open nights and a fix I think is worth it",
]


def _offer_plain(variant: int, first: str, outreach_hook: str,
                 open_nights: int, revenue_at_stake: float, checkout_url: str,
                 photo_position_hook: str = "", sends_so_far: int = 0) -> str:
    rev = f"£{revenue_at_stake:,.0f}"
    # Social proof line — only include when we have real send history
    proof = (
        "I've been doing this across UK Airbnb listings for the past few months — "
        "the photo order fix alone has been the single biggest lever I've seen.\n\n"
        if sends_so_far > 0 else ""
    )
    # Photo-specific hook — one sentence from teardown, appended naturally
    photo_line = f"\n\n({photo_position_hook})" if photo_position_hook else ""

    if variant == 0:
        return f"""Hi {first},

{outreach_hook}

I've spent the last few months going through Airbnb listings — it's a bit of an obsession at this point. I keep seeing the same thing: hosts with genuinely good properties sitting on empty nights because the listing isn't showing what the place actually is.

{proof}Yours caught my eye. The photos aren't bad — but the sequencing is off, and I'm fairly sure your cover isn't the one that would get the click.{photo_line}

You've got {open_nights} nights open in the next 90 days. At your rate that's around {rev}, and once those dates pass they don't come back.

For £29 I'll go through your listing properly — score every photo, edit and reorder them, pull the right one to the front — and have everything in your inbox as a ZIP within 48 hours.

If it doesn't move things, just reply and I'll refund it.

  {checkout_url}

AL
"""

    if variant == 1:
        return f"""Hi {first},

{outreach_hook}

I'll be straight with you — I almost didn't send this. But I went through your listing and a couple of things stood out that felt worth flagging.

{proof}Your photos aren't being shown in the order that would actually convert someone who's on the fence. And your cover — the one photo that decides whether someone clicks through or keeps scrolling — I don't think it's your strongest one.{photo_line}

You've got {open_nights} nights open in the next 90 days. That's around {rev} at your current rate, and once those dates move past, they're gone.

£29. Full photo scores, everything edited and reordered, cover pulled forward, ZIP in your inbox within 48 hours. If it doesn't help you pick up bookings, reply and I'll send the money back — no back and forth about it.

{checkout_url}

— AL
"""

    return f"""Hi {first},

{outreach_hook}

Real question — when did you last look at your listing the way a guest does? Not as the host who knows the place, but as someone scrolling through 40 options trying to decide which one to click.

{proof}I went through yours. The photos are decent — better than most, actually. But decent doesn't get the click. The sequencing is off and your cover is probably costing you bookings you don't even know you're losing.{photo_line}

You've got {open_nights} empty nights coming up, which is around {rev} at your rate.

For £29 I'll put together a full teardown of your listing, edit and reorder your photos with the right one up front, and have everything in your inbox as a ZIP within 48 hours.

Doesn't move things? Reply and I'll refund it.

{checkout_url}

AL
"""


_OFFER_CSS = """
  body { font-family: -apple-system, Arial, sans-serif; color: #1a1a1a;
          max-width: 560px; margin: 0 auto; padding: 24px 16px; }
  .logo { font-size: 18px; font-weight: 700; }
  .logo span { color: #ff5a3c; }
  .hook { font-size: 15px; line-height: 1.6; margin: 20px 0; }
  .revenue { background: #f5f5f3; border-radius: 8px; padding: 16px 20px;
              margin: 20px 0; font-size: 14px; line-height: 1.6; }
  .revenue strong { font-size: 22px; color: #ff5a3c; display: block; margin-bottom: 4px; }
  .what-you-get { border: 1px solid #e0e0e0; border-radius: 8px;
                   padding: 16px 20px; margin: 20px 0; }
  .what-you-get h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
                      color: #888; font-weight: 600; margin: 0 0 12px; }
  .item { display: flex; gap: 10px; margin: 8px 0; font-size: 14px; line-height: 1.5; }
  .item-icon { flex-shrink: 0; width: 20px; height: 20px; background: #fff3f0;
                border-radius: 50%; display: flex; align-items: center;
                justify-content: center; font-size: 11px; color: #ff5a3c;
                font-weight: 700; margin-top: 1px; }
  .pricing { display: flex; align-items: center; gap: 12px; margin: 20px 0; }
  .price-old { font-size: 18px; color: #bbb; text-decoration: line-through; }
  .price-new { font-size: 32px; font-weight: 800; color: #1a1a1a; }
  .price-badge { background: #fff3f0; border: 1px solid #ffd5cc; color: #ff5a3c;
                  border-radius: 20px; padding: 3px 10px; font-size: 12px; font-weight: 700; }
  .cta { display: block; background: #ff5a3c; color: #fff; text-decoration: none;
          text-align: center; padding: 16px 24px; border-radius: 8px;
          font-weight: 700; font-size: 17px; margin: 20px 0; }
  .guarantee { font-size: 12px; color: #888; text-align: center; margin-top: -10px; }
  .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0;
              font-size: 12px; color: #888; }
  a { color: #ff5a3c; }
"""

_CTA_LABELS = [
    "Get the package — $29",
    "Send me the teardown — $29",
    "Fix my listing — $29",
]

_GUARANTEE_LINES = [
    "Doesn't move your bookings? Reply and I'll refund it. No forms.",
    "If it doesn't help, just reply — I'll refund it.",
    "Not useful? Reply and I'll send the money back. No questions.",
]


def _offer_html(variant: int, first: str, outreach_hook: str,
                open_nights: int, revenue_at_stake: float,
                checkout_url: str, listing_id: str,
                cta_idx: int | None = None, guar_idx: int | None = None) -> str:
    rev = f"£{revenue_at_stake:,.0f}"
    cta  = _CTA_LABELS[cta_idx if cta_idx is not None else variant]
    guar = _GUARANTEE_LINES[guar_idx if guar_idx is not None else variant]
    pixel = _tracking_pixel_tag(listing_id)

    if variant == 0:
        # Obsession angle — personal context, specific find
        body_html = f"""
<p class="hook">Hi {first},<br><br>{outreach_hook}</p>

<p style="font-size:14px;color:#555;line-height:1.7;">I've spent the last few months going through Airbnb listings &mdash;
it's a bit of an obsession at this point. I keep seeing the same thing: hosts with genuinely good
properties sitting on empty nights because the listing isn't showing what the place actually is.</p>

<p style="font-size:14px;color:#555;line-height:1.7;">Yours caught my eye. The photos aren't bad &mdash; but the sequencing
is off, and I'm fairly sure your cover isn't the one that would get the click.</p>

<div class="revenue">
  <strong>{rev}</strong>
  {open_nights} open nights &mdash; at your rate, once those dates pass they don't come back.
</div>

<div class="what-you-get">
  <h3>For $29 I'll go through your listing properly</h3>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>Score every photo &mdash; teardown PDF with what's costing you clicks, what to fix first</div>
  </div>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>Edit and reorder the photos, pull the right one to the front as your cover</div>
  </div>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>ZIP in your inbox within 48 hours &mdash; upload and done</div>
  </div>
</div>"""

    elif variant == 1:
        # Honest/vulnerable — "almost didn't send this"
        body_html = f"""
<p class="hook">Hi {first},<br><br>{outreach_hook}</p>

<p style="font-size:14px;color:#555;line-height:1.7;">I'll be straight with you &mdash; I almost didn't send this.
But I went through your listing and a couple of things stood out that felt worth flagging.</p>

<p style="font-size:14px;color:#555;line-height:1.7;">Your photos aren't being shown in the order that would actually
convert someone who's on the fence. And your cover &mdash; the one photo that decides whether
someone clicks through or keeps scrolling &mdash; I don't think it's your strongest one.</p>

<div class="revenue">
  <strong>{rev}</strong>
  {open_nights} open nights in the next 90 days &mdash; once those dates move past, they're gone.
</div>

<div class="what-you-get">
  <h3>$29 &mdash; full teardown, photos fixed, ZIP in 48 hours</h3>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>Full photo scores &mdash; what's hurting your CTR and in what order to fix it</div>
  </div>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>Everything edited and reordered, cover pulled forward, ready to upload</div>
  </div>
  <div class="item"><div class="item-icon">&#10003;</div>
    <div>ZIP to your inbox within 48 hours &mdash; nothing to install</div>
  </div>
</div>"""

    else:
        # Guest-perspective question — shifts how they see their listing
        body_html = f"""
<p class="hook">Hi {first},<br><br>{outreach_hook}</p>

<p style="font-size:15px;font-weight:600;color:#1a1a1a;line-height:1.5;">When did you last look at your listing
the way a guest does &mdash; not as the host who knows the place, but as someone scrolling through
40 options trying to decide which one to click?</p>

<p style="font-size:14px;color:#555;line-height:1.7;">I went through yours. The photos are decent &mdash; better than most, actually.
But decent doesn't get the click. The sequencing is off and your cover is probably
costing you bookings you don't even know you're losing.</p>

<div class="revenue">
  <strong>{rev}</strong>
  {open_nights} empty nights coming up at your current rate.
</div>

<p style="font-size:14px;color:#555;line-height:1.7;">For $29: a full teardown of your listing, photos edited
and reordered with the right one up front, ZIP in your inbox within 48 hours.</p>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_OFFER_CSS}</style></head>
<body>
<div class="logo">Listing<span>Boost</span></div>
{body_html}
<div class="pricing">
  <span class="price-old">$197</span>
  <span class="price-new">$29</span>
  <span class="price-badge">85% off</span>
</div>
<a href="{checkout_url}" class="cta">{cta}</a>
<p class="guarantee">{guar}</p>
<div class="footer">
  AL &mdash; <a href="mailto:hello@scalr-us.com">hello@scalr-us.com</a><br>
  ListingBoost &bull; Airbnb listing optimization
</div>
{pixel}
</body>
</html>"""


# ── Offer email ───────────────────────────────────────────────────────────────
def send_offer_email(
    host_name: str,
    host_email: str,
    listing_title: str,
    checkout_url: str,
    outreach_hook: str,
    revenue_at_stake: float,
    open_nights: int,
    recipient: str,
    listing_id: str = "",
    photo_position_hook: str = "",
) -> None:
    """Send the payment-gated offer email (no PDF attached). Uses ML Thompson sampling."""
    from ml_variants import pick_variants, record_send, total_sends
    first    = host_name.split()[0] if host_name else "there"
    ml_v     = pick_variants()
    v        = ml_v["body"]
    v_subj   = ml_v["subject"]
    v_cta    = ml_v["cta"]
    v_guar   = ml_v["guarantee"]
    sends    = total_sends()
    subject  = _SUBJECTS[v_subj](first, open_nights, listing_title)
    plain    = _offer_plain(v, first, outreach_hook, open_nights, revenue_at_stake,
                            checkout_url, photo_position_hook=photo_position_hook,
                            sends_so_far=sends)
    html     = _offer_html(v, first, outreach_hook, open_nights, revenue_at_stake,
                           checkout_url, listing_id, cta_idx=v_cta, guar_idx=v_guar)

    token = _access_token()
    msg = MIMEMultipart("mixed")
    msg["To"]      = recipient
    msg["From"]    = "AL <hello@scalr-us.com>"
    msg["Subject"] = subject

    # Body (alternative plain + html)
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(plain, "plain"))
    body_part.attach(MIMEText(html,  "html"))
    msg.attach(body_part)

    # Outreach PDF — only attach when photos are genuinely weak (score_images <= 5).
    # For ok-photo listings, attachment adds spam score with no conversion payoff.
    attach_pdf = False
    if listing_id:
        try:
            td = json.loads((Path(__file__).parent / "work" / "teardowns" /
                             f"teardown_{listing_id}.json").read_text())
            si = td.get("analysis", {}).get("score_images") or 0
            attach_pdf = (si <= 5)
        except Exception:
            attach_pdf = True  # default to attach when teardown unavailable

    if listing_id and attach_pdf:
        pdf_path = Path(__file__).parent / "work" / "pdfs" / f"outreach_{listing_id}.pdf"
        if not pdf_path.exists():
            try:
                from outreach_pdf import build_outreach_pdf
                pdf_path = build_outreach_pdf(listing_id, checkout_url)
                print(f"  [pdf] Built outreach PDF: {pdf_path}")
            except Exception as e:
                print(f"  [pdf] Could not build outreach PDF: {e}")
                pdf_path = None
        if pdf_path and pdf_path.exists():
            with open(pdf_path, "rb") as f:
                att = MIMEBase("application", "pdf")
                att.set_payload(f.read())
            encoders.encode_base64(att)
            att.add_header("Content-Disposition", "attachment",
                           filename="your-listing-teardown-preview.pdf")
            msg.attach(att)
            print(f"  [pdf] Attached {pdf_path.name} ({pdf_path.stat().st_size//1024} KB)")
    elif listing_id and not attach_pdf:
        print(f"  [pdf] Skipped attachment (ok-photo listing, score_images > 5)")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = requests.post(
        _GMAIL_SEND,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=60,
    )
    resp.raise_for_status()
    record_send(ml_v, listing_id or host_email)
    print(f"  [gmail] Offer sent to {recipient} (body={v} subj={v_subj} cta={v_cta} guar={v_guar}, msg id: {resp.json().get('id', '?')})")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="ListingBoost delivery")
    parser.add_argument("--listing-dir",   required=True)
    parser.add_argument("--results-dir",   required=True)
    parser.add_argument("--host-email",    required=True)
    parser.add_argument("--host-name",     default="Host")
    parser.add_argument("--listing-title", default="Your Airbnb Listing")
    parser.add_argument("--listing-url",   default="")
    parser.add_argument("--test",          action="store_true",
                        help="Send to OWNER_EMAIL instead of host")
    parser.add_argument("--payment-first", action="store_true",
                        help="Generate Creem checkout link and print it (no email)")
    parser.add_argument("--send-offer",    action="store_true",
                        help="Email the host the payment link (no PDF). Reads teardown JSON for hook.")
    parser.add_argument("--creem-product-id",
                        default=os.environ.get("CREEM_PRODUCT_ID", ""),
                        help="Creem product ID (override CREEM_PRODUCT_ID env)")
    parser.add_argument("--gumroad-url",
                        default=os.environ.get("GUMROAD_URL", "https://itsalfahri.gumroad.com/l/bkitwy"),
                        help="Gumroad checkout URL (used when Creem is unavailable)")
    args = parser.parse_args()

    listing_dir = Path(args.listing_dir)
    results_dir = Path(args.results_dir)
    export_dir  = results_dir / "FINAL_EXPORT"
    pdf_path    = results_dir / "teardown_report.pdf"

    # Step 0a: send-offer mode — email the host a payment link, no PDF
    if args.send_offer:

        listing_id = listing_dir.name
        teardown_json = Path(f"work/teardowns_cache/teardown_{listing_id}.json")
        if not teardown_json.exists():
            print(f"[deliver] ERROR: teardown JSON not found at {teardown_json}")
            print("  Run:  python3 teardown.py <url>  first to generate it.")
            sys.exit(1)

        with open(teardown_json) as f:
            td = json.load(f)

        outreach_hook    = td.get("outreach_hook", "")
        revenue_at_stake = td.get("revenue_at_stake_90d") or 0
        open_nights      = td.get("open_nights_90d") or 0
        nightly_rate     = td.get("nightly_rate") or 0
        # Photo-specific hook: first sentence of photo_order_rec from teardown analysis
        _photo_rec = td.get("analysis", {}).get("photo_order_rec", "")
        photo_position_hook = (_photo_rec.split(".")[0] + ".").strip() if _photo_rec else ""

        # Hard stop — never send revenue numbers we can't verify from real data
        if not outreach_hook:
            print("[deliver] ERROR: outreach_hook missing in teardown JSON. Re-run teardown.py.")
            sys.exit(1)
        if not nightly_rate or nightly_rate == 0:
            print("[deliver] ERROR: nightly_rate is missing or zero in teardown JSON.")
            print("  The scraper didn't capture a real price for this listing.")
            print("  Check the listing manually and add 'nightly_rate' to the JSON before sending.")
            sys.exit(1)
        if not revenue_at_stake or revenue_at_stake == 0:
            print("[deliver] ERROR: revenue_at_stake_90d is zero — calculation is based on missing data.")
            print("  Set 'nightly_rate' in the teardown JSON and re-run teardown.py.")
            sys.exit(1)

        revenue_at_stake = float(revenue_at_stake)
        open_nights      = int(open_nights)

        if args.creem_product_id:
            from creem_payment import create_checkout_link
            discount_code = os.environ.get("CREEM_DISCOUNT_CODE", "FAST29")
            checkout_url = create_checkout_link(
                product_id=args.creem_product_id,
                customer_email=args.host_email,
                metadata={"listing_id": listing_id, "host_name": args.host_name,
                          "host_email": args.host_email},
                discount_code=discount_code,
            )
        else:
            checkout_url = args.gumroad_url
            print("[deliver] Creem product ID not set — using Gumroad checkout URL")

        recipient = os.environ.get("OWNER_EMAIL", "fakhrialmubarok@gmail.com") if args.test else args.host_email
        if args.test:
            print(f"[deliver] TEST MODE -- sending offer to {recipient} (not host)")

        print(f"[deliver] Sending offer to {recipient}...")
        print(f"  Hook: {outreach_hook[:80]}...")
        print(f"  Revenue at stake: ${revenue_at_stake:,.0f}  |  Open nights: {open_nights}")
        print(f"  Checkout: {checkout_url}")

        send_offer_email(
            host_name=args.host_name,
            host_email=args.host_email,
            listing_title=args.listing_title,
            checkout_url=checkout_url,
            outreach_hook=outreach_hook,
            revenue_at_stake=revenue_at_stake,
            open_nights=open_nights,
            recipient=recipient,
            listing_id=listing_id,
            photo_position_hook=photo_position_hook,
        )
        print("\n[deliver] Offer sent. Run without --send-offer once payment is confirmed.")
        return

    # Step 0b: payment-first mode — generate checkout link and stop
    if args.payment_first:
        if not args.creem_product_id:
            print("[deliver] ERROR: --creem-product-id or CREEM_PRODUCT_ID required for --payment-first")
            print("  1. Create 'ListingBoost' product in Creem dashboard at https://www.creem.io")
            print("  2. Copy the product ID and set CREEM_PRODUCT_ID=prod_xxx in .env")
            sys.exit(1)
        from creem_payment import create_checkout_link
        listing_id = listing_dir.name
        discount_code = os.environ.get("CREEM_DISCOUNT_CODE", "FAST29")
        url = create_checkout_link(
            product_id=args.creem_product_id,
            customer_email=args.host_email,
            metadata={"listing_id": listing_id, "host_name": args.host_name,
                      "host_email": args.host_email},
            discount_code=discount_code,
        )
        print(f"\n[deliver] Payment link for {args.host_name} ({args.host_email}):")
        print(f"  {url}\n")
        print(f"  Anchor: $197  →  Offer: $29  (discount code: {discount_code})")
        print("Send this link to the host. Once paid, run deliver.py again without --payment-first.")
        return

    # Step 1: generate PDF if missing
    if not pdf_path.exists():
        print("[deliver] Generating teardown PDF...")
        sys.path.insert(0, str(ROOT))
        from generate_teardown_pdf import generate_teardown
        generate_teardown(
            listing_dir, results_dir,
            args.host_name, args.listing_title, args.listing_url,
            pdf_path,
        )
    else:
        size_kb = pdf_path.stat().st_size // 1024
        print(f"[deliver] Using existing PDF ({size_kb} KB)")

    # Step 2: build ZIP
    if not export_dir.exists():
        print(f"[deliver] ERROR: FINAL_EXPORT not found at {export_dir}")
        print("  Run:  python3 photo_regen_free.py --export --listing-dir ... --results-dir ...")
        sys.exit(1)

    photos = sorted(p for p in export_dir.glob("*")
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    photo_count = len(photos)
    print(f"[deliver] Building ZIP: {photo_count} photos + PDF...")
    zip_bytes = build_zip(export_dir, pdf_path)
    if len(zip_bytes) > MAX_ATTACH_BYTES:
        print(f"[deliver] ZIP {len(zip_bytes)//(1024*1024)}MB > 20MB Gmail margin — "
              "attach would 500. Rebuild without staged/ set or deliver via Drive link.")
        raise SystemExit(1)
    zip_kb = len(zip_bytes) // 1024
    print(f"[deliver] ZIP ready: {zip_kb} KB")

    # Step 3: send
    recipient = os.environ.get("OWNER_EMAIL", "fakhrialmubarok@gmail.com") if args.test else args.host_email
    if args.test:
        print(f"[deliver] TEST MODE -- sending to {recipient} (not host)")

    listing_id = listing_dir.name
    zip_name   = f"ListingBoost_{listing_id}.zip"
    subject    = f"Your ListingBoost package is ready -- {args.listing_title}"

    plain, html = _build_body(args.host_name, args.listing_title, photo_count,
                              listing_id=listing_id)

    print(f"[deliver] Sending to {recipient}...")
    send_with_attachment(
        to=recipient,
        subject=subject,
        plain=plain,
        html=html,
        zip_bytes=zip_bytes,
        zip_filename=zip_name,
    )

    print(f"\n[deliver] Done.")
    print(f"  PDF:    {pdf_path.name}  ({pdf_path.stat().st_size // 1024} KB)")
    print(f"  Photos: {photo_count}")
    print(f"  ZIP:    {zip_name}  ({zip_kb} KB)")
    print(f"  Sent:   {recipient}")


if __name__ == "__main__":
    main()
