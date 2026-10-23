"""Export the SQLAlchemy model schema for review; does not connect to or mutate a DB."""
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.main import Base


def main() -> None:
    dialect = postgresql.dialect()
    output = [
        "-- TrustVault model schema snapshot generated from backend/app/main.py.",
        "-- Review/migration notes: DATABASE_SCHEMA.md. This is a schema snapshot, not a migration history.",
        "-- Audit triggers are appended below. Test changes against a fresh and an upgraded database.",
        "BEGIN;",
    ]
    for table in Base.metadata.sorted_tables:
        output.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";\n")
        for index in table.indexes:
            output.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";\n")
    output.extend([
        "CREATE OR REPLACE FUNCTION trustvault_block_audit_mutation() RETURNS trigger AS $$",
        "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql;",
        "DROP TRIGGER IF EXISTS trustvault_audit_immutable ON audit_events;",
        "CREATE TRIGGER trustvault_audit_immutable BEFORE UPDATE OR DELETE ON audit_events",
        "FOR EACH ROW EXECUTE FUNCTION trustvault_block_audit_mutation();",
        "COMMIT;",
        "",
    ])
    target = Path(__file__).resolve().parents[2] / "schema_postgresql.sql"
    target.write_text("\n".join(output), encoding="utf-8")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
