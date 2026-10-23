# TrustVault threat model

Version: 1.2 challenge-alignment review  
Scope: React/Vite UI, FastAPI API, PostgreSQL metadata, private document volume, and LibreOffice preview conversion.

> This is our threat model, not a claim that the system is production-certified. It should be compared directly with the evaluator's threat list. Items labelled **Residual** are known limitations, not solved problems.

## Assets and security goals

| Asset | Goal |
|---|---|
| Original document bytes | Confidentiality, integrity, owner-controlled deletion |
| Share/role rows | Only owners grant/revoke; Reader cannot become Editor |
| User credentials and bearer tokens | Resist guessing, avoid plaintext storage, reject forged/expired tokens |
| Preview renderings | Only current authorized users can fetch them; remove them when the source is deleted |
| Audit events | Record successful and refused actions, verify append order/integrity, and retain stable actor/document snapshots |
| Database, storage, signing secret | Not publicly exposed; strong secrets in production |

## Actors and trust boundaries

- **System administrator:** can inspect user/role metadata, active grants and global activity; being an administrator does not implicitly grant document-content access.
- **System owner:** can upload and manage documents that they own.
- **System viewer:** cannot upload documents. Document-level grants remain distinct from system roles.
- **Document Reader:** can preview a currently shared document, but cannot download the original, rename, share, or delete it.
- **Document Editor:** can preview/download and rename a currently shared document; cannot change sharing or delete the owner's document.
- **Unauthenticated visitor:** may register/sign in and access health checks only; document APIs require a valid bearer token.
- **Potential attacker:** may manipulate document IDs, bypass buttons, forge requests, brute-force sign-in, upload renamed or malformed files, or repeatedly trigger expensive conversions.

The browser is untrusted. Authorization is enforced in FastAPI for each protected request; frontend button visibility is only presentation. Original bytes and converted previews are in a private storage volume, not a static web directory. In the local Compose setup, PostgreSQL and the API bind to loopback; the frontend is also loopback-bound for local development.

## Threats, controls and tests

| ID | Threat / attack path | Controls in the MVP | Evidence / test | Residual risk |
|---|---|---|---|---|
| TV-01 | Anonymous user calls document APIs directly | Bearer-token dependency; rejects missing/invalid/expired tokens | `test_share_download_revoke_security_flow`, token helper tests | No MFA or account recovery flow |
| TV-02 | User changes a document ID to read another user's document (IDOR) | Every document endpoint calls owner/share authorization | Private-by-default and post-revocation tests in API flow | In-flight responses already authorized before a revoke may finish streaming |
| TV-03 | Reader hides UI button but requests `/download` directly | Backend denies the original download for Reader with 403 | Reader download assertions for DOCX, PDF, and PNG | Users with Editor/Owner access can retain files they downloaded earlier |
| TV-04 | Reader attempts rename, grant/revoke, delete, or share-list access | Role and owner checks are in API handlers, not only UI | Reader/editor owner-only action assertions | Role model is deliberately small (owner/reader/editor), not enterprise policy ABAC; corrupt role values fail closed |
| TV-05 | Old shared link/token works after access is revoked | No permanent public share links; permission is looked up from the database on each request | Post-revocation download and preview-content assertions | Already downloaded copies/screenshots cannot be recalled |
| TV-06 | User uploads an executable or other bytes named `invoice.pdf` / `photo.png` | Extension allowlist plus signature checks; Office ZIP requires expected parts | Fake PDF/PNG and malformed Office ZIP helper tests | Signature checks do not replace full malware scanning or deep format validation |
| TV-07 | Office ZIP bomb, encrypted archive, or traversal-like archive entry | Upload limit, archive member count/expanded-size caps, traversal/encryption rejection; conversion timeout | Office archive helper tests; 15 MB upload limit; conversion timeout in code | Parser/converter vulnerabilities remain possible; use an isolated, patched converter and consider AV/sandboxing |
| TV-08 | Uploaded files leak via predictable/static paths | Random storage key; private volume; API-only access | Protected preview/download endpoints; Compose storage mount | A server/volume administrator can access stored files; backups must also be protected |
| TV-09 | Converted preview remains after owner deletes source | Delete handler removes source and cached Office PDF renderings | Delete-and-storage-cleanup assertion; cache cleanup code review | Backups/snapshots and filesystem-level remnants are outside application control |
| TV-10 | Brute-force login or mass account registration | 12-character minimum, trivial password rejection, login-attempt and registration throttles, PBKDF2-HMAC-SHA256 | Auth validation/rate-limit assertions | Current throttle is per-process memory; distributed production deployment needs shared rate limiting (e.g. Redis/WAF) |
| TV-11 | Forged/tampered bearer token or expired session | HMAC-SHA256 signature, fixed algorithm/type checks, expiry and positive subject validation | Round-trip, tampering, wrong-algorithm and expiry tests | Token is stored in browser localStorage; an XSS bug could expose it |
| TV-12 | Production accidentally ships a known signing secret or SQLite | Production startup rejects placeholder/short signing secrets, development DB password markers, SQLite, and wildcard origins; API docs disabled in production | Production config tests | Operators still must set `APP_ENV=production`, unique `TOKEN_SECRET`, strong database password and HTTPS |
| TV-13 | Clickjacking, content sniffing, referrer leakage, or script injection | CSP at Nginx, `nosniff`, `SAMEORIGIN`, no-referrer, permissions policy, React escaped text | Response header assertions and config review | CSP is defence-in-depth, not an XSS audit; inline styles are allowed for the current UI |
| TV-14 | Audit history misses or is silently modified after an incident | Events store actor/document snapshots and are HMAC-SHA-256 chained with a key stored outside the database; DB triggers reject normal UPDATE/DELETE; preview pages, downloads, changes, grants/revocations and denials are logged; admin can verify the chain | `test_challenge_requirements.py` verifies a tamper attempt is rejected and the chain verifies; page-access event assertion | A host/app-secret administrator who can obtain the HMAC key or reset the app and database together can rewrite local history. An independently permissioned immutable external sink/checkpoint is not implemented. |
| TV-15 | Large request or slow conversion consumes resources | 15 MB upload cap, Nginx 20 MB request cap, Office conversion timeout, bounded archive expansion | Upload/Office helper tests and code inspection | Per-IP throttling and CPU/memory limits must be stronger for public multi-tenant hosting |
| TV-16 | Reader reuses or extracts preview content | Active permission is checked on each page request; original PDF/text bytes are not returned by the paged preview endpoints; re-encoding strips image metadata; responses use no-store headers | API-flow checks page PNG output, raw-PDF rejection, no-store headers, page bounds, pixel-preserving image re-encoding, and revocation | Preview images are delivered unwatermarked by user request and can be saved from browser tools, captured with screenshots, OCRed, or recorded. This is a known residual risk. |
| TV-17 | Database or API is directly exposed on a developer machine | Compose binds database/API to `127.0.0.1`; frontend is also loopback by default | `docker-compose.yml` review | A public deployment needs a hardened reverse proxy/TLS configuration and must not expose database/API ports publicly |

## Additional findings we identified during implementation

1. **The observed Reader behaviour was a release blocker.** A real two-account test showed that a Reader could download and edit a local Word copy. We treated this as a server-side authorization failure, not a UI issue: the download route now denies Readers and rename/sharing/deletion checks are covered by tests.
2. **A converted Office PDF is sensitive data too.** It is cached under private storage to avoid repeated conversions; deletion now removes matching cached renderings as well as the original.
3. **Extension-only checks were inadequate.** Uploads now need matching signatures/Office archive structure and bounded expansion. This still does not amount to malware scanning.
4. **Development secrets can become production incidents.** Production startup now refuses recognized placeholders, and the Windows launcher rotates a weak `TOKEN_SECRET` without deleting database/file volumes. Database credentials still need explicit production rotation and the production setting must be enabled.
5. **Corrupted permission roles must fail closed.** Unexpected persisted share-role values are treated as unauthorized instead of falling through to Editor-like behaviour.
6. **A frame-denial header can break the intended inline PDF preview.** The API uses `SAMEORIGIN` so the app can embed authorized preview content while discouraging cross-origin framing.

## Explicit out-of-scope / known limitations

- This MVP is not certified for storing highly sensitive personal, financial, medical, or regulated records.
- No malware scanning, antivirus pipeline, MFA, breached-password service, account recovery, email verification, externally anchored immutable audit sink, automated backups, or Alembic migration history are implemented. The current startup applies a limited in-place migration for this MVP.
- Rate limits use process memory. They can be bypassed by restarting the process and are not shared across multiple API replicas.
- The frontend demo stores bearer tokens in localStorage. A production revision should use a reviewed secure session architecture, HttpOnly/Secure/SameSite cookies if appropriate, CSRF protections as needed, and a complete XSS review.
- Screenshots/copies cannot be blocked once content has been displayed to a Reader. Revocation blocks future authorized requests only.
- No application test suite can prove absence of vulnerabilities. Run a fresh independent security review against the deployed host.


## Preview capture / exfiltration boundary

- **Threat:** A Reader tries to save preview content through a built-in PDF viewer, context menu, copy shortcut, image URL, browser developer tools, screenshots, or OS screen recording.
- **Mitigations implemented:** PDF/Office previews are rasterized on the server; Reader clients receive unwatermarked PNG pages rather than a PDF viewer stream. Uploaded images are safely re-encoded without adding a visible overlay. Preview responses use `no-store`; the native PDF toolbar is absent; common copy/select/context-menu/print/save shortcuts are blocked in the preview UI. Page routes re-check current authorization for every request.
- **Residual risk:** No normal web page can reliably prevent operating-system screenshots, screen recording, browser extensions, or a second camera. Browser-delivered text may still be retrieved from developer tools/network responses. There is no visual watermark, so captured previews have no built-in on-screen attribution. For highly sensitive files use managed devices/VDI or a dedicated controlled viewer and policy.
- **Tests:** The API-flow test checks Reader download denial, unwatermarked PNG page response (not PDF bytes), no-store headers, page-range rejection, image re-encoding, and revoked access to a preview page. Manual browser checks are still required for UI affordances and OS capture limitations.


## Audit integrity: precise guarantee

The event rows form an ordered keyed HMAC-SHA-256 chain and carry immutable actor/document snapshots. `AUDIT_HMAC_SECRET` is separate from the database and, in production, separate from `TOKEN_SECRET`; database triggers prevent ordinary SQL UPDATE/DELETE. Startup refuses to serve if it detects a partial or invalid chain. A database-only actor who does not control the app secret cannot recompute valid event HMACs. This is stronger tamper evidence, but it is **not independent immutable storage**: a host/app-secret administrator could access the key, and a sufficiently privileged operator could disable triggers or reset history. Before production use, send signed checkpoints/events to a separately permissioned append-only service/object-lock store or SIEM and alert if chain verification fails. Keep `AUDIT_HMAC_SECRET` stable; unplanned rotation makes old events unverifiable. Do not describe the current database-only chain as impossible to alter.


### Audit key loss / incompatible historical hash format

- **Threat:** A rotated/lost HMAC key or incompatible hash payload can make old audit rows unverifiable. Silently recomputing hashes would falsely present old events as authenticated evidence.
- **Control:** Normal startup fails closed unless the complete chain validates. In local development only, the explicit `recover-audit-chain.ps1` procedure takes a PostgreSQL backup, copies every prior event plus original hashes/head into an immutable archive marked `PRESERVED_BUT_UNVERIFIED`, anchors a snapshot digest in a new verified HMAC event, and checks a normal restart with the recovery switch removed. Production mode rejects this switch.
- **Residual risk:** The archived historical rows are preserved but not authenticated. An external protected audit sink/checkpoint and original key backups remain necessary for high-assurance production.
