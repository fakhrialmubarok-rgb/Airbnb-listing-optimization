"""
Step 0 — The Brain (runs BEFORE any new prospecting run)

Reads everything the system has learned so far and produces a run brief:
which market to scrape next, which lead criteria to apply, what process
lessons to carry into this run. No run starts without a brief.

Inputs read:
  work/leads_tracker.csv     — per-lead pipeline + outcome columns
  work/photo_lessons.json    — accumulated QC failure patterns (Step 3 loop)
  work/run_briefs/*.md       — previous briefs (continuity)

Output:
  work/run_briefs/brief_<date>.md   — human-readable, auditable run plan
  (also printed to stdout)

Usage:
  python3 step0_brain.py                     # analyze + write brief
  python3 step0_brain.py --dry               # analyze, print, don't write
"""
from __future__ import annotations
import sys, json, csv, datetime
from pathlib import Path
from collections import defaultdict

HERE     = Path(__file__).parent
TRACKER  = HERE / "work" / "leads_tracker.csv"
LESSONS  = HERE / "work" / "photo_lessons.json"
BRIEFS   = HERE / "work" / "run_briefs"

# Outcome columns the brain needs. step0 adds them to the tracker if missing
# so downstream steps (and manual updates) always have somewhere to record.
OUTCOME_COLS = ["outreach_sent_at", "opened", "replied", "paid", "outcome_notes"]

# Lead criteria (agreed with Fakhri):
#   - stake >= £2k, entire home, 5-500 host reviews, pro-operator name filter (Step 1)
#   - NEW 2026-07-15: bad photo quality = HIGHER priority (our before/after
#     delta is the product; ugly originals convert best)
MIN_SENDS_BEFORE_VERDICT = 10   # don't judge a market on fewer sends
CANDIDATE_MARKETS = [
    # same profile as Middleton: high listing density, mid-market rates,
    # weak photo culture (suburban UK, non-professional hosts)
    "Leeds suburbs (Headingley, Horsforth)",
    "Liverpool suburbs (Anfield, Wavertree)",
    "Birmingham suburbs (Selly Oak, Erdington)",
    "Sheffield (Ecclesall, Hillsborough)",
    "Newcastle (Jesmond, Heaton)",
]


def load_tracker() -> list[dict]:
    if not TRACKER.exists():
        return []
    rows = list(csv.DictReader(open(TRACKER)))
    # ensure outcome columns exist
    if rows and any(c not in rows[0] for c in OUTCOME_COLS):
        for r in rows:
            for c in OUTCOME_COLS:
                r.setdefault(c, "")
        with open(TRACKER, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print("[step0] added outcome columns to tracker")
    return rows


def market_stats(rows: list[dict]) -> dict:
    stats = defaultdict(lambda: {"leads": 0, "sent": 0, "opened": 0,
                                 "replied": 0, "paid": 0, "avg_stake": 0.0})
    for r in rows:
        m = (r.get("city") or "unknown").strip().lower()
        s = stats[m]
        s["leads"] += 1
        s["sent"] += bool(r.get("outreach_sent_at"))
        s["opened"] += r.get("opened", "").lower() in ("1", "true", "yes")
        s["replied"] += r.get("replied", "").lower() in ("1", "true", "yes")
        s["paid"] += r.get("paid", "").lower() in ("1", "true", "yes")
        try:
            s["avg_stake"] += float(r.get("revenue_at_stake_gbp") or 0)
        except ValueError:
            pass
    for m, s in stats.items():
        if s["leads"]:
            s["avg_stake"] = round(s["avg_stake"] / s["leads"])
    return dict(stats)


def photo_lessons() -> dict:
    try:
        return json.loads(LESSONS.read_text())
    except Exception:
        return {"fail_counts": {}, "candidates_seen": 0}


def reason(rows, markets, lessons) -> dict:
    """The actual brain: decide market, criteria emphasis, process lessons."""
    decisions = {"market": None, "market_reason": "", "criteria": [],
                 "process_lessons": [], "warnings": []}

    # --- market decision ---
    verdicts = []
    for m, s in markets.items():
        if s["sent"] >= MIN_SENDS_BEFORE_VERDICT and s["replied"] == 0:
            verdicts.append((m, "rotate", f"{s['sent']} sends, 0 replies — market not responding"))
        elif s["paid"] > 0:
            verdicts.append((m, "double_down", f"{s['paid']} sale(s) — proven market"))
        else:
            verdicts.append((m, "continue", f"only {s['sent']} sends — not enough outcome data"))
    doubling = [v for v in verdicts if v[1] == "double_down"]
    continuing = [v for v in verdicts if v[1] == "continue"]
    if doubling:
        decisions["market"] = doubling[0][0]
        decisions["market_reason"] = doubling[0][2]
    elif continuing:
        decisions["market"] = continuing[0][0]
        decisions["market_reason"] = (continuing[0][2] +
            " — finish gathering outcome data before rotating. Candidates if rotation "
            "becomes warranted: " + "; ".join(CANDIDATE_MARKETS[:3]))
    else:
        decisions["market"] = "ROTATE -> " + CANDIDATE_MARKETS[0]
        decisions["market_reason"] = ("all current markets exhausted without conversion; "
                                      "next candidates: " + "; ".join(CANDIDATE_MARKETS))
    decisions["market_verdicts"] = verdicts

    # --- lead criteria for this run ---
    decisions["criteria"] = [
        "stake >= £2,000 (agreed floor)",
        "entire home, 5-500 host reviews, pro-operator filter (agreed)",
        "PRIORITIZE bad original photos (dark/tilted/cluttered cover) — biggest "
        "before/after delta = strongest teaser = best conversion odds",
        "contact: email first, Airbnb DM fallback",
    ]

    # --- process lessons from QC history ---
    fails = sorted(lessons.get("fail_counts", {}).items(), key=lambda t: -t[1])
    seen = lessons.get("candidates_seen", 0)
    for check, count in fails[:3]:
        decisions["process_lessons"].append(
            f"'{check}' failed {count}x across {seen} candidates — prompt warning active")

    # --- warnings ---
    no_outcome = sum(1 for r in rows if r.get("status") in ("PDF Done", "Sent")
                     and not r.get("outreach_sent_at"))
    if no_outcome:
        decisions["warnings"].append(
            f"{no_outcome} finished lead(s) have no outreach outcome recorded — "
            "the brain is blind until sends are logged")
    cohort_rows = [r for r in rows if r.get("status") not in ("", "Skipped")]
    if len(cohort_rows) < 15:
        decisions["warnings"].append(
            f"tracker has only {len(cohort_rows)} active leads — cohort medians are weak; "
            "Step 1 must scrape 20+ per market before Step 2 prints market claims")
    return decisions


def write_brief(d: dict, markets: dict, dry=False) -> Path | None:
    today = datetime.date.today().isoformat()
    lines = [f"# Run brief — {today}", ""]
    lines += ["## Market decision", f"**{d['market']}** — {d['market_reason']}", ""]
    lines += ["## Per-market outcomes"]
    for m, s in markets.items():
        lines.append(f"- {m}: {s['leads']} leads, {s['sent']} sent, "
                     f"{s['replied']} replied, {s['paid']} paid, avg stake £{s['avg_stake']}")
    lines += ["", "## Lead criteria this run"] + [f"- {c}" for c in d["criteria"]]
    lines += ["", "## Process lessons in effect"] + \
             ([f"- {l}" for l in d["process_lessons"]] or ["- none yet"])
    if d["warnings"]:
        lines += ["", "## ⚠ Warnings"] + [f"- {w}" for w in d["warnings"]]
    text = "\n".join(lines) + "\n"
    print(text)
    if dry:
        return None
    BRIEFS.mkdir(exist_ok=True)
    p = BRIEFS / f"brief_{today}.md"
    p.write_text(text)
    print(f"[step0] brief written -> {p}")
    return p


def main():
    dry = "--dry" in sys.argv
    rows = load_tracker()
    markets = market_stats(rows)
    lessons = photo_lessons()
    decisions = reason(rows, markets, lessons)
    write_brief(decisions, markets, dry=dry)


if __name__ == "__main__":
    main()
