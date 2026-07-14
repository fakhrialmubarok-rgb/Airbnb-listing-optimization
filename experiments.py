"""
experiments.py — the A/B + learning layer every step plugs into.

One store (work/experiments.json) holds:
  arms         — the live test dimensions (price, subject line, hook angle)
  assignments  — which arm each lead got (assigned once, never re-rolled)
  outcomes     — per-arm tallies fed from tracker outcome columns

Assignment is Thompson-sampling-lite: explore evenly until an arm has
enough data, then weight toward winners — the same learn-while-earning
pattern as the photo lessons loop, applied to sales variables.

Usage:
  from experiments import assign, record_outcomes, summary
  arms = assign(listing_id)     # {"price": 39, "subject": "sN", "hook": "..."}
"""
from __future__ import annotations
import json, hashlib, random
from pathlib import Path

HERE  = Path(__file__).parent
STORE = HERE / "work" / "experiments.json"

DEFAULT_ARMS = {
    "price": [
        {"id": "p39",  "value": 39,  "creem": "prod_7iXHDBgS74UY3quKrlI6JZ"},
        {"id": "p99",  "value": 99,  "creem": "prod_gvsm2Kzvn941AQxAZai2c"},
        {"id": "p197", "value": 197, "creem": "prod_3pOdnn3pMt31VT1tssFkOs"},
    ],
    "subject": [
        {"id": "s_nights", "value": "{open_nights} nights are sitting empty on your {city} calendar"},
        {"id": "s_photo",  "value": "your cover photo is costing you bookings — proof inside"},
        {"id": "s_direct", "value": "I rebuilt your Airbnb listing (before/after inside)"},
    ],
    "hook": [
        {"id": "h_occupancy", "value": "occupancy math"},
        {"id": "h_photos",    "value": "photo transformation"},
        {"id": "h_title",     "value": "title rewrite tease"},
    ],
}
MIN_PER_ARM = 30   # explore evenly until each arm has this many sends


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {"arms": DEFAULT_ARMS, "assignments": {}, "outcomes": {}}


def _save(d: dict):
    STORE.write_text(json.dumps(d, indent=2))


def assign(listing_id: str) -> dict:
    """Assign (or return existing) arm per dimension for this lead."""
    d = _load()
    if listing_id in d["assignments"]:
        return d["assignments"][listing_id]
    picked = {}
    for dim, arms in d["arms"].items():
        counts = {a["id"]: 0 for a in arms}
        wins   = {a["id"]: 0 for a in arms}
        for lid, asg in d["assignments"].items():
            aid = asg.get(dim)
            if aid in counts:
                counts[aid] += 1
                o = d["outcomes"].get(lid, {})
                wins[aid] += 1 if o.get("paid") else 0
        under = [a for a in arms if counts[a["id"]] < MIN_PER_ARM]
        if under:   # exploration phase: fill evenly, deterministic by lead id
            h = int(hashlib.sha1(f"{listing_id}:{dim}".encode()).hexdigest(), 16)
            arm = under[h % len(under)]
        else:       # exploitation: sample proportional to smoothed win rate
            weights = [(wins[a["id"]] + 1) / (counts[a["id"]] + 2) for a in arms]
            arm = random.choices(arms, weights=weights)[0]
        picked[dim] = arm["id"]
    d["assignments"][listing_id] = picked
    _save(d)
    return picked


def arm_value(dim: str, arm_id: str):
    d = _load()
    for a in d["arms"].get(dim, []):
        if a["id"] == arm_id:
            return a
    return None


def record_outcomes(tracker_rows: list[dict]):
    """Sync tracker outcome columns into the experiment store."""
    d = _load()
    for r in tracker_rows:
        lid = r.get("listing_id")
        if lid in d["assignments"]:
            d["outcomes"][lid] = {
                "sent":    bool(r.get("outreach_sent_at")),
                "opened":  r.get("opened", "").lower() in ("1", "true", "yes"),
                "replied": r.get("replied", "").lower() in ("1", "true", "yes"),
                "paid":    r.get("paid", "").lower() in ("1", "true", "yes"),
            }
    _save(d)


def summary() -> list[str]:
    """Per-arm funnel lines for the Step 0 brief."""
    d = _load()
    lines = []
    for dim, arms in d["arms"].items():
        for a in arms:
            lids = [l for l, asg in d["assignments"].items() if asg.get(dim) == a["id"]]
            o = [d["outcomes"].get(l, {}) for l in lids]
            sent = sum(1 for x in o if x.get("sent"))
            if not lids:
                continue
            lines.append(f"{dim}:{a['id']} — {len(lids)} assigned, {sent} sent, "
                         f"{sum(1 for x in o if x.get('opened'))} opened, "
                         f"{sum(1 for x in o if x.get('replied'))} replied, "
                         f"{sum(1 for x in o if x.get('paid'))} paid")
    return lines or ["no experiment data yet"]
