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
COHORT_JSON    = HERE / "work" / "step1_cohort.json"
MIN_COHORT     = 15   # below this, the benchmark is too thin to put in a paid PDF
TRACKER_CSV    = HERE / "work" / "leads_tracker.csv"
TEARDOWN_DIR   = HERE / "work" / "teardowns"
TEARDOWN_DIR.mkdir(parents=True, exist_ok=True)


def _tracker_to_listing(r: dict) -> dict:
    """Reconstruct a listing dict from tracker CSV columns for step2 input."""
    def _f(v, t=float):
        try: return t(v) if v else None
        except: return None
    return {
        "listing_id":        r.get("listing_id",""),
        "listing_url":       r.get("url",""),
        "title":             r.get("title",""),
        "description":       r.get("description",""),
        "property_type":     "Entire home",
        "city":              r.get("city",""),
        "host_name":         r.get("host_name",""),
        "host_email":        r.get("host_email",""),
        "nightly_rate":      _f(r.get("nightly_rate_gbp")),
        "occupancy_pct":     _f(r.get("occupancy_pct")),
        "open_nights_90d":   _f(r.get("open_nights_90d"), int),
        "revenue_at_stake_gbp": _f(r.get("revenue_at_stake_gbp")),
        "photo_count":       _f(r.get("photo_count"), int),
        "rating_overall":    _f(r.get("rating")),
        "review_count":      _f(r.get("reviews"), int),
        "is_superhost":      r.get("superhost",""),
        "person_capacity":   4,
        "amenities_available": "",
        "cover_photo_url":   r.get("cover_photo_url",""),
        "is_entire_home":    True,
        "host_years": 0, "host_rating_avg": None,
        "amenities_missing": [], "image_rooms": [],
    }


def main():
    only_id = sys.argv[1] if len(sys.argv) > 1 else None

    # Always read leads from tracker (authoritative), not just the last scrape's JSON
    with open(TRACKER_CSV) as f:
        all_rows = list(csv.DictReader(f))
    scraped_rows = [r for r in all_rows if r.get("status") == "Scraped"]
    if only_id:
        scraped_rows = [r for r in all_rows
                        if r.get("listing_id") == only_id and
                        r.get("status") in ("Scraped", "Analyzed")]
    leads = [_tracker_to_listing(r) for r in scraped_rows]
    if not leads and not only_id:
        print("[step2] No Scraped leads in tracker."); return

    # Cohort = ALL tracker rows with a rate (multi-market benchmark)
    cohort_rows = [r for r in all_rows if r.get("nightly_rate_gbp")]
    cohort = [_tracker_to_listing(r) for r in cohort_rows]
    # Fallback: use the saved cohort JSON if tracker has no rates yet
    if not cohort and COHORT_JSON.exists():
        cohort = json.loads(COHORT_JSON.read_text())
    if len(cohort) < MIN_COHORT:
        print(f"[step2] WARNING: cohort has only {len(cohort)} listings (< {MIN_COHORT}). "
              f"Benchmark is thin — scrape a bigger batch (step1 count >= 20) before "
              f"putting these medians in a customer PDF.")

    import statistics as st
    rates = [l["nightly_rate"] for l in cohort if l.get("nightly_rate")]
    # Thin-cohort guard: no price-vs-market hooks off a <15 cohort
    median_rate = st.median(rates) if rates and len(cohort) >= 15 else None

    market_context = build_market_context(cohort)
    print(f"[step2] Market context:\n{market_context}\n")

    rows = all_rows   # already loaded above
    fieldnames = list(rows[0].keys())
    for col in ("score_title", "score_desc", "score_photos", "score_amenities",
                "weakest_element", "outreach_hook", "teardown_json"):
        if col not in fieldnames:
            fieldnames.append(col)

    by_id = {r["listing_id"]: r for r in rows}
    done = 0
    for l in leads:
        lid = l.get("listing_id")
        if only_id and lid != only_id:
            continue
        row = by_id.get(lid)
        if row is None or row.get("status") not in ("Scraped", "", None):
            continue

        print(f"[step2] Analyzing {lid} ({l.get('host_name')})...")
        try:
            analysis = _analyze(l, market_context=market_context, cohort_median_rate=median_rate)
        except Exception as e:
            print(f"  [step2] {lid} FAILED ({str(e)[:100]}) — continuing with next lead")
            continue

        out = TEARDOWN_DIR / f"teardown_{lid}.json"
        # City-level median from same-city cohort rows (free, no extra API call)
        city_key = (l.get("city") or "").strip().lower()
        city_rates = [
            float(r.get("nightly_rate_gbp", 0))
            for r in cohort_rows
            if (r.get("city") or "").strip().lower() == city_key
            and r.get("nightly_rate_gbp")
        ]
        city_median = round(st.median(city_rates), 2) if len(city_rates) >= 5 else median_rate

        out.write_text(json.dumps({
            "listing_id":   lid,
            "host_name":    l.get("host_name"),
            "location":     l.get("city") or "",
            "analyzed_at":  date.today().isoformat(),
            "market_context": market_context,
            "listing_numbers": {
                "nightly_rate_gbp":       l.get("nightly_rate"),
                "cohort_median_rate_gbp": city_median,
                "occupancy_pct":          l.get("occupancy_pct"),
                "open_nights_90d":        l.get("open_nights_90d"),
                "revenue_at_stake_gbp":   round((l.get("nightly_rate") or 0) * (l.get("open_nights_90d") or 0), 2),
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
        # per-lead commit: a crash at lead N keeps leads 1..N-1 Analyzed
        from tracker_io import write_rows
        write_rows(TRACKER_CSV, rows, fieldnames)

    from tracker_io import write_rows
    write_rows(TRACKER_CSV, rows, fieldnames)

    print(f"[step2] {done} lead(s) analyzed. Teardowns -> {TEARDOWN_DIR}/  Tracker updated.")


if __name__ == "__main__":
    main()
