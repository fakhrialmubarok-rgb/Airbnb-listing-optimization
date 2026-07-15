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
AUTO_ROTATE_AFTER_SENDS  = 10   # rotate if this many sends with 0 replies in one market
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
        from tracker_io import write_rows
        write_rows(TRACKER, rows)
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
        if s["sent"] >= AUTO_ROTATE_AFTER_SENDS and s["replied"] == 0:
            verdicts.append((m, "rotate", f"{s['sent']} sends, 0 replies — AUTO-ROTATING to next market"))
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

    # --- lead criteria for this run (stress-test doctrine 2026-07-15) ---
    decisions["criteria"] = [
        "stake >= £2,000 (agreed floor)",
        "entire home, 5-500 host reviews, pro-operator filter (agreed)",
        "PRIORITIZE bad original photos (dark/tilted/cluttered cover) — biggest "
        "before/after delta = strongest teaser = best conversion odds",
        "contact: cold email ONLY to business-domain addresses (PECR corporate "
        "exemption); personal-mailbox hosts = inbound_only, NEVER cold email",
        "Airbnb DMs: DEAD as a channel — identity-level ban risk (legal red-team)",
        "outreach: plain text, no images/attachments first touch; teaser assets "
        "only after a reply; NEVER send cold from scalr-us.com — secondary domains only",
        "KILL-LINE (pre-committed): <2 sales per 2,000 contacted leads = model "
        "falsified, stop and restructure; <0.2% purchase = structurally unprofitable",
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
    emailable = sum(1 for r in rows if r.get("contact_channel") == "email")
    if rows and emailable / len(rows) < 0.2:
        decisions["warnings"].append(
            f"only {emailable}/{len(rows)} leads are cold-emailable under the PECR "
            "policy — inbound channels (host groups, content, free listing-score "
            "lead magnet) are the real pipeline, not outbound")
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
    if d.get("experiments"):
        lines += ["", "## A/B experiment funnel (price / subject / hook)"] + \
                 [f"- {l}" for l in d["experiments"]]
    if d.get("icp_banks"):
        lines += ["", "## ICP banks (which host profile converts)"] + \
                 [f"- {l}" for l in d["icp_banks"]]
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


def icp_banks(rows) -> list[str]:
    """Per-segment funnel tallies — which host profile actually converts."""
    from collections import defaultdict
    banks = defaultdict(lambda: [0, 0, 0])   # leads, replied, paid
    for r in rows:
        # segment: business vs individual host x photo-badness band
        biz = "business" if r.get("contact_channel") == "email" else "individual"
        prio = 0
        if "photo_priority=" in (r.get("notes") or ""):
            try:
                prio = int(r["notes"].split("photo_priority=")[1][:2].rstrip(","))
            except ValueError:
                pass
        band = "ugly-photos" if prio >= 6 else "ok-photos"
        seg = f"{biz}/{band}"
        banks[seg][0] += 1
        banks[seg][1] += r.get("replied", "").lower() in ("1", "true", "yes")
        banks[seg][2] += r.get("paid", "").lower() in ("1", "true", "yes")
    return [f"{seg}: {v[0]} leads, {v[1]} replied, {v[2]} paid"
            for seg, v in sorted(banks.items())]


def main():
    dry = "--dry" in sys.argv
    rows = load_tracker()
    # learning sync: pull tracker outcomes into the experiment store
    try:
        from experiments import record_outcomes, summary as exp_summary
        record_outcomes(rows)
    except Exception as e:
        exp_summary = lambda: [f"experiments unavailable: {e}"]
    markets = market_stats(rows)
    lessons = photo_lessons()
    decisions = reason(rows, markets, lessons)
    decisions["experiments"] = exp_summary()
    decisions["icp_banks"] = icp_banks(rows)
    write_brief(decisions, markets, dry=dry)


if __name__ == "__main__":
    main()
