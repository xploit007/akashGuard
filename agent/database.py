import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.config import settings


def _get_conn() -> sqlite3.Connection:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                health_url TEXT NOT NULL,
                sdl_template TEXT,
                status TEXT NOT NULL DEFAULT 'unknown',
                current_dseq TEXT,
                current_provider TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL REFERENCES services(id),
                status_code INTEGER,
                response_time_ms REAL,
                is_healthy INTEGER NOT NULL,
                error_message TEXT,
                checked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL REFERENCES services(id),
                trigger TEXT NOT NULL,
                diagnosis TEXT,
                confidence REAL,
                action_taken TEXT NOT NULL,
                reasoning TEXT,
                langfuse_trace_id TEXT,
                outcome TEXT,
                new_dseq TEXT,
                new_provider TEXT,
                downtime_seconds REAL,
                decided_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provider_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_address TEXT NOT NULL,
                successful_deployments INTEGER NOT NULL DEFAULT 0,
                failed_deployments INTEGER NOT NULL DEFAULT 0,
                avg_uptime_pct REAL NOT NULL DEFAULT 100.0,
                avg_response_time_ms REAL,
                last_used_at TEXT,
                score REAL NOT NULL DEFAULT 50.0,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_health_service
                ON health_checks(service_id, checked_at DESC);

            CREATE INDEX IF NOT EXISTS idx_decisions_service
                ON agent_decisions(service_id, decided_at DESC);

            CREATE INDEX IF NOT EXISTS idx_provider_address
                ON provider_scores(provider_address);
        """)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def add_service(name: str, health_url: str, sdl_template: str | None = None) -> int:
    now = _now()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO services (name, health_url, sdl_template, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, health_url, sdl_template, now, now),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_service(service_id: int) -> dict[str, Any] | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
        return dict(row) if row else None


def get_all_services() -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def update_service_status(service_id: int, status: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE services SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), service_id),
        )


def update_service_deployment(
    service_id: int, dseq: str, provider: str, health_url: str | None = None,
) -> None:
    now = _now()
    with _get_conn() as conn:
        if health_url:
            conn.execute(
                """UPDATE services
                   SET current_dseq = ?, current_provider = ?, health_url = ?,
                       consecutive_failures = 0, status = 'recovering', updated_at = ?
                   WHERE id = ?""",
                (dseq, provider, health_url, now, service_id),
            )
        else:
            conn.execute(
                """UPDATE services
                   SET current_dseq = ?, current_provider = ?,
                       consecutive_failures = 0, status = 'recovering', updated_at = ?
                   WHERE id = ?""",
                (dseq, provider, now, service_id),
            )


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def record_health_check(
    service_id: int,
    status_code: int | None,
    response_time_ms: float | None,
    is_healthy: bool,
    error_message: str | None = None,
) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO health_checks
               (service_id, status_code, response_time_ms, is_healthy, error_message, checked_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (service_id, status_code, response_time_ms, int(is_healthy), error_message, _now()),
        )
        return cur.lastrowid  # type: ignore[return-value]


def get_recent_health_checks(service_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM health_checks
               WHERE service_id = ?
               ORDER BY checked_at DESC LIMIT ?""",
            (service_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Agent decisions
# ---------------------------------------------------------------------------

def record_decision(
    service_id: int,
    trigger: str,
    diagnosis: str | None,
    confidence: float | None,
    action_taken: str,
    reasoning: str | None = None,
    langfuse_trace_id: str | None = None,
) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_decisions
               (service_id, trigger, diagnosis, confidence, action_taken,
                reasoning, langfuse_trace_id, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (service_id, trigger, diagnosis, confidence, action_taken,
             reasoning, langfuse_trace_id, _now()),
        )
        return cur.lastrowid  # type: ignore[return-value]


def update_decision_outcome(
    decision_id: int,
    outcome: str,
    new_dseq: str | None = None,
    new_provider: str | None = None,
    downtime_seconds: float | None = None,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """UPDATE agent_decisions
               SET outcome = ?, new_dseq = ?, new_provider = ?, downtime_seconds = ?
               WHERE id = ?""",
            (outcome, new_dseq, new_provider, downtime_seconds, decision_id),
        )


def get_recent_decisions(limit: int = 20) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT d.*, s.name AS service_name
               FROM agent_decisions d
               LEFT JOIN services s ON s.id = d.service_id
               ORDER BY d.decided_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Initializing database...")
    init_db()

    sid = add_service("test-chatbot", "http://localhost:5000/health")
    print(f"Added service id={sid}")

    record_health_check(sid, 200, 42.5, True)
    record_health_check(sid, None, None, False, "Connection refused")
    checks = get_recent_health_checks(sid)
    print(f"Recorded {len(checks)} health checks")

    did = record_decision(sid, "consecutive_failures", "Provider unreachable", 0.92, "migrate", "High confidence failure")
    update_decision_outcome(did, "success", "dseq-123", "provider-abc", 45.2)
    print(f"Recorded decision id={did}")

    svc = get_service(sid)
    print(f"Service: {svc}")

    update_service_status(sid, "healthy")
    svc = get_service(sid)
    print(f"Updated status: {svc['status']}")

    all_svcs = get_all_services()
    print(f"Total services: {len(all_svcs)}")

    print("\nAll tables created and queries verified.")
