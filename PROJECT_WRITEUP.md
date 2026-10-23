# TrustVault — challenge write-up

## What we built

TrustVault is a secure document-sharing MVP: React/Vite UI, FastAPI API, PostgreSQL metadata, and original files stored in a private volume. It supports authenticated accounts, system roles (administrator, owner, viewer), per-document Reader/Editor grants, owner-controlled grant/revoke, upload validation, category/search filters, document management, read-only raster previews, and audit/activity views.

## Permission model

System roles are not document grants. `admin` can inspect and manage system metadata/roles but does not automatically get document contents. `owner` can upload and manage documents they own. `viewer` cannot upload. Within a document, the owner may grant a named person `reader` (preview only) or `editor` (preview, download, filename rename). Only the owner may manage shares or delete. Every protected request checks the current share/ownership state; revocation therefore blocks the next request. A downloaded copy or screenshot already captured cannot be recalled.

## Audit design

Events include uploads, downloads, page-view/preview access, metadata changes, deletion, permission changes, role changes, failed login and denied access attempts. Rows include actor/document snapshots, previous hash and keyed HMAC-SHA-256 event hash. Application code appends; DB triggers reject ordinary update/delete. The admin can verify the chain. Residual: an operator who obtains the application HMAC key or can reset application and database together can rewrite local history; a separately permissioned external immutable audit/checkpoint sink is required for stronger assurance and is not included in this local package.

## Upload and preview trade-offs

The app validates extensions, size, magic bytes and bounded Office archives, and converts common Office formats for raster preview. It does not include malware scanning or a hardened, separately sandboxed converter service. Reader preview does not stream original PDF/Office/text bytes through its page endpoint, and the original download endpoint returns 403. Browser UI deterrents are not DRM; a user permitted to view pixels can still capture them using OS/browser tools.

## AI usage and review

AI helped explain the requirements, prepare code/documentation and build regression tests. Human-in-the-loop errors included the user discovering that a Reader could still download the original file, noticing a native PDF Save toolbar, and pointing out UI/preview issues. The implementation changed to enforce download restrictions on the server, use rasterized preview pages, and explicitly document screenshot limitations. `PROMPTS.md` records the interactions and known limits; the earlier ZIP-based work did not contain its original Git history, so pre-import fix commits cannot be truthfully reconstructed.

## Not implemented / unfinished

- Public GitHub repository and week-spanning commit history are not created by this ZIP. Do not fake them; create a public repository and maintain real commits from the actual work.
- Live HTTPS deployment, externally accessible seed data/credentials, and the required five-minute video must still be produced by the submitter.
- No external immutable audit sink, antivirus scanning, MFA, distributed rate limiter, version history, nested folders, malware-analysis sandbox or formal independent security review.
- Full frontend production build and the final Docker/browser smoke test must be run on the target machine after applying the bundle.

## Run and demonstrate

Use `README.md`, `DEPLOYMENT.md`, `API_AUTHORIZATION.md`, and `DEMO_SCRIPT.md`. Run backend tests from `backend`: `python -m pytest -q`. Seed accounts with the seed command documented in README; never use local demo passwords on the public deployment.
