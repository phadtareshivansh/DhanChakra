"""The audit trail (TASK C1).

Everything that changes security-relevant state is written here: admin
actions, failed logins, lockouts, logouts and password resets. The trail
lives in the ``audit_log`` table (migration 004) and is read back through
``GET /audit`` for Super Admin.

The writer is deliberately dumb -- it takes the action name and whatever
context the caller has. Deciding *what* is worth recording is the caller's
job, so the same trail covers auth events and admin actions without either
of them needing to know about the other.
"""

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

# Action names. Kept as constants so the trail can be grepped for what the
# system actually records, and so a typo does not silently create a new
# action nobody looks at.
LOGIN_SUCCEEDED = "login_succeeded"
LOGIN_FAILED = "login_failed"
LOGIN_LOCKED_OUT = "login_locked_out"
LOGOUT = "logout"
TOKEN_REFRESHED = "token_refreshed"
PASSWORD_RESET = "password_reset"
USER_UPDATED = "user_updated"
USER_CREATED = "user_created"


async def log_event(db, action: str, *, user_id: Optional[str] = None,
                    entity_type: Optional[str] = None,
                    entity_id: Optional[str] = None,
                    details: Optional[Dict[str, Any]] = None) -> None:
    """Write one audit entry.

    Never raises: an audit write failing must not turn a successful
    operation into an error response, so problems are logged and swallowed.
    """
    try:
        await db.execute(
            text("""
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, details)
            VALUES (:user_id, :action, :entity_type, :entity_id, :details)
            """),
            {"user_id": user_id, "action": action, "entity_type": entity_type,
             "entity_id": entity_id, "details": json.dumps(details or {})},
        )
        await db.commit()
    except Exception:  # pragma: no cover - the audit trail must not break auth
        import logging
        logging.getLogger(__name__).warning(
            "audit write failed for action %s", action, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
