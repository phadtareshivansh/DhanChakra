# Neo4j Constraints & Indexes - per 05_Backend_Schema.md §2.4

CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE;
CREATE CONSTRAINT company_gstin IF NOT EXISTS FOR (c:Company) REQUIRE c.gstin IS UNIQUE;
CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE;
CREATE INDEX company_name_idx IF NOT EXISTS FOR (c:Company) ON (c.name);
CREATE INDEX address_normalized_idx IF NOT EXISTS FOR (a:Address) ON (a.normalized_address);
CREATE INDEX bank_ifsc_idx IF NOT EXISTS FOR (b:BankAccount) ON (b.ifsc, b.account_hash);
CREATE INDEX company_risk_score_idx IF NOT EXISTS FOR (c:Company) ON (c.risk_score);
