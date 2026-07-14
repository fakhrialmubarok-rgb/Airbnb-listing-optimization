"""
orchestrator.py — status-driven step chaining: each completed step hands the
lead to the next automatically. Run once (or on cron); it advances every lead
as far as it can, then reports. (Supersedes the legacy pipeline.py runner.)

Flow (tracker `status` column is the state machine):
  Scraped ──step1b──> (email discovery, non-blocking)
  Scraped ──step2───> Analyzed ──step3(TEASER_MODE)──> Photos Done
  Photos Done ──step4──> PDF Done  (ready to send only if contact_channel=email)
  paid=yes ──step3 FULL──> full set + step4 rebuild -> deliver.py

Design notes:
  - Step 0 brain runs FIRST; its brief opens every run.
  - Teaser mode is the pre-sale default (cost policy: ~3-4 generations/lead,
    free tier covers ~25 leads/day). FULL production (~40 gens) triggers ONLY
    on a `paid` outcome — cost lands per SALE, not per lead.
  - Each step is a subprocess: one step's crash never kills the chain, and
    per-lead commits inside the steps make reruns cheap.

Usage:
  python3 orchestrator.py            # advance everything
  python3 orchestrator.py --dry      # show what would run
"""
from __future__ import annotations
import csv, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
TRACKER = HERE / "work" / "leads_tracker.csv"
PY = sys.executable


def rows():
    return list(csv.DictReader(open(TRACKER))) if TRACKER.exists() else []


def run(label: str, cmd: list[str], env=None) -> bool:
    print(f"\n=== {label} ===")
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(cmd, cwd=HERE, env=e)
    ok = r.returncode == 0
    print(f"=== {label}: {'ok' if ok else f'EXIT {r.returncode} (watchdog?)'} ===")
    return ok


def main():
    dry = "--dry" in sys.argv

    if not dry:
        run("step0 brain", [PY, "step0_brain.py"])

    plan = []
    rs = rows()
    if any(r["status"] == "Scraped" and not r.get("host_email") for r in rs):
        plan.append(("step1b email discovery", [PY, "step1b_emails.py"], {}))
    if any(r["status"] == "Scraped" for r in rs):
        plan.append(("step2 teardown", [PY, "step2_teardown.py"], {}))
    plan.append(("step3 photos (TEASER)", [PY, "step3_photos.py"], {"TEASER_MODE": "1"}))
    plan.append(("step4 pdf", [PY, "step4_pdf.py"], {}))

    if dry:
        for label, _c, _e in plan:
            print("would run:", label)
        return

    for label, cmd, env in plan:
        run(label, cmd, env)

    # post-sale full production — the only place full cost is spent
    for r in rows():
        if r.get("paid", "").lower() in ("1", "true", "yes") and r.get("status") != "Delivered":
            lid = r["listing_id"]
            print(f"\n*** PAID lead {lid} — full production ***")
            run(f"step3 FULL {lid}", [PY, "step3_photos.py", lid],
                {"TEASER_MODE": "0", "BEST_OF": "2"})
            run(f"step4 rebuild {lid}", [PY, "step4_pdf.py", lid])
            print(f"*** {lid}: run deliver.py to ship the ZIP ***")

    from collections import Counter
    c = Counter(r["status"] for r in rows())
    ready = sum(1 for r in rows() if r["status"] == "PDF Done"
                and r.get("contact_channel") == "email")
    print("\n[orchestrator] status:", dict(c))
    print(f"[orchestrator] ready-to-send (PDF Done + emailable): {ready}")


if __name__ == "__main__":
    main()
