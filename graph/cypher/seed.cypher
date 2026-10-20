# Seed Data - per 05_Backend_Schema.md §2
#
# Minimal smoke-test data ONLY. The hero fraud ring lives in the sample CSVs
# (ingestion/samples/mca_sample.csv + gst_sample.csv), which is the path
# `make bootstrap` exercises end-to-end. This file deliberately contains no
# circular ring, so there is exactly one hero ring in the system.
#
# Relationships follow the current schema (§2.2): an invoice is a
# (seller)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(buyer) path, never a
# direct company-to-company edge.

# ── SMOKE COMPANIES (no cycle) ───────────────────────────────────
CREATE (s1:Company {id: 's1', cin: 'L12345TN2021PLC000001', gstin: '33SMOKE0000A1Z1', name: 'Smoke Test Trading Pvt Ltd', incorporation_date: date('2021-01-10'), status: 'active', authorized_capital: 500000, paid_up_capital: 500000, nic_code: '46900', roc: 'Chennai'})
CREATE (s2:Company {id: 's2', cin: 'L12345TN2022PLC000002', gstin: '33SMOKE0000B2Z2', name: 'Smoke Test Retail Pvt Ltd', incorporation_date: date('2022-03-15'), status: 'active', authorized_capital: 400000, paid_up_capital: 400000, nic_code: '47599', roc: 'Chennai'})

# ── DIRECTOR ─────────────────────────────────────────────────────
CREATE (sd1:Director {id: 'sd1', din: '09990001', name: 'Smoke Test Director', pan_hash: 'hash-smoke-director'})
CREATE (s1)-[:HAS_DIRECTOR]->(sd1)

# ── ADDRESS ──────────────────────────────────────────────────────
CREATE (sa1:Address {id: 'sa1', normalized_address: '1 SMOKE ROAD CHENNAI 600001', raw_address: '1, Smoke Road, Chennai 600001', state: 'Tamil Nadu'})
CREATE (s1)-[:REGISTERED_AT]->(sa1)

# ── BANK ACCOUNT ─────────────────────────────────────────────────
CREATE (sb1:BankAccount {id: 'sb1', ifsc: 'SBIN0009001', account_hash: 'hash-acct-smoke'})
CREATE (s1)-[:OPERATES_ACCOUNT]->(sb1)

# ── ONE OFF-CYCLE INVOICE (seller -> txn -> buyer) ───────────────
CREATE (st1:Transaction {id: 'st1', invoice_no: 'INV-SMOKE-001', amount: 100000, tax_amount: 18000, date: date('2023-06-10'), hsn_sac_code: '46900', eway_bill_ref: 'EWB-SMOKE-1'})
CREATE (s1)-[:BILLED]->(st1)
CREATE (st1)-[:BILLED_TO]->(s2)

# ── GSTIN FILING ─────────────────────────────────────────────────
CREATE (sf1:GSTINFiling {id: 'sf1', period: '2023-06', return_type: 'GSTR-3B', filed_on: date('2023-07-20'), reconciliation_status: 'matched'})
CREATE (s1)-[:FILED_RETURN]->(sf1)
