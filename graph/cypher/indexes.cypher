# Scale indexes - added by TASK A3 scale test (per docs/performance.md)
#
# Why this file exists
# --------------------
# `constraints.cypher` defines the schema's uniqueness constraints, but it was
# never applied to the running database (see docs/performance.md, "Finding 1"):
# the live DB had only the two default token-lookup indexes. Every property
# MATCH/MERGE therefore did a full label scan, which made the batched bulk load
# O(N^2) and every entity lookup linear.
#
# This file is applied idempotently (all statements are IF NOT EXISTS), so it is
# safe to run on every start and on an already-populated database. It adds the
# indexes the product's actual query paths require:
#
#   * :Company(id), :Company(cin), :Company(gstin)   -> get_entity / network /
#                                                       entity resolution
#   * :Director(din), :Address(normalized_address)   -> loader MERGE + lookups
#   * :Transaction(id)                               -> loader MERGE (the single
#                                                       biggest load bottleneck)
#   * :BankAccount(ifsc, account_hash)               -> account lookups
#   * full-text index over name/cin/gstin/din/ifsc   -> search_entities
#
# The full-text index is the honest fix for the search endpoint: the current
# `MATCH (n) WHERE toLower(n.name) CONTAINS ...` pattern cannot use a B-tree
# index at all (it is an unanchored substring match), so it stays an
# AllNodesScan. The query change to use the full-text index is a product
# decision tracked separately; the index is provisioned here so it is available.

CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE;
CREATE CONSTRAINT company_gstin IF NOT EXISTS FOR (c:Company) REQUIRE c.gstin IS UNIQUE;
CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE;

CREATE INDEX company_id_idx IF NOT EXISTS FOR (c:Company) ON (c.id);
CREATE INDEX company_name_idx IF NOT EXISTS FOR (c:Company) ON (c.name);
CREATE INDEX company_risk_score_idx IF NOT EXISTS FOR (c:Company) ON (c.risk_score);
CREATE INDEX director_id_idx IF NOT EXISTS FOR (d:Director) ON (d.id);
CREATE INDEX address_normalized_idx IF NOT EXISTS FOR (a:Address) ON (a.normalized_address);
CREATE INDEX address_id_idx IF NOT EXISTS FOR (a:Address) ON (a.id);
CREATE INDEX bank_ifsc_idx IF NOT EXISTS FOR (b:BankAccount) ON (b.ifsc, b.account_hash);
CREATE INDEX transaction_id_idx IF NOT EXISTS FOR (t:Transaction) ON (t.id);

CREATE FULLTEXT INDEX entity_search_ft IF NOT EXISTS
FOR (n:Company|Director|Address|BankAccount)
ON EACH [n.name, n.cin, n.gstin, n.din, n.ifsc, n.normalized_address];
