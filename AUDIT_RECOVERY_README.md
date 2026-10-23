# TrustVault: one-time recovery for an unverifiable local audit chain

## Why the API is failing

The current database contains an audit chain that the configured HMAC key and the supported legacy hash verifier cannot validate. The application correctly refuses to start rather than silently rewriting signed records. This can occur if the original audit key was changed/lost or if records were created by an incompatible earlier hash format. The error alone does **not** prove malicious tampering.

## What the recovery does

`recover-audit-chain.ps1` is a **development-only break-glass** process. It asks for explicit confirmation and first creates a `pg_dump` backup on your host. It then:

1. Preserves every prior audit row, its original hash, the claimed chain head, and a reason in `audit_event_archives.snapshot_json`.
2. Labels the archived chain `PRESERVED_BUT_UNVERIFIED`. We do not claim that old events are cryptographically authenticated.
3. Computes SHA-256 over the deterministic archive snapshot and writes an `AUDIT_HISTORY_ARCHIVED_UNVERIFIED` event into a new HMAC chain that references that digest.
4. Makes the archive append-only and checks both the new chain and archive digest.
5. Removes the one-time recovery flag and restarts the API normally. The script fails if the ordinary restart does not pass health checks.

Existing users, documents, permissions, and private file storage are not deleted. Only the live `audit_events` rows are moved into the immutable archive table; those rows remain preserved verbatim in the archive JSON and in the pre-recovery SQL backup.

## When not to use it

Do not run it against production. Do not use it if you have a secure backup of the exact original key available; restoring the correct old key is preferable because it may recover full authenticity of the original chain. Always keep the generated SQL backup. Do not delete Docker volumes.

## Run on Windows

From the extracted project root, with Docker Desktop running and `trustvault-db` healthy:

```powershell
.\recover-audit-chain.ps1
```

Read the prompt and type `ARCHIVE` only if you accept that the old event history must be retained as unverified evidence. The script saves a timestamped `.sql` backup in the project directory. Keep that backup private and do not commit it to Git.

After successful recovery:

```powershell
docker compose ps
docker compose logs --tail=60 api
docker compose exec -T api python -m app.verify_audit
```

The chain verifier should report `valid: true`. The administrator can inspect preserved archive metadata at `GET /api/admin/audit/archives`; the endpoint reports the archive digest check but intentionally labels the original chain unverified.

## Production policy

`APP_ENV=production` rejects this recovery mode. Production must restore the authentic prior key or use a formally reviewed incident-recovery procedure with an external protected checkpoint. Never make an unauthenticated historical chain look valid by simply recalculating its hashes.
