"""
Step 1b — Email discovery (SerpAPI first, Apollo fallback*)

For tracker leads with contact_channel=inbound_only, search the public web for
a BUSINESS email (custom domain). Personal mailboxes are ignored by design —
the PECR contact policy only cold-emails business-subscriber addresses.

*Apollo fallback requires APOLLO_OK=1 (Fakhri approves credit spend per rule).

Usage: python3 step1b_emails.py [--limit N]
"""
from __future__ import annotations
import csv, os, re, sys, json
import requests
from pathlib import Path
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)
from step1_scrape import _contact_channel, PERSONAL_MAIL_DOMAINS
from tracker_io import write_rows

TRACKER = HERE / "work" / "leads_tracker.csv"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
BAD_DOMAINS = PERSONAL_MAIL_DOMAINS | {"airbnb.com", "example.com", "sentry.io",
                                       "wixpress.com", "godaddy.com"}


def serp_search(query: str) -> list[str]:
    r = requests.get("https://serpapi.com/search", params={
        "q": query, "api_key": os.environ["SERPAPI_KEY"],
        "num": 10, "gl": "uk", "hl": "en"}, timeout=30)
    r.raise_for_status()
    d = r.json()
    text = json.dumps(d.get("organic_results", []))
    return EMAIL_RE.findall(text)


REJECT_DOMAIN_PATTERNS = (".gov.uk", ".nhs.uk", ".ac.uk", ".police.uk", ".org")

def _plausible(email: str, host: str, city: str) -> bool:
    """Cheap deterministic sanity + LLM vet — a wrong match is worse than none
    (spam complaint from a charity/council kills the domain)."""
    dom = email.rsplit("@", 1)[1].lower()
    if any(dom.endswith(p) for p in REJECT_DOMAIN_PATTERNS):
        return False
    # require some token connection between host name and the address
    tokens = [t for t in re.split(r"\W+", host.lower()) if len(t) > 2]
    hay = email.lower()
    if not any(t in hay for t in tokens):
        return False
    # LLM vet (free Gemini): is this plausibly THIS Airbnb host's business email?
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={"contents": [{"parts": [{"text":
                f"An Airbnb host in {city}, UK is named '{host}' (individual or small "
                f"property business). Is the email '{email}' PLAUSIBLY this host's own "
                f"business contact? Reject charities, councils, law firms, banks, big "
                f"institutions, or name-coincidences (e.g. 'Middleton' the place vs a "
                f"company named Middleton). Return ONLY JSON: "
                '{"plausible": true|false, "why": "<short>"}'}]}],
                  "generationConfig": {"responseMimeType": "application/json"}},
            timeout=45)
        r.raise_for_status()
        v = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        if not v.get("plausible"):
            print(f"    vetoed {email}: {v.get('why','')[:70]}")
        return bool(v.get("plausible"))
    except Exception:
        return False   # can't verify -> don't send


def discover(host: str, city: str) -> tuple[str, str]:
    """Return (email, source) — business domains only."""
    queries = [
        f'"{host}" {city} property email contact',
        f'"{host}" airbnb {city} contact',
        f'"{host}" short term lets {city}',
    ]
    for q in queries:
        try:
            for e in serp_search(q):
                dom = e.rsplit("@", 1)[1].lower()
                if dom not in BAD_DOMAINS and not dom.endswith(".png") \
                        and _plausible(e.lower(), host, city):
                    return e.lower(), f"serpapi:{q[:40]}"
        except Exception as ex:
            print(f"    serp error: {str(ex)[:60]}")
            break
    # Apollo fallback — gated on explicit approval (credit spend rule)
    if os.getenv("APOLLO_OK") == "1":
        print("    (Apollo fallback would run here — implement org search when approved)")
    return "", ""


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 99
    rows = list(csv.DictReader(open(TRACKER)))
    found = 0
    for r in rows:
        if r.get("host_email") or r.get("status") in ("Emailed (test)",):
            continue
        if found >= limit:
            break
        host, city = r.get("host_name", ""), r.get("city", "")
        if not host:
            continue
        print(f"[step1b] {host} ({city})...")
        email, src = discover(host, city)
        if email:
            r["host_email"], r["email_source"] = email, src
            r["contact_channel"] = _contact_channel(email)
            found += 1
            print(f"    FOUND {email} -> {r['contact_channel']}")
        else:
            print("    none")
    write_rows(TRACKER, rows)
    print(f"\n[step1b] {found} emails found. Tracker updated.")


if __name__ == "__main__":
    main()
