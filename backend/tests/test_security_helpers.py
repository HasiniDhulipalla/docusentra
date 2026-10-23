import base64
import hashlib
import json
import os
import time
import zipfile

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TOKEN_SECRET", "test-secret-that-is-long-enough")

import app.main as main
from app.seed import _resolve_existing_seed_user
from app.main import (
    hash_password,
    verify_password,
    create_token,
    read_token,
    validate_uploaded_content,
    validate_runtime_config,
    RegisterInput,
    _b64,
)


def test_password_hash_and_verify():
    stored = hash_password("correct horse battery staple")
    assert stored != "correct horse battery staple"
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong password", stored)


def test_malformed_password_hash_fails_closed():
    assert not verify_password("anything", "not-a-valid-hash")
    assert not verify_password("anything", "pbkdf2_sha256$not-a-number$abc$def")


def test_token_round_trip():
    token = create_token(123)
    assert read_token(token) == 123


def test_token_tampering_fails():
    token = create_token(123)
    parts = token.split(".")
    parts[1] = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
    with pytest.raises(HTTPException) as error:
        read_token(".".join(parts))
    assert error.value.status_code == 401


def test_expired_token_fails(monkeypatch):
    token = create_token(123)
    real_time = time.time
    monkeypatch.setattr(main.time, "time", lambda: real_time() + 100_000)
    with pytest.raises(HTTPException) as error:
        read_token(token)
    assert error.value.status_code == 401


def test_token_with_wrong_algorithm_fails():
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": "123", "exp": int(time.time()) + 60}, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"
    signature = _b64(main.hmac.new(main.TOKEN_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
    with pytest.raises(HTTPException) as error:
        read_token(f"{unsigned}.{signature}")
    assert error.value.status_code == 401


def test_registration_requires_strong_password_length():
    with pytest.raises(ValidationError):
        RegisterInput(username="test_user", email="test@example.test", password="Short123!")
    with pytest.raises(ValidationError):
        RegisterInput(username="test_user", email="test@example.test", password="123456789012")
    accepted = RegisterInput(username="test_user", email="test@example.test", password="Strong-Enough-123!")
    assert len(accepted.password) >= 12


def test_upload_signature_rejects_spoofed_pdf(tmp_path):
    path = tmp_path / "pretend.pdf"
    path.write_bytes(b"MZ-this-is-not-a-pdf")
    with pytest.raises(HTTPException) as error:
        validate_uploaded_content(path, ".pdf")
    assert error.value.status_code == 415


def test_upload_signature_accepts_pdf_header(tmp_path):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    validate_uploaded_content(path, ".pdf")


def test_upload_signature_rejects_fake_png(tmp_path):
    path = tmp_path / "pretend.png"
    path.write_bytes(b"this is just text")
    with pytest.raises(HTTPException) as error:
        validate_uploaded_content(path, ".png")
    assert error.value.status_code == 415


def test_office_archive_requires_expected_document_parts(tmp_path):
    valid_path = tmp_path / "valid.docx"
    with zipfile.ZipFile(valid_path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    validate_uploaded_content(valid_path, ".docx")

    invalid_path = tmp_path / "wrong.docx"
    with zipfile.ZipFile(invalid_path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(HTTPException) as error:
        validate_uploaded_content(invalid_path, ".docx")
    assert error.value.status_code == 415


def test_office_archive_rejects_path_traversal(tmp_path):
    path = tmp_path / "traversal.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("../outside.txt", "not allowed")
    with pytest.raises(HTTPException) as error:
        validate_uploaded_content(path, ".docx")
    assert error.value.status_code == 415


def test_production_config_rejects_development_defaults(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "TOKEN_SECRET", "local-only-change-this-secret-before-deploying")
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql+psycopg://trustvault:password@db:5432/trustvault")
    with pytest.raises(RuntimeError, match="TOKEN_SECRET"):
        validate_runtime_config()


def test_production_config_accepts_explicit_strong_settings(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "TOKEN_SECRET", "R6fz5C9jXhywJt7q9sK7vR2aH5pW3dN8gL4mB1vF0cQeZ6sA")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET", "a7Vq3Fz6mN9pL2wX5cR8dK1hT4sB0uYjE6gP9nM2vQ5xZ8cD")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET_EXPLICIT", True)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql+psycopg://trustvault:ProdDbPass_8wXqP9R2@db:5432/trustvault")
    monkeypatch.setattr(main, "FRONTEND_ORIGINS", ["https://trustvault.example.org"])
    validate_runtime_config()


def test_production_config_rejects_localhost_only_origins(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "TOKEN_SECRET", "R6fz5C9jXhywJt7q9sK7vR2aH5pW3dN8gL4mB1vF0cQeZ6sA")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET", "a7Vq3Fz6mN9pL2wX5cR8dK1hT4sB0uYjE6gP9nM2vQ5xZ8cD")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET_EXPLICIT", True)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql+psycopg://trustvault:ProdDbPass_8wXqP9R2@db:5432/trustvault")
    monkeypatch.setattr(main, "FRONTEND_ORIGINS", ["http://localhost:8080", "http://127.0.0.1:5173"])
    with pytest.raises(RuntimeError, match="deployed HTTPS frontend origin"):
        validate_runtime_config()


def test_production_config_requires_independent_audit_key(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "TOKEN_SECRET", "R6fz5C9jXhywJt7q9sK7vR2aH5pW3dN8gL4mB1vF0cQeZ6sA")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET", "")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET_EXPLICIT", False)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql+psycopg://trustvault:ProdDbPass_8wXqP9R2@db:5432/trustvault")
    monkeypatch.setattr(main, "FRONTEND_ORIGINS", ["https://trustvault.example.org"])
    with pytest.raises(RuntimeError, match="AUDIT_HMAC_SECRET"):
        validate_runtime_config()


def test_seed_refuses_partial_or_conflicting_identity_collisions():
    from types import SimpleNamespace

    existing = SimpleNamespace(id=1, username="employee", email="employee@example.test")
    other = SimpleNamespace(id=2, username="other", email="other@example.test")

    assert _resolve_existing_seed_user(None, None) is None
    assert _resolve_existing_seed_user(existing, existing) is existing
    with pytest.raises(RuntimeError, match="Seed identity collision"):
        _resolve_existing_seed_user(existing, None)
    with pytest.raises(RuntimeError, match="Seed identity collision"):
        _resolve_existing_seed_user(None, existing)
    with pytest.raises(RuntimeError, match="Seed identity collision"):
        _resolve_existing_seed_user(existing, other)
