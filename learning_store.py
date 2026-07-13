"""
LearningStore — shared SQLite brain for the entire ListingBoost ML pipeline.

Every process reads from and writes to this store. Two tables:

  signals   — atomic learnings emitted by any process at any time
              (what worked, what failed, cost/quality measurements)

  strategy  — derived rules per process, recomputed from signals
              (what each process should do differently next run)

Intra-process loop:  process runs → emits signals → reads strategy → adapts mid-run
Inter-process loop:  downstream signals (e.g. outcome) → upstream strategy (e.g. scraper)

Signal schema:
  process   — scraper | analyzer | generator | delivery | outcome
  event     — what happened (e.g. "title_length_correlated_with_booking")
  value     — numeric measurement (correlation, score, cost, CTR...)
  metadata  — JSON blob (any extra context)
  timestamp — when it happened

Strategy schema:
  process   — which process owns this rule
  key       — rule name (e.g. "preferred_title_length", "avoid_amenity_gap_score_below")
  value     — current best value for this parameter
  confidence — 0.0-1.0 (how many signals back this up)
  updated_at — last time this was recomputed
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "learning.db"


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            process   TEXT NOT NULL,
            event     TEXT NOT NULL,
            value     REAL,
            metadata  TEXT,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS strategy (
            process    TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (process, key)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_process ON signals(process);
        CREATE INDEX IF NOT EXISTS idx_signals_event   ON signals(event);
        """)


def emit(process: str, event: str, value: float | None = None, metadata: dict | None = None):
    """Any process calls this to record a learning signal."""
    with _conn() as con:
        con.execute(
            "INSERT INTO signals (process, event, value, metadata, timestamp) VALUES (?,?,?,?,?)",
            (process, event, value, json.dumps(metadata or {}), datetime.utcnow().isoformat())
        )


def get_strategy(process: str, key: str, default: Any = None) -> Any:
    """Read a learned strategy parameter. Returns default if not yet learned."""
    with _conn() as con:
        row = con.execute(
            "SELECT value, confidence FROM strategy WHERE process=? AND key=?",
            (process, key)
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_strategy(process: str, key: str, value: Any, confidence: float = 0.5):
    """Write/update a strategy parameter."""
    with _conn() as con:
        con.execute("""
        INSERT INTO strategy (process, key, value, confidence, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(process, key) DO UPDATE SET
            value=excluded.value,
            confidence=excluded.confidence,
            updated_at=excluded.updated_at
        """, (process, key, json.dumps(value), confidence, datetime.utcnow().isoformat()))


def recent_signals(process: str | None = None, event: str | None = None,
                   limit: int = 100) -> list[dict]:
    """Fetch recent signals, optionally filtered."""
    query = "SELECT * FROM signals WHERE 1=1"
    params: list[Any] = []
    if process:
        query += " AND process=?"
        params.append(process)
    if event:
        query += " AND event=?"
        params.append(event)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def avg_signal(process: str, event: str, limit: int = 50) -> float | None:
    """Rolling average of a numeric signal — used for strategy recomputation."""
    with _conn() as con:
        row = con.execute("""
        SELECT AVG(value) as avg FROM (
            SELECT value FROM signals
            WHERE process=? AND event=? AND value IS NOT NULL
            ORDER BY id DESC LIMIT ?
        )
        """, (process, event, limit)).fetchone()
    return row["avg"] if row else None


def recompute_all_strategies():
    """
    Derive updated strategy params from accumulated signals.
    Called at the end of every full pipeline run so each next run is smarter.

    Inter-process learning happens here:
      outcome signals → update scraper/analyzer/generator strategies
    """

    # --- GENERATOR: learn preferred title length from high-rated scraped listings ---
    avg_good_title_len = avg_signal("scraper", "high_rated_title_length")
    if avg_good_title_len:
        set_strategy("generator", "preferred_title_length", round(avg_good_title_len),
                     confidence=min(0.95, 0.5 + len(recent_signals("scraper", "high_rated_title_length")) * 0.01))

    # --- GENERATOR: learn which amenity categories correlate with high ratings ---
    amenity_signals = recent_signals("scraper", "top_amenity_category", limit=200)
    if amenity_signals:
        from collections import Counter
        cats = [json.loads(s["metadata"]).get("category") for s in amenity_signals if s["metadata"]]
        top_cats = [c for c, _ in Counter(cats).most_common(5) if c]
        if top_cats:
            set_strategy("generator", "high_value_amenity_categories", top_cats, confidence=0.7)

    # --- ANALYZER: learn which score thresholds predict outcome improvement ---
    avg_amenity_gap = avg_signal("analyzer", "amenity_gap_score")
    if avg_amenity_gap is not None:
        set_strategy("analyzer", "amenity_gap_alert_threshold", round(avg_amenity_gap - 1, 1),
                     confidence=0.6)

    # --- SCRAPER: learn from outcome which fields matter most (prioritize those) ---
    outcome_signals = recent_signals("outcome", "field_correlated_with_improvement", limit=100)
    if outcome_signals:
        fields = [json.loads(s["metadata"]).get("field") for s in outcome_signals if s["metadata"]]
        from collections import Counter
        priority_fields = [f for f, _ in Counter(fields).most_common(10) if f]
        if priority_fields:
            set_strategy("scraper", "priority_fields", priority_fields, confidence=0.65)

    # --- DELIVERY: learn from outcome what format clients engage with most ---
    avg_engagement = avg_signal("outcome", "client_engagement_score")
    if avg_engagement is not None:
        set_strategy("delivery", "min_engagement_score_to_send", round(avg_engagement * 0.8, 2),
                     confidence=0.6)

    emit("system", "strategies_recomputed", metadata={
        "strategies_updated": ["generator", "analyzer", "scraper", "delivery"]
    })


init()
