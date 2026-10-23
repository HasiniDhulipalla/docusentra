# Deployment and operations guide

## Local Windows run

1. Install Docker Desktop and wait until the engine is running.
2. Open this folder in VS Code (the folder containing `docker-compose.yml`).
3. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start-trustvault.ps1
   ```

4. Confirm `docker compose ps` shows `trustvault-db` and `trustvault-api` healthy and the frontend running.
5. Open `http://localhost:8080`; local development API docs are at `http://localhost:8000/docs` and health is at `http://localhost:8000/api/health`.
6. Run tests from `backend` with `py -m pytest -q`.

The launcher creates `.env` from `.env.example` if required, replaces a weak/placeholder `TOKEN_SECRET` with a random secret, and generates an independent `AUDIT_HMAC_SECRET` when absent. It never rotates a strong existing audit key automatically; changing the audit key without a key-transition plan makes old audit hashes unverifiable. Token-secret rotation invalidates active sessions, so users should sign in again. It does **not** delete or recreate PostgreSQL/file volumes and intentionally does not silently change an existing PostgreSQL database password.

To stop without deleting data:

```powershell
docker compose down
```

**Never run `docker compose down -v` unless you deliberately want to permanently delete the database and private-file volumes.**

## Production deployment checklist

Do not expose the sample configuration directly to the Internet. Before deployment:

- Set `APP_ENV=production`.
- Set a unique `TOKEN_SECRET` at least 32 characters long and a separate stable `AUDIT_HMAC_SECRET` at least 32 characters long; use a secret manager or protected environment file, not source control. Keep the audit key stable: unplanned rotation makes the existing chain unverifiable.
- Set a unique `POSTGRES_PASSWORD`. In Compose, use URL-safe random characters (`A-Z`, `a-z`, `0-9`, `_`, `-`) so the database URL does not require ad-hoc encoding.
- Start against a fresh production database volume or deliberately rotate the database user's password in PostgreSQL. Editing `.env` alone does not change the password of an already-initialized database volume.
- Put a maintained HTTPS reverse proxy in front of port 8080, enable HSTS at the TLS edge, and keep ports 5433 and 8000 private. The sample Compose file loopback-binds PostgreSQL, API, and frontend for local development.
- Restrict inbound network rules. Do not publish port 5432/5433 or API port 8000 publicly.
- Keep `FRONTEND_ORIGINS` explicit; never use `*` for production.
- Store `.env` outside source control; review `.gitignore`; rotate any secret previously committed or shared.
- Configure encrypted backups and rehearse restore; keep backups and preview caches as confidential as the original uploads.
- Use a managed, shared rate-limiter for multiple API replicas; current rate limiting is process-local memory.
- Add versioned database migrations (e.g. Alembic), monitoring/alerts, resource limits, and an independently permissioned external immutable audit sink/checkpoint before production use.
- Pin reviewed dependency versions and scan dependencies/images. Keep the base images, FastAPI, Nginx, PostgreSQL and LibreOffice patched.
- Consider antivirus/sandbox scanning of uploads and a stricter isolated converter process for untrusted Office files.
- Complete an independent review of localStorage token handling, XSS, access-control boundaries, file parsing and audit-log integrity.

## Operations and diagnosis

```powershell
docker compose ps
docker compose logs --tail=150 api
docker compose logs --tail=150 frontend
docker compose logs --tail=150 db
```

Check health:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

Expected response is JSON with `status: ok` and `database: connected`. If the database is disconnected, health now returns HTTP 503 instead of reporting success.

## Storage and deletion semantics

Original documents are stored in a private Docker volume, not in frontend static assets. Office preview PDFs are created in a private cache and are removed by the document-delete handler. Revocation prevents later API requests; it cannot erase files that a user previously downloaded or screenshots of displayed content. Backups and storage snapshots need their own retention controls.
