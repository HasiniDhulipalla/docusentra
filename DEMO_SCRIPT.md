# Judge demo script (4–5 minutes)

Use test documents only. Have two browsers/profiles ready so the owner and Reader sessions do not overwrite each other's localStorage token.

## Setup (before recording or judging)

- Start the latest package and confirm `docker compose ps` is healthy.
- For a local demonstration, run `docker compose exec api python -m app.seed` and use the three development-only accounts in `README.md`. Do not reuse them in a public deployment.
- Open Admin, Owner and Viewer accounts in separate browser profiles. The seeded owner has `sample-access-review.txt` shared as Reader to the seeded viewer.
- For the cross-user attack demonstration, upload a small DOCX/PDF to the owner account and keep its document ID visible from the API response/Network panel.

## Live walkthrough

1. **Private by default:** With Account B not yet shared, try opening the document ID via the UI/API. Show that the request is blocked.
2. **Owner grants Reader:** In Account A, grant Account B `Reader` access. In Account B, open Shared with me and show the read-only preview. PDF/Office/Text pages should appear as unwatermarked images, not in the native browser PDF viewer with a Save button.
3. **Test the server, not just the button:** While signed in as Reader, open DevTools Console and run the following after replacing `123` with the demo document ID:

   ```javascript
   fetch('/api/documents/123/download', {
     headers: { Authorization: `Bearer ${localStorage.getItem('trustvault_access_token')}` }
   }).then(async response => console.log(response.status, await response.text()));
   ```

   Expected: **403** with a Reader/view-only message. This proves the API rejects the request even if someone bypasses the UI.

4. **Editor contrast:** As owner, change Account B from Reader to Editor. Show that download and rename become available, while share management and deletion remain owner-only.
5. **Immediate revocation:** Revoke Account B's share as Account A. Re-run the preview/download request as Account B. Expected: **403** on subsequent requests.
6. **Preview deterrents:** While Reader preview is open, confirm no watermark is present; try right-click/text selection/Ctrl+C and confirm the UI blocks common shortcuts. Do not claim this makes OS screenshot or screen recording impossible.
7. **Admin and audit trail:** Sign in as the administrator and show Accounts/Roles, Active permissions, Global audit trail and Verify audit chain. Point out access granted/revoked, role changes and denied attempts. Show that the admin still cannot download an unshared document. Then return to the owner Activity view.
8. **File validation:** If time permits, show that a text payload named `fake.pdf` is rejected rather than accepted based only on its extension.

## Claims to avoid during the demo

- Do not claim that a Reader cannot take screenshots, transcribe content, or copy text displayed in a browser.
- Do not claim that revocation erases an already downloaded file.
- Do not claim antivirus/malware scanning, an externally immutable audit service, MFA, production certification, or distributed rate limiting. The current keyed HMAC chain plus DB triggers detects ordinary mutation and resists a database-only attacker who does not possess `AUDIT_HMAC_SECRET`. A host/app-secret administrator who obtains that key can still rewrite local history; external immutable audit anchoring is not included.
- Do not call the demo complete until the final Docker rebuild and browser tests pass on the exact submission revision.
