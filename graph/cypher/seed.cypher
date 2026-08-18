# Seed Data - per 05_Backend_Schema.md §2 + 06_Implementation_Plan.md Phase 6 (hero ring)

# ── HERO FRAUD RING ─────────────────────────────────────────────
# 6 companies in a circular invoice loop A->B->C->D->E->F->A,
# sharing 2 directors, 2 registered addresses, 2 bank accounts.
# Risk scores are intentionally left unset; the structural analytics
# job (POST /analytics/structural) computes and writes them back.

CREATE (c1:Company {id: 'c1', cin: 'L12345MH2020PLC123456', gstin: '27AAAAA0000A1Z5', name: 'Alpha Corp', incorporation_date: date('2020-01-01'), status: 'active', authorized_capital: 1000000, paid_up_capital: 1000000, nic_code: '62099', roc: 'Mumbai'})
CREATE (c2:Company {id: 'c2', cin: 'L12345MH2021PLC123457', gstin: '27AAAAA0000B2Z6', name: 'Beta Industries', incorporation_date: date('2021-02-01'), status: 'active', authorized_capital: 500000, paid_up_capital: 500000, nic_code: '62099', roc: 'Mumbai'})
CREATE (c3:Company {id: 'c3', cin: 'L12345MH2022PLC123458', gstin: '27AAAAA0000C3Z7', name: 'Gamma Solutions', incorporation_date: date('2022-03-01'), status: 'active', authorized_capital: 200000, paid_up_capital: 200000, nic_code: '62099', roc: 'Mumbai'})
CREATE (c4:Company {id: 'c4', cin: 'L12345GJ2021PLC987654', gstin: '24AAAAA0000D4Z8', name: 'Delta Trading Co', incorporation_date: date('2021-05-15'), status: 'active', authorized_capital: 300000, paid_up_capital: 300000, nic_code: '46900', roc: 'Ahmedabad'})
CREATE (c5:Company {id: 'c5', cin: 'L12345GJ2022PLC987655', gstin: '24AAAAA0000E5Z9', name: 'Epsilon Exports', incorporation_date: date('2022-07-20'), status: 'active', authorized_capital: 250000, paid_up_capital: 250000, nic_code: '46900', roc: 'Ahmedabad'})
CREATE (c6:Company {id: 'c6', cin: 'L12345DL2021PLC555111', gstin: '07AAAAA0000F6A1', name: 'Zeta Enterprises', incorporation_date: date('2021-09-30'), status: 'active', authorized_capital: 400000, paid_up_capital: 400000, nic_code: '62099', roc: 'Delhi'})

# ── CLEAN COMPANIES (control group) ─────────────────────────────
CREATE (n1:Company {id: 'n1', cin: 'L12345KA2021PLC111222', gstin: '29AAAAA0000G7B2', name: 'Nova Retail Pvt Ltd', incorporation_date: date('2021-04-10'), status: 'active', authorized_capital: 800000, paid_up_capital: 800000, nic_code: '47599', roc: 'Bangalore'})
CREATE (n2:Company {id: 'n2', cin: 'L12345TN2020PLC333444', gstin: '33AAAAA0000H8C3', name: 'Solstice Foods', incorporation_date: date('2020-11-05'), status: 'active', authorized_capital: 1200000, paid_up_capital: 1200000, nic_code: '10799', roc: 'Chennai'})

# ── DIRECTORS ────────────────────────────────────────────────────
CREATE (d1:Director {id: 'd1', din: '01234567', name: 'Rajesh Kumar', pan_hash: 'hash-rajesh-kumar'})
CREATE (d2:Director {id: 'd2', din: '01234568', name: 'Suresh Patel', pan_hash: 'hash-suresh-patel'})
CREATE (d3:Director {id: 'd3', din: '07654321', name: 'Anita Desai', pan_hash: 'hash-anita-desai'})
CREATE (d4:Director {id: 'd4', din: '08765432', name: 'Vikram Singh', pan_hash: 'hash-vikram-singh'})

# ── ADDRESSES ────────────────────────────────────────────────────
CREATE (a1:Address {id: 'a1', normalized_address: '101 MAKER TOWERS MUMBAI 400001', raw_address: '101, Maker Towers, Mumbai 400001', state: 'Maharashtra'})
CREATE (a2:Address {id: 'a2', normalized_address: '202 GIDC ESTATE AHMEDABAD 380015', raw_address: '202, GIDC Estate, Ahmedabad 380015', state: 'Gujarat'})
CREATE (a3:Address {id: 'a3', normalized_address: '303 MG ROAD BANGALORE 560001', raw_address: '303, MG Road, Bangalore 560001', state: 'Karnataka'})
CREATE (a4:Address {id: 'a4', normalized_address: '404 KODAMBAKKAM CHENNAI 600024', raw_address: '404, Kodambakkam, Chennai 600024', state: 'Tamil Nadu'})

# ── BANK ACCOUNTS ────────────────────────────────────────────────
CREATE (b1:BankAccount {id: 'b1', ifsc: 'HDFC0000123', account_hash: 'hash-acct-111'})
CREATE (b2:BankAccount {id: 'b2', ifsc: 'ICIC0000456', account_hash: 'hash-acct-222'})
CREATE (b3:BankAccount {id: 'b3', ifsc: 'SBIN0000789', account_hash: 'hash-acct-333'})

# ── HERO RING: SHARED DIRECTORS (entity resolution signal) ──────
CREATE (c1)-[:HAS_DIRECTOR]->(d1)
CREATE (c2)-[:HAS_DIRECTOR]->(d1)
CREATE (c3)-[:HAS_DIRECTOR]->(d2)
CREATE (c4)-[:HAS_DIRECTOR]->(d2)
CREATE (c5)-[:HAS_DIRECTOR]->(d1)
CREATE (c6)-[:HAS_DIRECTOR]->(d2)

# Clean companies, distinct directors
CREATE (n1)-[:HAS_DIRECTOR]->(d3)
CREATE (n2)-[:HAS_DIRECTOR]->(d4)

# ── HERO RING: SHARED REGISTERED ADDRESSES ──────────────────────
CREATE (c1)-[:REGISTERED_AT]->(a1)
CREATE (c2)-[:REGISTERED_AT]->(a1)
CREATE (c3)-[:REGISTERED_AT]->(a2)
CREATE (c4)-[:REGISTERED_AT]->(a2)
CREATE (c5)-[:REGISTERED_AT]->(a1)
CREATE (c6)-[:REGISTERED_AT]->(a2)
CREATE (n1)-[:REGISTERED_AT]->(a3)
CREATE (n2)-[:REGISTERED_AT]->(a4)

# ── HERO RING: BANK ACCOUNTS ────────────────────────────────────
CREATE (c1)-[:OPERATES_ACCOUNT]->(b1)
CREATE (c2)-[:OPERATES_ACCOUNT]->(b1)
CREATE (c3)-[:OPERATES_ACCOUNT]->(b2)
CREATE (c4)-[:OPERATES_ACCOUNT]->(b2)
CREATE (c5)-[:OPERATES_ACCOUNT]->(b1)
CREATE (c6)-[:OPERATES_ACCOUNT]->(b2)

# ── CIRCULAR INVOICE LOOP A→B→C→D→E→F→A (4-month cycle, FY 2023-24) ──
CREATE (c1)-[:TRANSACTS_WITH {id: 't01', gstin_seller: '27AAAAA0000A1Z5', gstin_buyer: '27AAAAA0000B2Z6', amount: 500000, invoice_date: date('2023-04-01'), return_period: '2023-04'}]->(c2)
CREATE (c2)-[:TRANSACTS_WITH {id: 't02', gstin_seller: '27AAAAA0000B2Z6', gstin_buyer: '27AAAAA0000C3Z7', amount: 300000, invoice_date: date('2023-04-02'), return_period: '2023-04'}]->(c3)
CREATE (c3)-[:TRANSACTS_WITH {id: 't03', gstin_seller: '27AAAAA0000C3Z7', gstin_buyer: '24AAAAA0000D4Z8', amount: 200000, invoice_date: date('2023-04-03'), return_period: '2023-04'}]->(c4)
CREATE (c4)-[:TRANSACTS_WITH {id: 't04', gstin_seller: '24AAAAA0000D4Z8', gstin_buyer: '24AAAAA0000E5Z9', amount: 250000, invoice_date: date('2023-04-04'), return_period: '2023-04'}]->(c5)
CREATE (c5)-[:TRANSACTS_WITH {id: 't05', gstin_seller: '24AAAAA0000E5Z9', gstin_buyer: '07AAAAA0000F6A1', amount: 180000, invoice_date: date('2023-04-05'), return_period: '2023-04'}]->(c6)
CREATE (c6)-[:TRANSACTS_WITH {id: 't06', gstin_seller: '07AAAAA0000F6A1', gstin_buyer: '27AAAAA0000A1Z5', amount: 450000, invoice_date: date('2023-04-06'), return_period: '2023-04'}]->(c1)

# Second pass of the same cycle (strengthens the pattern)
CREATE (c1)-[:TRANSACTS_WITH {id: 't07', gstin_seller: '27AAAAA0000A1Z5', gstin_buyer: '27AAAAA0000B2Z6', amount: 510000, invoice_date: date('2023-05-01'), return_period: '2023-05'}]->(c2)
CREATE (c2)-[:TRANSACTS_WITH {id: 't08', gstin_seller: '27AAAAA0000B2Z6', gstin_buyer: '27AAAAA0000C3Z7', amount: 310000, invoice_date: date('2023-05-02'), return_period: '2023-05'}]->(c3)
CREATE (c3)-[:TRANSACTS_WITH {id: 't09', gstin_seller: '27AAAAA0000C3Z7', gstin_buyer: '24AAAAA0000D4Z8', amount: 205000, invoice_date: date('2023-05-03'), return_period: '2023-05'}]->(c4)
CREATE (c4)-[:TRANSACTS_WITH {id: 't10', gstin_seller: '24AAAAA0000D4Z8', gstin_buyer: '24AAAAA0000E5Z9', amount: 255000, invoice_date: date('2023-05-04'), return_period: '2023-05'}]->(c5)
CREATE (c5)-[:TRANSACTS_WITH {id: 't11', gstin_seller: '24AAAAA0000E5Z9', gstin_buyer: '07AAAAA0000F6A1', amount: 185000, invoice_date: date('2023-05-05'), return_period: '2023-05'}]->(c6)
CREATE (c6)-[:TRANSACTS_WITH {id: 't12', gstin_seller: '07AAAAA0000F6A1', gstin_buyer: '27AAAAA0000A1Z5', amount: 460000, invoice_date: date('2023-05-06'), return_period: '2023-05'}]->(c1)

# ── CLEAN TRANSACTIONS (single edge, no cycle) ──────────────────
CREATE (n1)-[:TRANSACTS_WITH {id: 't13', gstin_seller: '29AAAAA0000G7B2', gstin_buyer: '33AAAAA0000H8C3', amount: 120000, invoice_date: date('2023-06-10'), return_period: '2023-06'}]->(n2)

# ── GSTIN FILINGS (filing gaps = risk signal) ───────────────────
CREATE (f1:GSTINFiling {id: 'f1', period: '2023-Q2', return_type: 'GSTR-3B', filed_on: date('2023-07-20'), reconciliation_status: 'mismatched'})
CREATE (f2:GSTINFiling {id: 'f2', period: '2023-Q2', return_type: 'GSTR-1', filed_on: date('2023-07-11'), reconciliation_status: 'mismatched'})
CREATE (c1)-[:FILED_RETURN]->(f1)
CREATE (c1)-[:FILED_RETURN]->(f2)
CREATE (n1)-[:FILED_RETURN]->(f1)
