"""Regression tests for upgrading the earlier SHA-256 audit-chain format safely."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import app.main as api


def _install_legacy_v1_db(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-audit.sqlite3"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(api, "engine", test_engine)
    monkeypatch.setattr(api, "SessionLocal", TestSession)
    api.Base.metadata.create_all(bind=test_engine)

    with TestSession() as db:
        user = api.User(
            username="legacy_owner", email="legacy_owner@example.test",
            password_hash="test-only-not-a-real-login-hash", system_role="owner",
        )
        db.add(user)
        db.flush()
        previous = api.ZERO_AUDIT_HASH
        moment = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
        for event_id, action in enumerate(("DOCUMENT_UPLOADED", "ACCESS_GRANTED", "DOCUMENT_PREVIEWED"), start=1):
            event = api.AuditEvent(
                id=event_id, actor_id=user.id, document_id=None, action=action,
                target_username="viewer_one", details=f"legacy fixture event {event_id}",
                created_at=moment + timedelta(minutes=event_id), actor_username_snapshot=user.username,
                document_ref=f"document:{event_id}", document_name_snapshot=f"legacy-{event_id}.txt",
                previous_hash=previous,
            )
            event.event_hash = api.calculate_legacy_v1_audit_hash(event)
            previous = event.event_hash
            db.add(event)
        db.add(api.AuditChainHead(id=1, last_event_id=3, head_hash=previous, updated_at=moment))
        db.commit()
    api.install_audit_immutability_triggers()
    return test_engine, TestSession


def test_valid_legacy_v1_chain_is_upgraded_to_hmac_v2_without_losing_events(tmp_path, monkeypatch):
    test_engine, TestSession = _install_legacy_v1_db(tmp_path, monkeypatch)
    try:
        with TestSession() as db:
            legacy = api.verify_legacy_v1_audit_chain(db)
            assert legacy["valid"] is True
            old_events = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id)).all()
            old_details = [event.details for event in old_events]
            old_actions = [event.action for event in old_events]

        api.migrate_or_verify_audit_chain()

        with TestSession() as db:
            result = api.verify_audit_chain(db)
            assert result["valid"] is True
            events = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id)).all()
            assert len(events) == 4  # three original rows plus a migration evidence row
            assert [event.details for event in events[:3]] == old_details
            assert [event.action for event in events[:3]] == old_actions
            assert all(event.event_hash != api.calculate_legacy_v1_audit_hash(event) for event in events[:3])
            migration = events[-1]
            assert migration.action == "AUDIT_CHAIN_MIGRATED_V1_TO_V2"
            assert "prior_head=" in migration.details
            head = db.get(api.AuditChainHead, 1)
            assert head.last_event_id == 4
            assert head.head_hash == events[-1].event_hash

        with test_engine.begin() as connection:
            with pytest.raises(SQLAlchemyError):
                connection.exec_driver_sql("UPDATE audit_events SET details='tamper' WHERE id=1")
    finally:
        test_engine.dispose()


def test_invalid_legacy_v1_chain_is_not_auto_repaired(tmp_path, monkeypatch):
    test_engine, TestSession = _install_legacy_v1_db(tmp_path, monkeypatch)
    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql("UPDATE audit_events SET details='tampered' WHERE id=1")
        api.install_audit_immutability_triggers()

        with TestSession() as db:
            original_hash = db.get(api.AuditEvent, 1).event_hash
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            api.migrate_or_verify_audit_chain()
        with TestSession() as db:
            assert db.get(api.AuditEvent, 1).event_hash == original_hash
            assert api.verify_legacy_v1_audit_chain(db)["valid"] is False
    finally:
        test_engine.dispose()


def _install_token_fallback_v2_db(tmp_path, monkeypatch):
    """Simulate v2 records originally signed with TOKEN_SECRET before independent key setup."""
    db_path = tmp_path / "token-fallback-audit.sqlite3"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(api, "engine", test_engine)
    monkeypatch.setattr(api, "SessionLocal", TestSession)
    old_token_key = "prior-token-key-for-audit-chain-test-2026"
    current_audit_key = "independent-current-audit-key-for-test-2026"
    monkeypatch.setattr(api, "TOKEN_SECRET", old_token_key)
    monkeypatch.setattr(api, "AUDIT_HMAC_SECRET", current_audit_key)
    api.Base.metadata.create_all(bind=test_engine)

    with TestSession() as db:
        user = api.User(
            username="fallback_owner", email="fallback_owner@example.test",
            password_hash="test-only-not-a-real-login-hash", system_role="owner",
        )
        db.add(user)
        db.flush()
        previous = api.ZERO_AUDIT_HASH
        moment = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)
        for event_id, action in enumerate(("DOCUMENT_UPLOADED", "ACCESS_GRANTED", "DOCUMENT_PREVIEWED"), start=1):
            event = api.AuditEvent(
                id=event_id, actor_id=user.id, document_id=None, action=action,
                target_username="viewer_one", details=f"v2 fallback fixture event {event_id}",
                created_at=moment + timedelta(minutes=event_id), actor_username_snapshot=user.username,
                document_ref=f"document:{event_id}", document_name_snapshot=f"fallback-{event_id}.txt",
                previous_hash=previous,
            )
            event.event_hash = api.calculate_audit_hash(event, secret_override=old_token_key)
            previous = event.event_hash
            db.add(event)
        db.add(api.AuditChainHead(id=1, last_event_id=3, head_hash=previous, updated_at=moment))
        db.commit()
    api.install_audit_immutability_triggers()
    return test_engine, TestSession, old_token_key, current_audit_key


def test_valid_token_secret_fallback_v2_chain_is_rekeyed_to_independent_audit_key(tmp_path, monkeypatch):
    test_engine, TestSession, old_token_key, current_audit_key = _install_token_fallback_v2_db(tmp_path, monkeypatch)
    try:
        with TestSession() as db:
            assert api.verify_audit_chain(db)["valid"] is False
            assert api.verify_audit_chain(db, secret_override=old_token_key)["valid"] is True
            old_events = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id)).all()
            old_details = [event.details for event in old_events]
            old_actions = [event.action for event in old_events]
        api.migrate_or_verify_audit_chain()
        with TestSession() as db:
            result = api.verify_audit_chain(db)
            assert result["valid"] is True
            events = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id)).all()
            assert len(events) == 4
            assert [event.details for event in events[:3]] == old_details
            assert [event.action for event in events[:3]] == old_actions
            assert all(event.event_hash == api.calculate_audit_hash(event) for event in events)
            migration = events[-1]
            assert migration.action == "AUDIT_CHAIN_REKEYED_TO_INDEPENDENT_HMAC"
            assert "prior_head=" in migration.details
            assert current_audit_key != old_token_key
            head = db.get(api.AuditChainHead, 1)
            assert head.last_event_id == 4
            assert head.head_hash == migration.event_hash
        with test_engine.begin() as connection:
            with pytest.raises(SQLAlchemyError):
                connection.exec_driver_sql("UPDATE audit_events SET details='tamper' WHERE id=1")
    finally:
        test_engine.dispose()


def test_invalid_token_secret_fallback_v2_chain_is_not_rekeyed(tmp_path, monkeypatch):
    test_engine, TestSession, old_token_key, _current_audit_key = _install_token_fallback_v2_db(tmp_path, monkeypatch)
    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql("UPDATE audit_events SET details='tampered' WHERE id=1")
        api.install_audit_immutability_triggers()
        with TestSession() as db:
            original_hash = db.get(api.AuditEvent, 1).event_hash
            assert api.verify_audit_chain(db, secret_override=old_token_key)["valid"] is False
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            api.migrate_or_verify_audit_chain()
        with TestSession() as db:
            assert db.get(api.AuditEvent, 1).event_hash == original_hash
    finally:
        test_engine.dispose()


def test_explicit_unverified_archive_recovery_preserves_old_rows_and_starts_valid_chain(tmp_path, monkeypatch):
    """Break-glass recovery must archive every old row, flag it unverified, and verify a new chain."""
    test_engine, TestSession, old_token_key, _current_audit_key = _install_token_fallback_v2_db(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "APP_ENV", "development")
    monkeypatch.setenv("TRUSTVAULT_AUDIT_RECOVERY", "archive_unverified")
    try:
        # Corrupt one event after removing the append-only trigger, simulating the user's
        # existing database whose prior hash/key candidates cannot be verified.
        with test_engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql("UPDATE audit_events SET details='not-the-signed-details' WHERE id=1")
        api.install_audit_immutability_triggers()

        with TestSession() as db:
            assert api.verify_audit_chain(db)["valid"] is False
            assert api.verify_legacy_v1_audit_chain(db)["valid"] is False
            old_rows = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id.asc())).all()
            old_hashes = [row.event_hash for row in old_rows]
            old_count = len(old_rows)

        api.migrate_or_verify_audit_chain()

        with TestSession() as db:
            new_chain = api.verify_audit_chain(db)
            assert new_chain["valid"] is True
            current_events = db.scalars(select(api.AuditEvent).order_by(api.AuditEvent.id.asc())).all()
            assert len(current_events) == 1
            assert current_events[0].action == "AUDIT_HISTORY_ARCHIVED_UNVERIFIED"
            assert current_events[0].id == 4

            archives = db.scalars(select(api.AuditEventArchive)).all()
            assert len(archives) == 1
            archive = archives[0]
            assert archive.event_count == old_count
            assert archive.first_event_id == 1
            assert archive.last_event_id == 3
            assert __import__("hashlib").sha256(archive.snapshot_json.encode("utf-8")).hexdigest() == archive.snapshot_sha256
            snapshot = __import__("json").loads(archive.snapshot_json)
            assert [row["event_hash"] for row in snapshot["events"]] == old_hashes
            assert snapshot["events"][0]["details"] == "not-the-signed-details"

        with test_engine.begin() as connection:
            with pytest.raises(SQLAlchemyError):
                connection.exec_driver_sql("UPDATE audit_event_archives SET recovery_reason='hide this' WHERE id=1")
            with pytest.raises(SQLAlchemyError):
                connection.exec_driver_sql("DELETE FROM audit_event_archives WHERE id=1")
    finally:
        test_engine.dispose()


def test_unverified_archive_recovery_is_disabled_in_production(tmp_path, monkeypatch):
    test_engine, TestSession, _old_token_key, _current_audit_key = _install_token_fallback_v2_db(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "APP_ENV", "production")
    monkeypatch.setenv("TRUSTVAULT_AUDIT_RECOVERY", "archive_unverified")
    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql("UPDATE audit_events SET details='not-the-signed-details' WHERE id=1")
        api.install_audit_immutability_triggers()
        with pytest.raises(RuntimeError, match="Refusing to serve"):
            api.migrate_or_verify_audit_chain()
        with TestSession() as db:
            assert db.scalars(select(api.AuditEvent)).all()
            assert db.scalars(select(api.AuditEventArchive)).all() == []
    finally:
        test_engine.dispose()


def test_explicit_recovery_archives_mixed_hashed_and_blank_events(tmp_path, monkeypatch):
    test_engine, TestSession, _old_token_key, _current_audit_key = _install_token_fallback_v2_db(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "APP_ENV", "development")
    monkeypatch.setenv("TRUSTVAULT_AUDIT_RECOVERY", "archive_unverified")
    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
            connection.exec_driver_sql("UPDATE audit_events SET event_hash='' WHERE id=2")
        api.install_audit_immutability_triggers()
        api.migrate_or_verify_audit_chain()
        with TestSession() as db:
            assert api.verify_audit_chain(db)["valid"] is True
            archive = db.scalars(select(api.AuditEventArchive)).one()
            assert archive.event_count == 3
            snapshot = __import__("json").loads(archive.snapshot_json)
            assert snapshot["events"][1]["event_hash"] == ""
            assert db.scalars(select(api.AuditEvent)).one().action == "AUDIT_HISTORY_ARCHIVED_UNVERIFIED"
    finally:
        test_engine.dispose()
