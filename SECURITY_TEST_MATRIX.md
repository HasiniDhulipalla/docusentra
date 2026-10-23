# Security test matrix and report

## Automated command

Run from the project root:

```powershell
cd backend
py -m pip install -r requirements.txt
py -m pytest -q
```

The current authoring-environment result after final seed-identity hardening is **22 passed**. The final Docker build should be rerun after applying this revision; the report below is not a substitute for the final local run.

## Coverage map

| Area | Test / assertion | Expected result |
|---|---|---|
| Authentication | Unauthenticated document list | 401 |
| Authentication | Valid token round trip | Subject ID returned |
| Authentication | Payload/signature tampering | 401 |
| Authentication | Wrong algorithm and expired token | 401 |
| Passwords | Weak registration password | Validation failure |
| Password storage | Valid hash and wrong-password comparison | Correct password verifies; wrong one fails |
| Login abuse | Consecutive wrong passwords over threshold | 401 until threshold; then 429 with Retry-After |
| Document privacy | Unshared user requests download | 403 |
| Role boundary | Reader rename/share-list/grant/delete | 403 |
| Reader preview | DOCX/PDF/PNG preview endpoints | Authenticated preview works for allowed fixtures |
| Reader download | Direct `/download` request as Reader | 403 |
| Editor boundary | Editor download/rename | Allowed |
| Editor boundary | Editor grants share or deletes document | 403 |
| Revocation | Reader requests preview/download after revoke | 403 |
| Upload validation | Executable bytes named `.pdf`, unknown `.exe`, malformed PNG | 415 |
| Office archive | Expected parts, traversal entries, mismatched document type | Valid structure accepted; unsafe/mismatched structure rejected |
| Audit | Grant/revoke/deny/preview/page-view/failed login events | Events visible to the appropriate user's activity endpoint; denied foreign-document metadata is redacted |
| Audit integrity | UPDATE/DELETE attempt against existing audit row; verify full hash chain | Database trigger rejects ordinary mutation; chain verifier reports valid |
| System roles | Admin-only endpoints, last-admin protection, owner demotion | 403 for non-admin; last admin cannot demote self; active owner cannot be demoted to viewer before transferring/deleting docs |
| Search | Filename, owner, category, date filters | Server-side filters apply only over documents owned/shared with caller |
| Deletion | Owner deletes test document | Source file removed and HTTP 204 returned |
| Production config | Placeholder key / SQLite database in production | Startup validation fails |
| Response headers | Preview endpoint | `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN` |

## Manual attack rehearsal (on your own local instance)

1. As Reader, hide/ignore the UI and call `GET /api/documents/{id}/download` with the Reader's bearer token. Expect `403`.
2. As Reader, attempt `PATCH /api/documents/{id}` with a new filename. Expect `403`.
3. As Reader, attempt `POST /api/documents/{id}/shares`. Expect `403`.
4. As a user with no share, try to fetch preview and download endpoints for a known document ID. Expect `403`.
5. Revoke access as owner, then retry preview and download with the previously valid user's token. Expect `403` on the next request.
6. Upload a text file named `.pdf` and a fake PNG. Expect 415 rather than acceptance.
7. Set `APP_ENV=production` while keeping the development signing secret; the API should refuse startup. Then set a unique secret, strong PostgreSQL password, explicit origins and HTTPS reverse proxy settings.

## Not tested / follow-up before final submission

- Live network scanning or a full OWASP ZAP/Burp test of the deployed host.
- Load/concurrency tests for simultaneous uploads, revocation and rate-limiting.
- Full format-fidelity testing for legacy DOC/XLS/PPT and all PDF conversion edge cases.
- Frontend production build in this authoring environment; npm dependency installation timed out. Verify locally with `docker compose build frontend`.
- Distributed throttling, malware scanning, database backup/restore, and externally anchored immutable audit export are not implemented. Full frontend production build and live deployment attack testing remain release gates.


| Raster preview without watermark | Reader opens PDF/Office/TXT/CSV preview; request a page endpoint | Authenticated request returns PNG without visible watermark, never raw PDF bytes or raw text blocks | Automated API flow; inspect the browser preview for absence of watermarking | OS screenshots/recording cannot be reliably disabled by a normal website |
| Copy / native toolbar deterrence | Attempt browser Save/Print toolbar, right-click, Ctrl/Cmd+C, Ctrl/Cmd+S/P, and text selection | No native PDF toolbar; common UI actions are blocked while preview modal is open | Manual browser test | Browser DevTools/extensions and external capture are out of scope for complete prevention |

## Final authorization-mutation sensitivity check (2026-10-22)

A one-off mutation check was run on a **disposable copy** of the latest ZIP, not on the deliverable source. The document-role guard inside `resolve_role` was deliberately replaced with an unconditional `return "editor"` to simulate removing the ownership/share authorization decision. Running `python -m pytest -q tests/test_challenge_requirements.py` then failed at the direct unauthorized-route assertions: multiple cases returned successful/other responses instead of the required `403`. This demonstrates that the current tests are sensitive to removal of that critical grant check. The mutant was confined to the disposable copy; the deliverable source remains unchanged. The pristine extracted ZIP was separately tested and reported 19 passing tests.

## Seeded-account collision regression (2026-10-22)

Seed provisioning now reuses an existing account only when both the configured username and email identify that same row. A username-only collision, email-only collision, or two identifiers resolving to different accounts fails closed instead of silently changing an unrelated account's password or system role. Unit tests cover the empty, valid idempotent, username-only, email-only, and conflicting-row cases. This was found during the final release review; it does not migrate or modify existing user rows by itself.

### Final authorization-mutation rerun after seed hardening

After adding the seed-identity collision regression (bringing the clean suite to 20 tests), the authorization mutation was repeated on a fresh disposable copy of the current source. Replacing the central `resolve_role` check with unconditional Editor access made `tests/test_challenge_requirements.py` fail (`At index 0 diff: 200 != 403`); result was 1 failed, 1 passed. The clean, unmodified source still passes all 20 tests. This manual mutation run is evidence of test sensitivity, not a claim that all authorization bugs are covered.

- Legacy audit version transition: valid v1 chain upgrades to HMAC v2 and emits a migration evidence event; tampered v1 chain fails closed and is not auto-repaired. See `backend/tests/test_audit_chain_migration.py`.


| Audit key loss | Current HMAC, legacy SHA-256 and prior-token-key checks all fail | Local-only explicit recovery after DB backup | Prior rows retained in immutable archive as UNVERIFIED; digest is anchored in a new HMAC chain and archive can be inspected by admin | `test_explicit_unverified_archive_recovery_preserves_old_rows_and_starts_valid_chain` |
| Archive mutation | Update/delete an archived audit snapshot | Archive table append-only triggers | SQL UPDATE/DELETE must fail | `test_explicit_unverified_archive_recovery_preserves_old_rows_and_starts_valid_chain` |
| Production recovery attempt | Set `TRUSTVAULT_AUDIT_RECOVERY=archive_unverified` with `APP_ENV=production` | Startup rejects archive recovery | Existing events/archive remain unchanged | `test_unverified_archive_recovery_is_disabled_in_production` |
| Partial chain | Mix hashed and blank event hashes then enable local break-glass recovery | Archive snapshot before starting new chain | Original values preserved, new chain validates | `test_explicit_recovery_archives_mixed_hashed_and_blank_events` |
