"""Generate curated MCA-style filing PDFs for the Phase 5 agentic-ingestion
demo. Pure-python minimal PDF writer (no external deps) producing text-only
pages that pypdf can extract.

Usage: python make_sample_filings.py [outdir]
"""

import os
import sys
import uuid


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines: list) -> bytes:
    """Minimal single-page text PDF."""
    content = ["BT", "/F1 11 Tf", "72 720 Td"]
    for i, line in enumerate(lines):
        y = 720 - 22 * i
        content.append(f"72 {y} Td ({_escape(line)}) Tj")
    content.append("ET")
    stream = "\n".join(content)
    stream_bytes = stream.encode("latin-1", "replace")

    objects = []
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    objects.append(f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1", "replace")
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


FILINGS = {
    "filing_apollo_transport.pdf": [
        "FORM - MGT-7 / AOC-4 EXTRACT",
        "Company Name: Apollo Roadways Private Limited",
        "CIN: U60200MH2024PTC400111",
        "GSTIN: 27AADCA1234M1Z2",
        "Registered Office: 42 Goods Yard Lane, Bhiwandi, Maharashtra 421302",
        "",
        "Directors & Shareholding:",
        "Director 1: Ramesh Kulkarni, DIN: 06754321, Equity: 40%",
        "Director 2: Sunita Kulkarni, DIN: 06754322, Equity: 35%",
        "Director 3: Prakash Kulkarni, DIN: 06754323, Equity: 25%",
        "",
        "This is a digitally generated sample filing for demonstration purposes.",
    ],
    "filing_meridian_trade.pdf": [
        "ANNUAL RETURN EXTRACT — MERIDIAN TRADING LLP",
        "LLP Name: Meridian Trading Solutions LLP",
        "CIN: AAN-2234",
        "Registered Office: 7 Indira Industrial Estate, Bawana, Delhi 110039",
        "",
        "Designated Partners:",
        "1. Anjali Mehta (DIN 08881234) — 60% share",
        "2. Vikram Mehta (DIN 08881235) — 40% share",
        "",
        "Auditor: K. R. Associates, New Delhi",
        "Sample document for the Dhan-Chakra agentic ingestion demo.",
    ],
    "filing_sunrise_agro.pdf": [
        "FORM - MGT-7 / AOC-4 EXTRACT",
        "Company Name: Sunrise Agro Exports Private Limited",
        "CIN: U15100GJ2023PTC900021",
        "GSTIN: 24AABCS3214N1Z5",
        "Registered Office: Plot 8, GIDC Phase II, Vapi, Gujarat 396195",
        "",
        "Directors & Shareholding:",
        "Director 1: Kavita Desai, DIN: 07765432, Equity: 55%",
        "Director 2: Mahesh Desai, DIN: 07765433, Equity: 45%",
        "",
        "This is a digitally generated sample filing for demonstration purposes.",
    ],
    "filing_kite_builders.pdf": [
        "ANNUAL RETURN EXTRACT — KITE BUILDERS & DEVELOPERS",
        "Company Name: Kite Builders & Developers Private Limited",
        "CIN: U45202TS2022PTC450009",
        "GSTIN: 36AACKT7788P1Z9",
        "Registered Office: H.No 12-3-22, Ameerpet, Hyderabad, Telangana 500016",
        "",
        "Directors & Shareholding:",
        "Director 1: Ravi Teja, DIN: 09012345, Equity: 60%",
        "Director 2: Naveen Kumar, DIN: 09012346, Equity: 40%",
        "",
        "This is a digitally generated sample filing for demonstration purposes.",
    ],
    "filing_bluewave_logistics.pdf": [
        "FORM - MGT-7 / AOC-4 EXTRACT",
        "Company Name: Bluewave Logistics Private Limited",
        "CIN: U63030WB2024PTC711882",
        "GSTIN: 19AABCB5678N1Z1",
        "Registered Office: 9 Taratala Road, Kolkata, West Bengal 700088",
        "",
        "Directors & Shareholding:",
        "Director 1: Sushmita Banerjee, DIN: 06543210, Equity: 50%",
        "Director 2: Arindam Sen, DIN: 06543211, Equity: 50%",
        "",
        "This is a digitally generated sample filing for demonstration purposes.",
    ],
}


def main(outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    for fname, lines in FILINGS.items():
        path = os.path.join(outdir, fname)
        with open(path, "wb") as f:
            f.write(build_pdf(lines))
        print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "samples", "filings"))