# TASK B1 — the movement-record source's coverage window.
#
# The movement-record source is a SINGLETON node: the rule needs one
# authoritative feed to be able to say "this reference has no movement
# record". Its `covers_from` / `covers_to` say which invoice period the feed
# actually covers, so an invoice from outside that window is not flagged.
#
# Without this, a deployment with no e-Way Bill feed (or a feed that only
# covers last quarter) would flag every high-value invoice it sees.
#
# This is a NEW file, applied after 001_eway_bill_movement.cypher (see
# api/benchmarks/apply_schema.py). Every statement is IF NOT EXISTS, so
# re-running is a no-op.

CREATE CONSTRAINT eway_bill_movement_source_id IF NOT EXISTS
FOR (s:EWayBillMovementSource) REQUIRE s.id IS UNIQUE;
