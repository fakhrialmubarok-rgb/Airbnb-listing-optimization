"""
ML Variant Manager — Thompson Sampling for outreach variant selection.

Replaces the MD5-hash deterministic variant picker in deliver.py.
Learns which subject / body / CTA / guarantee combinations convert best
and automatically shifts weight toward winners as data comes in.

Storage:
  work/ml_variants.json   — Beta distribution parameters per variant arm
  work/ml_send_log.jsonl  — one line per send: listing_id + which variants used
"""
from __future__ import annotations
import json, random, datetime
from pathlib import Path

HERE     = Path(__file__).parent
STATE    = HERE / "work" / "ml_variants.json"
LOG      = HERE / "work" / "ml_send_log.jsonl"

# Variant counts (must match deliver.py)
N_SUBJECT   = 5
N_BODY      = 3
N_CTA       = 3
N_GUARANTEE = 3

N_SEND_TIME = 3   # 0=morning 8-9am, 1=lunchtime 12-1pm, 2=evening 5-6pm

AXES = {
    "subject":   N_SUBJECT,
    "body":      N_BODY,
    "cta":       N_CTA,
    "guarantee": N_GUARANTEE,
    "send_time": N_SEND_TIME,
}

SEND_TIME_WINDOWS = {
    0: (8, 9),    # morning
    1: (12, 13),  # lunchtime
    2: (17, 18),  # evening
}


def recommended_send_hour() -> int:
    """Return the hour (local UK time) the ML system wants to send next."""
    chosen = pick_variants()
    window = SEND_TIME_WINDOWS.get(chosen.get("send_time", 0), (8, 9))
    return window[0]


def _load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return _blank()


def _blank() -> dict:
    state = {}
    for axis, n in AXES.items():
        for i in range(n):
            state[f"{axis}_{i}"] = {"sends": 0, "replies": 0, "conversions": 0}
    return state


def _save(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def _beta_sample(successes: int, sends: int) -> float:
    """Sample from Beta(successes+1, failures+1). Uses random.betavariate."""
    failures = max(0, sends - successes)
    return random.betavariate(successes + 1, failures + 1)


def pick_variants() -> dict:
    """
    Thompson sampling: for each variant arm, sample from Beta(conversions+1, sends-conversions+1).
    Pick the arm with the highest sample per axis.
    Returns {"subject": 0-4, "body": 0-2, "cta": 0-2, "guarantee": 0-2}
    """
    state = _load()
    chosen = {}
    for axis, n in AXES.items():
        best_val, best_idx = -1.0, 0
        for i in range(n):
            arm = state.get(f"{axis}_{i}", {"sends": 0, "conversions": 0})
            sample = _beta_sample(arm.get("conversions", 0), arm.get("sends", 0))
            if sample > best_val:
                best_val, best_idx = sample, i
        chosen[axis] = best_idx
    return chosen


def record_send(variants: dict, listing_id: str) -> None:
    """Increment sends for each chosen variant. Log to ml_send_log.jsonl."""
    state = _load()
    for axis, idx in variants.items():
        key = f"{axis}_{idx}"
        if key in state:
            state[key]["sends"] += 1
        else:
            state[key] = {"sends": 1, "replies": 0, "conversions": 0}
    _save(state)

    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({
            "ts": datetime.datetime.utcnow().isoformat(),
            "listing_id": listing_id,
            "variants": variants,
        }) + "\n")


def _get_variants_for_listing(listing_id: str) -> dict | None:
    """Look up which variants a listing received (from send log)."""
    if not LOG.exists():
        return None
    for line in LOG.read_text().splitlines():
        try:
            entry = json.loads(line)
            if entry.get("listing_id") == listing_id:
                return entry.get("variants")
        except Exception:
            continue
    return None


def record_outcome(listing_id: str, outcome: str) -> None:
    """
    outcome: 'opened' | 'replied' | 'paid'
    Finds which variants the listing received and increments the right counter.
    'paid' also increments replies (they replied by paying).
    """
    variants = _get_variants_for_listing(listing_id)
    if not variants:
        return
    state = _load()
    for axis, idx in variants.items():
        key = f"{axis}_{idx}"
        if key not in state:
            state[key] = {"sends": 0, "replies": 0, "conversions": 0}
        if outcome in ("replied", "paid"):
            state[key]["replies"] = state[key].get("replies", 0) + 1
        if outcome == "paid":
            state[key]["conversions"] = state[key].get("conversions", 0) + 1
    _save(state)


def get_stats() -> dict:
    """Return summary of all variant performance."""
    state = _load()
    total_sends = sum(v.get("sends", 0) for v in state.values())
    total_conversions = sum(v.get("conversions", 0) for v in state.values())
    by_axis = {}
    for axis, n in AXES.items():
        by_axis[axis] = []
        for i in range(n):
            arm = state.get(f"{axis}_{i}", {})
            s = arm.get("sends", 0)
            c = arm.get("conversions", 0)
            r = arm.get("replies", 0)
            by_axis[axis].append({
                "idx": i, "sends": s, "replies": r, "conversions": c,
                "conv_rate": round(c/s, 3) if s else None,
            })
    return {
        "total_sends": total_sends,
        "total_conversions": total_conversions,
        "overall_conv_rate": round(total_conversions/total_sends, 3) if total_sends else None,
        "by_axis": by_axis,
    }


def total_sends() -> int:
    return get_stats()["total_sends"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        import pprint; pprint.pprint(get_stats())
    elif len(sys.argv) > 2 and sys.argv[1] == "outcome":
        record_outcome(sys.argv[2], sys.argv[3])
        print(f"Recorded {sys.argv[3]} for {sys.argv[2]}")
    else:
        v = pick_variants()
        print("Sampled variants:", v)
