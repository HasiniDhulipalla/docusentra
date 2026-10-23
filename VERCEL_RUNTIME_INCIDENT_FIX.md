# Vercel runtime incident fix

This update addresses two independent failures seen in runtime logs:

1. `cannot import name vc_handler from vercel_runtime.vc_init`: the backend now uses the Vercel Services container runtime, so it runs the existing Dockerfile and Uvicorn directly instead of the generated Python Function handler. The Dockerfile is no longer excluded by `.vercelignore`, and Uvicorn binds to `$PORT` (default 8000).
2. `QueuePool limit of size 1 ... timed out` in `apply_legacy_schema_migrations`: schema inspection now uses the same checked-out connection held by `engine.begin()`, avoiding an attempt to check out a second connection from a one-connection pool.

## Deploy

- Keep the Vercel project Root Directory at the repository root.
- In Vercel Build & Development settings choose **Services** (Services is currently Beta).
- Keep the `services` block in root `vercel.json`; backend runtime is `container`.
- Add the backend secrets/Neon connection/private Blob environment variables to the Vercel project and redeploy.
- Do not reset the database or regenerate existing audit secrets. This fix does not edit audit rows or change keys.

Local regression test: `python -m pytest tests/test_single_connection_migration.py tests/test_vercel_entrypoint.py -q` from `backend/`.
