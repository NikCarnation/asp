import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _conn(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                created_at TEXT NOT NULL,

                category TEXT,
                confidence REAL,
                category_description TEXT,

                playbooks TEXT,

                plan_summary TEXT,
                steps_count INTEGER,
                raw_markdown TEXT,

                duration_seconds REAL
            )
        """)
        conn.commit()


def save_analysis(
    db_path: str,
    *,
    alert_id: str,
    category: str,
    confidence: float,
    category_description: str,
    playbook_titles: list[str],
    plan_summary: str,
    steps_count: int,
    raw_markdown: str,
    duration_seconds: float,
):
    init_db(db_path)
    with _conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO analyses (
                alert_id, created_at,
                category, confidence, category_description,
                playbooks,
                plan_summary, steps_count, raw_markdown,
                duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                datetime.now(timezone.utc).isoformat(),
                category,
                confidence,
                (category_description or "")[:500],
                ",".join(playbook_titles),
                (plan_summary or "")[:500],
                steps_count,
                raw_markdown or "",
                duration_seconds,
            ),
        )
        conn.commit()
