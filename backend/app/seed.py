"""Seed idempotent TrustVault demo roles and one private example document.

Local demo credentials are intentionally DEVELOPMENT-ONLY. Production uses explicit
SEED_* environment variables and must not use these defaults.
Run in Docker: docker compose exec api python -m app.seed
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import func, or_, select

from app.main import (
    APP_ENV, STORAGE_BACKEND, STORAGE_DIR, Document, DocumentShare, SessionLocal, User,
    _blob_path, hash_password, initialize_database, now_utc, record_event, validate_runtime_config,
)

LOCAL_DEMO = {
    "admin": ("admin", "admin@example.local", "AdminDemo!2026#Vault"),
    "owner": ("owner", "owner@example.local", "OwnerDemo!2026#Vault"),
    "viewer": ("viewer", "viewer@example.local", "ViewerDemo!2026#Vault"),
}


def _configuration(role: str) -> tuple[str, str, str]:
    username, email, password = LOCAL_DEMO[role]
    prefix = f"SEED_{role.upper()}_"
    if APP_ENV == "production":
        values = (os.getenv(prefix + "USERNAME", "").strip(),
                  os.getenv(prefix + "EMAIL", "").strip().lower(),
                  os.getenv(prefix + "PASSWORD", ""))
        if not all(values):
            raise RuntimeError(f"Production seeding requires {prefix}USERNAME, {prefix}EMAIL and {prefix}PASSWORD.")
        return values
    return (os.getenv(prefix + "USERNAME", "").strip() or username,
            os.getenv(prefix + "EMAIL", "").strip().lower() or email,
            os.getenv(prefix + "PASSWORD", "") or password)


def _resolve_existing_seed_user(found_by_name: User | None, found_by_email: User | None) -> User | None:
    """Only reuse a seed account when both configured identifiers resolve to the same user.

    A one-sided username/email collision must never silently promote or reset an unrelated
    account, especially when provisioning the administrator in a production database.
    """
    if found_by_name is None and found_by_email is None:
        return None
    if found_by_name is not None and found_by_email is not None and found_by_name.id == found_by_email.id:
        return found_by_name
    raise RuntimeError(
        "Seed identity collision: the configured username and email do not both match the "
        "same existing account. Choose unused seed identifiers or reconcile the account manually."
    )




def _store_sample_file(storage_key: str, content: bytes) -> None:
    """Store the demonstration file in local disk or a connected private Vercel Blob store."""
    if STORAGE_BACKEND == "vercel_blob":
        try:
            from vercel.blob import sync as blob_sync
            blob_sync.put_blob(_blob_path(storage_key), content, access="private", content_type="text/plain", add_random_suffix=False)
        except Exception as exc:
            raise RuntimeError("Could not store the demo document in private Vercel Blob storage.") from exc
    else:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / storage_key).write_bytes(content)


def _sample_file_exists(storage_key: str) -> bool:
    if STORAGE_BACKEND == "vercel_blob":
        try:
            from vercel.blob import sync as blob_sync
            blob_sync.head_blob(_blob_path(storage_key))
            return True
        except FileNotFoundError:
            return False
        except Exception as exc:
            raise RuntimeError("Could not check the demo document in private Vercel Blob storage.") from exc
    return (STORAGE_DIR / storage_key).is_file()


def seed() -> None:
    validate_runtime_config()
    initialize_database()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        users: dict[str, User] = {}
        created: list[str] = []
        for role in ("admin", "owner", "viewer"):
            username, email, password = _configuration(role)
            if len(password) < 16:
                raise RuntimeError(f"Seed password for {role} must be at least 16 characters.")
            found_by_name = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
            found_by_email = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
            try:
                user = _resolve_existing_seed_user(found_by_name, found_by_email)
            except RuntimeError as exc:
                raise RuntimeError(f"Seed identity collision for {role}; resolve it manually first.") from exc
            if user is None:
                user = User(username=username.lower(), email=email, password_hash=hash_password(password), system_role=role)
                db.add(user)
                db.flush()
                created.append(role)
            else:
                user.system_role = role
                user.email = email
                user.password_hash = hash_password(password)
            users[role] = user
        db.commit()
        for role in created:
            record_event(db, users["admin"].id, None, "DEMO_ACCOUNT_SEEDED", f"Seeded {role} demonstration account.", users[role].username)
        db.commit()

        owner = users["owner"]
        viewer = users["viewer"]
        sample_name = "sample-access-review.txt"
        sample = db.scalar(select(Document).where(Document.owner_id == owner.id, Document.filename == sample_name))
        sample_text = (
            "TrustVault demonstration document\n"
            "Category: Security\n\n"
            "This sample is visible to the seeded viewer because the owner granted Reader access.\n"
            "Try previewing it, then revoke the viewer grant from the owner account.\n"
            "The server must block subsequent preview page requests and original downloads.\n"
        )
        if sample is None:
            storage_key = uuid.uuid4().hex
            _store_sample_file(storage_key, sample_text.encode("utf-8"))
            sample = Document(owner_id=owner.id, filename=sample_name, category="Security",
                              storage_key=storage_key, content_type="text/plain", size_bytes=len(sample_text.encode()),
                              created_at=now_utc(), updated_at=now_utc())
            db.add(sample)
            db.flush()
            record_event(db, owner.id, sample.id, "DOCUMENT_UPLOADED", "Seeded security sample document.")
            db.commit()
            db.refresh(sample)
        elif not _sample_file_exists(sample.storage_key):
            _store_sample_file(sample.storage_key, sample_text.encode("utf-8"))
            sample.size_bytes = len(sample_text.encode())
            db.commit()

        grant = db.scalar(select(DocumentShare).where(DocumentShare.document_id == sample.id, DocumentShare.user_id == viewer.id))
        if grant is None:
            grant = DocumentShare(document_id=sample.id, user_id=viewer.id, granted_by=owner.id,
                                  role="reader", created_at=now_utc())
            db.add(grant)
            record_event(db, owner.id, sample.id, "ACCESS_GRANTED", "Granted reader access to the seeded viewer.", viewer.username)
            db.commit()
        print("TrustVault seed complete.")
        print("Accounts created/updated: administrator, owner, viewer")
        print(f"Sample document: {sample_name} (category: Security); viewer has Reader access.")
        if APP_ENV != "production":
            print("DEVELOPMENT-ONLY demo credentials:")
            for role in ("admin", "owner", "viewer"):
                username, email, password = _configuration(role)
                print(f"  {role}: {username} / {password} ({email})")
        else:
            print("Production seed credentials were taken from environment variables; they were not printed.")


if __name__ == "__main__":
    seed()
