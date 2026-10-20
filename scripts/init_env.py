#!/usr/bin/env python3
"""Create a local .env from .env.example with freshly generated secrets.

No credential ever lives in the repository: this fills the placeholders with
random values and writes the result to .env (gitignored, mode 0600). Run it
once on a fresh clone, then `make up && make bootstrap`.

    python3 scripts/init_env.py [--force]
"""

from __future__ import annotations

import argparse
import pathlib
import secrets

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"

PLACEHOLDERS = {"", "change-me"}
DEFAULT_SUPER_ADMIN_EMAIL = "officer@dggi.gov.in"
DEFAULT_USER1_EMAIL = "analyst@dggi.gov.in"
DEFAULT_USER2_EMAIL = "analyst2@dggi.gov.in"


def _token(nbytes: int) -> str:
    return secrets.token_urlsafe(nbytes)


def build(text: str, super_admin_email: str, user1_email: str,
          user2_email: str) -> tuple[str, dict[str, str]]:
    """Return the rendered .env plus the secrets we generated."""
    generated = {
        "JWT_SECRET": _token(48),
        "NEO4J_PASSWORD": _token(18),
        "POSTGRES_PASSWORD": _token(18),
        "SUPER_ADMIN_PASSWORD": _token(12),
        "USER1_PASSWORD": _token(12),
        "USER2_PASSWORD": _token(12),
    }
    emails = {
        "SUPER_ADMIN_EMAIL": super_admin_email,
        "USER1_EMAIL": user1_email,
        "USER2_EMAIL": user2_email,
    }

    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in generated and value.strip() in PLACEHOLDERS:
            out.append(f"{key}={generated[key]}")
        elif key in emails and not value.strip():
            out.append(f"{key}={emails[key]}")
        elif key == "SEED_DEMO_USERS":
            # A local stack wants the demo logins to exist.
            out.append("SEED_DEMO_USERS=true")
        elif key == "APP_ENV" and not value.strip():
            out.append("APP_ENV=development")
        else:
            out.append(line)
    return "\n".join(out) + "\n", generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing .env (default: keep it)")
    parser.add_argument("--super-admin-email", default=DEFAULT_SUPER_ADMIN_EMAIL)
    parser.add_argument("--user1-email", default=DEFAULT_USER1_EMAIL)
    parser.add_argument("--user2-email", default=DEFAULT_USER2_EMAIL)
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(f"{TARGET.name} already exists — leaving it untouched (use --force to overwrite).")
        return 0
    if not TEMPLATE.exists():
        print(f"error: {TEMPLATE} not found; run this from a full checkout.")
        return 1

    rendered, generated = build(
        TEMPLATE.read_text(encoding="utf-8"), args.super_admin_email,
        args.user1_email, args.user2_email,
    )
    TARGET.write_text(rendered, encoding="utf-8")
    TARGET.chmod(0o600)

    print(f"wrote {TARGET.name} with generated secrets")
    print()
    # Never print passwords: report only where they were written.
    print("  seeded logins written to .env (SEED_DEMO_USERS=true):")
    print(f"    super admin {args.super_admin_email}")
    print(f"    user 1      {args.user1_email}")
    print(f"    user 2      {args.user2_email}")
    print("  passwords were generated into .env and are not echoed here.")
    print()
    print("  next:  make up && make bootstrap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
