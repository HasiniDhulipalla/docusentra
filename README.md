# DocuSentra — Secure Document Access & Audit Platform

A challenge-aligned local-development MVP built with **React + Vite**, **FastAPI**, **PostgreSQL**, and private file storage. It implements system roles (`admin`, `owner`, `viewer`), per-document Reader/Editor grants, server-side authorization, revocation, protected preview/download routes, document categories and search filters, admin activity/permission views, a hash-chained append-only audit table, seed setup, and automated API/security tests.

> **Important:** this is a project/demo MVP, not a production-certified secure vault. Use test files only. Before sensitive/public use, harden authentication, secrets, deployment, uploads, backups, rate limits, and security testing.

## Deploy frontend to Vercel

The React/Vite frontend is prepared for Vercel. The FastAPI API, PostgreSQL database, and persistent private file storage must be hosted separately. Follow [`VERCEL_DEPLOYMENT.md`](VERCEL_DEPLOYMENT.md) for the exact setup, required environment variables, CORS configuration, durable storage, and production seed steps. Set Vercel's Root Directory to `frontend` and configure `VITE_API_BASE_URL` to the HTTPS API origin only. Never put backend secrets in Vercel `VITE_*` variables.

## Additional workspace features

- Document categories available during upload: HR, Finance, Legal, Personal, Education, General, and Others. Sidebar category shortcuts filter documents already accessible to the signed-in user.
- Settings include current-password verification, a strong new-password requirement, and password-change audit events. Existing stateless session tokens remain valid until expiry; sign out to clear the local browser session.
- Registration and sign-in are separate UI steps: after creating an account, the user signs in with the new credentials.
- The sidebar theme toggle switches between the blue/white light theme and orange/black dark theme. The preference is saved in browser local storage.


## Features implemented

- Account registration and sign-in; passwords are hashed with PBKDF2-HMAC-SHA256. System roles are `admin`, `owner`, and `viewer`; public registration cannot request the admin role.
- Signed bearer tokens with algorithm/type/signature/expiry validation and an eight-hour default expiry.
- Login-attempt throttling and registration-attempt throttling (single-process in-memory baseline).
- Private document storage outside the public frontend directory.
- Upload allowlist for PDF, common Office formats, TXT, CSV, PNG and JPG; maximum 15 MB, signature checks and bounded Office archive inspection.
- System administrator can manage users/roles and inspect activity/permissions but gets no implicit access to document contents. System owners upload/manage their own documents; system viewers cannot upload. Document roles are separately Reader/Editor.
- Grant/update/revoke per-document sharing by an exact existing username or email. Revocation is checked on the next protected API request.
- Reader can use authenticated in-browser previews; the backend blocks the original download endpoint for Readers. Editors can download and rename; only the owner can grant/revoke sharing or delete.
- Protected download endpoint logs successful downloads and denied attempts.
- Audit events for account/authentication activity, document upload/download/preview/page reads/rename/delete, permission grants/updates/revokes, role changes and denied requests. Events are keyed HMAC-SHA-256 hash chained; ordinary SQL UPDATE/DELETE is blocked by DB triggers, and admins can verify the chain.
- Responsive dashboard, search by name/owner/category/date, activity history, security settings and admin console.
- Docker Compose starts PostgreSQL, API and frontend together; API runs non-root with a read-only root filesystem and restricted Linux capabilities by default.
- Production-mode startup rejects recognized development secrets/DB defaults, requires a server database plus a separate stable audit HMAC key, and disables interactive API docs.
- Browser security headers including CSP, `nosniff`, same-origin framing, no-referrer and a restrictive permissions policy.

## Audit-chain upgrade compatibility and recovery

The application automatically migrates an old SHA-256 v1 chain or re-keys a transitional v2 chain **only if every event and the stored chain head verify** with the matching historical algorithm/key. If current HMAC, legacy v1 and prior-key checks all fail, startup intentionally stops instead of fabricating a valid-looking audit trail. For the local development database in your current error case, read [`AUDIT_RECOVERY_README.md`](AUDIT_RECOVERY_README.md) and run `.\recover-audit-chain.ps1` from PowerShell. It makes a PostgreSQL backup first, asks for explicit confirmation, preserves the old records and their claimed hashes as **PRESERVED_BUT_UNVERIFIED**, anchors the archive digest in a new verified chain, and confirms a normal restart works. User accounts, documents, permissions and private file storage are not deleted. Never run `docker compose down -v` as a troubleshooting shortcut. This break-glass path is disabled in production.

## Fastest start (recommended: Docker Desktop)

1. Install and start Docker Desktop on Windows.
2. Extract this ZIP and open the `trustvault-starter` folder in VS Code.
3. Open a terminal in the project root (the folder containing `docker-compose.yml`).
4. Run the one-command launcher in PowerShell (it creates local `.env` from the example when needed):

   ```powershell
   .\start-trustvault.ps1
   ```

   If PowerShell blocks scripts, use:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start-trustvault.ps1
   ```

   Or run manually after preparing `.env` with a unique `TOKEN_SECRET` (in local development the application can generate an ephemeral key, which invalidates sessions on restart):

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

5. Open **http://localhost:8080**. The API docs are at **http://localhost:8000/docs** in development and health is at **http://localhost:8000/api/health**.
6. Seed three development demo accounts and a sample document (do this once on a fresh local database):

   ```powershell
   docker compose exec api python -m app.seed
   ```

   **Development-only credentials** (the seed command will reset these account passwords each time it is rerun if the same local defaults are used):

   | Role | Username | Password |
   |---|---|---|
   | Administrator | `admin` | `AdminDemo!2026#Vault` |
   | Document owner | `owner` | `OwnerDemo!2026#Vault` |
   | Viewer | `viewer` | `ViewerDemo!2026#Vault` |

   Viewer is granted Reader access to `sample-access-review.txt`, owned by `owner`. These credentials must never be used on a public deployment. In production, set all `SEED_*` username/email/password environment variables to unique values; the production seeder does not print passwords.
7. Use a separate browser/private window to test Reader preview, direct API download denial, admin activity view, and revocation.

Stop the app:

```powershell
.\stop-trustvault.ps1
```

or run `docker compose down` manually.

Stop and also permanently remove the local database/file volumes (destructive):

```powershell
docker compose down -v
```

### Demo flow

1. Register account A and upload a test PDF.
2. Register account B in another browser/profile.
3. In account A, click the people icon beside the document and grant `reader` or `editor` access to account B's username/email.
4. In account B, open `Shared with me` and preview the document. As Reader, the original download API must return `403`; use `DEMO_SCRIPT.md` for the direct API check.
5. In account A, change B to Editor and confirm Editor download/rename works while sharing/deletion stay owner-only.
6. In account A, revoke B's access. Try preview/download again in account B; the backend should return `403` and Activity history should show denied attempts.

## Local development without Docker (uses SQLite by default)

This lets you run frontend + backend immediately if Docker is unavailable. PostgreSQL is recommended for the final submission/demo.

**Terminal 1 — backend** (PowerShell):

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./trustvault.db"
$env:STORAGE_DIR = "./private_storage"
$env:TOKEN_SECRET = "local-only-change-this-secret-before-deploying"
$env:AUDIT_HMAC_SECRET = "local-only-stable-audit-key-for-development-only"
uvicorn app.main:app --reload
```

If PowerShell blocks activation, use `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `\.venv\Scripts\python.exe -m uvicorn app.main:app --reload` instead.

**Terminal 2 — frontend** (project root):

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` requests to `http://127.0.0.1:8000`.

## Tests and build checks

Backend tests (from the `backend` folder; current authoring environment has 24 passing tests):

```powershell
py -m pip install -r requirements.txt
py -m pytest -q
```

The latest reported backend suite contains **20 passing tests** in the authoring environment. The exact test matrix and residual risks are in `SECURITY_TEST_MATRIX.md`. The latest Vite production build and deployed-system attack tests still need to be run on the target machine. Use `THREATS.md`, `PROMPTS.md`, `FUNCTIONAL_REQUIREMENTS.md`, `API_AUTHORIZATION.md`, `DATABASE_SCHEMA.md`, `DEPLOYMENT.md`, `PROJECT_WRITEUP.md`, `DEMO_SCRIPT.md`, and `SCORECARD.md` to prepare the submission. The supplied official 10 requirements are mapped in `FUNCTIONAL_REQUIREMENTS.md`; still verify the exact final deployment.

Frontend production build:

```powershell
cd frontend
npm install
npm run build
```

## Security design notes

- File IDs and storage keys are separate. Uploaded bytes are never placed inside `frontend/public` or exposed by a static URL.
- Every download checks the authenticated user against document ownership or a current share row. Removing a share blocks the next request; it cannot erase a file the other user already downloaded.
- Hiding a button is not the security boundary; the API is.
- Upload extension allowlisting, content-signature checks and size limits help reduce risk but do **not** equal malware scanning or deep format validation.
- The frontend stores the bearer token in browser local storage for this demo. For production, use a reviewed secure session architecture and complete XSS review. The database-local keyed HMAC chain detects ordinary row changes and cannot be recomputed by a database-only actor who does not have the independent `AUDIT_HMAC_SECRET`. A host/app-secret administrator who obtains that key or resets application and database state together may still rewrite local history; use an independently permissioned external immutable audit sink/checkpoint for a stronger production guarantee.
- Rate limiting in this MVP is process-local; public multi-instance deployments need a shared limiter. Upload checks are not malware scanning. Production requires unique database/signing secrets, HTTPS, restricted networks, backups, migrations, dependency scanning and independent security review. See `DEPLOYMENT.md` and `THREATS.md`.
- This MVP creates SQLAlchemy tables at startup for convenience; production should use versioned migrations (for example, Alembic).

## Project layout

```text
trustvault-starter/
├── docker-compose.yml
├── THREATS.md
├── PROMPTS.md
├── FUNCTIONAL_REQUIREMENTS.md
├── SECURITY_TEST_MATRIX.md
├── API_AUTHORIZATION.md
├── DATABASE_SCHEMA.md
├── schema_postgresql.sql
├── PROJECT_WRITEUP.md
├── GIT_PUBLISHING.md
├── DEPLOYMENT.md
├── DEMO_SCRIPT.md
├── SCORECARD.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/main.py
│   ├── app/seed.py
│   ├── app/verify_audit.py
│   ├── app/export_schema.py
│   └── tests/{test_api_flow.py,test_challenge_requirements.py,test_security_helpers.py}
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    └── src/{App.jsx,main.jsx,styles.css}
```

## API overview

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/users?q=...`
- `GET /api/documents`, `POST /api/documents`, `PATCH /api/documents/{id}`, `DELETE /api/documents/{id}`
- `GET /api/documents/{id}/download`
- `GET /api/documents/{id}/preview`, `GET /api/documents/{id}/preview-content`, `GET /api/documents/{id}/preview-pages/{page_number}` (authenticated, permission-checked preview endpoints; PDF/Office/text pages return unwatermarked PNGs, not raw PDF/text bytes; successful page retrieval is logged)
- `GET /api/documents/{id}/shares`, `POST /api/documents/{id}/shares`, `DELETE /api/documents/{id}/shares/{share_id}`
- `GET /api/activity`, `GET /api/health`
- `/api/admin/overview`, `/api/admin/users`, `PATCH /api/admin/users/{id}/role`, `/api/admin/permissions`, `/api/admin/activity`, `/api/admin/audit/verify`, `/api/admin/audit/archives`, `/api/admin/audit/archives/{archive_id}` (admin-only; see `API_AUTHORIZATION.md`)

## Production warning

This is a security-focused hackathon MVP, not a certified document vault. The Reader restriction controls future API access but cannot stop screenshots, copying visible text, or erase previously downloaded copies. Full format conversion, dependency hardening and the latest production frontend build must be tested on the exact final deployment. Never store real sensitive documents in the demo.


## Reader versus Editor permissions

- **Reader:** can preview every file type in the current upload allowlist: PDF and supported Office files are rasterized page-by-page server-side; TXT/CSV and DOCX fallback content is rasterized to pages; PNG/JPG is re-encoded as an image without visible watermarking. The preview UI does not embed the native PDF viewer, and the original download endpoint returns HTTP 403 for Reader accounts.
- **Editor:** can preview, download the original, and rename document metadata.
- **Owner:** can preview/download the original and manage sharing/deletion.

A preview is not DRM. By design, previews do not add visible watermarks. The UI hides the native PDF Save/Print toolbar by not using the browser's built-in PDF viewer and blocks common copy/select/context-menu/save/print shortcuts as best-effort deterrents: a normal website cannot reliably block OS screenshots, screen recording, browser extensions, or extraction via developer tools, and it cannot revoke an already captured image. Never grant preview access to content the recipient must not see. Files downloaded by an Editor/Owner cannot be remotely recalled. Office previews require the updated Docker image to be rebuilt so LibreOffice and Poppler tools are installed in the API container.


## Reader preview protections

PDF and Office previews, plus TXT/CSV and DOCX fallback previews, are rendered to individual PNG page images on the server; raw PDF bytes and raw preview text are not returned to the Reader UI. Page and image responses are re-encoded without a visible watermark and sent with no-store headers. The UI omits the native PDF Save/Print toolbar and blocks common copy, selection, context-menu, and shortcut actions as deterrents. These controls do **not** make screenshots or OS-level screen recording impossible; authorized viewers can still capture visible content or inspect browser-delivered image data. The authoritative protections are server-side per-request authorization, Reader download denial, and immediate revocation for subsequent requests.


## Challenge submission items not produced by this ZIP

This bundle is source code and documentation, not a public GitHub URL, live HTTPS deployment, or five-minute video. The previous development was exchanged as ZIP files without its original `.git` history, so earlier commit timestamps cannot honestly be reconstructed. Create/push a public repository with real commits from the current work, deploy this exact revision, provide the three appropriate role credentials through the submission README/environment process, and attach an actual demo video. See `PROJECT_WRITEUP.md`, `PROMPTS.md` and `GIT_PUBLISHING.md` for the exact outstanding evidence.

## Local recovery if the audit verifier blocks startup

If logs say `event_hash_mismatch` and also say the legacy/key fallback verifiers failed, do not delete database volumes or repeatedly regenerate keys. Read [`AUDIT_RECOVERY_README.md`](AUDIT_RECOVERY_README.md). On a local development database only, run `.\recover-audit-chain.ps1`. It creates a host-side SQL backup, asks for explicit confirmation, archives the old chain as **unverified** (without discarding its rows), creates and verifies a new HMAC chain, and restarts the API without the recovery flag. This break-glass procedure is intentionally disabled in production.
