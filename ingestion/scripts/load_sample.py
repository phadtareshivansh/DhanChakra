import argparse
import hashlib
import os
import uuid

import pandas as pd
from neo4j import GraphDatabase


def _load_dotenv(path: str) -> None:
    """Best-effort load of a .env file so secrets never need hardcoding."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise SystemExit(
        "NEO4J_PASSWORD is not set. Define it in .env (see .env.example)."
    )


def _uid(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_date(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return v


def _maybe(row, *names):
    for n in names:
        if n in row.index and pd.notna(row[n]) and str(row[n]).strip():
            return str(row[n]).strip()
    return None


def _norm_din(v) -> str:
    """Normalize a director DIN to an 8-digit zero-padded string.
    CSV/pandas may yield '03459904', '3459904', or '3459904.0'."""
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(8)


def _norm_addr(addr: str, state: str) -> str:
    return "|".join(p.strip().lower() for p in [addr, state] if p)


def load_mca_csv(file_path: str):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    df = pd.read_csv(file_path)
    counts = {"Company": 0, "Director": 0, "Address": 0, "BankAccount": 0}
    with driver.session() as session:
        for _, row in df.iterrows():
            cin = str(row["CIN"]).strip()
            gstin = _maybe(row, "GSTIN")
            name = str(row["Company Name"]).strip()
            cid = _uid("company:" + cin)
            session.run(
                """
                MERGE (c:Company {cin: $cin})
                SET c.id = $id,
                    c.gstin = $gstin,
                    c.name = $name,
                    c.incorporation_date = CASE WHEN $inc_date IS NULL THEN c.incorporation_date ELSE date($inc_date) END,
                    c.status = $status,
                    c.authorized_capital = $auth_cap,
                    c.paid_up_capital = $paid_cap,
                    c.nic_code = $nic_code,
                    c.roc = $roc,
                    c.updated_at = datetime()
                """,
                cin=cin, id=cid, gstin=gstin, name=name,
                inc_date=_to_date(_maybe(row, "Date of Incorporation")),
                status=_maybe(row, "Status"), auth_cap=_to_float(_maybe(row, "Authorized Capital")),
                paid_cap=_to_float(_maybe(row, "Paid Up Capital")),
                nic_code=_maybe(row, "NIC Code"), roc=_maybe(row, "ROC"),
            )
            counts["Company"] += 1

            din = _norm_din(_maybe(row, "Director DIN"))
            if din:
                did = _uid("director:" + din)
                session.run(
                    """
                    MERGE (d:Director {din: $din})
                    SET d.id = $id,
                        d.name = $dname,
                        d.pan_hash = $pan_hash
                    WITH d
                    MATCH (c:Company {cin: $cin})
                    MERGE (d)-[:DIRECTOR_OF {appointed_date: date($appt)}]->(c)
                    """,
                    din=din, id=did, dname=_maybe(row, "Director Name"),
                    pan_hash=_maybe(row, "PAN Hash"), appt=_to_date(_maybe(row, "Appointment Date")),
                    cin=cin,
                )
                counts["Director"] += 1

            addr = _maybe(row, "Registered Address")
            if addr:
                state = _maybe(row, "State") or ""
                aid = _uid("address:" + _norm_addr(addr, state))
                session.run(
                    """
                    MERGE (a:Address {normalized_address: $norm})
                    SET a.id = $id,
                        a.raw_address = $raw,
                        a.state = $state,
                        a.lat = $lat,
                        a.lng = $lng
                    WITH a
                    MATCH (c:Company {cin: $cin})
                    MERGE (c)-[:REGISTERED_AT {since_date: date($since)}]->(a)
                    """,
                    norm=_norm_addr(addr, state), id=aid, raw=addr, state=state,
                    lat=_to_float(_maybe(row, "Lat")), lng=_to_float(_maybe(row, "Lng")),
                    since=_to_date(_maybe(row, "Since Date")), cin=cin,
                )
                counts["Address"] += 1

            ifsc = _maybe(row, "IFSC")
            if ifsc:
                acct_hash = _maybe(row, "Account Hash") or hashlib.sha256(ifsc.encode()).hexdigest()
                bid = _uid("bank:" + ifsc)
                session.run(
                    """
                    MERGE (b:BankAccount {ifsc: $ifsc, account_hash: $acct_hash})
                    SET b.id = $id
                    WITH b
                    MATCH (c:Company {cin: $cin})
                    MERGE (c)-[:OPERATES_ACCOUNT {since_date: date($since)}]->(b)
                    """,
                    ifsc=ifsc, acct_hash=acct_hash, id=bid, since=_to_date(_maybe(row, "Since Date")), cin=cin,
                )
                counts["BankAccount"] += 1
    driver.close()
    print(f"Loaded: {counts}")


def load_gst_csv(file_path: str):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    df = pd.read_csv(file_path)
    counts = {"Transaction": 0, "GSTINFiling": 0}
    with driver.session() as session:
        for _, row in df.iterrows():
            seller = str(row["GSTIN Seller"]).strip()
            buyer = str(row["GSTIN Buyer"]).strip()
            amount = _to_float(_maybe(row, "Invoice Value"))
            inv_date = _to_date(_maybe(row, "Invoice Date"))
            period = _maybe(row, "Return Period")
            invoice_no = _maybe(row, "Invoice No") or f"INV-{seller[:4]}-{buyer[:4]}"
            tid = _uid(f"txn:{seller}:{buyer}:{invoice_no}")

            session.run(
                """
                MATCH (seller:Company {gstin: $seller})
                MATCH (buyer:Company {gstin: $buyer})
                MERGE (t:Transaction {id: $tid})
                SET t.invoice_no = $invoice_no,
                    t.amount = $amount,
                    t.tax_amount = $tax,
                    t.date = date($date),
                    t.hsn_sac_code = $hsn,
                    t.eway_bill_ref = $eway
                MERGE (seller)-[:BILLED]->(t)
                MERGE (t)-[:BILLED_TO]->(buyer)
                """,
                seller=seller, buyer=buyer, tid=tid, invoice_no=invoice_no,
                amount=amount, tax=_to_float(_maybe(row, "Tax Amount")),
                date=inv_date, hsn=_maybe(row, "HSN/SAC Code"), eway=_maybe(row, "Eway Bill Ref"),
            )
            counts["Transaction"] += 1

            if period:
                fid = _uid(f"filing:{buyer}:{period}")
                session.run(
                    """
                    MERGE (f:GSTINFiling {id: $fid})
                    SET f.period = $period,
                        f.return_type = $return_type,
                        f.filed_on = CASE WHEN $filed IS NULL THEN f.filed_on ELSE date($filed) END,
                        f.reconciliation_status = $status
                    WITH f
                    MATCH (c:Company {gstin: $gstin})
                    MERGE (c)-[:FILED_RETURN]->(f)
                    """,
                    fid=fid, period=period, return_type=_maybe(row, "Return Type") or "GSTR-3B",
                    filed=inv_date, status=_maybe(row, "Reconciliation Status") or "pending",
                    gstin=buyer,
                )
                counts["GSTINFiling"] += 1

            session.run(
                """
                MATCH (c:Company {gstin: $gstin})
                SET c.updated_at = datetime()
                """,
                gstin=buyer,
            )
    driver.close()
    print(f"Loaded: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load sample CSVs into Neo4j per 05_Backend_Schema.md §2")
    parser.add_argument("--file", required=True, help="Path to CSV file")
    parser.add_argument("--type", required=True, choices=["mca", "gst"])
    args = parser.parse_args()
    if args.type == "mca":
        load_mca_csv(args.file)
    else:
        load_gst_csv(args.file)
