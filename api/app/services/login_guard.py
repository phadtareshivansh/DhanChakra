"""Login rate limiting and temporary lockout (TASK C1).

Brute-force protection for ``POST /auth/login``. Two independent sliding
counters are kept, both over the ``login_attempts`` table so the decision
survives an API restart and can be audited afterwards:

* **per client IP** -- stops one host spraying many accounts;
* **per account**  -- stops one account being sprayed from many hosts.

Either counter reaching its limit locks the client out for
``login_lockout_minutes``.

Two properties matter as much as the limiting itself:

* The credential failure is **generic**. "Invalid email or password" is
  returned whether the address exists or not, and attempts are counted
  against an address that does not exist exactly as they are against one
  that does -- so the endpoint cannot be used to enumerate accounts.
* The client IP is taken from the socket, not from a header. ``X-Forwarded-For``
  is only honoured when the immediate peer is a proxy we explicitly trust,
  because otherwise anyone could rotate a fake header and walk straight
  past the per-IP limit.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from ..config import settings

logger = logging.getLogger(__name__)


def client_ip(request) -> str:
    """The address to rate-limit against.

    Uses the socket peer. ``X-Forwarded-For`` is consulted only when the
    peer is a trusted proxy, because an untrusted client controls that
    header entirely.
    """
    peer = "unknown"
    if request is not None and request.client is not None:
        peer = request.client.host or "unknown"

    trusted = {
        ip.strip()
        for ip in (settings.trusted_proxy_ips or "").split(",")
        if ip.strip()
    }
    if trusted and peer in trusted:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer


def _window_start() -> datetime:
    return datetime.utcnow() - timedelta(minutes=settings.login_rate_limit_window_minutes)


async def record_attempt(db, email: str, ip: str, succeeded: bool) -> None:
    """Record one login attempt (successful or not)."""
    await db.execute(
        text("""
        INSERT INTO login_attempts (email, client_ip, succeeded, created_at)
        VALUES (:email, :ip, :succeeded, now())
        """),
        {"email": (email or "").strip().lower(), "ip": ip, "succeeded": succeeded},
    )
    await db.commit()


async def clear_attempts(db, email: str, ip: str) -> None:
    """Forget the failures for one (account, IP) pair after a success.

    Only that pair is cleared. The wider per-IP and per-account counters
    stay, so a client that sprayed several accounts cannot buy itself a
    fresh budget by logging in successfully on one of them.
    """
    await db.execute(
        text("""
        DELETE FROM login_attempts
        WHERE succeeded = FALSE
          AND email = :email
          AND client_ip = :ip
        """),
        {"email": (email or "").strip().lower(), "ip": ip},
    )
    await db.commit()


async def _count_failures(db, where: str, params: dict) -> int:
    result = await db.execute(
        text(f"""
        SELECT count(*) AS n
          FROM login_attempts
         WHERE succeeded = FALSE
           AND {where}
           AND created_at >= :since
        """),
        {**params, "since": _window_start()},
    )
    return int(result.scalar_one())


async def failure_counts(db, email: str, ip: str) -> tuple[int, int]:
    """(failures for this IP, failures for this account) inside the window."""
    ip_count = await _count_failures(db, "client_ip = :ip", {"ip": ip})
    account_count = await _count_failures(
        db, "email = :email", {"email": (email or "").strip().lower()}
    )
    return ip_count, account_count


async def lockout_seconds_remaining(db, email: str, ip: str) -> int:
    """Seconds until the client may try again; 0 when it is not locked out.

    The lock lasts for ``login_lockout_minutes`` counted from the most
    recent failure, so a locked-out client has to sit out a full quiet
    period rather than sliding the window forward by retrying.
    """
    ip_count, account_count = await failure_counts(db, email, ip)
    ip_limit = settings.login_max_failures_per_ip
    account_limit = settings.login_max_failures_per_account

    if ip_count < ip_limit and account_count < account_limit:
        return 0

    result = await db.execute(
        text("""
        SELECT max(created_at) AS last
          FROM login_attempts
         WHERE succeeded = FALSE
           AND (client_ip = :ip OR email = :email)
        """),
        {"ip": ip, "email": (email or "").strip().lower()},
    )
    last = result.scalar_one()
    if last is None:
        return 0
    elapsed = (datetime.utcnow() - last).total_seconds()
    remaining = settings.login_lockout_minutes * 60 - elapsed
    return int(remaining) if remaining > 0 else 0


async def is_locked_out(db, email: str, ip: str) -> bool:
    return await lockout_seconds_remaining(db, email, ip) > 0
