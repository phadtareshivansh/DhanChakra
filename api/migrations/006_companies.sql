-- 006_companies.sql
CREATE TABLE companies (
    cin TEXT PRIMARY KEY,
    gstin TEXT UNIQUE,
    name TEXT NOT NULL,
    incorporation_date DATE,
    status TEXT,
    authorized_capital REAL,
    paid_up_capital REAL,
    nic_code TEXT,
    roc TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);