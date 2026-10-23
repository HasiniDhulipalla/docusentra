# Workspace page separation

## Overview
- Greets the signed-in user and gives a compact summary of documents, sharing, activity, and security status.
- Shows up to five recent documents without management filters.
- Keeps the recent security activity feed and 3D protection card beside the document snapshot.
- Provides a clear action to open **My documents** for the full library.

## My documents
- Shows the full-width document-management table.
- Includes server-side name search plus owner, category, and date filters.
- Keeps relevant per-document actions (preview/download, rename, manage sharing, and delete) subject to the existing UI role checks and server authorization.
- Does not repeat the dashboard summary cards or the overview activity sidebar.

## Shared with me
- Shows the documents explicitly shared with the signed-in user, in a full-width management list.
- Does not mix the user's owned documents into the list.

This is a presentation-layer separation; it does not change API permissions or treat UI visibility as a security boundary. Protected operations continue to be authorized by the backend.
