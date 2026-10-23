# DocuSentra deployment: Vercel frontend + hosted API

## Architecture note

Deploy the **React/Vite frontend** to Vercel. The FastAPI backend, PostgreSQL database, and durable private document storage are separate services. Do not deploy only the frontend and expect uploads, login, permissions, previews, or audit history to work without the API.

This project is prepared to use `VITE_API_BASE_URL` at frontend build time. It must be the API's HTTPS **origin only**, such as `https://docusentra-api.onrender.com` (no trailing slash and no `/api`). If empty, local development continues to use the same-origin `/api` path through the Vite proxy / local Nginx setup.

## A. Publish the source repository

1. Create a GitHub repository, e.g. `docusentra`.
2. From the extracted project root (the folder containing `docker-compose.yml`), make sure `.env` and database backups are not staged. `.gitignore` excludes those.
3. For a new repository, run (replace the URL with your repository URL):

   ```powershell
   git init
   git add .
   git status --short
   git commit -m "Prepare DocuSentra deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/docusentra.git
   git push -u origin main
   ```

   If the repository already exists and has a remote, commit and push to that repo instead. **Never commit `.env`, passwords, `trustvault-before-*.sql`, or document files.**

## B. Deploy the frontend on Vercel

1. Sign in to Vercel and choose **Add New → Project**. Import the GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite**. Build command: `npm run build`. Output directory: `dist`. The included `frontend/vercel.json` configures the SPA fallback for client-side routes.
4. Deploy once to obtain the public Vercel hostname. The page shell can load before the API is configured; authenticated features will not work until the backend is deployed and `VITE_API_BASE_URL` is set.

Official reference: https://vercel.com/docs/frameworks/frontend/vite

## C. Deploy PostgreSQL and the FastAPI API

The API uses a Docker image because its document-preview functionality depends on LibreOffice and Poppler. For this project, Render is one option; another Docker host is fine if it provides PostgreSQL connectivity and durable private-file storage.

1. Create a managed PostgreSQL database on your chosen host. Prefer the backend and database in the same region and use the provider's private/internal database URL when available.
2. Create a **Docker Web Service** from the same GitHub repository. Set **Root Directory** to `backend`; use `backend/Dockerfile`. Health-check path: `/api/health`.
3. Configure environment variables in the API service (not Vercel):

   | Variable | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | Managed PostgreSQL connection URL. The app normalizes `postgres://` / `postgresql://` to the installed psycopg v3 driver. |
   | `STORAGE_DIR` | `/app/private_storage` |
   | `TOKEN_SECRET` | A newly generated high-entropy secret, at least 32 characters |
   | `AUDIT_HMAC_SECRET` | A different newly generated high-entropy secret, at least 32 characters; keep stable between deploys |
   | `FRONTEND_ORIGINS` | Exact Vercel origin, e.g. `https://your-project.vercel.app` (no trailing slash, no `*`) |
   | `TOKEN_TTL_SECONDS` | `28800` |
   | `MAX_UPLOAD_BYTES` | `15728640` |

   Generate two independent secrets locally without sharing them in chat or committing them:

   ```powershell
   py -c "import secrets; print(secrets.token_urlsafe(48))"
   py -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Put one output in `TOKEN_SECRET`, the other in `AUDIT_HMAC_SECRET`. Do not rotate the audit secret casually: existing audit-chain verification depends on it.

4. **Persistent document storage is required.** Attach durable storage and mount it at `/app/private_storage`, matching `STORAGE_DIR`. On Render, persistent disks require a paid service plan; see https://render.com/docs/disks. Do not use an ephemeral filesystem for user uploads, because files can disappear after a redeploy/restart. If using a different host, verify that the directory is writable by the container's non-root `appuser` and persists across deploys.
5. Set `FRONTEND_ORIGINS` to the exact Vercel URL obtained in section B. Do not use a wildcard. Save/redeploy the API after changes. The app intentionally disables interactive FastAPI docs in production.
6. Verify the backend health URL directly: `https://YOUR-API-HOST/api/health`. Expected JSON includes `status: "ok"` and `database: "connected"`.

Render references:
- FastAPI/Docker service: https://render.com/docs/deploy-fastapi and https://render.com/docs/docker
- Environment variables/secrets: https://render.com/docs/configure-environment-variables
- Persistent disks: https://render.com/docs/disks

## D. Connect Vercel to the API

1. In Vercel → Project → **Settings → Environment Variables**, add:

   `VITE_API_BASE_URL = https://YOUR-API-HOST`

   Use the API origin only. Do not add `/api`, a trailing slash, database credentials, `TOKEN_SECRET`, or `AUDIT_HMAC_SECRET` to Vercel. `VITE_*` values become part of browser-delivered frontend code; the API hostname is public, secrets are not.
2. Select Production (and Preview only if you configure a separate safe staging API/CORS origin), save, and redeploy the Vercel project so Vite bakes in the variable.
3. Ensure the API service's `FRONTEND_ORIGINS` exactly matches the production Vercel origin; update and redeploy API if the final Vercel hostname differs.

## E. Create production demo accounts — once only

Set the following variables on the API service to unique account identifiers and unique passwords (at least 16 characters):

- `SEED_ADMIN_USERNAME`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`
- `SEED_OWNER_USERNAME`, `SEED_OWNER_EMAIL`, `SEED_OWNER_PASSWORD`
- `SEED_VIEWER_USERNAME`, `SEED_VIEWER_EMAIL`, `SEED_VIEWER_PASSWORD`

After the API has started against a **fresh production database**, run the one-time seed command in the API service shell/job:

```bash
python -m app.seed
```

Store the credentials in a password manager and share them only with the intended judges/client. Production seeding requires explicit values and does not print passwords. Do not rerun the seed command casually; it resets the configured seed-account passwords.

## F. Final smoke test

- Register a normal account, then log in separately.
- Upload a safe sample document with a category.
- Grant Reader access to a named viewer; verify preview works and direct original-download requests return `403`.
- Revoke the share and verify subsequent preview/download requests are denied.
- Check audit activity and run the admin audit verification route with the admin account.
- Test light/dark themes, category counts, password change and mobile/desktop layout.
- Confirm file uploads still exist after an API redeploy/restart.

## Important deployment limits

- Vercel hosts the static frontend; it does not replace the separately hosted FastAPI service, PostgreSQL database, or private storage.
- Never set production secrets in Vercel's `VITE_*` variables; any `VITE_*` value is exposed to the browser.
- Keep the database private, use HTTPS, keep audit secrets stable, and take encrypted backups.
- Browser previews cannot fully prevent screenshots or screen recording. A previously downloaded file cannot be remotely recalled.
- This is a challenge/demo MVP; verify the actual deployed app and complete an independent security review before putting sensitive real-company documents in it.
