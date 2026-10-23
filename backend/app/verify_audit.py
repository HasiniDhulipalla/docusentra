"""Verify the complete audit hash chain from inside the TrustVault API container."""
import json
from app.main import SessionLocal, initialize_database, verify_audit_chain


def main() -> int:
    initialize_database()
    with SessionLocal() as db:
        result = verify_audit_chain(db)
    print(json.dumps(result, indent=2))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
