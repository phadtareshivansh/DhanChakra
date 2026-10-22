"""e-Way Bill movement-record source and mismatch classification (TASK B1).

The fraud signal is NOT "this invoice has no e-Way Bill reference string". It
is **"this high-value invoice has no matching e-Way Bill movement record"**.
An e-Way Bill reference is only a *claim* that goods moved; the movement
record is the document that backs it. An invoice may cite a reference that no
movement record supports -- and that gap is the signal.

The movement records are SIMULATED (Backend Schema §2.1): `:EWayBillMovement`
nodes keyed by the e-Way Bill reference, loaded from
``ingestion/samples/eway_movement_sample.csv``. The join is by property --
``Transaction.eway_bill_ref`` (nullable) references ``EWayBillMovement.ref``
(unique) -- so there is no relationship to keep in sync and no stale edge to
mislead an analyst.

A SINGLETON ``:EWayBillMovementSource`` node records which invoice period the
feed covers (``covers_from`` / ``covers_to``). "No matching movement record"
is only asserted for invoices inside that window: a deployment with no feed,
or a feed for another quarter, cannot say that a record is missing. Without
that guard the signal would fire on every high-value invoice a system ever
sees.

A high-value invoice fails to match in one of three ways:

``no_ref``
    The invoice cites no e-Way Bill at all.
``no_movement_record``
    The invoice cites one, but the movement-record source has no record for
    that reference -- the claim is unsupported.
``amount_mismatch``
    A movement record exists, but its value differs from the invoice value by
    more than the tolerance (percentage of the invoice, with an absolute floor
    so small invoices are not flagged on rounding).

The rule lives here, once. :data:`MISMATCH_REASON` is the Cypher fragment used
by the feature extractor, the heuristic score and the explain endpoint;
:func:`classify_mismatch` is its Python mirror, kept in agreement with it by
``api/tests/test_eway.py``.
"""

from typing import Any, Dict, Optional

from ..config import settings


# --- Reason codes -----------------------------------------------------------

MISMATCH_NO_REF = "no_ref"
MISMATCH_NO_MOVEMENT = "no_movement_record"
MISMATCH_AMOUNT = "amount_mismatch"

#: Every reason the detector can produce, in the order they are reported.
MISMATCH_REASONS = (MISMATCH_NO_REF, MISMATCH_NO_MOVEMENT, MISMATCH_AMOUNT)

#: Short, human-readable labels. The UI and the explain endpoint use these so
#: the wording lives next to the rule, not scattered through the frontend.
MISMATCH_LABELS: Dict[str, str] = {
    MISMATCH_NO_REF: "No e-Way Bill reference on a high-value invoice",
    MISMATCH_NO_MOVEMENT: "e-Way Bill reference with no matching movement record",
    MISMATCH_AMOUNT: "e-Way Bill movement value does not match the invoice",
}


# --- Cypher fragments --------------------------------------------------------
#
# `t` must be a bound :Transaction and `m` must be bound by the OPTIONAL
# MATCH below, which joins the invoice to the movement record that claims its
# reference. The reason is NULL when the invoice is properly supported.

#: The movement-record source is a SINGLETON: the rule needs one
#: authoritative feed to say "this reference has no movement record". The
#: loader writes it; see :func:`in_coverage`.
MOVEMENT_SOURCE_ID = "active"

MOVEMENT_OPTIONAL_MATCH = (
    "    OPTIONAL MATCH (m:EWayBillMovement {ref: t.eway_bill_ref})\n"
    f"    OPTIONAL MATCH (src:EWayBillMovementSource {{id: '{MOVEMENT_SOURCE_ID}'}})\n"
)

MISMATCH_REASON = """
    CASE
        WHEN t IS NULL THEN NULL
        WHEN t.eway_bill_ref IS NULL OR trim(t.eway_bill_ref) = '' THEN 'no_ref'
        WHEN m.ref IS NULL
             AND src IS NOT NULL
             AND (src.covers_from IS NULL OR t.date IS NULL OR t.date >= src.covers_from)
             AND (src.covers_to   IS NULL OR t.date IS NULL OR t.date <= src.covers_to)
            THEN 'no_movement_record'
        WHEN m.ref IS NOT NULL
             AND abs(coalesce(m.amount, 0) - t.amount) >
                 CASE WHEN t.amount * $tol_pct > $tol_min
                      THEN t.amount * $tol_pct ELSE $tol_min END
            THEN 'amount_mismatch'
        ELSE NULL
    END
    """


# --- Assembling a query ------------------------------------------------------
#
# The fragments above contain Cypher braces, so they cannot simply be
# interpolated into an f-string. Queries reference them by these tokens
# instead and are rendered with :func:`render`. The tokens are Cypher block
# comments, so an unrendered template is still valid Cypher.

MOVEMENT_JOIN_TOKEN = "/*EWAY_MOVEMENT_JOIN*/"
MISMATCH_REASON_TOKEN = "/*EWAY_MISMATCH_REASON*/"


def render(query: str) -> str:
    """Substitute the movement join and the mismatch reason into a query
    template. Plain string replacement, so the Cypher's own braces and the
    ``$parameter`` placeholders are left untouched."""
    return query.replace(MOVEMENT_JOIN_TOKEN, MOVEMENT_OPTIONAL_MATCH).replace(
        MISMATCH_REASON_TOKEN, MISMATCH_REASON
    )


def mismatch_params() -> Dict[str, float]:
    """Query parameters the :data:`MISMATCH_REASON` fragment needs."""
    return {
        "tol_pct": settings.eway_amount_tolerance_pct,
        "tol_min": settings.eway_amount_tolerance_min,
    }


def tolerance_for(amount: float) -> float:
    """The amount difference above which an invoice and its movement record
    disagree: a percentage of the invoice, with an absolute floor."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    return max(
        amount * settings.eway_amount_tolerance_pct,
        settings.eway_amount_tolerance_min,
    )


def in_coverage(
    invoice_date: Optional[Any] = None,
    covers_from: Optional[Any] = None,
    covers_to: Optional[Any] = None,
) -> bool:
    """Is an invoice inside the movement-record source's coverage window?

    A feed that has not been loaded (``covers_from`` and ``covers_to`` both
    ``None`` and no source at all) covers nothing, so "no movement record"
    cannot be asserted. A feed that IS loaded but does not cover the invoice's
    date cannot be used to say the record is missing either -- the invoice may
    simply predate the feed.

    The invoice date being unknown is treated as *in* coverage: we have no
    evidence that it falls outside the window.
    """
    if covers_from is None and covers_to is None:
        # No source loaded -> the feed is not in use.
        return False
    if invoice_date is None:
        return True
    if covers_from is not None and invoice_date < covers_from:
        return False
    if covers_to is not None and invoice_date > covers_to:
        return False
    return True


def classify_mismatch(
    amount: Optional[float],
    claimed_ref: Optional[str],
    movement_amount: Optional[float] = None,
    covered: bool = True,
) -> Optional[str]:
    """Python mirror of :data:`MISMATCH_REASON`.

    Returns the reason code, or ``None`` when the invoice is properly
    supported by a matching movement record. Used for unit tests and by any
    caller that already holds the invoice and its movement record.

    ``movement_amount`` is ``None`` when no movement record exists for the
    claimed reference.

    ``covered`` says whether the movement-record source covers this invoice.
    When it does not, a missing movement record is not evidence of anything,
    so only the other two reasons can apply.
    """
    ref = (claimed_ref or "").strip()
    if not ref:
        return MISMATCH_NO_REF
    if movement_amount is None:
        return MISMATCH_NO_MOVEMENT if covered else None
    try:
        invoice_value = float(amount or 0.0)
        moved_value = float(movement_amount)
    except (TypeError, ValueError):
        return MISMATCH_AMOUNT
    if abs(moved_value - invoice_value) > tolerance_for(invoice_value):
        return MISMATCH_AMOUNT
    return None


def describe(reason: Optional[str]) -> str:
    """Human-readable label for a reason code."""
    if not reason:
        return ""
    return MISMATCH_LABELS.get(reason, reason)


def summarise(mismatches: Any) -> str:
    """One-line summary of a list of mismatch evidence dicts, for reasons[]."""
    items = list(mismatches or [])
    if not items:
        return ""
    by_reason: Dict[str, int] = {}
    for m in items:
        code = m.get("reason") if isinstance(m, dict) else None
        by_reason[code or "unknown"] = by_reason.get(code or "unknown", 0) + 1
    parts = [
        f"{count} {describe(code).lower()}"
        for code, count in sorted(by_reason.items())
    ]
    return "; ".join(parts)
