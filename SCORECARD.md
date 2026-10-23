# Submission scorecard — mapped to the provided rubric

The evaluator assigns points. This document organizes evidence; it does not guarantee marks or predict the evaluator's independent results.

| Rubric | Max | Evidence included | Remaining work before final submission |
|---|---:|---|---|
| Security | 35 | `backend/app/main.py`, `SECURITY_TEST_MATRIX.md`, 19 automated tests; per-request authorization; direct Reader download denial; token checks; upload content checks; response headers; production configuration checks | Rebuild/deploy this exact revision; manually verify direct API calls; scan deployed host; add shared rate limiting, malware scanning, secure-session/XSS review before production |
| Threat thinking | 15 | `THREATS.md` with assets, actors, 19 attack paths, mitigations, tests, residuals and additional findings | Private evaluator threats are unknown; compare against any judge feedback and add evidence for every newly found path |
| Functionality | 15 | `FUNCTIONAL_REQUIREMENTS.md` maps 10 acceptance checks to implementation and tests | Rebuild the latest images and test all ten official items against the final running system, especially every Office format |
| AI use | 15 | `PROMPTS.md` records user directions, a caught Reader-permission flaw, corrections, and what remains unverified | Keep actual final terminal output/screenshots; update the log if further AI-generated code is used or corrected |
| Engineering quality | 10 | Validation helpers, descriptive API errors, typed schemas, private file storage, runtime config guard, unit + API tests, container hardening defaults | CI workflow is included but must complete successfully; add dependency/image scans; consider migrations and shared rate-limiter |
| Documentation, deployment and demo | 10 | `README.md`, `DEPLOYMENT.md`, `DEMO_SCRIPT.md`, `SECURITY_TEST_MATRIX.md` | Deploy to judge-accessible HTTPS host if required, rehearse the demo from a clean browser, attach screenshots and logs from the final revision |

## Current verified state

- Backend tests in the authoring environment: **22 passed** (`python -m pytest -q`).
- Earlier user screenshot showed the database and API healthy and the frontend container started for a prior package revision. This challenge-alignment package still needs a fresh build/run on the user's machine.
- Full frontend production build was not independently confirmed in the authoring environment due npm dependency installation timeout.
- The official ten requirements supplied by the user are mapped in `FUNCTIONAL_REQUIREMENTS.md`. The judge's private threat list is unknown. The project archive does not supply a public Git remote, a live HTTPS deployment, or a recorded video.

## Release gate

Do not submit until the following are all true: exact official requirements reconciled; latest Docker images built; frontend loads; all 22 backend tests pass; Reader direct download returns 403; post-revoke requests return 403; audit events are visible; Office preview works in the actual built container; production deployment uses unique secrets and HTTPS; demo is rehearsed from a clean browser.

- Audit migration handling: tested against an intact legacy v1 chain and a tampered legacy chain; see `AUDIT_CHAIN_MIGRATION.md`. PostgreSQL startup after migration remains an on-machine release check.
