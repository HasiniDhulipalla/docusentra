# DocuSentra — One Vercel Project (Frontend + FastAPI Backend)

This repository now deploys both applications from **one Vercel project and one URL** using Vercel Services (currently Beta). The root `vercel.json` defines the frontend and backend services and routes `/api/*` to FastAPI; all other paths go to the Vite/React app. Official guide: https://vercel.com/docs/services

## Repository layout

- `frontend/` — React + Vite application
- `backend/` — FastAPI application and Python dependencies
- `vercel.json` — one root-level Services configuration (the nested frontend/backend `vercel.json` files have been removed intentionally)
- PostgreSQL — hosted Neon database
- Files — private Vercel Blob storage (never use ephemeral function disk as permanent storage)

## 1. Push the combined configuration to GitHub

Run from the Git repository root. Review staged files before committing. Never commit `.env`, database dumps, audit archives, private documents, or secret values.

```powershell
git status --short
git add vercel.json README.md VERCEL_BACKEND_DEPLOYMENT.md frontend backend
git status --short
git commit -m "Deploy frontend and FastAPI together with Vercel Services"
git push
```


## 2. Reconfigure the existing Vercel project

1. Open Vercel Dashboard and select the existing DocuSentra frontend project. Do not create a separate backend project.
2. Go to **Settings → Build & Development Settings**.
3. Set **Root Directory** to the repository root (usually leave it blank or `.`; do not leave it as `frontend`). Enable access to files outside the root if the dashboard displays that setting.
4. Remove old Build Command and Output Directory overrides that force the whole project to behave as a Vite-only project. The root `vercel.json` owns the service-specific build settings.
5. If Vercel asks for a framework preset, select **Services** if available. Do not set the overall project to `frontend/` or `backend/`; each service root is configured in `vercel.json`.
6. Save, then trigger a deployment from the `main` branch.

The services are configured as:

- Frontend service: root `frontend/`, Vite build `npm run build`, output `dist`, SPA fallback to `/index.html`.
- Backend service: root `backend/`, built as a Docker container using `backend/Dockerfile`. This avoids Vercel's generated Python Function handler, which in the reported deployment failed importing `vc_handler`. The Docker command starts Uvicorn and listens on the Vercel-provided `PORT` (default 8000). The backend requirements use the official `vercel` Python SDK for Blob APIs.
- Public routing: `/api/*` goes to the backend service, then `/*` to the frontend service. The API receives the original `/api/...` path.

## 3. Remove the old split-backend URL from frontend environment

Since both services share one domain, the frontend calls `/api/...` on the same origin. In **Settings → Environment Variables**, delete `VITE_API_BASE_URL` if it still points to the deleted backend project. Do not set it to a second domain. Keep/add `VITE_MAX_UPLOAD_BYTES=3800000` for the frontend build. Redeploy after changing environment variables.

## 4. Add Neon PostgreSQL

Use a fresh Neon production database; do not import local Docker audit data that was previously marked unverified. Copy the Neon pooled connection string from the Neon dashboard and add it to the Vercel project's **Production** environment as `DATABASE_URL`.

## 5. Attach a private Vercel Blob store

In the same Vercel project, open **Storage → Create → Blob**, select **Private** access, and connect the store to this project. Confirm the runtime gets the Blob storage credentials/identifier. Keep the store private; never place a Blob secret in a `VITE_*` variable.

## 6. Set backend runtime environment variables

Set these variables in the Vercel project for **Production**:

| Key | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Neon pooled PostgreSQL URL (keep SSL parameters) |
| `STORAGE_BACKEND` | `vercel_blob` |
| `STORAGE_DIR` | `/tmp/docusentra` (temporary working/cache only) |
| `TOKEN_SECRET` | Unique random secret, at least 32 characters/high entropy |
| `AUDIT_HMAC_SECRET` | A separate unique random secret, different from `TOKEN_SECRET`; keep stable |
| `FRONTEND_ORIGINS` | Exact one-project URL, e.g. `https://docusentra-yourname.vercel.app`, no trailing slash |
| `MAX_UPLOAD_BYTES` | `3800000` |
| `TOKEN_TTL_SECONDS` | `28800` |
| `MAX_PREVIEW_PAGES` | `30` |
| `LOGIN_MAX_FAILURES` | `10` |
| `LOGIN_RATE_WINDOW_SECONDS` | `300` |
| `REGISTER_MAX_ATTEMPTS` | `10` |
| `REGISTER_RATE_WINDOW_SECONDS` | `3600` |

Generate each secret separately on a local PowerShell terminal, run twice and save the different outputs securely:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never paste secrets into chat or commit them. Do not regenerate `AUDIT_HMAC_SECRET` after production audit events exist. Do not deploy the old local database or its unverifiable historical audit events to the fresh production database.

## 7. Deploy and verify

After adding variables and connecting storage, redeploy the same Vercel project. Open these routes on the **same domain**:

- `https://YOUR-PROJECT.vercel.app/` — frontend
- `https://YOUR-PROJECT.vercel.app/api/health` — backend health endpoint; expect successful status and `database: connected`
- `https://YOUR-PROJECT.vercel.app/api/auth/register` — API route (POST only; a browser GET may return 405, which is expected)

Then test account registration/login, upload a small allowed file, category selection, sharing with a second account, Reader preview, `403` original-download denial, revocation, and audit verification. Keep real confidential data out until all tests pass on the deployed URL.

## 8. One-time demo/admin seeding (optional)

The public registration endpoint creates standard owner accounts; it does not let users self-assign administrator roles. If a demo requires admin/owner/viewer seed accounts, follow `backend/app/seed.py` and use a trusted local workstation with production Neon settings and a server-side Blob token. Do not expose default demo passwords on a public deployment or commit a temporary `backend/.env` used for seeding.

## Platform limits and known limitations

- Vercel Services are currently Beta and available across plans; account UI may differ. If Services configuration is rejected, read the Vercel deployment logs rather than reverting to split projects silently.
- Vercel Functions have a 4.5 MB request/response body limit, so the app is configured to 3.8 MB uploads. This is a demo constraint.
- Vercel function filesystems are ephemeral. Durable originals must go to private Blob; `/tmp` is only temporary preview/cache data.
- The backend is configured as a Vercel Services container so it can include system packages such as LibreOffice; container support and Vercel Services availability depend on the current project/plan rollout. Verify the runtime in deployment logs.
- An ordinary browser application cannot reliably prevent OS screenshots or screen recording.
- This remains a challenge/demo MVP. Verify all authorization routes and the live deployment before using real confidential documents.


## Runtime incident fix

The backend now uses `runtime: "container"` in the Vercel Services config and the Vercel deployment must include `backend/Dockerfile` (do not exclude it in `.vercelignore`). This avoids the generated `vc__handler__python.py` / `vc_handler` runtime import failure seen in the prior deployment. The Dockerfile binds Uvicorn to `$PORT` (default 8000).

Startup schema migration also uses the single checked-out SQLAlchemy connection for inspection and DDL. This avoids a deadlock/timeout when the serverless database pool is intentionally configured with `pool_size=1` and `max_overflow=0`.

The `requirements.txt` uses the official `vercel` Python SDK because application code imports `vercel.blob`; the unrelated `vercel-blob` distribution is not the SDK used by this source.
