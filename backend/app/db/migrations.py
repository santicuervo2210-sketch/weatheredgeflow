from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.utils.time import utc_now


def run_migrations(engine: Engine) -> None:
    migrations_dir = Path(__file__).resolve().parent / "migrations"
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
        )
        applied = {
            row[0]
            for row in conn.execute(text("SELECT version FROM schema_migrations")).all()
        }
        for path in sorted(migrations_dir.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                conn.exec_driver_sql(statement)
            conn.execute(
                text("INSERT INTO schema_migrations(version, applied_at_utc) VALUES (:version, :applied)"),
                {"version": version, "applied": utc_now().isoformat()},
            )

