"""TrustVault MVP API: authenticated private document sharing with per-request authorization."""
from __future__ import annotations

import base64
from collections import deque
from contextlib import asynccontextmanager
import hashlib
from io import BytesIO
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import threading
import zipfile
import uuid
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from docx import Document as WordDocument
from docx.table import Table as WordTable
from docx.text.paragraph import Paragraph as WordParagraph
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, or_, select, func, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

def normalize_database_url(value: str) -> str:
    """Normalize common managed-Postgres URLs to the installed psycopg v3 driver."""
    value = (value or "sqlite:///./trustvault.db").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./trustvault.db"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/tmp/docusentra" if os.getenv("VERCEL") else str(BASE_DIR / "private_storage"))).resolve()
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "filesystem").strip().lower()
VERCEL_RUNTIME = os.getenv("VERCEL", "").strip() == "1"
# In local development an ephemeral secret is safer than a known hard-coded key.
# Set TOKEN_SECRET explicitly for any environment where sessions must survive restarts.
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "").strip()
if not TOKEN_SECRET and APP_ENV != "production":
    TOKEN_SECRET = secrets.token_urlsafe(48)
AUDIT_HMAC_SECRET_EXPLICIT = bool(os.getenv("AUDIT_HMAC_SECRET", "").strip())
AUDIT_HMAC_SECRET = os.getenv("AUDIT_HMAC_SECRET", "").strip()
if not AUDIT_HMAC_SECRET and APP_ENV != "production":
    # Local compatibility fallback. The launcher persists an independent value in .env.
    AUDIT_HMAC_SECRET = TOKEN_SECRET
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "28800"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
MAX_PREVIEW_PAGES = int(os.getenv("MAX_PREVIEW_PAGES", "100"))
FRONTEND_ORIGINS = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "10"))
LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
REGISTER_MAX_ATTEMPTS = int(os.getenv("REGISTER_MAX_ATTEMPTS", "10"))
REGISTER_RATE_WINDOW_SECONDS = int(os.getenv("REGISTER_RATE_WINDOW_SECONDS", "3600"))

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".png", ".jpg", ".jpeg"}
UPLOAD_CATEGORIES = {"hr": "HR", "finance": "Finance", "legal": "Legal", "personal": "Personal", "education": "Education", "general": "General", "others": "Others", "security": "Security", "contracts": "Contracts", "engineering": "Engineering", "customer": "Customer", "policy": "Policy"}

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {"connect_timeout": 5}
if VERCEL_RUNTIME:
    # Serverless instances should keep a small pool; Neon pooled URLs are recommended.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=1, max_overflow=0, pool_timeout=5, pool_recycle=300, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # System role and per-document share role are intentionally separate.
    # Admins monitor the system but do not automatically get document-content access.
    system_role: Mapped[str] = mapped_column(String(16), default="owner", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="General", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentShare(Base):
    __tablename__ = "document_shares"
    __table_args__ = (UniqueConstraint("document_id", "user_id", name="uq_document_share_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    target_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # Immutable snapshots avoid changing the cryptographic record when a document is
    # renamed or soft-deleted, or when a user is later disabled.
    actor_username_snapshot: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    document_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    previous_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class AuditChainHead(Base):
    __tablename__ = "audit_chain_head"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_event_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    head_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class AuditEventArchive(Base):
    """Immutable snapshot of a prior audit chain whose authenticity could not be verified.

    Archived rows remain available as evidence, but are explicitly not represented as
    authenticated history. A new HMAC chain references the archive digest.
    """
    __tablename__ = "audit_event_archives"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    recovery_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_head_last_event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    original_head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", value):
            raise ValueError("Username must be 3–32 characters using letters, numbers, dot, underscore, or hyphen.")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        # Length is the primary guard; reject trivial patterns as well.
        normalized = value.strip().lower()
        if len(value) < 12:
            raise ValueError("Password must contain at least 12 characters.")
        if normalized in {"password1234", "password12345", "qwerty123456", "letmein123456", "admin1234567"}:
            raise ValueError("Choose a less predictable password.")
        if re.fullmatch(r"(.)\1{11,}", value) or value.isdigit():
            raise ValueError("Choose a less predictable password.")
        return value


class LoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_new_password(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(value) < 12:
            raise ValueError("New password must contain at least 12 characters.")
        if normalized in {"password1234", "password12345", "qwerty123456", "letmein123456", "admin1234567"}:
            raise ValueError("Choose a less predictable password.")
        if re.fullmatch(r"(.)\1{11,}", value) or value.isdigit():
            raise ValueError("Choose a less predictable password.")
        return value


class ShareInput(BaseModel):
    user_identifier: str = Field(min_length=1, max_length=254)
    role: str = "reader"

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"reader", "editor"}:
            raise ValueError("Role must be reader or editor.")
        return value


class RenameInput(BaseModel):
    filename: str = Field(min_length=1, max_length=200)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        value = Path(value.replace("\\", "/")).name.strip()
        if not value or value in {".", ".."} or any(ord(c) < 32 for c in value):
            raise ValueError("Enter a valid document name.")
        return value[:200]


class RoleChangeInput(BaseModel):
    system_role: str

    @field_validator("system_role")
    @classmethod
    def valid_system_role(cls, value: str) -> str:
        if value not in {"admin", "owner", "viewer"}:
            raise ValueError("Role must be admin, owner, or viewer.")
        return value


bearer = HTTPBearer(auto_error=False)


def validate_runtime_config() -> None:
    """Fail closed on known development defaults when APP_ENV=production."""
    if TOKEN_TTL_SECONDS < 60 or TOKEN_TTL_SECONDS > 24 * 60 * 60:
        raise RuntimeError("TOKEN_TTL_SECONDS must be between 60 seconds and 24 hours.")
    if MAX_UPLOAD_BYTES < 1 or MAX_UPLOAD_BYTES > 100 * 1024 * 1024:
        raise RuntimeError("MAX_UPLOAD_BYTES must be between 1 byte and 100 MB.")
    if VERCEL_RUNTIME and APP_ENV == "production" and MAX_UPLOAD_BYTES > 4_000_000:
        raise RuntimeError("On Vercel, set MAX_UPLOAD_BYTES to 4000000 or less because Function request bodies are limited to 4.5 MB.")
    if APP_ENV == "production":
        lowered_secret = TOKEN_SECRET.lower()
        if len(TOKEN_SECRET) < 32 or len(set(TOKEN_SECRET)) < 12 or any(marker in lowered_secret for marker in ("change-me", "replace-this", "local-only", "example", "secret-here", "password", "default")):
            raise RuntimeError("Production requires a unique, high-entropy TOKEN_SECRET of at least 32 characters; do not use a development placeholder.")
        lowered_audit_secret = AUDIT_HMAC_SECRET.lower()
        if (not AUDIT_HMAC_SECRET_EXPLICIT or len(AUDIT_HMAC_SECRET) < 32 or len(set(AUDIT_HMAC_SECRET)) < 12
                or any(marker in lowered_audit_secret for marker in ("change-me", "replace-this", "local-only", "example", "secret-here", "password", "default"))
                or hmac.compare_digest(AUDIT_HMAC_SECRET, TOKEN_SECRET)):
            raise RuntimeError("Production requires an independent AUDIT_HMAC_SECRET of at least 32 high-entropy characters, different from TOKEN_SECRET.")
        if DATABASE_URL.lower().startswith("sqlite"):
            raise RuntimeError("Production requires PostgreSQL or another supported server database, not SQLite.")
        try:
            database_url = make_url(DATABASE_URL)
            database_password = database_url.password or ""
        except Exception as exc:
            raise RuntimeError("Production DATABASE_URL is invalid.") from exc
        lowered_db_password = database_password.lower()
        if len(database_password) < 16 or len(set(database_password)) < 8 or any(marker in lowered_db_password for marker in ("trustvault_local", "change-this", "password", "example", "default")):
            raise RuntimeError("Production DATABASE_URL must use a unique database password of at least 16 characters; development defaults are not allowed.")
        if not FRONTEND_ORIGINS or "*" in FRONTEND_ORIGINS:
            raise RuntimeError("Production FRONTEND_ORIGINS must list explicit trusted origins.")
        if all(origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1") for origin in FRONTEND_ORIGINS):
            raise RuntimeError("Production FRONTEND_ORIGINS must list the deployed HTTPS frontend origin, not only localhost.")
        if VERCEL_RUNTIME and STORAGE_BACKEND != "vercel_blob":
            raise RuntimeError("Vercel deployment requires STORAGE_BACKEND=vercel_blob; function filesystems are ephemeral.")
        if VERCEL_RUNTIME and not (os.getenv("BLOB_STORE_ID") or os.getenv("BLOB_READ_WRITE_TOKEN") or os.getenv("VERCEL_BLOB_READ_WRITE_TOKEN")):
            raise RuntimeError("Connect a private Vercel Blob store to this project before starting the API.")


def _uses_vercel_blob() -> bool:
    return STORAGE_BACKEND == "vercel_blob"


def _blob_path(storage_key: str) -> str:
    # The database stores only a random opaque key; never use a user-supplied filename as a Blob path.
    return f"docusentra/documents/{storage_key}"


def _blob_sync_client():
    try:
        from vercel.blob import sync as blob_sync
    except ImportError as exc:
        raise RuntimeError("Install the official vercel Python SDK to use Vercel private storage.") from exc
    return blob_sync


def _document_file_path(storage_key: str) -> Path:
    """Resolve a document to a private local path, downloading private Blob data to /tmp when deployed on Vercel.

    Authorization must be checked by the caller before calling this helper. The local cache is temporary and is
    never exposed as a public/static directory. Blob objects stay private and the SDK token is server-side only.
    """
    path = STORAGE_DIR / storage_key
    if not _uses_vercel_blob():
        return path
    if path.is_file() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _blob_sync_client().get_blob(_blob_path(storage_key), access="private")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail="The stored document is no longer available.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Private document storage is temporarily unavailable.") from exc
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(result.body)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _delete_document_file(storage_key: str) -> None:
    """Delete the private original from configured storage and remove any ephemeral local cache."""
    if _uses_vercel_blob():
        try:
            _blob_sync_client().delete_blob(_blob_path(storage_key))
        except FileNotFoundError:
            pass
        except Exception as exc:
            # A deleted DB row remains inaccessible even if storage cleanup must be retried operationally.
            raise HTTPException(status_code=503, detail="The document was deleted from the library, but private storage cleanup failed.") from exc
    (STORAGE_DIR / storage_key).unlink(missing_ok=True)


ZERO_AUDIT_HASH = "0" * 64


def _canonical_audit_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def calculate_audit_hash(event: AuditEvent, secret_override: str | None = None) -> str:
    """Keyed HMAC over stable event fields, not mutable foreign-key display fields.

    secret_override is used only by the fail-closed migration verifier to validate a
    historical chain created before an independent AUDIT_HMAC_SECRET was configured.
    New or migrated events always use the current AUDIT_HMAC_SECRET.
    """
    payload = {
        "v": 2,
        "id": event.id,
        "previous_hash": event.previous_hash or ZERO_AUDIT_HASH,
        "actor_id": event.actor_id,
        "actor": event.actor_username_snapshot or "system",
        "document_id": event.document_id,
        "document_ref": event.document_ref or "",
        "document_name": event.document_name_snapshot or "",
        "action": event.action,
        "target_username": event.target_username or "",
        "details": event.details or "",
        "created_at": _canonical_audit_timestamp(event.created_at),
    }
    packed = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signing_secret = AUDIT_HMAC_SECRET if secret_override is None else secret_override
    return hmac.new(signing_secret.encode("utf-8"), packed, hashlib.sha256).hexdigest()


def calculate_legacy_v1_audit_hash(event: AuditEvent) -> str:
    """Reproduce the pre-HMAC v1 hash exactly for a verified one-time migration.

    Legacy hashes were plain SHA-256. They are accepted only as a complete,
    internally consistent legacy chain and are immediately re-chained with the
    current keyed v2 HMAC; the verifier never allows v1 hashes after migration.
    """
    payload = {
        "v": 1,
        "id": event.id,
        "previous_hash": event.previous_hash or ZERO_AUDIT_HASH,
        "actor": event.actor_username_snapshot or "system",
        "document_ref": event.document_ref or "",
        "document_name": event.document_name_snapshot or "",
        "action": event.action,
        "target_username": event.target_username or "",
        "details": event.details or "",
        "created_at": _canonical_audit_timestamp(event.created_at),
    }
    packed = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(packed).hexdigest()


def verify_legacy_v1_audit_chain(db: Session) -> dict:
    """Verify the whole pre-HMAC v1 chain before allowing a one-time upgrade."""
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
    head = db.get(AuditChainHead, 1)
    previous = ZERO_AUDIT_HASH
    for event in events:
        if event.previous_hash != previous:
            return {"valid": False, "events_checked": max(0, event.id - 1), "failed_event_id": event.id, "reason": "previous_hash_mismatch"}
        expected = calculate_legacy_v1_audit_hash(event)
        if not event.event_hash or not hmac.compare_digest(event.event_hash, expected):
            return {"valid": False, "events_checked": max(0, event.id - 1), "failed_event_id": event.id, "reason": "legacy_event_hash_mismatch"}
        previous = event.event_hash
    expected_last_id = events[-1].id if events else 0
    if not head or head.last_event_id != expected_last_id or not hmac.compare_digest(head.head_hash if head else "", previous):
        return {"valid": False, "events_checked": len(events), "failed_event_id": None, "reason": "chain_head_mismatch"}
    return {"valid": True, "events_checked": len(events), "failed_event_id": None, "reason": None, "last_hash": previous}


def _drop_audit_immutability_triggers(connection) -> None:
    """Temporarily remove append-only triggers inside the verified migration transaction."""
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_update")
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_no_delete")
    elif engine.dialect.name == "postgresql":
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_immutable ON audit_events")


def _create_audit_immutability_triggers(connection) -> None:
    """Restore append-only triggers before the migration transaction commits."""
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS trustvault_audit_no_update "
            "BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS trustvault_audit_no_delete "
            "BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END"
        )
    elif engine.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION trustvault_block_audit_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER trustvault_audit_immutable BEFORE UPDATE OR DELETE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION trustvault_block_audit_mutation()"
        )


def apply_legacy_schema_migrations() -> None:
    """Add columns to existing SQLite/PostgreSQL installs without dropping user data."""
    columns_to_add = {
        "users": {
            "system_role": ("VARCHAR(16) NOT NULL DEFAULT 'owner'", "VARCHAR(16) NOT NULL DEFAULT 'owner'"),
        },
        "documents": {
            "category": ("VARCHAR(80) NOT NULL DEFAULT 'General'", "VARCHAR(80) NOT NULL DEFAULT 'General'"),
            "deleted_at": ("DATETIME NULL", "TIMESTAMP WITH TIME ZONE NULL"),
        },
        "audit_events": {
            "actor_username_snapshot": ("VARCHAR(32) NOT NULL DEFAULT 'system'", "VARCHAR(32) NOT NULL DEFAULT 'system'"),
            "document_ref": ("VARCHAR(80) NULL", "VARCHAR(80) NULL"),
            "document_name_snapshot": ("VARCHAR(200) NULL", "VARCHAR(200) NULL"),
            "previous_hash": (f"VARCHAR(64) NOT NULL DEFAULT '{ZERO_AUDIT_HASH}'", f"VARCHAR(64) NOT NULL DEFAULT '{ZERO_AUDIT_HASH}'"),
            "event_hash": ("VARCHAR(64) NOT NULL DEFAULT ''", "VARCHAR(64) NOT NULL DEFAULT ''"),
        },
    }
    dialect = engine.dialect.name
    # Use the transaction's checked-out connection for all schema introspection.
    # On serverless deployments the pool may be size 1; inspect(engine) inside
    # engine.begin() checks out a second connection and deadlocks until pool_timeout.
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, additions in columns_to_add.items():
            if not inspector.has_table(table_name):
                continue
            present = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, (sqlite_ddl, postgres_ddl) in additions.items():
                if column_name in present:
                    continue
                ddl = postgres_ddl if dialect == "postgresql" else sqlite_ddl
                if dialect == "postgresql":
                    connection.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {ddl}')
                else:
                    connection.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}')


def verify_audit_chain(db: Session, secret_override: str | None = None) -> dict:
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
    head = db.get(AuditChainHead, 1)
    previous = ZERO_AUDIT_HASH
    for event in events:
        if event.previous_hash != previous:
            return {"valid": False, "events_checked": max(0, event.id - 1), "failed_event_id": event.id, "reason": "previous_hash_mismatch"}
        expected = calculate_audit_hash(event, secret_override=secret_override)
        if not event.event_hash or not hmac.compare_digest(event.event_hash, expected):
            return {"valid": False, "events_checked": max(0, event.id - 1), "failed_event_id": event.id, "reason": "event_hash_mismatch"}
        previous = event.event_hash
    expected_last_id = events[-1].id if events else 0
    if not head or head.last_event_id != expected_last_id or not hmac.compare_digest(head.head_hash if head else "", previous):
        return {"valid": False, "events_checked": len(events), "failed_event_id": None, "reason": "chain_head_mismatch"}
    return {"valid": True, "events_checked": len(events), "failed_event_id": None, "reason": None, "last_hash": previous}


def _audit_archive_snapshot(events: list[AuditEvent], head: AuditChainHead | None, reason: str, archived_at: datetime) -> tuple[str, str]:
    """Create deterministic, lossless JSON of unverifiable audit rows and the claimed head."""
    rows = []
    for event in events:
        rows.append({
            "id": event.id,
            "actor_id": event.actor_id,
            "document_id": event.document_id,
            "action": event.action,
            "target_username": event.target_username,
            "details": event.details,
            "created_at": _canonical_audit_timestamp(event.created_at),
            "actor_username_snapshot": event.actor_username_snapshot,
            "document_ref": event.document_ref,
            "document_name_snapshot": event.document_name_snapshot,
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
        })
    manifest = {
        "format": "trustvault-unverified-audit-archive-v1",
        "archived_at": _canonical_audit_timestamp(archived_at),
        "recovery_reason": reason,
        "event_count": len(rows),
        "first_event_id": rows[0]["id"] if rows else None,
        "last_event_id": rows[-1]["id"] if rows else None,
        "original_head_last_event_id": int(head.last_event_id) if head else 0,
        "original_head_hash": head.head_hash if head else ZERO_AUDIT_HASH,
        "events": rows,
    }
    packed = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(packed.encode("utf-8")).hexdigest()
    return packed, digest


def archive_unverifiable_audit_history(db: Session, head: AuditChainHead | None, events: list[AuditEvent], reason: str) -> dict:
    """Explicit break-glass recovery: preserve old rows as UNVERIFIED, then start a new chain.

    This must never run automatically in production. The operator enables it only after
    taking a database backup and confirming the prompt in recover-audit-chain.ps1.
    The archived event JSON is immutable and its digest is anchored in the new HMAC chain.
    """
    if APP_ENV == "production":
        raise RuntimeError("Unverifiable audit-history recovery is disabled in production.")
    if os.getenv("TRUSTVAULT_AUDIT_RECOVERY", "").strip() != "archive_unverified":
        raise RuntimeError("Set TRUSTVAULT_AUDIT_RECOVERY=archive_unverified only after a verified database backup and explicit operator approval.")

    now = now_utc()
    original_head_last_id = int(head.last_event_id) if head else 0
    original_head_hash = head.head_hash if head else ZERO_AUDIT_HASH
    old_ids = [event.id for event in events]
    next_event_id = max([original_head_last_id, *old_ids], default=0) + 1
    snapshot_json, snapshot_sha256 = _audit_archive_snapshot(events, head, reason, now)
    try:
        manifest = json.loads(snapshot_json)
        archive = AuditEventArchive(
            archived_at=now,
            recovery_reason=reason[:500],
            event_count=len(events),
            first_event_id=manifest["first_event_id"],
            last_event_id=manifest["last_event_id"],
            original_head_last_event_id=original_head_last_id,
            original_head_hash=original_head_hash,
            snapshot_sha256=snapshot_sha256,
            snapshot_json=snapshot_json,
        )
        db.add(archive)
        db.flush()

        connection = db.connection()
        _drop_audit_immutability_triggers(connection)
        connection.exec_driver_sql("DELETE FROM audit_events")
        db.expire_all()

        if head is None:
            head = AuditChainHead(id=1, last_event_id=0, head_hash=ZERO_AUDIT_HASH, updated_at=now)
            db.add(head)
            db.flush()

        details = (
            "Prior audit events failed all available cryptographic verifiers; original rows were preserved "
            f"as UNVERIFIED archive_id={archive.id}; event_count={len(events)}; "
            f"snapshot_sha256={snapshot_sha256}; original_head_id={original_head_last_id}; "
            f"original_head_hash={original_head_hash}. Do not treat archived events as authenticated."
        )[:500]
        recovery_event = AuditEvent(
            id=next_event_id,
            actor_id=None,
            document_id=None,
            action="AUDIT_HISTORY_ARCHIVED_UNVERIFIED",
            target_username=None,
            details=details,
            created_at=now,
            actor_username_snapshot="system",
            document_ref=None,
            document_name_snapshot=None,
            previous_hash=ZERO_AUDIT_HASH,
        )
        recovery_event.event_hash = calculate_audit_hash(recovery_event)
        db.add(recovery_event)
        db.flush()
        head.last_event_id = recovery_event.id
        head.head_hash = recovery_event.event_hash
        head.updated_at = now
        _create_audit_immutability_triggers(connection)
        _create_audit_archive_immutability_triggers(connection)
        db.commit()
    except Exception:
        db.rollback()
        raise

    with SessionLocal() as verify_db:
        new_chain = verify_audit_chain(verify_db)
        archived = verify_db.get(AuditEventArchive, archive.id)
        archive_integrity = bool(archived and hashlib.sha256(archived.snapshot_json.encode("utf-8")).hexdigest() == archived.snapshot_sha256)
    if not new_chain["valid"] or not archive_integrity:
        raise RuntimeError("Audit recovery post-check failed. The old chain remains archived; do not delete the database volume.")
    return {"archive_id": archive.id, "archived_events": len(events), "snapshot_sha256": snapshot_sha256, "new_chain_valid": True, "archive_digest_valid": True}


def _create_audit_archive_immutability_triggers(connection) -> None:
    if engine.dialect.name == "sqlite":
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS trustvault_audit_archive_no_update "
            "BEFORE UPDATE ON audit_event_archives BEGIN SELECT RAISE(ABORT, 'audit_event_archives is append-only'); END"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS trustvault_audit_archive_no_delete "
            "BEFORE DELETE ON audit_event_archives BEGIN SELECT RAISE(ABORT, 'audit_event_archives is append-only'); END"
        )
    elif engine.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION trustvault_block_audit_archive_mutation() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_event_archives is append-only'; END; $$ LANGUAGE plpgsql"
        )
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_archive_immutable ON audit_event_archives")
        connection.exec_driver_sql(
            "CREATE TRIGGER trustvault_audit_archive_immutable BEFORE UPDATE OR DELETE ON audit_event_archives "
            "FOR EACH ROW EXECUTE FUNCTION trustvault_block_audit_archive_mutation()"
        )


def migrate_or_verify_audit_chain() -> None:
    """Chain legacy events only for an untouched legacy DB; never silently repair a partial chain."""
    with SessionLocal() as db:
        head = db.get(AuditChainHead, 1)
        if head is None:
            head = AuditChainHead(id=1, last_event_id=0, head_hash=ZERO_AUDIT_HASH, updated_at=now_utc())
            db.add(head)
            db.commit()
            db.refresh(head)
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
        if events and all(not event.event_hash for event in events):
            # Auto-chain only if this is a true legacy database whose newly-created head
            # has never recorded a chain. If the head existed, blank hashes are tampering.
            if head.last_event_id != 0 or head.head_hash != ZERO_AUDIT_HASH:
                if os.getenv("TRUSTVAULT_AUDIT_RECOVERY", "").strip() == "archive_unverified" and APP_ENV != "production":
                    recovery = archive_unverifiable_audit_history(
                        db, head, events, "All event hashes were blank while the chain head was populated."
                    )
                    if not recovery.get("new_chain_valid") or not recovery.get("archive_digest_valid"):
                        raise RuntimeError("Audit chain recovery post-check failed. Refusing to serve.")
                    return
                raise RuntimeError("Audit chain is incomplete while its head is populated. Refusing to auto-repair it.")
            previous = ZERO_AUDIT_HASH
            for event in events:
                actor = db.get(User, event.actor_id) if event.actor_id else None
                document = db.get(Document, event.document_id) if event.document_id else None
                event.actor_username_snapshot = actor.username if actor else "system"
                if event.document_ref is None and event.document_id is not None:
                    event.document_ref = f"document:{event.document_id}"
                if event.document_name_snapshot is None and document:
                    event.document_name_snapshot = document.filename
                event.previous_hash = previous
                event.event_hash = calculate_audit_hash(event)
                previous = event.event_hash
            head.last_event_id = events[-1].id
            head.head_hash = previous
            head.updated_at = now_utc()
            db.commit()
        elif any(not event.event_hash for event in events):
            if os.getenv("TRUSTVAULT_AUDIT_RECOVERY", "").strip() == "archive_unverified" and APP_ENV != "production":
                recovery = archive_unverifiable_audit_history(
                    db, head, events, "Audit chain contained a mixture of hashed and unhashed events."
                )
                if not recovery.get("new_chain_valid") or not recovery.get("archive_digest_valid"):
                    raise RuntimeError("Audit chain recovery post-check failed. Refusing to serve.")
                return
            raise RuntimeError("Audit chain contains a mixture of hashed and unhashed events. Refusing to serve until reviewed.")

        result = verify_audit_chain(db)
        if not result["valid"]:
            # The prior release used SHA-256 audit hash version 1. Validate the
            # entire legacy chain (including its head) before any mutation. If it
            # does not validate, do not rewrite anything: this can be tampering or
            # an incorrect AUDIT_HMAC_SECRET for an already-v2 database.
            legacy_result = verify_legacy_v1_audit_chain(db)
            legacy_events = db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
            if legacy_events and legacy_result["valid"]:
                connection = db.connection()
                _drop_audit_immutability_triggers(connection)
                legacy_head_hash = legacy_result["last_hash"]
                previous = ZERO_AUDIT_HASH
                for event in legacy_events:
                    event.previous_hash = previous
                    event.event_hash = calculate_audit_hash(event)
                    previous = event.event_hash
                head = db.get(AuditChainHead, 1)
                # Record the verified format migration itself as the first event
                # written in the new HMAC format, preserving the old chain root
                # as evidence rather than silently rewriting history.
                migration_event = AuditEvent(
                    id=legacy_events[-1].id + 1,
                    actor_id=None,
                    document_id=None,
                    action="AUDIT_CHAIN_MIGRATED_V1_TO_V2",
                    target_username=None,
                    details=(
                        f"Verified legacy v1 SHA-256 chain upgraded to v2 HMAC; "
                        f"migrated_events={len(legacy_events)}; prior_head={legacy_head_hash}"
                    )[:500],
                    created_at=now_utc(),
                    actor_username_snapshot="system",
                    document_ref=None,
                    document_name_snapshot=None,
                    previous_hash=previous,
                )
                migration_event.event_hash = calculate_audit_hash(migration_event)
                db.add(migration_event)
                previous = migration_event.event_hash
                head.last_event_id = migration_event.id
                head.head_hash = previous
                head.updated_at = migration_event.created_at
                db.flush()
                _create_audit_immutability_triggers(connection)
                db.commit()
                result = verify_audit_chain(db)
                if not result["valid"]:
                    raise RuntimeError(f"Audit chain failed verification immediately after verified v1-to-v2 migration: {result.get('reason')} at event {result.get('failed_event_id')}.")
            elif legacy_events and TOKEN_SECRET and not hmac.compare_digest(TOKEN_SECRET, AUDIT_HMAC_SECRET):
                # A transitional development release used TOKEN_SECRET as the audit
                # HMAC key when AUDIT_HMAC_SECRET was blank. The launcher later wrote
                # a separate audit key, which makes otherwise intact v2 rows fail the
                # current-key check. Accept only a fully verified old-key chain, then
                # re-key all rows under the current independent audit key atomically.
                fallback_result = verify_audit_chain(db, secret_override=TOKEN_SECRET)
                if not fallback_result["valid"]:
                    if os.getenv("TRUSTVAULT_AUDIT_RECOVERY", "").strip() == "archive_unverified" and APP_ENV != "production":
                        recovery = archive_unverifiable_audit_history(
                            db,
                            head,
                            legacy_events,
                            reason=(
                                f"Current HMAC failed ({result.get('reason')}); legacy SHA-256 failed "
                                f"({legacy_result.get('reason')}); TOKEN_SECRET HMAC failed "
                                f"({fallback_result.get('reason')})."
                            ),
                        )
                        if not recovery.get("new_chain_valid") or not recovery.get("archive_digest_valid"):
                            raise RuntimeError("Audit chain recovery post-check failed. Refusing to serve.")
                    else:
                        raise RuntimeError(
                            f"Audit chain verification failed: {result.get('reason')} at event {result.get('failed_event_id')}. "
                            f"Legacy v1 verification also failed ({legacy_result.get('reason')}); "
                            f"TOKEN_SECRET-keyed v2 verification also failed ({fallback_result.get('reason')}). "
                            "Refusing to serve. Do not delete the database volume or regenerate secrets. "
                            "Restore the original keys, or run the explicit local archive-recovery script after backup."
                        )
                else:
                    connection = db.connection()
                    _drop_audit_immutability_triggers(connection)
                    prior_head_hash = fallback_result["last_hash"]
                    previous = ZERO_AUDIT_HASH
                    for event in legacy_events:
                        event.previous_hash = previous
                        event.event_hash = calculate_audit_hash(event)
                        previous = event.event_hash
                    migration_event = AuditEvent(
                        id=legacy_events[-1].id + 1,
                        actor_id=None,
                        document_id=None,
                        action="AUDIT_CHAIN_REKEYED_TO_INDEPENDENT_HMAC",
                        target_username=None,
                        details=(
                            "Verified prior v2 HMAC chain signed with TOKEN_SECRET fallback and re-keyed "
                            f"to independent AUDIT_HMAC_SECRET; migrated_events={len(legacy_events)}; "
                            f"prior_head={prior_head_hash}"
                        )[:500],
                        created_at=now_utc(),
                        actor_username_snapshot="system",
                        document_ref=None,
                        document_name_snapshot=None,
                        previous_hash=previous,
                    )
                    migration_event.event_hash = calculate_audit_hash(migration_event)
                    db.add(migration_event)
                    previous = migration_event.event_hash
                    head = db.get(AuditChainHead, 1)
                    head.last_event_id = migration_event.id
                    head.head_hash = previous
                    head.updated_at = migration_event.created_at
                    db.flush()
                    _create_audit_immutability_triggers(connection)
                    _create_audit_archive_immutability_triggers(connection)
                    db.commit()
                    result = verify_audit_chain(db)
                    if not result["valid"]:
                        raise RuntimeError(
                            "Audit chain failed verification immediately after re-keying the verified TOKEN_SECRET fallback chain: "
                            f"{result.get('reason')} at event {result.get('failed_event_id')}."
                        )
            elif os.getenv("TRUSTVAULT_AUDIT_RECOVERY", "").strip() == "archive_unverified" and APP_ENV != "production":
                recovery = archive_unverifiable_audit_history(
                    db,
                    head,
                    legacy_events,
                    reason=(
                        f"Startup verifier failed ({result.get('reason')}); legacy verifier failed "
                        f"({legacy_result.get('reason')}); previous key candidates were unavailable or invalid."
                    ),
                )
                if not recovery.get("new_chain_valid") or not recovery.get("archive_digest_valid"):
                    raise RuntimeError("Audit chain recovery post-check failed. Refusing to serve.")
            else:
                raise RuntimeError(
                    f"Audit chain verification failed: {result.get('reason')} at event {result.get('failed_event_id')}. "
                    f"Legacy v1 verification also failed ({legacy_result.get('reason')}). "
                    "No valid prior key was available. Refusing to serve. Do not delete the database volume or regenerate secrets. "
                    "Back up the database, restore the original key if available, or run the explicit development-only "
                    "archive recovery script to preserve the old chain as UNVERIFIED before starting a new chain."
                )


def install_audit_immutability_triggers() -> None:
    """Prevent ordinary SQL UPDATE/DELETE against audit rows at the database layer."""
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS trustvault_audit_no_update "
                "BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END"
            )
            connection.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS trustvault_audit_no_delete "
                "BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END"
            )
        elif engine.dialect.name == "postgresql":
            connection.exec_driver_sql(
                "CREATE OR REPLACE FUNCTION trustvault_block_audit_mutation() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql"
            )
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS trustvault_audit_immutable ON audit_events")
            connection.exec_driver_sql(
                "CREATE TRIGGER trustvault_audit_immutable BEFORE UPDATE OR DELETE ON audit_events "
                "FOR EACH ROW EXECUTE FUNCTION trustvault_block_audit_mutation()"
            )
        _create_audit_archive_immutability_triggers(connection)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    apply_legacy_schema_migrations()
    migrate_or_verify_audit_chain()
    install_audit_immutability_triggers()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    yield


app = FastAPI(
    title="DocuSentra API",
    description="Private document sharing with server-side authorization and audit events.",
    version="1.1.0",
    docs_url=None if APP_ENV == "production" else "/docs",
    redoc_url=None if APP_ENV == "production" else "/redoc",
    openapi_url=None if APP_ENV == "production" else "/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "pbkdf2_sha256${}${}${}".format(rounds, base64.urlsafe_b64encode(salt).decode().rstrip("="), base64.urlsafe_b64encode(digest).decode().rstrip("="))


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds_s, salt_s, expected_s = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_s + "=" * (-len(salt_s) % 4))
        expected = base64.urlsafe_b64decode(expected_s + "=" * (-len(expected_s) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds_s))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def create_token(user_id: int) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": str(user_id), "exp": int(time.time()) + TOKEN_TTL_SECONDS}, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"
    signature = _b64(hmac.new(TOKEN_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
    return f"{unsigned}.{signature}"


def read_token(token: str) -> int:
    try:
        header, payload, signature = token.split(".")
        expected = _b64(hmac.new(TOKEN_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Bad signature")
        header_data = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        if not isinstance(header_data, dict) or header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            raise ValueError("Unsupported token header")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(data, dict):
            raise ValueError("Invalid token payload")
        expires_at = data.get("exp")
        if not isinstance(expires_at, int) or expires_at <= int(time.time()):
            raise ValueError("Expired or invalid expiry")
        subject = data.get("sub")
        if not isinstance(subject, (str, int)) or not str(subject).isdigit() or int(subject) <= 0:
            raise ValueError("Invalid subject")
        return int(subject)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please sign in again.") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    user_id = read_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session user no longer exists.")
    if user.system_role not in {"admin", "owner", "viewer"}:
        record_event(db, user.id, None, "ACCESS_DENIED", "Account has an invalid system role; access was denied.")
        db.commit()
        raise HTTPException(status_code=403, detail="Account role is invalid. Contact an administrator.")
    return user


# Single-process sliding-window limits are a useful local baseline. Public multi-instance
# deployments should back these counters with a shared limiter (for example Redis).
_RATE_LOCK = threading.Lock()
_RATE_EVENTS: dict[str, deque[float]] = {}


def request_client_key(request: Request) -> str:
    # The local Compose deployment only exposes the API on loopback and Nginx overwrites
    # X-Real-IP. Do not expose port 8000 directly on a public network.
    client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    return client_ip.strip()[:128] or "unknown"


def _prune_rate_bucket(bucket_key: str, now: float, window_seconds: int) -> deque[float]:
    events = _RATE_EVENTS.get(bucket_key, deque())
    cutoff = now - window_seconds
    while events and events[0] <= cutoff:
        events.popleft()
    _RATE_EVENTS[bucket_key] = events
    return events


def _bound_rate_limit_memory(now: float, window_seconds: int) -> None:
    if len(_RATE_EVENTS) > 10_000:
        stale_cutoff = now - max(window_seconds, REGISTER_RATE_WINDOW_SECONDS)
        for stored_key in list(_RATE_EVENTS.keys())[:2_000]:
            stored = _RATE_EVENTS[stored_key]
            while stored and stored[0] <= stale_cutoff:
                stored.popleft()
            if not stored:
                _RATE_EVENTS.pop(stored_key, None)


def ensure_not_rate_limited(scope: str, key: str, *, limit: int, window_seconds: int) -> None:
    """Reject a locked-out client before performing the expensive password hash check."""
    now = time.monotonic()
    bucket_key = f"{scope}:{key}"
    with _RATE_LOCK:
        events = _prune_rate_bucket(bucket_key, now, window_seconds)
        _bound_rate_limit_memory(now, window_seconds)
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])))
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )


def check_rate_limit(scope: str, key: str, *, limit: int, window_seconds: int) -> None:
    """Atomically check and reserve a request slot in a sliding window."""
    now = time.monotonic()
    bucket_key = f"{scope}:{key}"
    with _RATE_LOCK:
        events = _prune_rate_bucket(bucket_key, now, window_seconds)
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])))
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )
        events.append(now)
        _RATE_EVENTS[bucket_key] = events
        _bound_rate_limit_memory(now, window_seconds)


def clear_rate_limit(scope: str, key: str) -> None:
    with _RATE_LOCK:
        _RATE_EVENTS.pop(f"{scope}:{key}", None)


def record_event(db: Session, actor_id: int | None, document_id: int | None, action: str,
                 details: str = "", target_username: str | None = None,
                 *, expose_document_snapshot: bool = True) -> None:
    """Append a hash-chained audit event inside the caller's transaction.

    A singleton chain-head row serializes writers in PostgreSQL. Event IDs are allocated
    from the same locked row so the hash order cannot diverge from the append order.
    """
    head = db.scalar(select(AuditChainHead).where(AuditChainHead.id == 1).with_for_update())
    if head is None:
        raise RuntimeError("Audit chain head is not initialized; refuse to write an unchained event.")
    actor = db.get(User, actor_id) if actor_id is not None else None
    document = db.get(Document, document_id) if document_id is not None else None
    safe_document_ref = f"document:{document_id}" if (document_id is not None and expose_document_snapshot) else None
    event = AuditEvent(
        id=max(head.last_event_id, db.scalar(select(func.max(AuditEvent.id))) or 0) + 1,
        actor_id=actor_id,
        document_id=document_id,
        action=action,
        target_username=target_username,
        details=details[:500],
        created_at=now_utc(),
        actor_username_snapshot=actor.username if actor else "system",
        document_ref=safe_document_ref,
        document_name_snapshot=document.filename if document and expose_document_snapshot else None,
        previous_hash=head.head_hash,
    )
    event.event_hash = calculate_audit_hash(event)
    head.last_event_id = event.id
    head.head_hash = event.event_hash
    head.updated_at = event.created_at
    db.add(event)
    db.flush()


def get_document_or_404(db: Session, document_id: int) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


def resolve_role(db: Session, doc: Document, user: User, *, log_denial: bool = True) -> str:
    if doc.owner_id == user.id:
        return "owner"
    share = db.scalar(select(DocumentShare).where(
        DocumentShare.document_id == doc.id,
        DocumentShare.user_id == user.id,
    ))
    if share and share.role in {"reader", "editor"}:
        return share.role
    # Corrupt/unrecognized DB roles fail closed instead of accidentally acting as Editor.
    if log_denial:
        record_event(db, user.id, doc.id, "ACCESS_DENIED", "A user attempted to access a document without an active grant.", expose_document_snapshot=False)
        db.commit()
    raise HTTPException(status_code=403, detail="Access denied. You do not have permission to access this document.")


def require_owner(db: Session, doc: Document, user: User) -> None:
    if doc.owner_id != user.id:
        record_event(db, user.id, doc.id, "ACCESS_DENIED", "A non-owner attempted an owner-only document action.", expose_document_snapshot=False)
        db.commit()
        raise HTTPException(status_code=403, detail="Only the document owner can manage sharing or delete this file.")


def serialize_document(db: Session, doc: Document, role: str) -> dict:
    owner = db.get(User, doc.owner_id)
    shares_count = 0
    if role == "owner":
        shares_count = db.scalar(select(func.count(DocumentShare.id)).where(DocumentShare.document_id == doc.id)) or 0
    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "created_at": dt(doc.created_at),
        "updated_at": dt(doc.updated_at),
        "owner_username": owner.username if owner else "unknown",
        "category": doc.category,
        "access_role": role,
        "is_owner": role == "owner",
        "shares_count": shares_count,
    }


def serialize_event(db: Session, event: AuditEvent, *, admin_view: bool = False) -> dict:
    actor = db.get(User, event.actor_id) if event.actor_id else None
    # Normal users do not receive a foreign document's identifying metadata when
    # an IDOR attempt is denied. Admins can correlate it using the stable document_ref.
    is_denial = event.action in {"ACCESS_DENIED", "ADMIN_ACCESS_DENIED"}
    document_name = event.document_name_snapshot
    if not admin_view and is_denial:
        document_name = None
    return {
        "id": event.id,
        "action": event.action,
        "details": event.details,
        "target_username": event.target_username,
        "actor_username": event.actor_username_snapshot or (actor.username if actor else "system"),
        "document_name": document_name,
        "created_at": dt(event.created_at),
        **({"document_ref": event.document_ref, "document_id": event.document_id,
            "event_hash": event.event_hash, "previous_hash": event.previous_hash}
           if admin_view else {}),
    }


def require_admin(db: Session, user: User) -> None:
    if user.system_role != "admin":
        record_event(db, user.id, None, "ADMIN_ACCESS_DENIED", "A non-administrator attempted to access an administrator-only endpoint.")
        db.commit()
        raise HTTPException(status_code=403, detail="Administrator role required.")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "DocuSentra API", "version": "1.2.0", "docs": "/docs" if APP_ENV != "production" else "disabled", "health": "/api/health"}


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        database_status = "connected"
    except SQLAlchemyError:
        database_status = "disconnected"
    if database_status != "connected":
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable.")
    return {"status": "ok", "service": "trustvault-api", "database": database_status}


@app.post("/api/auth/register", status_code=201)
def register(request: Request, payload: RegisterInput, db: Session = Depends(get_db)) -> dict:
    ip_key = request_client_key(request)
    check_rate_limit("register", ip_key, limit=REGISTER_MAX_ATTEMPTS, window_seconds=REGISTER_RATE_WINDOW_SECONDS)
    username = payload.username.strip().lower()
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
        raise HTTPException(status_code=409, detail="That username is already registered.")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="That email address is already registered.")
    user = User(username=username, email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
        record_event(db, user.id, None, "ACCOUNT_CREATED", "Account created.")
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already registered.") from exc
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": {"id": user.id, "username": user.username, "email": user.email, "system_role": user.system_role}}


@app.post("/api/auth/login")
def login(request: Request, payload: LoginInput, db: Session = Depends(get_db)) -> dict:
    ip_key = request_client_key(request)
    check_rate_limit("login-attempt", ip_key, limit=LOGIN_MAX_FAILURES, window_seconds=LOGIN_RATE_WINDOW_SECONDS)
    ident = payload.identifier.strip()
    user = db.scalar(select(User).where(or_(func.lower(User.username) == ident.lower(), func.lower(User.email) == ident.lower())))
    if not user or not verify_password(payload.password, user.password_hash):
        record_event(db, user.id if user else None, None, "LOGIN_FAILED", "Failed sign-in attempt; credentials were not accepted.")
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
    clear_rate_limit("login-attempt", ip_key)
    record_event(db, user.id, None, "LOGIN", "Successful sign-in.")
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": {"id": user.id, "username": user.username, "email": user.email, "system_role": user.system_role}}


@app.get("/api/auth/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email, "system_role": user.system_role}


@app.post("/api/auth/change-password")
def change_password(
    request: Request,
    payload: ChangePasswordInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Change the signed-in user's password after verifying the current password."""
    rate_key = f"{user.id}:{request_client_key(request)}"
    check_rate_limit("password-change", rate_key, limit=5, window_seconds=300)
    if not verify_password(payload.current_password, user.password_hash):
        record_event(db, user.id, None, "PASSWORD_CHANGE_FAILED", "Password change rejected because the current password was incorrect.")
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current password.")
    user.password_hash = hash_password(payload.new_password)
    record_event(db, user.id, None, "PASSWORD_CHANGED", "Account password changed successfully.")
    db.commit()
    clear_rate_limit("password-change", rate_key)
    # Existing bearer tokens remain valid until expiry; users can sign out to clear the local session.
    return {"message": "Password changed successfully. Your current session remains active until it expires or you sign out."}


@app.get("/api/users")
def search_users(q: str = Query(min_length=1, max_length=254), db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    term = q.strip()
    if not term:
        return []
    # Exact-match lookup avoids returning a broad account roster for one-character queries.
    target = db.scalar(select(User).where(
        User.id != user.id,
        or_(func.lower(User.username) == term.lower(), func.lower(User.email) == term.lower()),
    ))
    if target is None:
        return []
    return [{"id": target.id, "username": target.username, "email": target.email}]


@app.get("/api/documents")
def list_documents(
    q: str | None = Query(default=None, max_length=200),
    owner: str | None = Query(default=None, max_length=64),
    category: str | None = Query(default=None, max_length=80),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date.")
    statement = (
        select(Document, DocumentShare.role)
        .join(User, User.id == Document.owner_id)
        .outerjoin(DocumentShare, (DocumentShare.document_id == Document.id) & (DocumentShare.user_id == user.id))
        .where(Document.deleted_at.is_(None), or_(Document.owner_id == user.id, DocumentShare.user_id == user.id))
    )
    if category and category.strip():
        statement = statement.where(func.lower(Document.category) == category.strip().lower())
    if from_date:
        statement = statement.where(Document.created_at >= datetime.combine(from_date, datetime_time.min, tzinfo=timezone.utc))
    if to_date:
        statement = statement.where(Document.created_at < datetime.combine(to_date + timedelta(days=1), datetime_time.min, tzinfo=timezone.utc))
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        statement = statement.where(func.lower(Document.filename).like(term))
    if owner and owner.strip():
        statement = statement.where(func.lower(User.username).like(f"%{owner.strip().lower()}%"))
    rows = db.execute(statement.order_by(Document.updated_at.desc(), Document.id.desc()).limit(500)).all()
    results = []
    for doc, shared_role in rows:
        role = "owner" if doc.owner_id == user.id else shared_role
        if role:
            results.append(serialize_document(db, doc, role))
    return results


OLE_COMPOUND_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
PNG_MAGIC = bytes.fromhex("89504E470D0A1A0A")


def validate_uploaded_content(path: Path, extension: str) -> None:
    """Validate the file signature and bound Office archive expansion before use."""
    with path.open("rb") as stream:
        sample = stream.read(8192)

    if extension == ".pdf":
        if not sample.startswith(b"%PDF-"):
            raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid PDF.")
        return
    if extension == ".png":
        if not sample.startswith(PNG_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid PNG image.")
        return
    if extension in {".jpg", ".jpeg"}:
        if not sample.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid JPEG image.")
        return
    if extension in {".doc", ".xls", ".ppt"}:
        if not sample.startswith(OLE_COMPOUND_MAGIC):
            raise HTTPException(status_code=415, detail="The uploaded file does not look like a valid legacy Office document.")
        return
    zip_requirements = {
        ".docx": {"[Content_Types].xml", "word/document.xml"},
        ".xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
        ".pptx": {"[Content_Types].xml", "ppt/presentation.xml"},
    }
    if extension in zip_requirements:
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if not infos or len(infos) > 2_000:
                    raise HTTPException(status_code=415, detail="The Office document archive has an invalid structure.")
                total_uncompressed = sum(info.file_size for info in infos)
                if total_uncompressed > 50 * 1024 * 1024 or any(info.file_size > 25 * 1024 * 1024 for info in infos):
                    raise HTTPException(status_code=413, detail="The Office document expands beyond the allowed preview safety limit.")
                for info in infos:
                    normalized_name = info.filename.replace("\\", "/")
                    if normalized_name.startswith("/") or re.match(r"^[A-Za-z]:", normalized_name) or ".." in normalized_name.split("/") or info.flag_bits & 0x1:
                        raise HTTPException(status_code=415, detail="The Office document contains an unsafe or encrypted archive entry.")
                names = set(archive.namelist())
                if not zip_requirements[extension].issubset(names):
                    raise HTTPException(status_code=415, detail="The uploaded ZIP does not contain the expected Office document structure.")
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise HTTPException(status_code=415, detail="The Office document archive is damaged.")
        except HTTPException:
            raise
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid Office document archive.") from exc
        return
    if extension in {".txt", ".csv"}:
        known_binary_prefixes = (b"MZ", b"\x7fELF", b"%PDF-", PNG_MAGIC, b"\xff\xd8\xff", b"PK\x03\x04", OLE_COMPOUND_MAGIC)
        if b"\x00" in sample or any(sample.startswith(prefix) for prefix in known_binary_prefixes):
            raise HTTPException(status_code=415, detail="Upload a text or CSV file rather than binary content.")
        return
    raise HTTPException(status_code=415, detail="This file type is not supported.")


@app.post("/api/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=200),
    category: str = Form(default="General", max_length=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.system_role == "viewer":
        record_event(db, user.id, None, "ACCESS_DENIED", "A viewer account attempted to upload a new document.")
        db.commit()
        raise HTTPException(status_code=403, detail="Viewer accounts cannot upload documents. Ask an administrator to change your account role.")
    raw_name = Path((file.filename or "document").replace("\\", "/")).name
    extension = Path(raw_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="File type not allowed. Upload PDF, Office documents, TXT, CSV, or common images.")
    if not raw_name or any(ord(c) < 32 for c in raw_name):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    safe_name = (title or raw_name).strip()
    safe_name = Path(safe_name.replace("\\", "/")).name[:200]
    if not safe_name:
        raise HTTPException(status_code=400, detail="Document name cannot be empty.")
    if any(ord(character) < 32 for character in safe_name):
        raise HTTPException(status_code=400, detail="Document name contains unsupported control characters.")
    requested_category = category.strip() or "General"
    if any(ord(character) < 32 for character in requested_category) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 &().,_/-]{0,79}", requested_category):
        raise HTTPException(status_code=400, detail="Choose a valid document category.")
    safe_category = UPLOAD_CATEGORIES.get(requested_category.lower())
    if safe_category is None:
        raise HTTPException(status_code=400, detail="Choose one of the available document categories: HR, Finance, Legal, Personal, Education, General, or Others.")
    title_extension = Path(safe_name).suffix.lower()
    if title_extension and title_extension != extension:
        raise HTTPException(status_code=400, detail="The document name must keep the uploaded file's extension.")
    if not title_extension:
        safe_name = f"{safe_name}{extension}"[:200]

    storage_key = uuid.uuid4().hex
    destination = STORAGE_DIR / storage_key
    size = 0
    blob_saved = False
    content_type = mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"File is too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        validate_uploaded_content(destination, extension)
        if _uses_vercel_blob():
            try:
                from vercel import blob as vercel_blob
                await vercel_blob.put_blob(
                    _blob_path(storage_key), destination.read_bytes(), access="private",
                    content_type=content_type, add_random_suffix=False,
                )
                blob_saved = True
                # Do not keep the original copy in the ephemeral filesystem once it is durably stored.
                destination.unlink(missing_ok=True)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Private document storage upload failed. Please retry.") from exc
        doc = Document(owner_id=user.id, filename=safe_name, category=safe_category, storage_key=storage_key, content_type=content_type, size_bytes=size)
        db.add(doc)
        db.flush()
        record_event(db, user.id, doc.id, "DOCUMENT_UPLOADED", f"Uploaded {safe_name} ({size} bytes), category {safe_category}.")
        db.commit()
        db.refresh(doc)
        return serialize_document(db, doc, "owner")
    except HTTPException:
        db.rollback()
        destination.unlink(missing_ok=True)
        if blob_saved:
            try:
                from vercel import blob as vercel_blob
                await vercel_blob.delete_blob(_blob_path(storage_key))
            except Exception:
                pass
        raise
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        if blob_saved:
            try:
                from vercel import blob as vercel_blob
                await vercel_blob.delete_blob(_blob_path(storage_key))
            except Exception:
                pass
        raise HTTPException(status_code=500, detail="Upload failed. Please try again.")
    finally:
        await file.close()


OFFICE_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
IMAGE_MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PREVIEW_CACHE_DIR = STORAGE_DIR / ".preview_cache"


def prepare_office_pdf(doc: Document, source_path: Path) -> Path:
    """Convert an Office document to a private cached PDF for in-browser preview.

    LibreOffice runs headlessly with a per-conversion profile. The original upload
    remains private and is never returned by this endpoint.
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise HTTPException(status_code=415, detail="Office preview requires the TrustVault preview converter. Rebuild the updated Docker image and try again.")

    stat = source_path.stat()
    PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PREVIEW_CACHE_DIR / f"{doc.storage_key}-{stat.st_size}-{stat.st_mtime_ns}.pdf"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    with tempfile.TemporaryDirectory(prefix="trustvault-preview-") as temp_name:
        work_dir = Path(temp_name)
        input_dir = work_dir / "input"
        output_dir = work_dir / "output"
        profile_dir = work_dir / "profile"
        input_dir.mkdir()
        output_dir.mkdir()
        original_named_path = input_dir / Path(doc.filename).name
        shutil.copyfile(source_path, original_named_path)
        command = [
            soffice,
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(original_named_path),
        ]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=422, detail="Office preview took too long to prepare. Ask the owner to simplify or re-upload the document.") from exc
        converted_path = output_dir / f"{original_named_path.stem}.pdf"
        if result.returncode != 0 or not converted_path.is_file() or converted_path.stat().st_size == 0:
            raise HTTPException(status_code=422, detail="This Office file could not be converted for preview. The file may be damaged or unsupported.")
        temporary_cache = PREVIEW_CACHE_DIR / f".{cache_path.name}.{uuid.uuid4().hex}.tmp"
        shutil.copyfile(converted_path, temporary_cache)
        os.replace(temporary_cache, cache_path)
    return cache_path



def pdf_for_preview(doc: Document, source_path: Path) -> Path:
    """Return a private PDF rendition for raster-only page preview."""
    extension = Path(doc.filename).suffix.lower()
    if extension == ".pdf":
        return source_path
    if extension in OFFICE_EXTENSIONS:
        return prepare_office_pdf(doc, source_path)
    raise HTTPException(status_code=415, detail="This file type does not have a paged preview.")


def get_pdf_page_count(pdf_path: Path) -> int:
    """Read page count using Poppler locally or PyMuPDF on Vercel where OS binaries are unavailable."""
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        try:
            import fitz  # PyMuPDF ships its rendering engine as a Python wheel.
            with fitz.open(pdf_path) as document:
                count = len(document)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="This PDF could not be read for secure preview.") from exc
    else:
        try:
            result = subprocess.run(
                [pdfinfo, str(pdf_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=12, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=422, detail="This document took too long to inspect for preview.") from exc
        if result.returncode != 0:
            raise HTTPException(status_code=422, detail="This PDF could not be read for secure preview. It may be damaged or password protected.")
        match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, flags=re.MULTILINE)
        if not match:
            raise HTTPException(status_code=422, detail="Could not determine the number of pages in this document.")
        count = int(match.group(1))
    if count < 1:
        raise HTTPException(status_code=422, detail="This document has no pages to preview.")
    if count > MAX_PREVIEW_PAGES:
        raise HTTPException(status_code=413, detail=f"Secure preview is limited to {MAX_PREVIEW_PAGES} pages per document.")
    return count


def render_pdf_page_cached(doc: Document, pdf_path: Path, page_number: int) -> Path:
    """Render one PDF page to a private PNG cache using Poppler or PyMuPDF."""
    renderer = shutil.which("pdftoppm")
    stat = pdf_path.stat()
    PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_page = PREVIEW_CACHE_DIR / f"{doc.storage_key}-{stat.st_size}-{stat.st_mtime_ns}-page-{page_number}.png"
    if cached_page.is_file() and cached_page.stat().st_size > 0:
        return cached_page

    temporary = PREVIEW_CACHE_DIR / f".{cached_page.name}.{uuid.uuid4().hex}.tmp.png"
    if renderer:
        with tempfile.TemporaryDirectory(prefix="trustvault-page-") as temp_name:
            prefix = Path(temp_name) / "page"
            command = [renderer, "-f", str(page_number), "-l", str(page_number), "-r", "110", "-png", "-singlefile", str(pdf_path), str(prefix)]
            try:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20, check=False)
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status_code=422, detail="Rendering this page took too long. Try a simpler document.") from exc
            generated = Path(f"{prefix}.png")
            if result.returncode != 0 or not generated.is_file() or generated.stat().st_size == 0:
                raise HTTPException(status_code=404, detail="This page does not exist or could not be rendered.")
            shutil.copyfile(generated, temporary)
    else:
        try:
            import fitz
            with fitz.open(pdf_path) as document:
                if page_number < 1 or page_number > len(document):
                    raise HTTPException(status_code=404, detail="This page does not exist.")
                page = document.load_page(page_number - 1)
                rect = page.rect
                scale = min(1.35, 1500 / max(rect.width, 1), 1900 / max(rect.height, 1))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(str(temporary))
        except HTTPException:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="This PDF page could not be rendered by the available preview engine.") from exc
    os.replace(temporary, cached_page)
    return cached_page


def _prepare_preview_image(path: Path) -> bytes:
    """Re-encode a preview without metadata or visible watermark text.

    Vercel responses are encoded as JPEG to keep raster previews comfortably below
    the platform's 4.5 MB function response-body limit. Local Docker previews stay PNG.
    """
    try:
        with Image.open(path) as opened:
            opened.load()
            preview = opened.convert("RGB")
            preview.thumbnail((1400, 1800), Image.Resampling.LANCZOS)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=422, detail="This page could not be prepared as a safe preview image.") from exc

    output = BytesIO()
    if VERCEL_RUNTIME:
        preview.save(output, format="JPEG", quality=82, optimize=True, progressive=True)
    else:
        preview.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def preview_image_response(path: Path, filename: str = "preview.png") -> Response:
    """Serve a re-encoded preview image without visible watermarking or metadata."""
    image_bytes = _prepare_preview_image(path)
    is_vercel_jpeg = VERCEL_RUNTIME
    if is_vercel_jpeg:
        filename = Path(filename).with_suffix(".jpg").name
    return Response(
        content=image_bytes,
        media_type="image/jpeg" if is_vercel_jpeg else "image/png",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


def extract_read_only_preview(doc: Document, path: Path) -> list[dict]:
    """Extract display-only text for text formats and DOCX fallback mode."""
    extension = Path(doc.filename).suffix.lower()
    blocks: list[dict] = []
    character_budget = 200_000

    if extension == ".docx":
        word_doc = WordDocument(path)
        used = 0
        for child in word_doc.element.body.iterchildren():
            if child.tag == qn("w:p"):
                paragraph = WordParagraph(child, word_doc)
                content = paragraph.text.strip()
                if content and used < character_budget:
                    content = content[:character_budget - used]
                    blocks.append({"type": "paragraph", "text": content})
                    used += len(content)
            elif child.tag == qn("w:tbl") and used < character_budget:
                table = WordTable(child, word_doc)
                rows = []
                for row in table.rows:
                    cells = [cell.text.strip()[:5000] for cell in row.cells]
                    used += sum(len(cell) for cell in cells)
                    rows.append(cells)
                    if used >= character_budget:
                        break
                if rows:
                    blocks.append({"type": "table", "rows": rows})
        if used >= character_budget:
            blocks.append({"type": "paragraph", "text": "Preview truncated because the document is very large."})
        return blocks

    if extension == ".xlsx":
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="This spreadsheet could not be read for preview.") from exc
        used = 0
        try:
            for sheet in workbook.worksheets:
                blocks.append({"type": "paragraph", "text": f"Sheet: {sheet.title}"})
                rows = []
                for row in sheet.iter_rows(values_only=True):
                    values = [str(value)[:1000] if value is not None else "" for value in row]
                    used += sum(len(value) for value in values)
                    rows.append(values)
                    if used >= character_budget or len(rows) >= 500:
                        break
                if rows:
                    blocks.append({"type": "table", "rows": rows})
                if used >= character_budget:
                    blocks.append({"type": "paragraph", "text": "Preview truncated because the workbook is very large."})
                    break
        finally:
            workbook.close()
        return blocks

    if extension == ".pptx":
        try:
            from pptx import Presentation
            presentation = Presentation(str(path))
        except Exception as exc:
            raise HTTPException(status_code=422, detail="This presentation could not be read for preview.") from exc
        used = 0
        for slide_number, slide in enumerate(presentation.slides, start=1):
            blocks.append({"type": "paragraph", "text": f"Slide {slide_number}"})
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    content = shape.text.strip()
                    if content and used < character_budget:
                        content = content[:character_budget - used]
                        blocks.append({"type": "paragraph", "text": content})
                        used += len(content)
                if getattr(shape, "has_table", False) and used < character_budget:
                    rows = []
                    for row in shape.table.rows:
                        values = [cell.text.strip()[:1000] for cell in row.cells]
                        used += sum(len(value) for value in values)
                        rows.append(values)
                        if used >= character_budget:
                            break
                    if rows:
                        blocks.append({"type": "table", "rows": rows})
            if used >= character_budget:
                blocks.append({"type": "paragraph", "text": "Preview truncated because the presentation is very large."})
                break
        return blocks

    if extension in {".txt", ".csv"}:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > character_budget:
            content = content[:character_budget] + "\n\n[Preview truncated because the document is very large.]"
        return [{"type": "paragraph", "text": content}] if content else []

    raise HTTPException(status_code=415, detail="This file type cannot be previewed by the available viewer.")


TEXT_PREVIEW_CHAR_LIMIT = 200_000
TEXT_PREVIEW_PAGE_LINES = 44
TEXT_PREVIEW_PAGE_WIDTH = 1240
TEXT_PREVIEW_PAGE_HEIGHT = 1600


def _text_preview_lines(doc: Document, source_path: Path) -> list[str]:
    """Build bounded display lines for raster preview so raw text is not sent to the Reader UI."""
    extension = Path(doc.filename).suffix.lower()
    if extension in {".txt", ".csv"}:
        content = source_path.read_text(encoding="utf-8", errors="replace")
    elif extension in {".docx", ".xlsx", ".pptx"}:
        blocks = extract_read_only_preview(doc, source_path)
        display_lines: list[str] = []
        for block in blocks:
            if block.get("type") == "table":
                for row in block.get("rows", []):
                    display_lines.append("   |   ".join(str(cell) for cell in row))
            else:
                display_lines.extend(str(block.get("text", "")).splitlines() or [""])
        content = "\n".join(display_lines)
    else:
        raise HTTPException(status_code=415, detail="This file type does not support text page rendering.")

    truncated = len(content) > TEXT_PREVIEW_CHAR_LIMIT
    content = content[:TEXT_PREVIEW_CHAR_LIMIT]
    result: list[str] = []
    for original_line in content.splitlines() or ["(This document is empty.)"]:
        line = original_line.expandtabs(4)
        if not line:
            result.append("")
            continue
        # Approximate 108 characters per line at the chosen page/font size.
        while len(line) > 108:
            cut = line.rfind(" ", 0, 109)
            if cut < 24:
                cut = 108
            result.append(line[:cut])
            line = line[cut:].lstrip()
        result.append(line)
    if truncated:
        result.append("[Preview truncated at the configured character limit.]")
    return result


def get_text_preview_page_count(doc: Document, source_path: Path) -> int:
    lines = _text_preview_lines(doc, source_path)
    count = max(1, (len(lines) + TEXT_PREVIEW_PAGE_LINES - 1) // TEXT_PREVIEW_PAGE_LINES)
    if count > MAX_PREVIEW_PAGES:
        raise HTTPException(status_code=413, detail=f"Text preview is limited to {MAX_PREVIEW_PAGES} pages per document.")
    return count


def render_text_page_cached(doc: Document, source_path: Path, page_number: int) -> Path:
    """Render a TXT/CSV/DOCX fallback page to a private raster image; no selectable text reaches the browser."""
    stat = source_path.stat()
    PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PREVIEW_CACHE_DIR / f"{doc.storage_key}-{stat.st_size}-{stat.st_mtime_ns}-text-page-v2-{page_number}.png"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    lines = _text_preview_lines(doc, source_path)
    count = max(1, (len(lines) + TEXT_PREVIEW_PAGE_LINES - 1) // TEXT_PREVIEW_PAGE_LINES)
    if page_number < 1 or page_number > count:
        raise HTTPException(status_code=404, detail="This page does not exist.")
    page_lines = lines[(page_number - 1) * TEXT_PREVIEW_PAGE_LINES: page_number * TEXT_PREVIEW_PAGE_LINES]
    page = Image.new("RGB", (TEXT_PREVIEW_PAGE_WIDTH, TEXT_PREVIEW_PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(page)
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    bold_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    try:
        body_font = ImageFont.truetype(font_path, 19)
        title_font = ImageFont.truetype(bold_path, 25)
        meta_font = ImageFont.truetype(font_path, 14)
    except OSError:
        body_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        meta_font = ImageFont.load_default()

    draw.text((78, 48), "DOCUSENTRA • READ-ONLY PREVIEW", fill=(34, 70, 125), font=title_font)
    draw.text((80, 88), doc.filename[:100], fill=(95, 107, 127), font=meta_font)
    draw.line((80, 118, TEXT_PREVIEW_PAGE_WIDTH - 80, 118), fill=(218, 225, 235), width=2)
    y = 146
    for line in page_lines:
        draw.text((80, y), line[:150], fill=(35, 43, 57), font=body_font)
        y += 29
    draw.line((80, TEXT_PREVIEW_PAGE_HEIGHT - 85, TEXT_PREVIEW_PAGE_WIDTH - 80, TEXT_PREVIEW_PAGE_HEIGHT - 85), fill=(225, 229, 236), width=1)
    draw.text((80, TEXT_PREVIEW_PAGE_HEIGHT - 66), f"Page {page_number} of {count}", fill=(105, 115, 132), font=meta_font)

    temporary = PREVIEW_CACHE_DIR / f".{cache_path.name}.{uuid.uuid4().hex}.tmp"
    page.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, cache_path)
    return cache_path


@app.get("/api/documents/{document_id}/preview")
def preview_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    doc = get_document_or_404(db, document_id)
    role = resolve_role(db, doc, user)
    path = _document_file_path(doc.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="The stored document is no longer available.")

    extension = Path(doc.filename).suffix.lower()
    preview_type = "blocks"
    blocks: list[dict] = []
    page_count: int | None = None
    try:
        if extension == ".pdf":
            pdf_path = pdf_for_preview(doc, path)
            page_count = get_pdf_page_count(pdf_path)
            preview_type = "pages"
        elif extension in OFFICE_EXTENSIONS:
            if not (shutil.which("soffice") or shutil.which("libreoffice")):
                # Serverless Vercel functions do not install OS-level LibreOffice binaries.
                # Render text-based fallbacks for modern OpenXML formats instead.
                if extension in {".docx", ".xlsx", ".pptx"}:
                    page_count = get_text_preview_page_count(doc, path)
                    preview_type = "pages"
                else:
                    raise HTTPException(status_code=415, detail="Preview for legacy .doc/.xls/.ppt requires the desktop converter; download remains available to Editors/Owners.")
            else:
                pdf_path = pdf_for_preview(doc, path)
                page_count = get_pdf_page_count(pdf_path)
                preview_type = "pages"
        elif extension in IMAGE_MIME_TYPES:
            # Uploaded images are decoded and re-encoded before being returned to the browser.
            preview_type = "image"
        elif extension in {".txt", ".csv"}:
            page_count = get_text_preview_page_count(doc, path)
            preview_type = "pages"
        else:
            raise HTTPException(status_code=415, detail="This file type cannot be previewed by the available viewer.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="This document could not be previewed. The file may be invalid or unsupported.") from exc

    record_event(db, user.id, doc.id, "DOCUMENT_PREVIEWED", f"Viewed read-only preview of {doc.filename}.")
    db.commit()
    result = {
        "filename": doc.filename,
        "content_type": doc.content_type,
        "access_role": role,
        "preview_type": preview_type,
        "blocks": blocks,
    }
    if page_count is not None:
        result["page_count"] = page_count
    return result


@app.get("/api/documents/{document_id}/preview-content")
def preview_document_content(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    """Serve re-encoded image previews; PDF/Office content is exposed as individual raster pages."""
    doc = get_document_or_404(db, document_id)
    resolve_role(db, doc, user)
    original_path = _document_file_path(doc.storage_key)
    if not original_path.is_file():
        raise HTTPException(status_code=410, detail="The stored document is no longer available.")

    extension = Path(doc.filename).suffix.lower()
    if extension not in IMAGE_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Binary preview content is disabled. Paged documents are served only as individual raster images.")

    record_event(db, user.id, doc.id, "DOCUMENT_PREVIEW_CONTENT_OPENED", f"Opened read-only image preview for {doc.filename}.")
    db.commit()
    return preview_image_response(original_path, "trustvault-preview.png")


@app.get("/api/documents/{document_id}/preview-pages/{page_number}")
def preview_document_page(
    document_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Serve one authenticated raster page instead of exposing a PDF viewer/save toolbar."""
    doc = get_document_or_404(db, document_id)
    resolve_role(db, doc, user)
    if page_number < 1 or page_number > MAX_PREVIEW_PAGES:
        raise HTTPException(status_code=404, detail="This page is outside the preview range.")
    original_path = _document_file_path(doc.storage_key)
    if not original_path.is_file():
        raise HTTPException(status_code=410, detail="The stored document is no longer available.")

    extension = Path(doc.filename).suffix.lower()
    try:
        no_office_converter = not (shutil.which("soffice") or shutil.which("libreoffice"))
        if extension in {".txt", ".csv"} or (extension in {".docx", ".xlsx", ".pptx"} and no_office_converter):
            rendered_page = render_text_page_cached(doc, original_path, page_number)
        elif extension == ".pdf" or (extension in OFFICE_EXTENSIONS and not no_office_converter):
            pdf_path = pdf_for_preview(doc, original_path)
            rendered_page = render_pdf_page_cached(doc, pdf_path, page_number)
        else:
            raise HTTPException(status_code=415, detail="This document does not support paged preview.")
        content = _prepare_preview_image(rendered_page)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="This page could not be rendered for secure preview.") from exc

    # Record each successful page retrieval: a one-time "preview opened" event is
    # insufficient to evidence which content was actually rendered to an authorized user.
    record_event(db, user.id, doc.id, "DOCUMENT_PAGE_VIEWED", f"Rendered read-only preview page {page_number}.")
    db.commit()
    # Original PDF bytes are not sent to the browser; the authorized viewer receives raster page pixels.
    is_vercel_jpeg = VERCEL_RUNTIME
    return Response(
        content=content,
        media_type="image/jpeg" if is_vercel_jpeg else "image/png",
        headers={
            "Content-Disposition": 'inline; filename="trustvault-page.jpg"' if is_vercel_jpeg else 'inline; filename="trustvault-page.png"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    doc = get_document_or_404(db, document_id)
    role = resolve_role(db, doc, user)
    if role == "reader":
        record_event(db, user.id, doc.id, "ACCESS_DENIED", f"Reader attempted to download {doc.filename}; download is editor/owner only.")
        db.commit()
        raise HTTPException(status_code=403, detail="Reader permission is view-only. Use Preview to read this document; ask the owner for Editor access if you need to download it.")
    path = _document_file_path(doc.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="The stored document is no longer available.")
    record_event(db, user.id, doc.id, "DOCUMENT_DOWNLOADED", f"Downloaded {doc.filename}.")
    db.commit()
    return FileResponse(path=path, media_type=doc.content_type, filename=doc.filename, content_disposition_type="attachment")


@app.patch("/api/documents/{document_id}")
def rename_document(document_id: int, payload: RenameInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    doc = get_document_or_404(db, document_id)
    role = resolve_role(db, doc, user)
    if role == "reader":
        record_event(db, user.id, doc.id, "ACCESS_DENIED", f"Reader attempted to rename {doc.filename}.")
        db.commit()
        raise HTTPException(status_code=403, detail="Reader permission is read-only. Ask the owner for editor access.")
    old_name = doc.filename
    if Path(payload.filename).suffix.lower() != Path(doc.filename).suffix.lower():
        raise HTTPException(status_code=400, detail="Renaming must preserve the file extension.")
    doc.filename = payload.filename
    doc.updated_at = now_utc()
    record_event(db, user.id, doc.id, "DOCUMENT_RENAMED", f"Renamed document from {old_name} to {doc.filename}.")
    db.commit()
    db.refresh(doc)
    return serialize_document(db, doc, role)


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    doc = get_document_or_404(db, document_id)
    require_owner(db, doc, user)
    name = doc.filename
    # Soft deletion preserves stable audit references; app routes treat deleted docs as 404.
    # Record each access removal before removing the active grants.
    active_shares = db.scalars(select(DocumentShare).where(DocumentShare.document_id == doc.id)).all()
    for share in active_shares:
        target = db.get(User, share.user_id)
        target_name = target.username if target else "unknown"
        record_event(db, user.id, doc.id, "ACCESS_REVOKED", f"Revoked {share.role} access because the document was deleted.", target_name)
        db.delete(share)
    record_event(db, user.id, doc.id, "DOCUMENT_DELETED", f"Deleted document {name} (ID {doc.id}).")
    doc.deleted_at = now_utc()
    db.commit()
    _delete_document_file(doc.storage_key)
    # Remove rendered Office previews too; they may contain the full document text.
    cache_dir = STORAGE_DIR / ".preview_cache"
    if cache_dir.is_dir():
        for cached_preview in cache_dir.glob(f"{doc.storage_key}-*"):
            if cached_preview.is_file():
                cached_preview.unlink(missing_ok=True)
    return None


@app.get("/api/documents/{document_id}/shares")
def list_shares(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    doc = get_document_or_404(db, document_id)
    require_owner(db, doc, user)
    rows = db.execute(select(DocumentShare, User).join(User, User.id == DocumentShare.user_id)
                      .where(DocumentShare.document_id == doc.id).order_by(User.username)).all()
    return [{"id": share.id, "user_id": target.id, "username": target.username, "email": target.email,
             "role": share.role, "created_at": dt(share.created_at)} for share, target in rows]


@app.post("/api/documents/{document_id}/shares", status_code=201)
def grant_share(document_id: int, payload: ShareInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    doc = get_document_or_404(db, document_id)
    require_owner(db, doc, user)
    identifier = payload.user_identifier.strip()
    target = db.scalar(select(User).where(or_(func.lower(User.username) == identifier.lower(), func.lower(User.email) == identifier.lower())))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found. Ask them to create a TrustVault account first.")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You already own this document.")
    existing = db.scalar(select(DocumentShare).where(DocumentShare.document_id == doc.id, DocumentShare.user_id == target.id))
    if existing:
        existing.role = payload.role
        record_event(db, user.id, doc.id, "PERMISSION_UPDATED", f"Changed access for @{target.username} to {payload.role}.", target.username)
        share = existing
    else:
        share = DocumentShare(document_id=doc.id, user_id=target.id, granted_by=user.id, role=payload.role)
        db.add(share)
        record_event(db, user.id, doc.id, "ACCESS_GRANTED", f"Granted {payload.role} access to @{target.username}.", target.username)
    db.commit()
    db.refresh(share)
    return {"id": share.id, "user_id": target.id, "username": target.username, "email": target.email,
            "role": share.role, "created_at": dt(share.created_at)}


@app.delete("/api/documents/{document_id}/shares/{share_id}", status_code=204)
def revoke_share(document_id: int, share_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    doc = get_document_or_404(db, document_id)
    require_owner(db, doc, user)
    share = db.scalar(select(DocumentShare).where(DocumentShare.id == share_id, DocumentShare.document_id == doc.id))
    if share is None:
        raise HTTPException(status_code=404, detail="Sharing permission not found.")
    target = db.get(User, share.user_id)
    target_name = target.username if target else "unknown"
    role = share.role
    db.delete(share)
    record_event(db, user.id, doc.id, "ACCESS_REVOKED", f"Revoked {role} access for @{target_name}.", target_name)
    db.commit()
    return None


@app.get("/api/activity")
def activity(db: Session = Depends(get_db), user: User = Depends(get_current_user), limit: int = Query(default=100, ge=1, le=250)) -> list[dict]:
    owned_ids = select(Document.id).where(Document.owner_id == user.id)
    events = db.scalars(select(AuditEvent).where(
        or_(AuditEvent.actor_id == user.id, AuditEvent.document_id.in_(owned_ids))
    ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)).all()
    return [serialize_event(db, event) for event in events]


@app.get("/api/admin/overview", summary="Administrator: system overview")
def admin_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Global operational metrics. Admin privilege does not bypass document content grants."""
    require_admin(db, user)
    verification = verify_audit_chain(db)
    active_documents = db.scalar(select(func.count(Document.id)).where(Document.deleted_at.is_(None))) or 0
    active_shares = db.scalar(select(func.count(DocumentShare.id)).join(Document, Document.id == DocumentShare.document_id).where(Document.deleted_at.is_(None))) or 0
    denied_events = db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action.in_(["ACCESS_DENIED", "ADMIN_ACCESS_DENIED"]))) or 0
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "administrators": db.scalar(select(func.count(User.id)).where(User.system_role == "admin")) or 0,
        "owners": db.scalar(select(func.count(User.id)).where(User.system_role == "owner")) or 0,
        "viewers": db.scalar(select(func.count(User.id)).where(User.system_role == "viewer")) or 0,
        "active_documents": active_documents,
        "active_grants": active_shares,
        "audit_events": db.scalar(select(func.count(AuditEvent.id))) or 0,
        "denied_events": denied_events,
        "audit_valid": verification["valid"],
        "audit_events_checked": verification["events_checked"],
    }


@app.get("/api/admin/users", summary="Administrator: list users and roles")
def admin_list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    require_admin(db, user)
    rows = db.scalars(select(User).order_by(User.created_at.asc(), User.id.asc())).all()
    return [{"id": row.id, "username": row.username, "email": row.email,
             "system_role": row.system_role, "created_at": dt(row.created_at)} for row in rows]


@app.patch("/api/admin/users/{target_user_id}/role", summary="Administrator: change an account role")
def admin_change_user_role(target_user_id: int, payload: RoleChangeInput,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    require_admin(db, user)
    target = db.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == user.id and payload.system_role != "admin":
        admin_count = db.scalar(select(func.count(User.id)).where(User.system_role == "admin")) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="The last administrator cannot demote themselves.")
    if target.system_role == "admin" and payload.system_role != "admin":
        admin_count = db.scalar(select(func.count(User.id)).where(User.system_role == "admin")) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=409, detail="The system must retain at least one administrator.")
    if payload.system_role == "viewer" and target.system_role != "viewer":
        owned_docs = db.scalar(select(func.count(Document.id)).where(
            Document.owner_id == target.id, Document.deleted_at.is_(None)
        )) or 0
        if owned_docs:
            raise HTTPException(status_code=409, detail="Transfer or delete this account's active documents before changing it to the system viewer role.")
    old_role = target.system_role
    target.system_role = payload.system_role
    record_event(db, user.id, None, "USER_ROLE_CHANGED",
                 f"Changed account role for @{target.username} from {old_role} to {payload.system_role}.", target.username)
    db.commit()
    db.refresh(target)
    return {"id": target.id, "username": target.username, "email": target.email,
            "system_role": target.system_role, "created_at": dt(target.created_at)}


@app.get("/api/admin/permissions", summary="Administrator: inspect active document grants")
def admin_permissions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    require_admin(db, user)
    rows = db.execute(
        select(DocumentShare, Document, User)
        .join(Document, Document.id == DocumentShare.document_id)
        .join(User, User.id == DocumentShare.user_id)
        .where(Document.deleted_at.is_(None))
        .order_by(Document.filename.asc(), User.username.asc())
        .limit(1000)
    ).all()
    result = []
    for share, doc, target in rows:
        owner = db.get(User, doc.owner_id)
        grantor = db.get(User, share.granted_by)
        result.append({
            "share_id": share.id, "document_id": doc.id, "document_name": doc.filename,
            "category": doc.category, "owner_username": owner.username if owner else "unknown",
            "user_id": target.id, "username": target.username, "email": target.email,
            "permission": share.role, "granted_by": grantor.username if grantor else "unknown",
            "created_at": dt(share.created_at),
        })
    return result


@app.get("/api/admin/activity", summary="Administrator: global audit trail")
def admin_activity(
    action: str | None = Query(default=None, max_length=40),
    actor: str | None = Query(default=None, max_length=32),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_admin(db, user)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date.")
    statement = select(AuditEvent)
    if action and action.strip():
        statement = statement.where(AuditEvent.action == action.strip().upper())
    if actor and actor.strip():
        statement = statement.where(func.lower(AuditEvent.actor_username_snapshot).like(f"%{actor.strip().lower()}%"))
    if from_date:
        statement = statement.where(AuditEvent.created_at >= datetime.combine(from_date, datetime_time.min, tzinfo=timezone.utc))
    if to_date:
        statement = statement.where(AuditEvent.created_at < datetime.combine(to_date + timedelta(days=1), datetime_time.min, tzinfo=timezone.utc))
    events = db.scalars(statement.order_by(AuditEvent.id.desc()).limit(limit)).all()
    return [serialize_event(db, event, admin_view=True) for event in events]


@app.get("/api/admin/audit/verify", summary="Administrator: verify the audit hash chain")
def admin_verify_audit(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    require_admin(db, user)
    result = verify_audit_chain(db)
    result["checked_at"] = dt(now_utc())
    # Report a failing event ID/reason, but don't write another event that could hide
    # which record was found invalid. Successful calls are read-only verification.
    return result


@app.get("/api/admin/audit/archives", summary="Administrator: inspect preserved unverifiable audit archives")
def admin_audit_archives(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    require_admin(db, user)
    archives = db.scalars(select(AuditEventArchive).order_by(AuditEventArchive.id.desc()).limit(100)).all()
    result = []
    for archive in archives:
        digest_valid = hmac.compare_digest(
            hashlib.sha256(archive.snapshot_json.encode("utf-8")).hexdigest(), archive.snapshot_sha256
        )
        result.append({
            "id": archive.id,
            "archived_at": dt(archive.archived_at),
            "status": "PRESERVED_BUT_UNVERIFIED",
            "recovery_reason": archive.recovery_reason,
            "event_count": archive.event_count,
            "first_event_id": archive.first_event_id,
            "last_event_id": archive.last_event_id,
            "original_head_last_event_id": archive.original_head_last_event_id,
            "original_head_hash": archive.original_head_hash,
            "snapshot_sha256": archive.snapshot_sha256,
            "archive_digest_valid": digest_valid,
        })
    return result


@app.get("/api/admin/audit/archives/{archive_id}", summary="Administrator: read preserved unverified audit events")
def admin_audit_archive_detail(archive_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    require_admin(db, user)
    archive = db.get(AuditEventArchive, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="Audit archive not found.")
    digest_valid = hmac.compare_digest(
        hashlib.sha256(archive.snapshot_json.encode("utf-8")).hexdigest(), archive.snapshot_sha256
    )
    return {
        "id": archive.id,
        "status": "PRESERVED_BUT_UNVERIFIED",
        "archive_digest_valid": digest_valid,
        "snapshot_sha256": archive.snapshot_sha256,
        "snapshot": json.loads(archive.snapshot_json) if digest_valid else None,
        "warning": "Archived events are preserved but the original hash chain could not be authenticated; do not treat them as verified audit evidence.",
    }
