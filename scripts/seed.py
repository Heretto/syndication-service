#!/usr/bin/env python3
"""Create the initial admin account for the syndication service.

Run from the syndication-service directory (with the virtualenv active):

    python scripts/seed.py

For unattended / CI use, set ADMIN_EMAIL and ADMIN_PASSWORD as env vars
before running — the script will skip the interactive prompts.
"""
import getpass
import os
import re
import sys
import uuid

# Load .env if present so the script works without manually exporting vars.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from syndication.settings import get_settings
from hop_core.db import init_engine, get_session_factory
from hop_core.models.organization import Organization, OrganizationMember
from hop_core.models.user import User
from hop_core.models.enums import OrganizationRole
from hop_core.core.security import get_password_hash

PASSWORD_MIN_LEN = 12


def _password_error(pw: str) -> str | None:
    if len(pw) < PASSWORD_MIN_LEN:
        return f"Must be at least {PASSWORD_MIN_LEN} characters."
    if not re.search(r"[A-Z]", pw):
        return "Must contain at least one uppercase letter."
    if not re.search(r"\d", pw):
        return "Must contain at least one digit."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-\[\]\\/+=~`';]", pw):
        return "Must contain at least one special character."
    return None


def main() -> None:
    settings = get_settings()
    init_engine(settings.database_url)
    db = get_session_factory()()

    try:
        if db.query(User).filter(User.is_superuser.is_(True)).first():
            print("An admin account already exists. Nothing to do.")
            return

        # ── Email ─────────────────────────────────────────────────────────────
        email = os.environ.get("ADMIN_EMAIL", "").strip()
        if not email:
            email = input("Admin email: ").strip()
        if not email:
            print("Email is required.", file=sys.stderr)
            sys.exit(1)

        # ── Password ──────────────────────────────────────────────────────────
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not password:
            while True:
                password = getpass.getpass("Admin password: ")
                err = _password_error(password)
                if err:
                    print(f"  ✗ {err}")
                    continue
                confirm = getpass.getpass("Confirm password: ")
                if password != confirm:
                    print("  ✗ Passwords do not match.")
                    continue
                break
        else:
            err = _password_error(password)
            if err:
                print(f"ADMIN_PASSWORD: {err}", file=sys.stderr)
                sys.exit(1)

        # ── Org ───────────────────────────────────────────────────────────────
        slug = settings.single_org_slug or "syndication"
        org = db.query(Organization).filter_by(slug=slug).first()
        if not org:
            org = Organization(id=uuid.uuid4(), name=slug.capitalize(), slug=slug)
            db.add(org)
            db.flush()
            print(f"Created organization '{org.name}'.")

        # ── Admin user ────────────────────────────────────────────────────────
        admin = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=get_password_hash(password),
            is_active=True,
            is_superuser=True,
            current_organization_id=org.id,
        )
        db.add(admin)
        db.flush()
        db.add(OrganizationMember(
            user_id=admin.id,
            organization_id=org.id,
            role=OrganizationRole.ADMIN,
        ))
        db.commit()
        print(f"✓ Admin account created: {email}")

    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
