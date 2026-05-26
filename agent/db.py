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

                raw_alert TEXT,
                normalized_alert TEXT,

                category TEXT,
                confidence REAL,
                category_description TEXT,

                rag_query TEXT,
                rag_playbooks TEXT,

                plan_result TEXT,
                plan_summary TEXT,
                steps_count INTEGER,
                raw_markdown TEXT,

                duration_seconds REAL
            )
        """)
        conn.commit()

def _get(db_path: str, analysis_id: int) -> dict | None:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("raw_alert", "normalized_alert", "plan_result"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    if d.get("rag_playbooks"):
        d["rag_playbooks"] = [p.strip() for p in d["rag_playbooks"].split(",") if p.strip()]
    return d


def get_analysis_by_id(db_path: str, analysis_id: int) -> dict | None:
    return _get(db_path, analysis_id)


def get_analyses(db_path: str, limit: int = 20, offset: int = 0) -> list[dict]:
    init_db(db_path)
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, alert_id, created_at, category, steps_count, duration_seconds FROM analyses ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def count_analyses(db_path: str) -> int:
    init_db(db_path)
    with _conn(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]


def save_analysis(
    db_path: str,
    *,
    alert_id: str,
    raw_alert: object = None,
    normalized_alert: object = None,
    category: str,
    confidence: float,
    category_description: str,
    rag_query: str = "",
    rag_playbooks: list[str] = None,
    plan_result: object = None,
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
                raw_alert, normalized_alert,
                category, confidence, category_description,
                rag_query, rag_playbooks,
                plan_result, plan_summary, steps_count, raw_markdown,
                duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(raw_alert, default=str) if raw_alert else None,
                json.dumps(normalized_alert, default=str) if normalized_alert else None,
                category,
                confidence,
                (category_description or "")[:500],
                (rag_query or "")[:500],
                ",".join(pb for pb in (rag_playbooks or [])),
                json.dumps(plan_result, default=str) if plan_result else None,
                (plan_summary or "")[:500],
                steps_count,
                raw_markdown or "",
                duration_seconds,
            ),
        )
        conn.commit()
