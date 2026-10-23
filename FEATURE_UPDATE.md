# DocuSentra Feature Update

This update adds the requested workspace features while preserving the existing document-security APIs and audit design.

## Document categories

- Sidebar category shortcuts: HR, Finance, Legal, Personal, Education, General, Others.
- Upload modal category selector with General as the default.
- Category is stored with the document and included in document list/search metadata.
- Selecting a sidebar category filters documents visible to the current user. It does not grant access to documents.
- Backend validates incoming categories against an allowlist. Legacy categories retained for existing records remain searchable.

## Settings and password change

- Settings includes a password-change form.
- User must provide the current password.
- New password must be at least 12 characters and pass server-side checks; confirmation is checked in the frontend.
- Password changes and failed current-password checks are written to the audit trail.
- Existing stateless bearer tokens remain valid until expiry. Signing out clears the token from the current browser; this endpoint does not revoke other existing tokens.

## Registration and login

- Account creation and sign-in are separate UI actions.
- After registration succeeds, the UI returns to the sign-in form and does not store the token returned from registration.
- User then signs in with the created username/email and password.

## Themes

- Light theme: blue and white.
- Dark theme: orange accents and near-black backgrounds.
- Sidebar theme toggle persists the preference in browser local storage.
- The preference also styles the authentication screen.

## Validation performed in this build workspace

- Backend automated tests: 27 passed.
- Python application compilation: passed.
- JSX syntax transpilation/parser diagnostics: 0.
- CSS curly-brace balance check: passed.
- Full frontend Vite production build was not verified: the source ZIP has no `package-lock.json`, and a deterministic `npm ci` therefore cannot run. Docker/Windows browser runtime was not available here.

## Apply the update

On an existing local installation, back up the project and preserve `.env` and Docker volumes. Replace source files using this package, then run:

```powershell
docker compose build api frontend
docker compose up -d
docker compose ps
```

Do not run `docker compose down -v` as a routine update command.
