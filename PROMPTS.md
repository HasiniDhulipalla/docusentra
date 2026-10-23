# AI-use log — TrustVault Snovasys challenge

This is a retrospective log based on the dated conversation and actual review iterations. Summaries are labelled as summaries, not fake verbatim prompts. The previous iterations were exchanged as ZIP files with no `.git` directory; original commit hashes for those old fixes do not exist in the supplied source. We do **not** invent old commits or dates. Current challenge-alignment changes are committed in the repository history created with this bundle; replace local commit references with public GitHub URLs only after publishing the repo.

## 2026-10-21 — Understand the project before implementation

- **Prompt / direction:** The user asked to explain the TrustVault project clearly before starting implementation.
- **What AI produced:** A concept walkthrough for secure uploads, named sharing, access checks and audit history; then a React/FastAPI/PostgreSQL starter plan.
- **Specific error / omission:** The initial explanation did not yet implement or validate the official system-administrator role, category/date search, hash-chained audit integrity, admin activity view, or final submission deliverables. An architectural explanation was not evidence that those features existed.
- **Correction / verification:** The official ten-item requirements were later supplied by the user and mapped explicitly in `FUNCTIONAL_REQUIREMENTS.md` and `API_AUTHORIZATION.md`; current implementation added system roles, admin endpoints, SQL-side filters and audit-chain verification. Tests run with the current source are recorded in `SECURITY_TEST_MATRIX.md`.
- **Commit evidence:** Those features are in implementation commit `51686a9`; audit signing/production-key hardening was added in `44671f8`. Earlier ZIP-only work has no reconstructable source commit. Do not describe this as week-spanning history.

## 2026-10-21 — Debug local Docker setup

- **Prompt / direction:** The user ran the launcher and shared screenshots of Docker Engine failure and then host port 5432 binding failure.
- **What AI produced:** Docker Desktop startup instructions and a change from host port 5432 to 5433 while keeping PostgreSQL's container port at 5432.
- **Specific error / omission:** The first failure was an environment issue, not a code defect; after Docker started, the next port conflict needed a second diagnosis. A successful `docker compose ps` only proved local containers started, not secure app behavior.
- **Correction / verification:** The user changed the port and shared a screenshot showing the database/API healthy and frontend started. `docker-compose.yml` now documents local loopback bindings. The final challenge package still needs a fresh rebuild on the user's machine.
- **Commit evidence:** The base ZIP contained no Git history. See the import-baseline note above; do not fabricate a prior commit link.

## 2026-10-21 — Catch the Reader authorization flaw (**authorization**)

- **Prompt / direction:** The user reported that User B had Reader permission but could download a Word document, edit it locally and save it.
- **What AI produced:** A revised implementation of server-side Reader download denial and owner/editor boundaries, with a Reader preview path.
- **Specific error caught:** The behaviour in the running version showed the original download operation was not effectively restricted. Hiding a UI button cannot protect an API endpoint, and a saved local copy cannot be controlled by the website.
- **Correction / verification:** Reader downloads now return 403 at the API; Reader rename/share/delete operations are denied; protected routes re-check active permissions. API tests call the routes directly, then test revocation. Current source also logs successfully served preview pages separately. See `backend/tests/test_api_flow.py` and `backend/tests/test_challenge_requirements.py`.
- **Commit evidence:** The initial Reader fix was in a ZIP-only source snapshot without `.git`, so there is no honest original commit hash. Current regression tests and per-route documentation are in `51686a9` and `be2ac8e`.

## 2026-10-22 — Correct the PDF preview toolbar and capture claim (**authorization / data protection**)

- **Prompt / direction:** The user shared a screenshot where the native PDF viewer still exposed a Save control, then asked about text copy and screen recording prevention.
- **What AI first produced:** A CSP `blob:` adjustment for a blank PDF viewer, which fixed rendering but did not remove the browser PDF toolbar.
- **Specific error caught:** A successful render was mistaken for the complete preview-security requirement. A normal browser app also cannot reliably block OS screenshots or screen recording.
- **Correction / verification:** The current approach rasterizes PDF/Office/text page previews and sends PNG page responses instead of a native PDF stream; each page request checks current authorization and successful page reads are audited. Common copy/select/context-menu/save/print shortcuts are best-effort UI deterrents only. The code and tests do not claim screenshot prevention.
- **Commit evidence:** The old toolbar fix existed in a prior ZIP without Git history. The current per-page audit addition is in `51686a9`.

## 2026-10-22 — Remove visible watermarks at the user's request

- **Prompt / direction:** The user said the repeated watermark was too prominent and asked to remove it.
- **What AI produced:** A no-watermark preview revision.
- **Specific trade-off:** Removing the watermark means captured screenshots no longer have visual attribution. Watermarks were a deterrent, not a security boundary; they cannot replace server authorization.
- **Correction / verification:** Current preview code has no visible watermark. Server-side access controls, original Reader-download denial, per-page permission checks and `no-store` headers remain. We documented the trade-off in `THREATS.md` and `PROJECT_WRITEUP.md`.
- **Commit evidence:** The previous no-watermark revision arrived as a ZIP with no `.git` history, so its original commit cannot honestly be linked. Do not claim attribution survives watermark removal.

## 2026-10-22 — Reconcile to the official 10 requirements (**audit and authorization**)

- **Prompt / direction:** The user supplied the full Snovasys brief and asked whether the existing implementation actually met it, then requested the code be changed to fit the requirements.
- **What AI initially got wrong:** A prior “score-ready” package and scorecard overstated readiness: a separate admin role/view was missing, audit rows could be changed without detection, category/date search and per-endpoint role documentation were incomplete, and the scorecard incorrectly said the exact official list was unavailable even though the user supplied it.
- **Correction:** Added `User.system_role`; admin-only overview/users/role management/permission/audit routes; a keyed HMAC-SHA-256 audit chain using a separate stable key and database triggers against ordinary UPDATE/DELETE; owner/category/date server filters; owner demotion guard; page-view audit events; schema export/docs and an exact official requirement matrix.
- **Verification at this checkpoint:** `python -m pytest -q` reported 18 passing backend tests; the subsequent audit-key test/config correction below increased the suite to 19. The exact test output was produced in the authoring environment; latest Docker/frontend production build and live deployment still need verification. The keyed chain protects against a database-only actor without the separate HMAC secret, but does not defeat a host/app-secret administrator who can obtain that key; an externally protected immutable audit sink is explicitly listed as residual risk.
- **Commit evidence:** `51686a9` — `feat: align TrustVault roles, audit integrity, search, and admin APIs`. After the repository is pushed, publish the full commit URL. This is the real current implementation commit, not a reconstructed historic commit.

## 2026-10-22 — Strengthen audit integrity and catch a test/config mismatch (**audit**)

- **Prompt / direction:** While reviewing what stops audit history from being quietly changed, make the hash chain harder for a database-only actor to recompute and retain a reliable test result.
- **What AI produced:** A keyed HMAC-SHA-256 chain using an independent `AUDIT_HMAC_SECRET`, database immutability triggers, and production config validation that requires a separate stable key. The Windows launcher now persists a generated local audit key in `.env`.
- **Specific error caught by test execution:** The first change added a new production prerequisite but did not update the existing production-configuration test fixtures. The suite failed with 2 tests, showing that the “known-good production configuration” test was no longer providing all required keys and the localhost-origin test was failing at the earlier validation check instead.
- **Correction:** Updated the fixtures to supply a distinct audit key, added a test asserting that production refuses to start without it, then reran the suite: **19 passed**. Seed initialization and `verify_audit.py` were also exercised against an isolated temporary SQLite database; the sample roles were created and 5 audit events verified. A test also disables the SQLite UPDATE trigger temporarily, tampers with a row, confirms HMAC verification fails, restores the row, and reinstalls the trigger.
- **Commit evidence:** `44671f8` (`security: HMAC-sign audit events and require independent production key`).

## 2026-10-22 — Reconcile final validation report and test count (engineering quality)

- **Prompt / direction:** Compare the completed repository against the organizer's ten requirements and provide an honest delivery package with test evidence and remaining deployment work.
- **What AI produced:** The challenge-aligned repository, 19 passing backend tests, and requirement/security/API/deployment documentation.
- **Specific error caught:** During final review, `README.md` still said 18 backend tests even though the latest pytest run reported 19. It would have made the repository's evidence inconsistent. A final frontend production build was also not verifiable because dependency installation timed out; Docker could not be invoked in this authoring environment because the CLI is absent.
- **Correction / verification:** Changed the current README count to 19, added `VALIDATION_REPORT.md` distinguishing executed checks from unverified Docker/frontend/deployment checks, and syntax-parsed `App.jsx`, `main.jsx`, and `vite.config.js` with the globally installed TypeScript parser. Backend rerun: `python -m pytest -q` → 19 passed. Docker and live hosting are explicitly not claimed as verified.
- **Commit evidence:** `f31b435` — `docs: record final validation status and test count`.

## 2026-10-22 — Add restrained 3D shield and page-motion polish (UI only)

- **Prompt / direction:** The user asked for TrustVault-themed 3D effects: an animated shield, category-change/button animations, and page transitions.
- **What AI produced:** A layered 3D-style ShieldCheck brand mark, a bevelled floating shield with animated perspective/orbit rings in the protection card, subtle 3D button/nav/card interactions, category selection pulses, and staggered workspace page entry effects. The CSS honours `prefers-reduced-motion` and adds no runtime dependency.
- **Specific issue checked:** CSS entrance animations do not replay when React reuses the same subtree between workspace views. The first CSS-only approach would have animated only initial mount; the view container now uses `key={activeNav}` to remount its visual content on navigation. This means view-local child components reinitialise on navigation, while application-level state stays in `App`.
- **Correction / verification:** The icon changed from a generic lock to the existing `ShieldCheck` glyph, and the 3D depth is composed with CSS layers and transforms, without touching API/authentication/permission logic. `App.jsx` parsed with the installed TypeScript JSX parser; `styles.css` parsed with PostCSS; backend regression tests were rerun from `backend/`: **19 passed**. A full Vite production build and live browser visual check were not run because frontend dependencies are not installed in this authoring environment.
- **Commit evidence:** `3239487f940d8a4a4aa2a92857587bcdb89b2b24` — `feat(ui): add 3D TrustVault shield and motion effects`.

## Shared instructions/context reused

- The official challenge brief pasted by the user (ten requirements, security standards, rubric, submission artifacts).
- Existing project `README.md`, `docker-compose.yml`, FastAPI model/routes, frontend files, tests, and `.env.example`.
- A repeated instruction to preserve current working behavior while adding narrowly scoped changes; security claims need test evidence.

## Current evidence state after audit migration fix (2026-10-22)

- Backend test suite: **22 passed** in this authoring environment, including valid v1-to-v2 migration and tampered-legacy fail-closed cases.
- JSX/JavaScript syntax parse: passed with TypeScript's transpile parser. A full Vite production build was not independently completed because npm dependency installation timed out in this environment.
- The user has now shared actual Docker logs where the API fails with `event_hash_mismatch at event 1`. This fix addresses the identified v1-to-v2 hash-format transition, but the exact patched API image must still be rebuilt and smoke-tested on the user's machine.
- A public GitHub repo, historic week-spanning commit history for prior ZIP-only work, live HTTPS URL and actual five-minute demo video are still not present in this archive. These must be created honestly; no URL or historical commit is fabricated here.


## Commit and publication note

- Baseline import: `84f4364` (a ZIP snapshot; prior source history unavailable).
- Feature implementation: `51686a9` (`feat: align TrustVault roles, audit integrity, search, and admin APIs`).
- Requirement/docs/test matrix: `be2ac8e` (`docs: map official requirements and document security evidence`).
- HMAC audit-key hardening: `44671f8` (`security: HMAC-sign audit events and require independent production key`).
- Final audit-tamper regression and environment/setup notes: `a3e872d` (`test: verify HMAC chain detects tampering beyond DB trigger`).
- The original pre-challenge source was supplied as ZIP files without `.git`, so the prior UI, Reader download, and watermark-removal fixes have no recoverable original commit links. This is an actual evidence gap. The local Git history created for this updated bundle contains real import/feature/docs/security commits but they are not a public, week-spanning history like the organizer requests. After creating the public repository, replace commit hashes in this document with full clickable URLs and keep making real commits as work continues; do not backdate commits.

## 2026-10-22 — Separate Overview dashboard from My documents management view (UI behavior)

- **Prompt / direction:** The user shared screenshots showing the Overview page and My documents page had nearly identical stat cards, document table, and activity sidebar. They asked why the pages looked the same.
- **What AI found:** The app used a single generic rendering branch for Overview, My documents, and Shared with me. Only the page heading and the document filtering changed, so the dashboard layout was reused on the management route.
- **Specific defect:** My documents was still showing Overview's summary cards and activity/protection sidebar; Overview was showing the full filter form and complete document table, making the two page purposes unclear.
- **Correction:** Overview now shows the four summary cards, the latest five documents, and the security-activity/protection sidebar without the owner/category/date filter form. My documents now uses a full-width document-management table with filters and actions, and no duplicate dashboard summary/side panel. Shared with me uses the full-width list of only documents granted to the current account. Added `UI_PAGE_SEPARATION.md`. No backend permission or API behavior was changed.
- **Verification:** TypeScript's installed JSX parser passed for `App.jsx`; from `backend/`, `python -m pytest -q` reported **19 passed**. A full Vite production build and final browser screenshot were not available in this authoring environment, so the user should rebuild the frontend and visually verify the navigation views locally.
- **Commit evidence:** Local commit `642d040e532f244ad32a1fbe7ede9f37ceb3ec98` (`fix(ui): separate overview dashboard from document library`). This is a real local commit; it becomes a clickable public URL only after the repository is published.

## 2026-10-22 — Final pre-submission audit and authorization mutation check (**authorization / release engineering**)

- **Prompt / direction:** The user asked for one final requirements check before showing/submitting TrustVault to the client the following day.
- **What AI produced:** Re-extracted the latest workspace-views ZIP, reran the backend test suite, parsed the JSX and Compose YAML, checked ZIP integrity and Git-tracked file names, and tested whether the suite catches removal of the central authorization guard.
- **Specific issue caught / limitation:** The local test suite passing does not establish production readiness. The frontend production build timed out during dependency installation; Docker is unavailable in the authoring environment, so the final Docker/browser run is still unverified. Public HTTPS deployment and the five-minute video are also outstanding.
- **Correction / verification:** In a disposable copy only, `resolve_role` was mutated to unconditionally return Editor. `tests/test_challenge_requirements.py` failed on direct unauthorized-route expectations (expected 403, observed successful/other responses). The deliverable copy was not mutated; the pristine latest ZIP independently returned 19 passing tests. A release checklist was added in `FINAL_SUBMISSION_PREFLIGHT.md`; detailed evidence is in `SECURITY_TEST_MATRIX.md` and `VALIDATION_REPORT.md`.
- **Commit evidence:** `ddc9b5e` — `docs: record final pre-submission verification and mutation check`. Once published, replace this local hash with the actual public GitHub commit URL. This entry is an honest same-day final review and does not claim reconstructed earlier history.

## 2026-10-22 — Catch a seed-account identity collision before client handoff (**authorization / account provisioning**)

- **Prompt / direction:** The user asked for a final requirement and release check before presenting TrustVault to the client the next day.
- **What AI produced initially:** A seed script that found an existing account by username *or* email and then reused it when either match existed.
- **Specific defect caught during review:** A configured seed administrator email could collide with an unrelated pre-existing account even if the configured username did not match. The previous logic could silently reset that account's password and change its system role, potentially promoting an unrelated account to administrator.
- **Correction / verification:** Added `_resolve_existing_seed_user`, which only reuses an account when both username and email resolve to the same existing row; one-sided or conflicting matches now fail closed. Added regression tests for empty, matching, username-only, email-only, and two-row collisions. Clean backend suite: **20 passed**. Re-ran the disposable authorization mutation; bypassing `resolve_role` made the direct-route challenge test fail as expected. The mutation remained outside the deliverable source.
- **Commit evidence:** `394b913` — `security: reject partial seed identity collisions`; supporting evidence is in `SECURITY_TEST_MATRIX.md` and `VALIDATION_REPORT.md`. Replace the local hash with the real public commit URL after pushing; this is a same-day correction, not fabricated historic work.

## 2026-10-22 — Fix API startup after an audit-hash version upgrade (**audit migration**)

- **Prompt / direction:** The user pasted Docker logs showing the API repeatedly failed startup with `Audit chain verification failed: event_hash_mismatch at event 1`, while PostgreSQL was healthy. They also pasted a PowerShell `docker inspect --format` command that failed because nested quotes were parsed as a template function.
- **What AI first found wrong in the project's code:** The earlier v1 code used plain SHA-256 over a version-1 payload; the current v2 code uses HMAC-SHA-256 over a different payload. Startup only auto-chained records with blank hashes, so it incorrectly treated a potentially intact legacy v1 database as an unexplained integrity failure.
- **Correction:** Added an exact legacy-v1 verifier that checks every event link, each original event hash, and the old chain head before it changes anything. Only a fully valid v1 chain is upgraded transactionally to the current HMAC v2 format; the original actions/details are preserved, immutable database triggers are restored, and an `AUDIT_CHAIN_MIGRATED_V1_TO_V2` event records the old head hash. If legacy verification also fails, it remains fail-closed and tells the operator not to delete the volume or rotate the key.
- **Tests:** Added isolated temporary-SQLite regression tests for successful migration and refusal to repair a tampered legacy chain. `cd backend; python -m pytest -q` → **22 passed**. This validates the migration logic in SQLite. The user's actual PostgreSQL container startup and `.env` key cannot be inspected from here and still must be verified on their machine.
- **Commit evidence:** `77a34b2` — `fix(audit): migrate verified legacy hashes to HMAC chain`. After publishing, replace this short local hash with its actual public GitHub commit URL. This is today's real fix; it is not backdated.


## 2026-10-22 — Catch the previous TOKEN_SECRET audit-key fallback transition (audit key recovery)

- **Prompt / direction:** The user reran the API after the v1 migration patch; startup still failed with `event_hash_mismatch at event 1` and `legacy_event_hash_mismatch`. Diagnose using the exact error rather than weakening fail-closed startup.
- **What AI found:** The previous v1 verifier only covers old unkeyed SHA-256 records. A separate plausible history is a valid HMAC-v2 chain created while the app fell back to `TOKEN_SECRET` because `AUDIT_HMAC_SECRET` was blank; the later launcher can then generate an independent audit key, making the same intact v2 records fail the current verifier. This is consistent with the log, but cannot be proven without verifying the local key/chain.
- **Specific defect in the previous fix:** It handled the v1 SHA-256 transition but did not try the documented earlier v2 `TOKEN_SECRET` fallback case, so this legitimate key transition could still block startup. It correctly refused to rewrite the chain when neither known format verified.
- **Correction:** Added a fail-closed verifier for the exact existing v2 payload keyed with `TOKEN_SECRET`. Only a full chain and stored head that validate under that old key are transactionally re-keyed under the current independent `AUDIT_HMAC_SECRET`; an evidence event stores the old head and count. The source still refuses startup if both historical formats/keys fail. Added valid-chain and tampered-chain regression tests.
- **Verification:** `python -m pytest -q` from `backend/` reports **24 passed**. The user's PostgreSQL database and Docker startup remain unverified until the patch is rebuilt locally.
- **Commit evidence:** This patch is prepared in the current working source; publish it as a real commit and replace this note with its actual commit URL after pushing. No historical commit is fabricated.


## 2026-10-22 — Stop repeated audit-key patching and preserve unverifiable history (**audit integrity / recovery**)

- **Prompt / direction:** The user uploaded the current project ZIP after repeated startup failures and asked for one complete project that works without errors. The exact logs showed current HMAC, legacy SHA-256, and prior `TOKEN_SECRET` candidate verification all failing at audit event 1.
- **What the previous fix got wrong:** It added another candidate-key path but still stopped at the same failure. The uploaded ZIP did not include the real `.env`, so the historical signing key could not be established from the supplied files; the SQL backup contained 52 events but not the secret. Claiming that another key guess would recover authentic history would be unsupported.
- **Correction:** Added an explicit, development-only break-glass workflow which first requires a PostgreSQL backup and operator confirmation. It stores all prior audit rows and claimed hashes in an immutable snapshot labelled `PRESERVED_BUT_UNVERIFIED`, hashes the snapshot and anchors its digest in a new verified chain event, restarts the API with recovery disabled, and exposes archive metadata/details to administrators. User accounts, documents, shares and source file storage remain intact. Production refuses this recovery flag.
- **Verification:** Latest `cd backend; python -m pytest -q` → **27 passed**, including successful archival recovery, snapshot digest verification, append-only archive checks, mixed/blank hash handling, and production refusal. Compose YAML parse and Python compilation passed. Docker Engine and Windows PowerShell were not available in the authoring environment, so the recovery script must be run on the target Windows machine and the result reported accurately.
- **Commit evidence:** No new commit hash or public URL is claimed for this ZIP-only fix. After importing this exact source into the real Git working tree, create a real commit and replace this note with its actual commit URL; do not backdate or invent history.


## 2026-10-23 — Collapse sidebar categories and complete dark filter surfaces (UI/theme)

- **Prompt / direction:** The user shared a screenshot and requested a single “Document Categories” sidebar item that expands to HR, Finance, Legal, Personal, Education, General, and Others, each with a document count. They also pointed out that the document filter area remained white in dark mode.
- **What was changed:** Added an accessible collapsible category navigation group; category counts are computed from documents returned for the signed-in user, and selecting a category keeps the existing category filter behavior. Added dark-theme backgrounds and readable colors for the filter form, filter hint, date/select controls, browser-autofill fields, and administrative filter surfaces.
- **Specific issue caught during validation:** The first JSX syntax check found a missing closing bracket in the theme state declaration introduced during the edit. That syntax issue was corrected before packaging.
- **Verification:** Backend tests: `python -m pytest -q` → **27 passed**. TypeScript JSX parser → **0 diagnostics**. CSS parser → **0 top-level parse errors**. `npm install` timed out in this environment, so a full Vite production build and browser visual verification are still pending on the user's Docker machine.
- **Commit evidence:** This is a local ZIP/source update and has not yet been committed to the public repository. Do not claim a commit URL until a real commit is created and pushed.
