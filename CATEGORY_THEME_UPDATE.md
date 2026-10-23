# DocuSentra Category + Dark Theme UI Fix — 2026-10-23

## Changes
- Category-specific pages show the category chosen in the sidebar as a fixed, read-only Category field rather than a redundant dropdown.
- Filter and Clear preserve the sidebar-selected category; the category cannot accidentally be cleared while viewing that category.
- Dark theme styles the workspace switcher, table headers, document table surfaces, category display field, notices, and empty states with black/charcoal surfaces and readable text.
- Light theme remains blue/white.
- Only `frontend/src/App.jsx` and `frontend/src/styles.css` were functionally changed. No backend, authentication, document authorization, audit, database schema, or `.env` behavior was changed.

## Apply
Replace these files in the existing project:
- `frontend/src/App.jsx`
- `frontend/src/styles.css`

Then run from the folder containing `docker-compose.yml`:

```powershell
docker compose build frontend
docker compose up -d frontend
```

Open `http://localhost:8080`, press `Ctrl+0` to reset browser zoom if needed, then `Ctrl+Shift+R` for a hard refresh.

## Validation in this workspace
- JSX syntax/transpile check: passed
- CSS brace and targeted selector smoke checks: passed
- Backend regression tests: 27 passed
- Full Vite production build: not verified here because `npm install` timed out
