"""Challenge-level regressions for system roles, search, audit integrity and admin APIs."""
from __future__ import annotations

from datetime import date
from sqlalchemy.exc import SQLAlchemyError
from fastapi.testclient import TestClient

import app.main as api
from app.main import app


def _register(client: TestClient, username: str, email: str, password: str) -> tuple[dict, dict]:
    response = client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    assert response.status_code == 201, response.text
    account = response.json()["user"]
    return account, {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_system_roles_admin_dashboard_search_and_audit_integrity():
    suffix = str(date.today().toordinal()) + "x"
    with TestClient(app) as client:
        admin, admin_headers = _register(client, f"admin_{suffix}", f"admin_{suffix}@test.example", "Admin-Password-2026!Strong")
        owner, owner_headers = _register(client, f"owner_{suffix}", f"owner_{suffix}@test.example", "Owner-Password-2026!Strong")
        viewer, viewer_headers = _register(client, f"viewer_{suffix}", f"viewer_{suffix}@test.example", "Viewer-Password-2026!Strong")

        # Simulate the trusted bootstrap process; public registration cannot choose its role.
        session = api.SessionLocal()
        try:
            admin_row = session.get(api.User, admin["id"])
            admin_row.system_role = "admin"
            viewer_row = session.get(api.User, viewer["id"])
            viewer_row.system_role = "viewer"
            session.commit()
        finally:
            session.close()
        assert client.get("/api/auth/me", headers=admin_headers).json()["system_role"] == "admin"
        assert client.get("/api/auth/me", headers=viewer_headers).json()["system_role"] == "viewer"
        assert "system_role" not in api.RegisterInput.model_fields

        denied_admin_api = client.get("/api/admin/users", headers=owner_headers)
        assert denied_admin_api.status_code == 403

        # Upload categories are persisted and filters are applied server-side to authorized results.
        uploaded = client.post(
            "/api/documents", headers=owner_headers,
            files={"file": (f"contract_{suffix}.txt", b"Confidential contract summary", "text/plain")},
            data={"category": "Contracts"},
        )
        assert uploaded.status_code == 201, uploaded.text
        doc = uploaded.json()
        assert doc["category"] == "Contracts"
        doc_id = doc["id"]

        assert client.get(f"/api/documents?category=Contracts", headers=owner_headers).json()[0]["id"] == doc_id
        assert client.get(f"/api/documents?owner=owner_", headers=owner_headers).json()[0]["id"] == doc_id
        assert client.get(f"/api/documents?q=contract_{suffix}", headers=owner_headers).json()[0]["id"] == doc_id
        assert client.get(f"/api/documents?from_date={date.today().isoformat()}&to_date={date.today().isoformat()}", headers=owner_headers).status_code == 200
        assert client.get(f"/api/documents?from_date=2026-10-22&to_date=2026-01-01", headers=owner_headers).status_code == 400

        # A system viewer cannot upload; no per-document grant means no content access.
        viewer_upload = client.post("/api/documents", headers=viewer_headers,
                                    files={"file": ("no.txt", b"no", "text/plain")})
        assert viewer_upload.status_code == 403
        # Exercise every sensitive route directly before any document grant exists.
        unshared_attempts = [
            client.get(f"/api/documents/{doc_id}/preview", headers=viewer_headers),
            client.get(f"/api/documents/{doc_id}/preview-content", headers=viewer_headers),
            client.get(f"/api/documents/{doc_id}/preview-pages/1", headers=viewer_headers),
            client.get(f"/api/documents/{doc_id}/download", headers=viewer_headers),
            client.patch(f"/api/documents/{doc_id}", headers=viewer_headers, json={"filename": f"stolen_{suffix}.txt"}),
            client.delete(f"/api/documents/{doc_id}", headers=viewer_headers),
            client.get(f"/api/documents/{doc_id}/shares", headers=viewer_headers),
            client.post(f"/api/documents/{doc_id}/shares", headers=viewer_headers,
                        json={"user_identifier": owner["username"], "role": "reader"}),
        ]
        assert [response.status_code for response in unshared_attempts] == [403] * len(unshared_attempts)
        # Admin metadata privileges do not implicitly grant access to the file bytes.
        assert client.get(f"/api/documents/{doc_id}/download", headers=admin_headers).status_code == 403
        viewer_activity = client.get("/api/activity", headers=viewer_headers).json()
        denial = next(item for item in viewer_activity if item["action"] == "ACCESS_DENIED")
        assert denial["document_name"] is None
        assert f"contract_{suffix}.txt" not in denial["details"]

        grant = client.post(f"/api/documents/{doc_id}/shares", headers=owner_headers,
                            json={"user_identifier": viewer["username"], "role": "reader"})
        assert grant.status_code == 201
        assert client.get("/api/documents", headers=viewer_headers).json()[0]["category"] == "Contracts"
        assert client.get(f"/api/documents/{doc_id}/download", headers=viewer_headers).status_code == 403
        preview_page = client.get(f"/api/documents/{doc_id}/preview-pages/1", headers=viewer_headers)
        assert preview_page.status_code == 200, preview_page.text
        if preview_page.status_code == 200:
            assert preview_page.headers.get("cache-control", "").startswith("no-store")
            viewer_activity_after_page = client.get("/api/activity", headers=viewer_headers).json()
            assert any(item["action"] == "DOCUMENT_PAGE_VIEWED" for item in viewer_activity_after_page)

        # Global admin views include permission changes and events; normal users cannot call them.
        overview = client.get("/api/admin/overview", headers=admin_headers)
        assert overview.status_code == 200, overview.text
        assert overview.json()["audit_valid"] is True
        assert overview.json()["viewers"] >= 1
        permissions = client.get("/api/admin/permissions", headers=admin_headers)
        assert permissions.status_code == 200
        assert any(item["document_id"] == doc_id and item["username"] == viewer["username"] for item in permissions.json())
        admin_events = client.get("/api/admin/activity?action=ACCESS_GRANTED", headers=admin_headers)
        assert admin_events.status_code == 200
        assert any(item["document_name"] == doc["filename"] for item in admin_events.json())

        owner_role_change_blocked = client.patch(f"/api/admin/users/{owner['id']}/role", headers=admin_headers,
                                                 json={"system_role": "viewer"})
        assert owner_role_change_blocked.status_code == 409  # owner must transfer/delete active owned documents first
        role_change = client.patch(f"/api/admin/users/{viewer['id']}/role", headers=admin_headers,
                                   json={"system_role": "owner"})
        assert role_change.status_code == 200, role_change.text
        assert role_change.json()["system_role"] == "owner"
        last_admin_demotion = client.patch(f"/api/admin/users/{admin['id']}/role", headers=admin_headers,
                                           json={"system_role": "owner"})
        # This test creates only one administrator, so self-demotion must be refused.
        assert last_admin_demotion.status_code == 409

        # Database triggers reject ordinary mutation of audit evidence.
        latest = client.get("/api/admin/activity?limit=1", headers=admin_headers).json()[0]
        with api.engine.connect() as connection:
            with connection.begin():
                try:
                    connection.exec_driver_sql("UPDATE audit_events SET details = 'tampered' WHERE id = ?", (latest["id"],))
                except SQLAlchemyError:
                    pass
                else:
                    raise AssertionError("Audit database trigger allowed UPDATE of an event")
        verify = client.get("/api/admin/audit/verify", headers=admin_headers)
        assert verify.status_code == 200, verify.text
        assert verify.json()["valid"] is True

        # Defense-in-depth test: simulate a DB-level actor disabling the ordinary-row trigger.
        # HMAC validation must still notice the modified audit content without the app key.
        with api.engine.begin() as connection:
            original_details = connection.exec_driver_sql(
                "SELECT details FROM audit_events WHERE id = ?", (latest["id"],)
            ).scalar_one()
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql(
                "UPDATE audit_events SET details = ? WHERE id = ?", ("tampered after trigger bypass", latest["id"])
            )
        tampered_verify = client.get("/api/admin/audit/verify", headers=admin_headers)
        assert tampered_verify.status_code == 200
        assert tampered_verify.json()["valid"] is False
        assert tampered_verify.json()["reason"] == "event_hash_mismatch"
        with api.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE audit_events SET details = ? WHERE id = ?", (original_details, latest["id"]))
        api.install_audit_immutability_triggers()
        restored_verify = client.get("/api/admin/audit/verify", headers=admin_headers)
        assert restored_verify.status_code == 200 and restored_verify.json()["valid"] is True


def test_soft_delete_preserves_chained_audit_history_and_revokes_access():
    suffix = str(date.today().toordinal()) + "z"
    with TestClient(app) as client:
        owner, owner_headers = _register(client, f"delowner_{suffix}", f"delowner_{suffix}@test.example", "Delete-Owner-2026!Strong")
        viewer, viewer_headers = _register(client, f"delviewer_{suffix}", f"delviewer_{suffix}@test.example", "Delete-Viewer-2026!Strong")
        uploaded = client.post("/api/documents", headers=owner_headers,
                               files={"file": (f"retained_{suffix}.txt", b"remove this file", "text/plain")},
                               data={"category": "Security"})
        assert uploaded.status_code == 201, uploaded.text
        doc_id = uploaded.json()["id"]
        grant = client.post(f"/api/documents/{doc_id}/shares", headers=owner_headers,
                            json={"user_identifier": viewer["username"], "role": "reader"})
        assert grant.status_code == 201
        assert client.delete(f"/api/documents/{doc_id}", headers=owner_headers).status_code == 204
        assert client.get(f"/api/documents/{doc_id}/download", headers=viewer_headers).status_code == 404
        # Event snapshots preserve the deleted document name without rewriting old audit rows.
        admin = _register(client, f"dela_{suffix}", f"dela_{suffix}@test.example", "Delete-Admin-2026!Strong")
        session = api.SessionLocal()
        try:
            row = session.get(api.User, admin[0]["id"])
            row.system_role = "admin"
            session.commit()
        finally:
            session.close()
        global_events = client.get("/api/admin/activity?limit=500", headers=admin[1]).json()
        assert any(event["action"] == "DOCUMENT_DELETED" and event["document_name"] == uploaded.json()["filename"] for event in global_events)
        verify = client.get("/api/admin/audit/verify", headers=admin[1])
        assert verify.status_code == 200 and verify.json()["valid"] is True
