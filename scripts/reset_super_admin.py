#!/usr/bin/env python3
"""Break-glass recovery for a forgotten Super Admin password (CLI only).

There is deliberately **no API endpoint** for this: the fixed 3-slot role model
has no self-service account recovery, so the only way back in after a lost
Super Admin password is an operator running this script on the host.

It reads SUPER_ADMIN_EMAIL / SUPER_ADMIN_PASSWORD from the environment, rehashes
the password, and updates the *existing* admin row in place (never inserts, never
touches the analyst slots). It refuses to run if those values are missing or are
still placeholders.

Run it inside the API container (which has the app env + dependencies):

    docker compose exec api python /scripts/reset_super_admin.py [--dry-run]

Exit codes:
    0  success (or a --dry-run that would have succeeded)
    1  unexpected error
    2  SUPER_ADMIN_EMAIL/PASSWORD missing or a placeholder
    3  no admin row exists (run the normal seed path instead)
    4  more than one admin row exists (invariant broken)
    5  admin email differs from SUPER_ADMIN_EMAIL and --allow-email-change absent
    6  --allow-email-change given but the new email already belongs to another row
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

# The script lives in /scripts (read-only mount) while the app package lives in
# /app, so make `from app... import ...` work regardless of the CWD.
for candidate in ("/app", str(pathlib.Path(__file__).resolve().parents[1] / "api")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from sqlalchemy import text  # noqa: E402

from app.config import PLACEHOLDER_SECRETS, settings  # noqa: E402
from app.deps import async_session_maker  # noqa: E402
from app.services import auth_service, case_service  # noqa: E402

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_MISSING_ENV = 2
EXIT_NO_ADMIN = 3
EXIT_MULTIPLE_ADMINS = 4
EXIT_EMAIL_CHANGE_NOT_ALLOWED = 5
EXIT_EMAIL_TAKEN = 6

ACTION = "super_admin_recovery"


def _fail(code: int, message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def _credentials_problem() -> str | None:
    """Return a human message if the recovery credentials are unusable."""
    email = (settings.super_admin_email or "").strip()
    password = (settings.super_admin_password or "").strip()
    if not email:
        return "SUPER_ADMIN_EMAIL is not set"
    if not password:
        return "SUPER_ADMIN_PASSWORD is not set"
    if password.lower() in PLACEHOLDER_SECRETS:
        return "SUPER_ADMIN_PASSWORD is still a placeholder"
    return None


async def _run(allow_email_change: bool, dry_run: bool) -> int:
    problem = _credentials_problem()
    if problem:
        return _fail(EXIT_MISSING_ENV, problem)

    email = settings.super_admin_email.strip()
    password = settings.super_admin_password.strip()

    async with async_session_maker() as db:
        rows = (await db.execute(
            text("SELECT id, email FROM users WHERE role = 'admin' ORDER BY created_at, id")
        )).fetchall()

        if not rows:
            return _fail(
                EXIT_NO_ADMIN,
                "no admin row exists — run `make bootstrap` (or the seed path) "
                "to create the Super Admin before recovering it",
            )
        if len(rows) > 1:
            return _fail(
                EXIT_MULTIPLE_ADMINS,
                f"found {len(rows)} admin rows but the role model allows exactly "
                "one; refusing to guess which to update",
            )

        admin_id = str(rows[0].id)
        current_email = rows[0].email
        email_changes = current_email != email

        if email_changes and not allow_email_change:
            return _fail(
                EXIT_EMAIL_CHANGE_NOT_ALLOWED,
                f"admin email is {current_email!r} but SUPER_ADMIN_EMAIL is "
                f"{email!r}; pass --allow-email-change to re-point the slot",
            )

        if email_changes:
            clash = (await db.execute(
                text("SELECT id FROM users WHERE email = :email AND id <> :id"),
                {"email": email, "id": admin_id},
            )).fetchone()
            if clash:
                return _fail(
                    EXIT_EMAIL_TAKEN,
                    f"email {email!r} already belongs to another user "
                    f"({clash.id}); refusing to overwrite it",
                )

        if dry_run:
            what = "rehash password"
            if email_changes:
                what += f" and move email {current_email!r} -> {email!r}"
            print(f"[dry-run] would {what} for Super Admin (id {admin_id})")
            return EXIT_OK

        # One transaction: the password/email UPDATE and its audit row.
        await db.execute(
            text("UPDATE users SET password_hash = :h, email = :email WHERE id = :id"),
            {"h": auth_service.hash_password(password), "email": email, "id": admin_id},
        )
        # Out-of-band operator action: no authenticated user performed it, so
        # user_id is NULL (the column is nullable) and the target is recorded
        # in entity_id. Never store the password or its hash here.
        await case_service.log_audit(
            db,
            None,
            ACTION,
            "user",
            admin_id,
            {"via": "cli", "email_changed": email_changes, "dry_run": False},
        )

    print(f"updated Super Admin {email} (id {admin_id}, password rehashed)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-email-change", action="store_true",
        help="allow SUPER_ADMIN_EMAIL to re-point an existing admin row "
             "(refused if the new email already belongs to another user)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change and exit without writing (no audit row)",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_run(args.allow_email_change, args.dry_run))
    except KeyboardInterrupt:
        return EXIT_UNEXPECTED
    except Exception as exc:  # noqa: BLE001 - surface any failure as a clear exit
        return _fail(EXIT_UNEXPECTED, f"unexpected failure: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
