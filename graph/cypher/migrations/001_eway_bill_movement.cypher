# TASK B1 — e-Way Bill movement-record source.
#
# :EWayBillMovement nodes are the SIMULATED movement-record source: one node
# per e-Way Bill that a movement record exists for, keyed by the reference the
# invoice cites. The join is by property:
#
#     Transaction.eway_bill_ref  ->  EWayBillMovement.ref
#
# The uniqueness constraint makes that key authoritative — two records for the
# same reference are a data error, not something to merge. The index on
# Transaction.eway_bill_ref keeps the join a lookup instead of a scan (see
# docs/performance.md).
#
# This is a NEW file, applied after graph/cypher/constraints.cypher and
# graph/cypher/indexes.cypher (see api/benchmarks/apply_schema.py). Every
# statement is IF NOT EXISTS, so re-running is a no-op.

CREATE CONSTRAINT eway_bill_movement_ref IF NOT EXISTS
FOR (m:EWayBillMovement) REQUIRE m.ref IS UNIQUE;

CREATE INDEX transaction_eway_bill_ref IF NOT EXISTS
FOR (t:Transaction) ON (t.eway_bill_ref);
