# TrustVault — Final Submission Pre-flight

**Review date:** 2026-10-22 (audit migration follow-up)  
**Reviewed artifact:** the exact `TrustVault-Distinct-Workspace-Views.zip` source snapshot, including separate Overview/My Documents/Shared with Me layouts and 3D shield styling.

## Checks completed

- [x] Extracted the latest ZIP into a clean temporary directory.
- [x] Ran backend test suite from the extracted package: **22 passed**.
- [x] Deliberately bypassed the central `resolve_role` grant check in a disposable copy; the authorization regression test failed as expected. The deliverable source was not modified by the test mutation.
- [x] Parsed `frontend/src/App.jsx` with TypeScript's JSX transpile parser: zero syntax diagnostics.
- [x] Checked CSS brace balance: 515 opening and 515 closing braces.
- [x] Parsed `docker-compose.yml` with PyYAML: `db`, `api`, and `frontend` services present.
- [x] Ran ZIP integrity check: no archive errors.
- [x] Checked tracked file names for `.env`, local database, private storage, and PEM/key files: no matching paths found.

## Latest audit-hash migration follow-up

- [x] Identified that old v1 SHA-256 audit hashes are incompatible with the current v2 HMAC payload unless explicitly migrated.
- [x] Added a fail-closed migration path: validates the entire old chain and head, transactionally re-chains a valid v1 history with v2 HMAC, appends a migration evidence event, restores append-only triggers, then verifies again.
- [x] Added isolated regression tests for valid migration and tampered-chain rejection. Latest suite: **22 passed**.
- [ ] The user must back up PostgreSQL and verify this exact API revision starts successfully in Docker. If legacy v1 verification also fails, restore the original `AUDIT_HMAC_SECRET` for an already-v2 database or investigate tampering. Do not delete volumes.

## Checks not completed (must not be represented as passed)

- [ ] Frontend dependency installation and Vite production build. `npm install --no-audit --no-fund` timed out after 120 seconds in the authoring environment.
- [ ] Docker build/start/health check against this exact final revision. Docker CLI is not installed in the authoring environment.
- [ ] Final browser regression on the exact updated revision and all three roles.
- [ ] Live public HTTPS deployment with unique credentials and post-deploy attack rehearsal.
- [ ] Public GitHub repository and publicly accessible URLs for commit evidence.
- [ ] Five-minute demo video recording.

## Important submission caveats

1. The local Git history starts with an imported ZIP baseline and current challenge-alignment work. The original ZIP snapshots did not include the old repository history, so this package cannot honestly reproduce a week-spanning commit history. Do not backdate commits.
2. `PROMPTS.md` records the actual issues noticed during the iterations, including the Reader download vulnerability and native PDF toolbar problem. After publishing, replace local commit hashes with real GitHub commit URLs; do not invent old hashes.
3. The audit HMAC chain and database triggers make ordinary edits detectable/prevented, but there is no independently permissioned external immutable audit sink. A sufficiently privileged host/application-secret administrator remains a known residual risk.
4. Browser preview controls are deterrents, not DRM. Screenshots, OS-level recordings, browser inspection, OCR, and external cameras cannot be reliably prevented by a normal web app.
5. This is a security-focused hackathon MVP, not a production-certified document vault. Use only non-sensitive demo documents until the outstanding release gates and an independent review are complete.

## Exact local checks to run before tomorrow's demo

From the extracted project root:

```powershell
docker compose config
docker compose build api frontend
docker compose up -d
docker compose ps
docker compose exec api python -m app.seed
```

Then open `http://127.0.0.1:8080` and demonstrate:

1. Admin login → global activity, active grants, and audit-chain verification.
2. Owner login → upload a clearly fake test document and grant Reader access to Viewer.
3. Viewer login → preview the file, try the original download endpoint directly, and show `403`.
4. Owner revokes the grant → Viewer retries a page endpoint and download; subsequent requests are denied.
5. Admin checks the denied attempts in global audit history.

Use the role credentials and reset behavior documented in `README.md`. If using a public deployment, replace every local demo credential with unique deployment-only credentials and do not expose `.env`.

- [x] Final seed-identity collision hardening added: seed provisioning refuses to promote/reset an account when only one configured identifier collides. Regression tests cover both partial-collision cases.

- [x] Re-ran the authorization-guard mutation against a disposable copy after the final test addition: the challenge authorization test failed as expected when `resolve_role` was deliberately bypassed; pristine suite passed 20 tests.


## One-time local audit recovery added after final preflight

For a development database whose old chain cannot be verified by available keys, the project includes `recover-audit-chain.ps1`. It backs up PostgreSQL, requires explicit `ARCHIVE` confirmation, stores the unchanged historic rows and their original hashes in an immutable archive marked `PRESERVED_BUT_UNVERIFIED`, anchors the archive digest in a new verified chain event, removes the one-time recovery flag, and proves ordinary API startup works. This is not an authenticity upgrade for old events, and the mode is disabled in production. Backend suite on this revision: 26 tests passing. Docker CLI/production frontend build were not available in the authoring environment.
