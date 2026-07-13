"""
pipeline.py — ListingBoost ML Pipeline runner

Scrape → Analyze → Generate → Deliver → Measure → Retrain
  ↑_____________________feedback loop______________________↑

Learning happens at two levels:
  INTRA-PROCESS: each module reads its own learned strategy before acting,
                 emits signals as it runs, adapts mid-batch
  INTER-PROCESS: recompute_all_strategies() at the end of each run
                 so upstream processes benefit from downstream signals

Usage:
  python pipeline.py scrape  <url>           # scrape + sheet + drive
  python pipeline.py scrape  --location Bali # market scan
  python pipeline.py status                  # show learned strategies
  python pipeline.py signals [--process X]   # show recent ML signals
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import learning_store as ls


def cmd_scrape(args):
    from scraper import scrape_url, scrape_location
    from sheet_writer import SheetWriter

    if args.url:
        listing = scrape_url(args.url, calendar_months=args.calendar)
        listings = [listing]
    else:
        listings = scrape_location(args.location, max_listings=args.max,
                                   calendar_months=args.calendar)

    writer = SheetWriter()
    urls = writer.write_batch(listings)

    # After full run: recompute all strategies from accumulated signals
    ls.recompute_all_strategies()

    print(f"\n✅ Pipeline complete. {len(listings)} listing(s) processed.")
    for listing, url in zip(listings, urls):
        print(f"  [{listing['listing_id']}] {listing['title'][:50]}")
        if url:
            print(f"    Drive: {url}")


def cmd_status(args):
    """Show all learned strategy parameters."""
    with ls._conn() as con:
        rows = con.execute(
            "SELECT process, key, value, confidence, updated_at FROM strategy ORDER BY process, key"
        ).fetchall()

    if not rows:
        print("No strategies learned yet. Run a scrape first.")
        return

    current_process = None
    for row in rows:
        if row["process"] != current_process:
            current_process = row["process"]
            print(f"\n── {current_process.upper()} ──")
        val = row["value"]
        try:
            val = json.loads(val)
        except Exception:
            pass
        conf = f"{row['confidence']*100:.0f}%"
        print(f"  {row['key']:<35} {str(val):<30} (confidence: {conf})")


def cmd_signals(args):
    """Show recent ML signals, optionally filtered by process."""
    signals = ls.recent_signals(process=args.process, limit=args.limit)
    if not signals:
        print("No signals yet.")
        return
    print(f"{'Process':<12} {'Event':<40} {'Value':<10} Timestamp")
    print("-" * 80)
    for s in signals:
        val = f"{s['value']:.3f}" if s["value"] is not None else "—"
        print(f"{s['process']:<12} {s['event']:<40} {val:<10} {s['timestamp'][:19]}")


def main():
    parser = argparse.ArgumentParser(description="ListingBoost ML Pipeline")
    sub = parser.add_subparsers(dest="cmd")

    # scrape command
    p_scrape = sub.add_parser("scrape", help="Scrape listing(s) → Sheet + Drive")
    grp = p_scrape.add_mutually_exclusive_group(required=True)
    grp.add_argument("url", nargs="?", help="Single Airbnb URL")
    grp.add_argument("--location", help="Market location (e.g. 'Bali')")
    p_scrape.add_argument("--max", type=int, default=10, help="Max listings (market scan)")
    p_scrape.add_argument("--calendar", type=int, default=3, help="Months of calendar data")

    # status command
    sub.add_parser("status", help="Show learned strategy parameters")

    # signals command
    p_sig = sub.add_parser("signals", help="Show recent ML signals")
    p_sig.add_argument("--process", help="Filter by process name")
    p_sig.add_argument("--limit", type=int, default=30)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    {"scrape": cmd_scrape, "status": cmd_status, "signals": cmd_signals}[args.cmd](args)


if __name__ == "__main__":
    main()
