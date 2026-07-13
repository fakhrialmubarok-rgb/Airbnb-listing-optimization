"""
Step 2 — Teardown Analysis (process v1, pending lock)

Reads work/step1_qualified.json, runs the sharpened LLM analysis on each lead
with a same-batch market benchmark, saves per-listing teardown JSON, and
updates the tracker CSV (scores, weakest_element, hook, status=Analyzed).

LLM chain is free-first: 5 Groq models (independent per-model limits) →
Gemini Flash (if key set) → Together/SiliconFlow (if keys set) → paid last.

Usage:
  python3 step2_teardown.py                 # analyze all status=Scraped leads
  python3 step2_teardown.py <listing_id>    # analyze one
"""
import sys, json, csv
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env", override=True)
sys.path.insert(0, str(HERE))

from teardown import _analyze, build_market_context

QUALIFIED_JSON = HERE / "work" / "step1_qualified.json"
TRACKER_CSV    = HERE / "work" / "leads_tracker.csv"
TEARDOWN_DIR   = HERE / "work" / "teardowns"
TEARDOWN_DIR.mkdir(parents=True, exist_ok=True)


def main():
    only_id = sys.argv[1] if len(sys.argv) > 1 else None
    cohort = json.loads(QUALIFIED_JSON.read_text())
    market_context = build_market_context(cohort)
    print(f"[step2] Market context:\n{market_context}\n")

    with open(TRACKER_CSV) as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())
    for col in ("score_title", "score_desc", "score_photos", "score_amenities",
                "weakest_element", "outreach_hook", "teardown_json"):
        if col not in fieldnames:
            fieldnames.append(col)

    by_id = {r["listing_id"]: r for r in rows}
    done = 0
    for l in cohort:
        lid = l.get("listing_id")
        if only_id and lid != only_id:
            continue
        row = by_id.get(lid)
        if row is None or row.get("status") not in ("Scraped", "", None):
            continue

        print(f"[step2] Analyzing {lid} ({l.get('host_name')})...")
        analysis = _analyze(l, market_context=market_context)

        out = TEARDOWN_DIR / f"teardown_{lid}.json"
        out.write_text(json.dumps({
            "listing_id": lid,
            "host_name": l.get("host_name"),
            "analyzed_at": date.today().isoformat(),
            "market_context": market_context,
            "listing_numbers": {
                "nightly_rate_gbp": l.get("nightly_rate"),
                "occupancy_pct": l.get("occupancy_pct"),
                "open_nights_90d": l.get("open_nights_90d"),
                "revenue_at_stake_gbp": round((l.get("nightly_rate") or 0) * (l.get("open_nights_90d") or 0), 2),
            },
            "analysis": analysis,
        }, indent=2))

        row.update({
            "score_title":     analysis.get("score_title"),
            "score_desc":      analysis.get("score_desc"),
            "score_photos":    analysis.get("score_images"),
            "score_amenities": analysis.get("score_amenities"),
            "weakest_element": analysis.get("weakest_element", ""),
            "outreach_hook":   analysis.get("outreach_hook", ""),
            "teardown_json":   str(out),
            "status":          "Analyzed",
        })
        done += 1
        print(f"  scores T{analysis.get('score_title')}/D{analysis.get('score_desc')}/"
              f"P{analysis.get('score_images')}/A{analysis.get('score_amenities')} "
              f"| weakest={analysis.get('weakest_element')}")
        print(f"  hook: {analysis.get('outreach_hook')}\n")

    with open(TRACKER_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"[step2] {done} lead(s) analyzed. Teardowns -> {TEARDOWN_DIR}/  Tracker updated.")


if __name__ == "__main__":
    main()
