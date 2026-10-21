"""Tests for the A3 scale test (api/benchmarks/scale_gen.py,
api/benchmarks/run_scale_test.py) and the idempotent schema applier
(api/benchmarks/apply_schema.py).

These tests are deliberately offline: they exercise the *pure* parts (the graph
generator and the markdown renderer) so they need neither a live Neo4j nor a
loaded graph. The measured timings themselves live in docs/performance.md and
api/benchmarks/scale_results.json.

Run: docker compose exec api pytest tests/test_scale.py -q
"""

import sys

sys.path.insert(0, "/benchmarks")

import scale_gen  # noqa: E402
import run_scale_test as rst  # noqa: E402
import apply_schema  # noqa: E402


# --- generator ---------------------------------------------------------------

def test_build_rows_sizes_and_shape():
    rows = scale_gen.build_rows(500, seed=7)
    stats = rows["stats"]
    assert stats["companies"] == 500
    assert stats["transactions"] > 0
    assert stats["rings"] >= 2
    # Every transaction carries a seller and buyer drawn from the companies.
    cins = {c["cin"] for c in rows["companies"]}
    for t in rows["transactions"]:
        assert t["seller_cin"] in cins
        assert t["buyer_cin"] in cins


def test_build_rows_is_seeded_and_reproducible():
    a = scale_gen.build_rows(300, seed=3)
    b = scale_gen.build_rows(300, seed=3)
    assert a["stats"] == b["stats"]
    assert [t["id"] for t in a["transactions"]] == [t["id"] for t in b["transactions"]]


def test_planted_rings_are_closed_loops():
    rows = scale_gen.build_rows(400, seed=1)
    # Ring members are marked with ring_id >= 0 on the company rows.
    ring_members = [c for c in rows["companies"] if c["ring_id"] >= 0]
    assert ring_members, "generator must plant at least one ring"
    # Each planted ring's members must form a closed loop in the edge set.
    edges = {(t["seller_cin"], t["buyer_cin"]) for t in rows["transactions"]}
    by_ring = {}
    for c in ring_members:
        by_ring.setdefault(c["ring_id"], []).append(c["cin"])
    for members in by_ring.values():
        if len(members) < 3:
            continue
        # closed loop: each member bills the next, last bills first
        for i, cin in enumerate(members):
            nxt = members[(i + 1) % len(members)]
            assert (cin, nxt) in edges, f"ring not closed at {cin}->{nxt}"


def test_ring_transactions_are_labelled_in_ring():
    rows = scale_gen.build_rows(400, seed=2)
    assert any(t["in_ring"] == 1 for t in rows["transactions"])
    assert any(t["in_ring"] == 0 for t in rows["transactions"])


def test_all_scale_nodes_carry_the_removable_tag():
    rows = scale_gen.build_rows(200, seed=1)
    assert scale_gen.SCALE_TAG  # non-empty
    # Transactions are identified by an id prefix so cleanup can find them.
    for t in rows["transactions"]:
        assert t["id"].startswith("scale-txn-")


# --- schema applier ----------------------------------------------------------

def test_parse_statements_ignores_comments_and_blank_lines(tmp_path):
    p = tmp_path / "x.cypher"
    p.write_text(
        "# a comment\n"
        "\n"
        "CREATE INDEX a IF NOT EXISTS FOR (n:X) ON (n.id);\n"
        "# another\n"
        "CREATE INDEX b IF NOT EXISTS FOR (n:Y) ON (n.id);\n"
    )
    stmts = apply_schema.parse_statements(str(p))
    assert len(stmts) == 2
    assert all(s.startswith("CREATE INDEX") for s in stmts)


def test_repo_schema_files_are_all_idempotent():
    # Every statement must be safe to re-run, otherwise bootstrapping twice
    # (or running the scale test after `make up`) would fail.
    import glob
    paths = ["/cypher/constraints.cypher", "/cypher/indexes.cypher"]
    paths = [p for p in paths if glob.glob(p)]
    if not paths:
        import pytest
        pytest.skip("schema files not mounted (run inside the api container)")
    for path in paths:
        for stmt in apply_schema.parse_statements(path):
            assert "IF NOT EXISTS" in stmt, f"not idempotent: {stmt}"


# --- renderer ----------------------------------------------------------------

def _sample_report():
    return {
        "versions": {"python": "3.11.0", "platform": "Linux", "neo4j_driver": "5.19.0"},
        "container": {"torch": "2.4.1", "torch_threads": 8},
        "largest_completed": 1000,
        "sizes": [
            {
                "size": 1000, "seed": 1,
                "graph_stats": {"companies": 1000, "transactions": 2500},
                "stages": {
                    "generate": {"ok": True, "seconds": 0.01},
                    "bulk_load": {"ok": True, "seconds": 0.5},
                },
                "load_breakdown": {"companies": 0.1, "transactions": 0.4,
                                   "directors": 0.0, "addresses": 0.0},
                "endpoints": {"search": {"p50_ms": 1.0, "p95_ms": 2.0,
                                         "min_ms": 0.9, "max_ms": 2.1}},
            },
            {"size": 100000, "seed": 1, "aborted": True,
             "reason": "killed by signal 9 (out of memory)",
             "stages": {"bulk_load": {"ok": True, "seconds": 15.0},
                        "centrality": {"ok": False, "timed_out": True,
                                       "timeout_s": 300, "seconds": 300.0}}},
        ],
        "notes": ["measured only"],
        "cleanup": {"ok": True, "counts": {"Company": 8}},
    }


def test_render_doc_reports_largest_and_aborted_with_reason():
    doc = rst.render_doc(_sample_report(), commit_hash="abc123")
    assert "abc123" in doc
    assert "1,000 company nodes" in doc          # largest completed, formatted
    assert "killed by signal 9 (out of memory)" in doc
    assert "**timeout**" in doc                   # timed-out stage rendered
    # The doc must not claim a size ran that was aborted.
    assert "**100,000 company nodes** completed" not in doc


def test_stage_cell_shapes():
    assert rst._stage_cell({"ok": True, "seconds": 1.234}) == "1.23s"
    assert rst._stage_cell({"ok": False, "timed_out": True, "timeout_s": 10}) \
        == "**timeout** (> 10s)"
    assert rst._stage_cell({"ok": False, "error": "boom"}) == "**failed**"
    assert rst._stage_cell(None) == "—"
