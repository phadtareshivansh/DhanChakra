"""Privacy guard for sample data (PRD §9 / §NFR Privacy, TRD §7).

The demo dataset must contain no real PAN or Aadhaar identifiers: identity
fields are hashed (see Director.pan_hash) or synthetic. This test makes that
policy enforceable rather than aspirational.

Rules enforced over every file under the explicit scan roots below:
  1. No STANDALONE PAN-shaped token (5 letters + 4 digits + 1 letter, with a
     valid PAN 4th-character entity type) may appear.
  2. A GSTIN embeds a PAN in characters 3-12. Any such embedded PAN must be
     listed in ingestion/guards/synthetic_pans.txt (the synthetic allowlist);
     an unlisted embedded PAN fails the guard.
  3. No Aadhaar-shaped 12-digit number (4-4-4, first digit 2-9) may appear.

The PAN 4th character encodes holder type: P (person), C (company),
H (HUF), F (firm), A (AOP), T (trust), B (BOI), L (local), J (artificial),
G (government). Matching on this makes the regex specific to real PANs.

SCAN ROOTS are pinned explicitly (not discovered) and deliberately exclude the
guards directory, whose allowlist file contains bare PAN-shaped tokens by
design. See test_allowlist_is_outside_scan_roots.
"""

import os
import re

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _find_ingestion_root() -> str:
    """Locate the ingestion/ tree.

    Works both on the host (repo root, where ingestion/ sits next to api/) and
    inside the api container (ingestion/ is mounted at /ingestion). We probe a
    few candidates and require the samples dir to exist, so the guard fails
    loudly rather than silently scanning nothing.
    """
    candidates = [
        os.path.join(_REPO_ROOT, "ingestion"),   # host layout
        "/ingestion",                            # container mount
    ]
    for base in candidates:
        if os.path.isdir(os.path.join(base, "samples")):
            return base
    raise RuntimeError(
        "could not locate ingestion/samples; looked in: %s" % candidates
    )


_INGESTION_ROOT = _find_ingestion_root()
_GUARDS_DIR = os.path.join(_INGESTION_ROOT, "guards")

# The explicit set of directories the guard walks. ingestion/guards/ is
# intentionally absent: its allowlist holds bare PAN-shaped synthetic tokens.
SCAN_ROOTS = (
    os.path.join(_INGESTION_ROOT, "samples"),
)
ALLOWLIST_PATH = os.path.join(_GUARDS_DIR, "synthetic_pans.txt")

SAMPLES_DIR = SCAN_ROOTS[0]

# PAN: 5 letters + 4 digits + 1 letter. The 4th letter encodes holder type.
PAN_RE = re.compile(r"\b[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]\b")
# GSTIN: 2-digit state + 10-char PAN + entity digit + Z + checksum.
GSTIN_RE = re.compile(r"\b[0-9]{2}([A-Z]{5}[0-9]{4}[A-Z])[0-9A-Z]Z[0-9A-Z]\b")
# Aadhaar: 4-4-4 digits, first digit 2-9 (never starts 0/1).
AADHAAR_RE = re.compile(r"\b[2-9][0-9]{3}[ \-]?[0-9]{4}[ \-]?[0-9]{4}\b")


def _load_allowlist() -> set[str]:
    allowed: set[str] = set()
    with open(ALLOWLIST_PATH) as f:
        for line in f:
            # Comments may trail an entry, e.g. "AADCA1234M   # Apollo".
            token = line.split("#", 1)[0].strip()
            if token:
                allowed.add(token)
    return allowed


def _line_of(text: str, offset: int) -> int:
    """1-based line number of a character offset."""
    return text.count("\n", 0, offset) + 1


def _iter_sample_texts(roots=SCAN_ROOTS):
    """Yield (path, text) for every file under the given roots."""
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as f:
                    yield path, f.read().decode("latin-1", errors="replace")


def scan_text(text: str, allowlist: set[str]):
    """Return (standalone_pans, unlisted_gstin_pans, aadhaars) for one blob.

    Each element is a tuple (token, line_number) so failures can name the
    offending value and where it is, making a new synthetic entry a one-line
    fix.
    """
    # GSTIN-embedded PANs, with provenance.
    gstin_embedded = [
        (m.group(1), _line_of(text, m.start())) for m in GSTIN_RE.finditer(text)
    ]

    # Strip GSTINs first so the PAN inside one is not also reported as
    # "standalone"; it is checked separately against the allowlist.
    stripped = GSTIN_RE.sub(" ", text)
    standalone = [
        (m.group(0), _line_of(text, m.start())) for m in PAN_RE.finditer(stripped)
    ]
    unlisted_embedded = [
        (pan, line) for pan, line in gstin_embedded if pan not in allowlist
    ]
    aadhaars = [
        (m.group(0), _line_of(text, m.start())) for m in AADHAAR_RE.finditer(stripped)
    ]
    return standalone, unlisted_embedded, aadhaars


def _format_failures(path: str, root: str, findings) -> list[str]:
    standalone, unlisted, aadhaars = findings
    rel = os.path.relpath(path, root)
    out = []
    for pan, line in standalone:
        out.append(
            f"{rel}:{line}: standalone PAN {pan} (not allowlisted)"
        )
    for pan, line in unlisted:
        out.append(
            f"{rel}:{line}: GSTIN embeds non-allowlisted PAN {pan} - add it to "
            f"ingestion/guards/synthetic_pans.txt if it is synthetic"
        )
    for val, line in aadhaars:
        out.append(f"{rel}:{line}: Aadhaar-shaped {val}")
    return out


# ---------------------------------------------------------------------------
# Layout: the allowlist must be excluded by configuration, not by luck.
# ---------------------------------------------------------------------------

def test_samples_dir_exists():
    assert os.path.isdir(SAMPLES_DIR), f"missing samples dir: {SAMPLES_DIR}"
    assert os.path.isfile(ALLOWLIST_PATH), "missing synthetic_pans.txt allowlist"


def test_allowlist_is_outside_scan_roots():
    """The allowlist holds bare PAN-shaped tokens by design, so it must not be
    under any walked root. This fails if the file is ever moved back into e.g.
    ingestion/samples/."""
    for root in SCAN_ROOTS:
        root_real = os.path.realpath(root)
        allow_real = os.path.realpath(ALLOWLIST_PATH)
        assert os.path.commonpath([allow_real, root_real]) != root_real, (
            f"allowlist {ALLOWLIST_PATH} is inside scan root {root}"
        )
    # And no file named like the allowlist appears under a walked root.
    for path, _text in _iter_sample_texts():
        assert os.path.basename(path) != "synthetic_pans.txt", (
            f"allowlist file found under a scan root: {path}"
        )


def test_every_allowlist_entry_is_documented_synthetic():
    """Each entry must be a well-formed token and the file must state that all
    entries are synthetic (so nobody appends a real PAN)."""
    with open(ALLOWLIST_PATH) as f:
        raw = f.read()
    header = raw.lower()
    assert "synthetic" in header, "allowlist must state entries are synthetic"
    assert "do not add a real pan" in header, "allowlist must warn against real PANs"

    allowlist = _load_allowlist()
    assert allowlist, "allowlist is empty"
    for entry in allowlist:
        assert re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", entry), (
            f"malformed allowlist entry: {entry!r}"
        )


# ---------------------------------------------------------------------------
# The hard-fail guard over the shipped dataset.
# ---------------------------------------------------------------------------

def test_no_real_pan_or_aadhaar_in_samples():
    """Hard fail: no standalone real-shaped PAN, no unlisted GSTIN PAN, no
    Aadhaar-shaped number anywhere under the scan roots."""
    allowlist = _load_allowlist()
    failures = []
    for root in SCAN_ROOTS:
        for path, text in _iter_sample_texts((root,)):
            failures.extend(_format_failures(path, root, scan_text(text, allowlist)))
    assert not failures, "privacy guard failed:\n  " + "\n  ".join(failures)


def test_mca_csv_identity_fields_are_hashed():
    """The MCA sample must not carry a raw PAN column; the identity column is
    a hash and director identifiers are public DINs."""
    csv_path = os.path.join(SAMPLES_DIR, "mca_sample.csv")
    with open(csv_path) as f:
        header = f.readline().strip().split(",")
    assert "PAN" not in header, f"raw PAN column present: {header}"
    assert "PAN Hash" in header
    import csv as _csv
    with open(csv_path) as f:
        for row in _csv.DictReader(f):
            v = (row.get("PAN Hash") or "").strip()
            if v:
                assert not PAN_RE.fullmatch(v), f"raw PAN in PAN Hash column: {v}"


# ---------------------------------------------------------------------------
# Controls: prove the guard FAILS on a real-looking PAN and PASSES on the
# synthetic GSTINs we actually ship.
# ---------------------------------------------------------------------------

def test_guard_flags_injected_standalone_pan():
    allowlist = _load_allowlist()
    # AAAPC1234F: 'P' = individual, not allowlisted, not inside a GSTIN.
    blob = "Director PAN: AAAPC1234F\n"
    standalone, unlisted, aadhaars = scan_text(blob, allowlist)
    assert ("AAAPC1234F", 1) in standalone, "guard failed to catch a standalone PAN"


def test_guard_allows_synthetic_gstin():
    allowlist = _load_allowlist()
    # Hero ring GSTIN embeds HEROA0000A, which is on the allowlist.
    ok_blob = "GSTIN: 27HEROA0000A1Z1\n"
    standalone, unlisted, aadhaars = scan_text(ok_blob, allowlist)
    assert not standalone, f"false positive standalone: {standalone}"
    assert not unlisted, f"synthetic GSTIN PAN wrongly rejected: {unlisted}"


def test_guard_flags_unlisted_gstin_embedded_pan():
    allowlist = _load_allowlist()
    bad_blob = "GSTIN: 27AAAPC1234F1Z5\n"
    standalone, unlisted, aadhaars = scan_text(bad_blob, allowlist)
    assert ("AAAPC1234F", 1) in unlisted, "guard failed to catch an unlisted embedded PAN"


def test_guard_flags_aadhaar():
    allowlist = _load_allowlist()
    blob = "Aadhaar: 2345 6789 0123\n"
    standalone, unlisted, aadhaars = scan_text(blob, allowlist)
    assert any(a.startswith("2345") for a, _ in aadhaars), "guard failed to catch Aadhaar"


def test_guard_fails_on_planted_pan_in_temp_root(tmp_path):
    """Negative control end-to-end: a planted non-allowlisted PAN in a file
    under a temp 'samples' root makes the full guard routine fail, and the
    message names the PAN, file and line."""
    planted = tmp_path / "planted_sample.csv"
    planted.write_text(
        "CIN,GSTIN,Name\n"
        "U12345MH2024PTC000001,27AAAPC1234F1Z5,Planted Co\n"
    )
    # A standalone PAN on line 4.
    planted2 = tmp_path / "planted_standalone.txt"
    planted2.write_text("line1\nline2\nline3\nDirector PAN: AAAPC1234F\n")

    allowlist = _load_allowlist()
    failures = []
    for path, text in _iter_sample_texts((str(tmp_path),)):
        failures.extend(_format_failures(path, str(tmp_path), scan_text(text, allowlist)))

    joined = "\n".join(failures)
    assert failures, "guard did not fail on a planted PAN"
    assert "AAAPC1234F" in joined, f"failure message missing PAN: {joined}"
    assert "planted_standalone.txt:4" in joined, f"missing file:line: {joined}"
    assert "planted_sample.csv:2" in joined, f"missing GSTIN file:line: {joined}"


def test_guard_passes_clean_temp_root(tmp_path):
    """Positive control: a file whose only PAN-like value is an allowlisted
    GSTIN passes."""
    ok = tmp_path / "clean_sample.csv"
    ok.write_text("GSTIN,Name\n27HEROA0000A1Z1,Maya Infra Projects Pvt Ltd\n")
    allowlist = _load_allowlist()
    failures = []
    for path, text in _iter_sample_texts((str(tmp_path),)):
        failures.extend(_format_failures(path, str(tmp_path), scan_text(text, allowlist)))
    assert not failures, f"clean synthetic data wrongly failed: {failures}"
