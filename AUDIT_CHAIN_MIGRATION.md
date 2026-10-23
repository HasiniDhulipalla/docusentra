# Audit-chain migration and key recovery

## Why startup can fail after an upgrade

TrustVault has used two relevant prior audit formats: an older unkeyed SHA-256 v1 format, and a transitional v2 HMAC format that could use `TOKEN_SECRET` as the audit key when `AUDIT_HMAC_SECRET` was still blank. The launcher can later create an independent audit key. In that case, a valid chain signed with the old token-key fallback fails the current-key check, and it is not a v1 SHA-256 chain either. The latest migration verifies both historical formats without rewriting anything unless the entire chain and stored head validate.

## Current migration behavior

At startup, the application:

1. Verifies the chain using the current independent `AUDIT_HMAC_SECRET`.
2. If that fails, verifies **every event and the chain head** with the exact legacy v1 SHA-256 formula. A valid v1 chain is migrated and an `AUDIT_CHAIN_MIGRATED_V1_TO_V2` evidence event is appended.
3. If v1 fails and `TOKEN_SECRET` differs from `AUDIT_HMAC_SECRET`, verifies every event and the head again using the same v2 HMAC payload with `TOKEN_SECRET`. This covers the transitional case where previous events used the token-key fallback before the launcher created an independent audit key.
4. Only if that complete token-keyed v2 chain validates, the application re-chains the same historical events under the current independent audit key in one transaction and appends `AUDIT_CHAIN_REKEYED_TO_INDEPENDENT_HMAC`, recording the prior head hash and event count.
5. Restores database immutability triggers and verifies the new chain again before serving.
6. If no full historical chain verifies, startup remains blocked by default. In local development only, the operator may use the explicit, backed-up `archive_unverified` recovery described in `AUDIT_RECOVERY_README.md`. The code never guesses, silently repairs mismatched data, or drops the database.

## Safe recovery on Windows / Docker Desktop

If both historical verifiers and the available key candidates fail, the exact old signing key is not recoverable from the hashes themselves. Prefer restoring the original `.env` key from a secure backup if you have one. If you do not, the local-development break-glass workflow preserves all old event rows in an append-only archive marked `PRESERVED_BUT_UNVERIFIED` and starts a new chain without deleting users/documents/permissions/files.

Run from the project root after updating the full project source:

```powershell
.\recover-audit-chain.ps1
```

The script requires typing `ARCHIVE`, takes a host-side `pg_dump` first, creates a durable `.env` key pair if needed without rotating the PostgreSQL password, executes the one-time recovery, clears the recovery flag, restarts normally, and runs `python -m app.verify_audit`. Do not manually delete rows or recalculate hashes. The SQL backup is sensitive; do not commit it to Git.

## If startup still refuses

If both the legacy-v1 and token-keyed-v2 verifiers fail, do not force migration. Possible causes include audit-row tampering, a different historical audit key, a changed `TOKEN_SECRET`, or a different earlier hash payload. Preserve the database backup. If a secure `.env` backup exists, restoring the exact key is preferred. If no key reproduces the full chain and head, investigate the audit history. For the local development database only, the explicit break-glass procedure can preserve old events as unverified evidence and start a fresh chain; it does not make the old events authenticated and it is disabled in production.

## Verification

The automated tests cover these cases in isolated temporary SQLite databases:

- A valid v1 chain migrates to current HMAC, preserving event actions/details and adding a migration evidence row; triggers are restored.
- A tampered v1 chain fails closed and its hash is not automatically rewritten.
- A valid v2 chain keyed with the prior `TOKEN_SECRET` fallback is re-keyed to the current independent audit key, preserving history and documenting the old head.
- A tampered token-keyed v2 chain fails closed and its hash is not automatically rewritten.

The authoring-environment test result for the updated recovery source revision is 26 passing tests. PostgreSQL/Docker startup must still be verified on the target machine.


## If no old key can validate the chain

Do not regenerate hashes in-place. For a local development database only, follow [`AUDIT_RECOVERY_README.md`](AUDIT_RECOVERY_README.md) and run `recover-audit-chain.ps1`. The script backs up the database first, keeps every old audit event and claimed hash in an immutable archive marked `PRESERVED_BUT_UNVERIFIED`, and anchors the snapshot digest in a new verified chain. The original history is not certified as authentic. This mode is disabled for `APP_ENV=production`.
