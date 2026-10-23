# TrustVault validation report

**Report date:** 2026-10-22  
**Scope:** Challenge-alignment source snapshot included in this repository.  
**Important:** Results below apply to this local source snapshot only. They do not certify a public deployment or prove that no vulnerabilities exist.

## Executed checks

| Check | Result | Notes |
|---|---|---|
| Backend tests | **27 passed** | Ran `cd backend && python -m pytest -q` in the authoring environment, including v1-to-v2 audit migration/refusal tests. Includes API authorization flows, role separation, category/date search, Reader download denial, revocation, upload validation and audit-chain integrity/tamper tests. |
| Docker Compose YAML parse | **Passed** | Parsed `docker-compose.yml` using PyYAML and confirmed `db`, `api`, and `frontend` service definitions. |
| Compose build/config via Docker CLI | **Not run** | Docker CLI/engine is not installed in the authoring environment. Must be run on the target Windows machine with Docker Desktop. |
| Frontend production build | **Not completed** | `npm install` timed out while attempting to retrieve dependencies; the environment had no `frontend/node_modules`. Do not treat the Vite production bundle as verified yet. |
| Public HTTPS deployment | **Not completed** | Requires a hosting account, configured secrets, domain/HTTPS endpoint, seed credentials and post-deploy smoke tests. |
| Five-minute demo video | **Not recorded** | `DEMO_SCRIPT.md` provides the script only. Record a real video after final deployment. |
| Public Git repository | **Not published** | A local `.git` history is included. It honestly starts from an imported ZIP snapshot and current challenge-alignment commits; it does not recreate an earlier week of history. |

## Reproduce locally

Backend tests:

```powershell
cd backend
py -m pip install -r requirements.txt
py -m pytest -q
```

Frontend production build, from project root:

```powershell
cd frontend
npm install
npm run build
```

Docker smoke test, from the project root:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
docker compose exec api python -m app.seed
```

Then verify the live browser workflow and direct HTTP/API checks described in `DEMO_SCRIPT.md`, `API_AUTHORIZATION.md`, and `SECURITY_TEST_MATRIX.md`. Preserve `.env` and named Docker volumes when updating an existing local installation; never run `docker compose down -v` unless deliberately deleting data.

## Security interpretation

- A passing test demonstrates only the specific assertion it makes; it is not a security certification.
- The audit HMAC chain and DB triggers make ordinary mutation detectable/prevented, but there is no independently permissioned external immutable audit sink/checkpoint yet.
- The public app must use strong independent `TOKEN_SECRET` and `AUDIT_HMAC_SECRET`, strong PostgreSQL credentials, HTTPS, explicit origins, and a restricted database/network configuration.
- Browser preview is not DRM. It cannot prevent all screenshots, screen recording, developer-tool extraction, OCR, or capture with another camera.

## Additional pre-flight checks (2026-10-22)

| Check | Result | Notes |
|---|---|---|
| Exact latest downloadable ZIP, backend suite | **19 passed** | Extracted `TrustVault-Distinct-Workspace-Views.zip` to a clean temporary folder and ran `python -m pytest -q` from its `backend` directory. |
| Authorization mutation sensitivity | **Expected failure observed** | In a disposable copy only, changed the central `resolve_role` grant check to unconditional Editor access. `tests/test_challenge_requirements.py` then failed because unauthorised direct route attempts no longer returned 403. Deliverable source was not mutated. |
| JSX syntax parse | **Passed** | TypeScript transpile parser returned zero diagnostics for `frontend/src/App.jsx`; this is a syntax check, not a Vite production build. |
| CSS delimiter smoke check | **Passed** | Latest `styles.css` has balanced opening/closing braces (515 each); this is not a full CSS lint/build. |
| Compose YAML parse | **Passed** | PyYAML parsed services `db`, `api`, and `frontend`. |
| ZIP integrity | **Passed** | `unzip -t` reported no archive errors. |
| Sensitive local artifacts tracked by Git | **No matches found** | `git ls-files` found no `.env`, local DB, private storage, PEM/key-named secret files. Review the exact files once more before publishing. |
| Frontend dependency install / Vite build | **Blocked / not verified** | `npm install --no-audit --no-fund` timed out after 120 seconds in this environment. No successful production bundle claim is made. |
| Docker Compose build and browser smoke test | **Not run here** | Docker CLI is not installed in the authoring environment; run on the target Windows machine. |

## Release gates before submission

- [ ] Rebuild the exact final source on the Windows machine using Docker Desktop.
- [ ] Run seed setup with deployment-unique credentials; never publish development demo passwords as production credentials.
- [ ] Verify the admin, owner, and viewer workflows in a clean browser session.
- [ ] Verify direct unauthorized API requests, Reader download denial, and access revocation after a grant is removed.
- [ ] Deploy to a public HTTPS URL and run the same security checks against that URL.
- [ ] Push the local Git repository to a public remote and replace local commit references in `PROMPTS.md` with real public commit URLs.
- [ ] Record and link the required five-minute demo video.

These release gates are deliberately unchecked until evidence exists. A passing local test suite does not prove the deployed system is secure or make the package submission-complete.

### Final review finding: seeded identity collision

The last pass found that seed provisioning could previously reuse an account if only its configured username or email collided, potentially resetting credentials or promoting an unrelated account. `_resolve_existing_seed_user` now requires both identifiers to resolve to the same existing account; partial or conflicting matches stop with an explicit error. New unit tests cover empty, matching, username-only, email-only and conflicting-row cases. The clean suite after this change is **20 passed**. The authorization-bypass mutation was repeated on a disposable copy of the current source and failed the route authorization assertions as expected.


## Audit hash-version compatibility correction (2026-10-22)

The final pre-flight error report showed `event_hash_mismatch at event 1`. Source history confirms that the prior revision hashed audit events with SHA-256 version 1 while the current revision uses HMAC-SHA-256 version 2. The startup migration now validates the complete legacy chain and head before re-chaining it, records a migration evidence event, restores immutability triggers, and remains fail-closed if the legacy chain does not validate. Two regression tests were added. Latest backend suite: **22 passed**. PostgreSQL/Docker startup on the user's machine still needs confirmation. See `AUDIT_CHAIN_MIGRATION.md`.


### Audit key fallback recovery follow-up (2026-10-22)

The user-reported logs showed both current HMAC-v2 and legacy unkeyed-v1 verification failing. The previous migration patch covered only v1. Source configuration showed a documented transitional behavior: when `AUDIT_HMAC_SECRET` was blank in development, the app used `TOKEN_SECRET`; the launcher can later populate a separate audit key. The migration now verifies the full current-v2 payload/chain using `TOKEN_SECRET` only as a candidate prior key and only re-keys if every event and the stored chain head validate. Any candidate failure remains fail-closed. Two new regression tests were added (valid prior-key chain migrates; tampered prior-key chain is not rewritten). Latest backend suite: **24 passed**. The exact user's `.env`, database, and Docker startup still need local verification; no secrets should be pasted into chat.


## Local unverifiable-chain recovery (2026-10-22)

The user-provided PostgreSQL dump showed a live chain through event 52. The app's current HMAC, legacy v1 SHA-256, and `TOKEN_SECRET`-keyed v2 checks all failed. The original `.env` was not included in the uploaded ZIP, so the historical signing key cannot be confirmed from the provided artifact. Instead of inventing hashes, this revision adds an explicitly confirmed local-only recovery: take a PostgreSQL backup, preserve all old audit rows and claimed hashes in an append-only `audit_event_archives` snapshot marked `PRESERVED_BUT_UNVERIFIED`, anchor the archive digest in a new verified HMAC event, and verify normal startup with the recovery flag removed. The application refuses this recovery mode when `APP_ENV=production`.

| Check on this source revision | Result |
|---|---|
| Backend tests | **27 passed** | Includes valid legacy migrations, fail-closed cases, explicit archival recovery, digest preservation, archive immutability, and production recovery refusal. |
| Python compile | **Passed** | `main.py`, `seed.py`, and `verify_audit.py`. |
| Docker Compose YAML | **Passed** | Parsed `db`, `api`, `frontend`, and the one-time recovery env flag. |
| Docker engine / PostgreSQL startup | **Not run here** | This environment has no Docker CLI; run `recover-audit-chain.ps1` on the target Windows installation. |
| PowerShell runtime parse/execution | **Not run here** | PowerShell is not installed in this authoring environment. Script is documented; execute it from the user's Windows PowerShell. |

This recovery restores application availability without deleting user/document data, but it **does not authenticate the archived old events**. Keep both the host-side SQL backup and the archive table; report the old history as unverifiable, not as a valid audit chain.
