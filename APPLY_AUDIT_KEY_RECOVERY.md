# Apply the audit-key recovery patch (Windows / Docker Desktop)

This patch handles one specific safe migration: audit events previously signed with the transitional `TOKEN_SECRET` fallback, while the current `.env` now provides a separate `AUDIT_HMAC_SECRET`.

## Before changing anything

1. Do not run `docker compose down -v`.
2. Do not delete volumes, clear `audit_events`, manually edit hashes, or generate new secrets.
3. Back up PostgreSQL first while `trustvault-db` is healthy:

   ```powershell
   docker exec trustvault-db pg_dump -U trustvault -d trustvault -f /tmp/trustvault-before-key-recovery.sql
   docker cp trustvault-db:/tmp/trustvault-before-key-recovery.sql .\trustvault-before-key-recovery.sql
   ```

4. Keep the existing `.env` file unchanged. Do not share its secret values in chat.

## Apply files

Extract the ZIP and copy these paths into the existing project, replacing the matching files:

- `backend/app/main.py`
- `backend/tests/test_audit_chain_migration.py`
- `AUDIT_CHAIN_MIGRATION.md`
- `README.md`
- `PROMPTS.md`
- `VALIDATION_REPORT.md`

## Rebuild only the API

From the project root (the folder containing `docker-compose.yml`):

```powershell
docker compose build api
docker compose up -d api
docker compose logs --tail=100 api
docker compose ps
```

The patch first verifies every event and the stored head using the current audit key. If that fails, it tries the exact older SHA-256-v1 formula. If that also fails and `TOKEN_SECRET` differs from `AUDIT_HMAC_SECRET`, it tests the same v2 HMAC format against `TOKEN_SECRET`. It will re-key the chain only if every event and the chain head validate under that prior key. The original event actions/details remain, and a migration evidence event records the old head hash.

If logs still report `TOKEN_SECRET-keyed v2 verification also failed`, startup remains deliberately blocked. Preserve the backup and restore the exact historical key from a secure `.env` backup, or investigate audit integrity. Do not force startup by rewriting hashes.

## Local test

From `backend/`:

```powershell
py -m pytest -q
```

The updated authoring-environment suite reports 24 passing tests. The actual PostgreSQL volume on your machine still needs to be verified after applying the patch.
