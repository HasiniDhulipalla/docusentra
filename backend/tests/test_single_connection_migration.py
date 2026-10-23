from sqlalchemy import create_engine, inspect

import app.main as api


def test_legacy_schema_migration_uses_one_checked_out_connection(tmp_path, monkeypatch):
    # Simulate the Vercel/Neon setup where SQLAlchemy is deliberately limited
    # to a single connection per function instance.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'single-connection.sqlite3'}",
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE documents (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE audit_events (id INTEGER PRIMARY KEY)")
        monkeypatch.setattr(api, "engine", engine)

        api.apply_legacy_schema_migrations()

        inspector = inspect(engine)
        assert "system_role" in {c["name"] for c in inspector.get_columns("users")}
        assert {"category", "deleted_at"}.issubset({c["name"] for c in inspector.get_columns("documents")})
        assert {"event_hash", "previous_hash", "actor_username_snapshot"}.issubset(
            {c["name"] for c in inspector.get_columns("audit_events")}
        )
    finally:
        engine.dispose()
