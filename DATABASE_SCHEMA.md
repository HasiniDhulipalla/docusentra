# Database schema and setup

## Source of truth

The application model definitions live in `backend/app/main.py` (`Base` SQLAlchemy declarative models). `schema_postgresql.sql` is a generated PostgreSQL DDL snapshot for review and clean-database setup. Generate it again after model changes with:

```powershell
cd backend
python -m app.export_schema
```

The app creates missing tables at startup and has a small in-place compatibility migration for older challenge databases. That migration is intentionally not a full migration framework. Before production use, replace startup `ALTER TABLE` logic with versioned Alembic migrations and rehearse upgrade/rollback on a database copy.

## Main tables

- `users`: unique username/email, password hash, system role (`admin`, `owner`, `viewer`), created timestamp.
- `documents`: owner, opaque random storage key, original filename, content type/size/category, timestamps and soft-delete timestamp.
- `document_shares`: one active per-document grant per named user, Reader/Editor role, grantor and timestamp.
- `audit_events`: actor ID plus actor snapshot, document ID/reference/name snapshot, action, target, details, event timestamp, previous hash and event hash.
- `audit_chain_heads`: singleton ordered chain head, last event ID/hash and update timestamp.

The audit event rows are protected from normal `UPDATE`/`DELETE` by database triggers. Each event HMAC-SHA-256 covers its canonical fields plus previous event hash. `/api/admin/audit/verify` recomputes the chain. This is tamper-evident against ordinary mutation and against a database-only actor without the HMAC key, but not independent immutable storage against a host/app-secret administrator who can obtain the key and rewrite the chain. Production should export signed checkpoints/events to an independently permissioned immutable service.

## Fresh local setup

From repository root, run the Windows launcher (or `docker compose up --build -d` after configuring `.env`). Then seed local demo accounts:

```powershell
docker compose exec api python -m app.seed
```

Local development-only credentials and the seeded sample file are listed in `README.md`. Never reuse these credentials in an Internet-accessible environment.


### `audit_event_archives`

Stores a deterministic JSON snapshot of prior audit events whose original chain could not be verified during an explicitly approved local recovery. It records the old claimed head, number/range of records, recovery reason, and SHA-256 digest of the snapshot. Update/delete triggers make archive rows append-only. Every archive is marked **preserved but unverified**; a new HMAC-chain event records its ID and snapshot digest. This is a recovery/evidence-preservation mechanism, not authentication of the legacy events.
