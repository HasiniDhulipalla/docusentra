# TrustVault API authorization guide

All protected APIs use a signed bearer token and look up the current user/role from the database. A frontend hidden button is not an authorization boundary. IDs are never treated as permissions. All document operations exclude soft-deleted documents.

## Public / pre-authentication

| Endpoint | Authentication | Notes |
|---|---|---|
| `GET /`, `GET /api/health` | None | Root/health metadata only; health checks database connectivity. |
| `POST /api/auth/register` | None | Registration creates a non-admin system account (`owner` default); request cannot choose `admin`. Validates inputs and uses rate limiting. |
| `POST /api/auth/login` | None | Username/email + password; failed attempts are audited/rate-limited. |

## Signed-in account and documents

| Endpoint | Who may call | Enforcement |
|---|---|---|
| `GET /api/auth/me` | Any authenticated user | Returns only the current account's own profile and system role. |
| `GET /api/users?q=...` | Any authenticated user | Exact username/email lookup for sharing; does not expose a full account list. |
| `GET /api/documents?q=&owner=&category=&from_date=&to_date=` | Any authenticated user | Server only returns documents owned by the caller or actively shared with them. Filters are applied server-side. |
| `POST /api/documents` | `admin` or `owner` system role; not `viewer` | Extension, size, byte-signature/Office archive validation; random storage key; private volume. System administrators do not inherit rights to existing document contents. |
| `GET /api/documents/{id}/preview` | Owner or current Reader/Editor share | Re-checks current permission and records a preview-open event. |
| `GET /api/documents/{id}/preview-content` | Owner or current Reader/Editor share | Only re-encoded image previews; raw Office/PDF/TXT bytes are not returned by this endpoint. |
| `GET /api/documents/{id}/preview-pages/{page}` | Owner or current Reader/Editor share | Permission rechecked on every page; individual raster response uses no-store and page-view is audited. |
| `GET /api/documents/{id}/download` | Owner or current Editor share | Reader receives 403; successful original downloads are audited. |
| `PATCH /api/documents/{id}` | Owner or current Editor share | Reader denied; only filename metadata, with extension preserved. |
| `DELETE /api/documents/{id}` | Owner only | Soft delete, revokes active shares, removes source/cache bytes, preserves an audit reference. |
| `GET /api/documents/{id}/shares` | Owner only | Only the owner can enumerate named grants. |
| `POST /api/documents/{id}/shares` | Owner only | Grants/updates named Reader/Editor; each change is audited. |
| `DELETE /api/documents/{id}/shares/{share_id}` | Owner only | Removes current share; following requests re-check permission and fail. |
| `GET /api/activity` | Any authenticated user | User's own actions plus activity for documents they own; denied foreign-document events redact foreign document name/details. |

## Administrator-only endpoints

| Endpoint | Role | Purpose |
|---|---|---|
| `GET /api/admin/overview` | `admin` | Role/document/grant/audit counts and current audit-chain validation status. |
| `GET /api/admin/users` | `admin` | User roles and creation metadata. |
| `PATCH /api/admin/users/{user_id}/role` | `admin` | Changes role; cannot remove the last administrator, and cannot set an active document owner to Viewer until owned documents are transferred/deleted. |
| `GET /api/admin/permissions` | `admin` | Active share grants and grantor. Does not grant content access. |
| `GET /api/admin/activity` | `admin` | Global event filters by action, actor and dates; includes hash references. |
| `GET /api/admin/audit/verify` | `admin` | Recomputes chain and reports first invalid event. |

## Response policy

- `401`: missing, expired, malformed or invalid authentication token.
- `403`: existing document/operation not authorized, Reader attempts to download/modify, or non-admin calls an admin route.
- `404`: missing or soft-deleted document/record.
- `413`: upload/archive/page limits exceeded.
- `415`: unsupported or invalid file signature/format.
- `422`: file cannot be safely rendered/parsed.
- `503`: storage/database/render dependency unavailable.

## Security boundary and audit guarantees

An administrator can inspect metadata/activity but is not automatically owner or Editor of every file. Access is checked server-side on every document route. A read-only browser preview blocks the original Reader download route but is not DRM: visible pixels can be captured, and it cannot recall previously downloaded copies.

The audit table has update/delete triggers and a keyed HMAC-SHA-256 hash chain with a stored head. This detects ordinary row changes and a database-only attacker without the HMAC key cannot forge event hashes. It is not independent immutable storage: a host/app-secret administrator who obtains the HMAC key or can reset application and database together could rewrite history. Use an independently permissioned immutable external sink/checkpoint for stronger production evidence.


### Audit recovery archive endpoints

- `GET /api/admin/audit/archives` — **administrator only**. Lists preserved archive metadata, explicitly marked `PRESERVED_BUT_UNVERIFIED`, plus a snapshot digest check.
- `GET /api/admin/audit/archives/{archive_id}` — **administrator only**. Returns the archived raw audit events only if the deterministic snapshot digest matches the stored digest. It clearly warns that the original history could not be cryptographically authenticated.

These endpoints do not make legacy rows trustworthy. They expose preserved evidence and integrity status without presenting the legacy chain as verified.


## Password change

- `POST /api/auth/change-password` — any authenticated user. Requires the current password and a new password of at least 12 characters. Incorrect current passwords are rejected; successful changes are written to the audit trail.
