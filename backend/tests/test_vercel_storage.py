from pathlib import Path

import pytest
from fastapi import HTTPException

import app.main as main


class FakeBlobResult:
    def __init__(self, body: bytes):
        self.body = body


class FakeBlobClient:
    def __init__(self, body: bytes = b"private document bytes"):
        self.body = body
        self.get_calls = []
        self.deleted = []

    def get_blob(self, pathname, *, access):
        self.get_calls.append((pathname, access))
        if self.body is None:
            raise FileNotFoundError(pathname)
        return FakeBlobResult(self.body)

    def delete_blob(self, pathname):
        self.deleted.append(pathname)


def test_vercel_blob_document_is_materialized_only_through_private_sdk(tmp_path, monkeypatch):
    client = FakeBlobClient()
    monkeypatch.setattr(main, "STORAGE_BACKEND", "vercel_blob")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(main, "_blob_sync_client", lambda: client)

    path = main._document_file_path("c0ffee" * 5 + "c0ff")

    assert path.read_bytes() == b"private document bytes"
    assert client.get_calls == [(main._blob_path(path.name), "private")]
    # Cached locally only to /tmp/private scratch; a second read avoids another Blob transfer.
    assert main._document_file_path(path.name) == path
    assert len(client.get_calls) == 1


def test_vercel_blob_missing_document_returns_gone(tmp_path, monkeypatch):
    client = FakeBlobClient()
    client.body = None
    monkeypatch.setattr(main, "STORAGE_BACKEND", "vercel_blob")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(main, "_blob_sync_client", lambda: client)

    with pytest.raises(HTTPException) as error:
        main._document_file_path("missing-key")

    assert error.value.status_code == 410


def test_vercel_blob_delete_removes_remote_and_local_cache(tmp_path, monkeypatch):
    client = FakeBlobClient()
    monkeypatch.setattr(main, "STORAGE_BACKEND", "vercel_blob")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(main, "_blob_sync_client", lambda: client)
    cached = tmp_path / "abc123"
    cached.write_bytes(b"ephemeral cache")

    main._delete_document_file("abc123")

    assert client.deleted == [main._blob_path("abc123")]
    assert not cached.exists()


def test_vercel_production_requires_private_blob_and_small_upload_cap(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "VERCEL_RUNTIME", True)
    monkeypatch.setattr(main, "STORAGE_BACKEND", "filesystem")
    monkeypatch.setattr(main, "TOKEN_SECRET", "Strong-token-secret-0123456789-abcdef")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET", "Strong-audit-secret-ABCDEFGHIJKL-123456")
    monkeypatch.setattr(main, "AUDIT_HMAC_SECRET_EXPLICIT", True)
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql+psycopg://app:D9gx2vT5rQz8mLf3wHs7Kp@db.example.test/db")
    monkeypatch.setattr(main, "FRONTEND_ORIGINS", ["https://docusentra.example.vercel.app"])
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 3_800_000)
    monkeypatch.setenv("BLOB_STORE_ID", "store_test")

    with pytest.raises(RuntimeError, match="STORAGE_BACKEND=vercel_blob"):
        main.validate_runtime_config()

    monkeypatch.setattr(main, "STORAGE_BACKEND", "vercel_blob")
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 4_500_001)
    with pytest.raises(RuntimeError, match="MAX_UPLOAD_BYTES"):
        main.validate_runtime_config()


def test_managed_postgres_urls_use_psycopg_v3_driver():
    assert main.normalize_database_url("postgres://app:pass@host/db") == "postgresql+psycopg://app:pass@host/db"
    assert main.normalize_database_url("postgresql://app:pass@host/db?sslmode=require") == "postgresql+psycopg://app:pass@host/db?sslmode=require"
    local = "postgresql+psycopg://app:pass@host/db"
    assert main.normalize_database_url(local) == local
    assert main.normalize_database_url("sqlite:///./trustvault.db") == "sqlite:///./trustvault.db"


def test_vercel_preview_image_is_jpeg_to_reduce_function_response_size(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image

    source = tmp_path / "large-preview.png"
    Image.new("RGB", (1400, 1800), (245, 245, 245)).save(source, format="PNG")
    monkeypatch.setattr(main, "VERCEL_RUNTIME", True)
    content = main._prepare_preview_image(source)
    with Image.open(BytesIO(content)) as rendered:
        assert rendered.format == "JPEG"
        assert rendered.size == (1400, 1800)


def test_local_preview_image_keeps_png_for_docker_compatibility(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image

    source = tmp_path / "preview.png"
    Image.new("RGB", (180, 200), (245, 245, 245)).save(source, format="PNG")
    monkeypatch.setattr(main, "VERCEL_RUNTIME", False)
    content = main._prepare_preview_image(source)
    with Image.open(BytesIO(content)) as rendered:
        assert rendered.format == "PNG"
