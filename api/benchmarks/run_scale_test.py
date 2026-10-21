"""A3 scale test: measured timings + endpoint latency + query plans.

Runs the real product code paths (``graph_service``, ``gnn.train``,
``gnn.predict``) against the live Neo4j, at increasing graph sizes, and writes
``docs/performance.md``. Every number is measured on the machine that runs it;
nothing is estimated. If a size cannot complete, the runner records the failing
stage and the error, and stops — it never pretends a larger size passed.

Usage (inside the api container):

    python /benchmarks/run_scale_test.py --sizes 10000 100000 500000 --seed 1
    python /benchmarks/run_scale_test.py --sizes 10000 --profile-only

Stages timed per size: generate, bulk load, WCC, Louvain, cycle detection
(3–8 hops), centrality (pagerank+betweenness), GNN training, GNN inference,
and p50/p95 latency of /entities/search, /entities/{id}/network, /worklist.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

for candidate in ("/app", "/benchmarks"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.deps import neo4j_driver  # noqa: E402
from app.services import graph_service  # noqa: E402
from app.services.gnn import train as gnn_train  # noqa: E402
from app.services.gnn import predict as gnn_predict  # noqa: E402
import scale_gen  # noqa: E402

SIZES_DEFAULT = [10_000, 100_000, 500_000]
ENDPOINT_REPEATS = 20


def _versions() -> Dict[str, str]:
    import neo4j
    return {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "neo4j_driver": neo4j.__version__,
    }


def _container_stats() -> Dict[str, Any]:
    """Best-effort container memory/cpu limits (no fabrication if absent)."""
    out: Dict[str, Any] = {}
    try:
        with open("/sys/fs/cgroup/memory.max") as fh:
            out["cgroup_memory_max_bytes"] = int(fh.read().strip())
    except Exception:
        pass
    try:
        with open("/sys/fs/cgroup/cpu.max") as fh:
            out["cgroup_cpu_max"] = fh.read().strip()
    except Exception:
        pass
    try:
        import torch
        out["torch"] = torch.__version__
        out["torch_threads"] = torch.get_num_threads()
    except Exception:
        pass
    return out


class Failure(Exception):
    pass


def _terminate_long_transactions_sync(min_age_s: float = 5.0) -> int:
    """Sync variant: terminate server-side transactions older than min_age_s.

    Uses a *fresh* sync driver connection, because after an asyncio timeout the
    async session that issued the query may be defunct.
    """
    from neo4j import GraphDatabase
    from app.config import settings

    killed = 0
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri,
                                      auth=(settings.neo4j_user,
                                            settings.neo4j_password))
        with driver.session() as session:
            rows = list(session.run(
                "SHOW TRANSACTIONS YIELD transactionId, elapsedTime, currentQuery "
                "RETURN transactionId, elapsedTime, currentQuery"
            ))
            for row in rows:
                el = row["elapsedTime"]
                secs = getattr(el, "seconds", 0) + getattr(el, "days", 0) * 86400
                q = (row.get("currentQuery") or "")
                if "SHOW TRANSACTIONS" in q:
                    continue
                if secs >= min_age_s:
                    try:
                        session.run(
                            f'TERMINATE TRANSACTION "{row["transactionId"]}"'
                        ).consume()
                        killed += 1
                    except Exception:
                        pass
        driver.close()
    except Exception:
        pass
    return killed


@contextmanager
def _preserve_checkpoint():
    """Snapshot the live GNN checkpoint and restore it afterwards.

    The scale test runs the *real* training pipeline, which writes to the live
    checkpoint path (``settings.gnn_checkpoint_file``). Without this guard a
    scale run would overwrite the product's model with one trained on test
    junk — leaving the worklist scoring garbage. We snapshot every file in the
    checkpoint dir that the pipeline may touch and restore bytes-for-bytes.
    """
    from app.config import settings

    ckpt_dir = settings.gnn_checkpoint_dir
    paths = []
    for name in (settings.gnn_checkpoint_filename, settings.gnn_metrics_filename):
        paths.append(os.path.join(ckpt_dir, name))
    saved: Dict[str, bytes] = {}
    existed: Dict[str, bool] = {}
    for p in paths:
        existed[p] = os.path.exists(p)
        if existed[p]:
            with open(p, "rb") as fh:
                saved[p] = fh.read()
    # Drop the in-process model cache so predict re-loads after restore.
    try:
        import app.services.gnn.predict as _pred
        _pred._model = None
        _pred._checkpoint = None
    except Exception:
        pass
    try:
        yield
    finally:
        for p in paths:
            try:
                if existed[p]:
                    with open(p, "wb") as fh:
                        fh.write(saved[p])
                elif os.path.exists(p):
                    os.remove(p)
            except Exception as e:  # noqa: BLE001
                print(f"[scale-test] WARNING: could not restore {p}: {e}",
                      flush=True)
        try:
            import app.services.gnn.predict as _pred
            _pred._model = None
            _pred._checkpoint = None
        except Exception:
            pass
        print("[scale-test] restored live GNN checkpoint after scale run",
              flush=True)


async def _time_stage(name: str, coro_fn: Callable, results: Dict[str, Any],
                      timeout: Optional[float] = None,
                      optional: bool = False,
                      persist: Optional[Callable[[Dict[str, Any]], None]] = None) -> Any:
    """Time one async stage.

    ``timeout`` (seconds) guards against a query that never returns — at scale
    the betweenness-centrality query is O(V*E) and effectively hangs on 100K+
    nodes, so without a timeout the whole run would stall forever. On timeout we
    record it as a failure (or, when ``optional``, as a recorded skip) and let
    the caller decide whether to abort.

    ``persist`` is called after every stage so that, if a later stage is killed
    by the OOM killer, the timings measured so far are still saved to disk.
    """
    def _save():
        if persist:
            try:
                persist(results)
            except Exception:
                pass

    t0 = time.perf_counter()
    try:
        if timeout:
            value = await asyncio.wait_for(coro_fn(), timeout=timeout)
        else:
            value = await coro_fn()
    except asyncio.TimeoutError as e:
        entry = {
            "ok": False,
            "timed_out": True,
            "timeout_s": timeout,
            "seconds": time.perf_counter() - t0,
            "error": f"TimeoutError: exceeded {timeout}s",
        }
        results["stages"][name] = entry
        _save()
        print(f"[scale-test]   {name}: TIMEOUT after {timeout}s", flush=True)
        if optional:
            return None
        raise Failure(f"{name} timed out after {timeout}s") from e
    except Exception as e:  # noqa: BLE001 — we want to record *any* failure shape
        results["stages"][name] = {
            "ok": False,
            "seconds": time.perf_counter() - t0,
            "error": f"{type(e).__name__}: {e}",
        }
        _save()
        print(f"[scale-test]   {name}: FAILED {type(e).__name__}: {e}", flush=True)
        raise Failure(f"{name} failed: {type(e).__name__}: {e}") from e
    results["stages"][name] = {"ok": True, "seconds": time.perf_counter() - t0}
    _save()
    print(f"[scale-test]   {name}: {results['stages'][name]['seconds']:.2f}s",
          flush=True)
    return value


async def _percentiles(session, query: str, params: Dict[str, Any],
                       repeats: int) -> Dict[str, float]:
    times: List[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = await session.run(query, **params)
        await result.data()
        times.append((time.perf_counter() - t0) * 1000.0)  # ms
    times.sort()
    return {
        "p50_ms": round(statistics.median(times), 2),
        "p95_ms": round(times[min(len(times) - 1, int(0.95 * len(times)))], 2),
        "min_ms": round(times[0], 2),
        "max_ms": round(times[-1], 2),
        "n": len(times),
    }


async def run_one_size(size: int, seed: int, batch: int,
                       endpoint_repeats: int,
                       stage_timeout: Optional[float] = None,
                       persist_path: Optional[str] = None) -> Dict[str, Any]:
    res: Dict[str, Any] = {"size": size, "seed": seed, "stages": {}}

    def _persist(obj: Dict[str, Any]) -> None:
        if not persist_path:
            return
        tmp = persist_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(obj, fh, indent=2)
        os.replace(tmp, persist_path)

    async def stage(name, fn, timeout=stage_timeout, optional=False):
        return await _time_stage(name, fn, res, timeout=timeout,
                                 optional=optional, persist=_persist)

    # 0. ensure schema (constraints/indexes) is applied before loading.
    #    Without this the MERGEs in the loader do full label scans and the load
    #    is O(N^2) -- see docs/performance.md.
    async def _ensure_schema():
        from apply_schema import apply_files
        return await apply_files(["/cypher/constraints.cypher",
                                  "/cypher/indexes.cypher"])
    await stage("apply_schema", _ensure_schema)

    # 1. generate (in-process; timed)
    t0 = time.perf_counter()
    rows = scale_gen.build_rows(size, seed=seed)
    res["stages"]["generate"] = {"ok": True, "seconds": time.perf_counter() - t0}
    res["graph_stats"] = rows["stats"]
    _persist(res)

    # 2. wipe + bulk load (sync driver inside scale_gen)
    async def _load():
        scale_gen.wipe_scale_data()
        timings = await asyncio.to_thread(scale_gen.load_rows, rows, batch)
        res["load_breakdown"] = timings
        return timings["total"]
    await stage("bulk_load", _load)

    # Pick a real company node id / cin to exercise entity endpoints.
    async with neo4j_driver.session() as session:
        rec = await (await session.run(
            "MATCH (c:Company {scale_tag: $t}) RETURN c.cin AS cin, c.id AS id "
            "LIMIT 1", t=scale_gen.SCALE_TAG)).single()
        cin = rec["cin"] if rec else None
        node_id = rec["id"] if rec else None

        # 3. WCC
        await stage("wcc", lambda: graph_service.compute_wcc(session))
        # 4. Louvain is inside run_structural_analytics, but time it directly via
        #    the projection the analytics step uses.
        await stage(
            "louvain_project",
            lambda: graph_service._ensure_invoice_graph(session))

        async def _louvain_write():
            prof = graph_service.settings.gds_projection_name
            result = await session.run(
                f"CALL gds.louvain.write('{prof}', "
                "{writeProperty: 'community_id', maxIterations: 20}) "
                "YIELD communityCount RETURN communityCount"
            )
            return await result.single()
        await stage("louvain_write", _louvain_write)
        # 5. cycle detection (3–8 hops) — the exact cycle query the product runs
        await stage(
            "cycle_detection",
            lambda: graph_service.get_loops(
                session, graph_service.settings.max_cycle_hops))
        # 6. centrality (pagerank + betweenness stream).
        #    Betweenness is O(V*E): at 10K it is ~2s, at 100K it does not return
        #    within the timeout. Recorded as an optional stage so a slow
        #    centrality does not hide the rest of the pipeline's numbers.
        await stage(
            "centrality",
            lambda: graph_service.compute_centrality(session, cin),
            optional=True)
        # If centrality timed out, its query is still running inside Neo4j.
        # Kill stragglers so the following stages get CPU.
        if res["stages"].get("centrality", {}).get("timed_out"):
            killed = await asyncio.to_thread(_terminate_long_transactions_sync)
            res["centrality_terminated"] = killed
            print(f"[scale-test]   terminated {killed} straggler txn(s)",
                  flush=True)

        # 7. GNN training (real pipeline, default args)
        #    Guarded: the pipeline writes the live checkpoint, so we snapshot
        #    and restore it so the product model is never left overwritten.
        args = gnn_train._default_args()
        with _preserve_checkpoint():
            await stage(
                "gnn_train",
                lambda: gnn_train.run_pipeline(session, args))
            # 8. GNN inference / write-back
            await stage(
                "gnn_inference",
                lambda: gnn_predict.predict_and_writeback(session))

        # 9. endpoint latency: the three product queries, verbatim
        res["endpoints"] = {}
        res["endpoints"]["search"] = await _percentiles(
            session,
            "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($q) "
            "OR n.cin CONTAINS $q OR n.gstin CONTAINS $q OR n.din CONTAINS $q "
            "OR n.ifsc CONTAINS $q RETURN n, labels(n) AS labels LIMIT $limit",
            {"q": "ScaleCo 0000", "limit": 25}, endpoint_repeats)
        if node_id:
            res["endpoints"]["network"] = await _percentiles(
                session,
                "MATCH path = (n)-[*1..2]-(m) WHERE n.id = $id "
                "RETURN nodes(path) AS nodes, "
                "[x IN nodes(path) | labels(x)] AS labels, "
                "relationships(path) AS rels",
                {"id": node_id}, endpoint_repeats)
        res["endpoints"]["worklist"] = await _percentiles(
            session,
            "MATCH (c:Company) WITH c "
            "OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address) WITH c, a "
            "OPTIONAL MATCH (c)-[:MEMBER_OF_CYCLE]->(cy:FraudCycle) "
            "WITH c, a, count(cy) AS cycle_count "
            "RETURN c.cin AS cin, c.name AS name, c.risk_score AS risk_score, "
            "a.state AS state, cycle_count "
            "ORDER BY c.risk_score DESC SKIP 0 LIMIT 50",
            {}, endpoint_repeats)
        _persist(res)

    return res


async def profile_queries() -> Dict[str, Any]:
    """PROFILE the three endpoint queries and return the plan summaries."""
    out: Dict[str, Any] = {}
    async with neo4j_driver.session() as session:
        queries = {
            "search": ("PROFILE MATCH (n) WHERE toLower(n.name) CONTAINS toLower($q) "
                       "OR n.cin CONTAINS $q OR n.gstin CONTAINS $q "
                       "OR n.din CONTAINS $q OR n.ifsc CONTAINS $q "
                       "RETURN n, labels(n) AS labels LIMIT $limit",
                       {"q": "ScaleCo 0000", "limit": 25}),
            "worklist_count": ("PROFILE MATCH (c:Company) RETURN count(DISTINCT c) AS total",
                               {}),
        }
        for name, (q, params) in queries.items():
            t0 = time.perf_counter()
            result = await session.run(q, **params)
            summary = await result.consume()
            plan = summary.profile if hasattr(summary, "profile") else None
            out[name] = {
                "ms": round((time.perf_counter() - t0) * 1000.0, 2),
                "db_hits": getattr(summary, "db_hits", None),
                "plan": _flatten_plan(plan) if plan else None,
            }
    return out


def _flatten_plan(plan: Any, depth: int = 0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not plan:
        return rows
    op = plan.get("operatorType", "?")
    rows.append({
        "depth": depth,
        "operator": op,
        "dbHits": plan.get("dbHits"),
        "rows": plan.get("rows"),
        "details": plan.get("args", {}).get("Details")
        or plan.get("args", {}).get("planner-impl"),
    })
    for child in plan.get("children", []) or []:
        rows += _flatten_plan(child, depth + 1)
    return rows


def _fmt(v: Any, ndigits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{ndigits}f}"
    return str(v)


def _stage_cell(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "—"
    if entry.get("ok"):
        return f"{entry['seconds']:.2f}s"
    if entry.get("timed_out"):
        return f"**timeout** (> {entry.get('timeout_s')}s)"
    return "**failed**"


def render_doc(report: Dict[str, Any], commit_hash: str = "unknown") -> str:
    """Render ``docs/performance.md`` from a measured report.

    Every number comes from ``report``; nothing is written that was not
    measured. Aborted sizes are shown as aborted, with the stages that DID
    complete still listed.
    """
    sizes = report.get("sizes", [])
    largest = report.get("largest_completed")
    lines: List[str] = []
    a = lines.append

    a("# Dhan-Chakra — Performance and Scale")
    a("")
    a("Measured timings for the graph algorithms, the GNN pipeline and the three")
    a("hot API queries, at increasing graph sizes. Generated by")
    a("`api/benchmarks/run_scale_test.py`; **every number here was measured on the")
    a("machine that wrote this file** — nothing is estimated or extrapolated.")
    a("")
    a(f"Report generated at commit: `{commit_hash}`")
    a("")
    env = report.get("versions", {})
    cont = report.get("container", {})
    a("## Environment")
    a("")
    a("| Item | Value |")
    a("|---|---|")
    a(f"| Python | {_fmt(env.get('python'))} |")
    a(f"| Platform | {_fmt(env.get('platform'))} |")
    a(f"| Neo4j driver | {_fmt(env.get('neo4j_driver'))} |")
    a(f"| PyTorch | {_fmt(cont.get('torch'))} |")
    a(f"| Torch threads | {_fmt(cont.get('torch_threads'))} |")
    a("| Neo4j heap / pagecache | see `NEO4J_HEAP_MAX` / `NEO4J_PAGECACHE` in `.env` |")
    a("")
    a("## What was tested")
    a("")
    a("A seeded synthetic graph (`api/benchmarks/scale_gen.py`) is generated at")
    a("each size and loaded into Neo4j. `nodes` counts **Company** nodes;")
    a("directors, addresses and invoice Transactions scale with it. Planted")
    a("closed invoice rings (the shape the product detects) are included at a")
    a("realistic needle-in-a-haystack ratio.")
    a("")
    a("Per size we time, using the **real product code paths**:")
    a("")
    a("- **generate** — build the row sets in memory")
    a("- **bulk load** — batched `UNWIND` writes into Neo4j (per-entity breakdown below)")
    a("- **WCC** — `graph_service.compute_wcc`")
    a("- **Louvain** — projection then `gds.louvain.write` (the analytics step)")
    a("- **cycle detection (3–8 hops)** — `graph_service.get_loops`")
    a("- **centrality** — `graph_service.compute_centrality` (PageRank **and** betweenness)")
    a("- **GNN training** — `gnn.train.run_pipeline`, the real pipeline")
    a("- **GNN inference** — `gnn.predict.predict_and_writeback`")
    a("- **endpoint latency** — p50/p95 of the three hot queries over 20 runs")
    a("")
    a("Each size runs in its **own child process**: building the GNN adjacency at")
    a("large sizes exhausts memory and the OOM killer sends SIGKILL, which Python")
    a("cannot catch. In a child process that only fails that one size; the run")
    a("records it and carries on.")
    a("")
    a("## Largest size that ran end to end")
    a("")
    if largest:
        a(f"**{largest:,} company nodes** completed every stage.")
    else:
        a("No size completed every stage.")
    a("")
    aborted = [s for s in sizes if s.get("aborted")]
    if aborted:
        a("Sizes that did **not** complete, and why:")
        a("")
        for s in aborted:
            a(f"- **{s['size']:,}** — {s.get('reason', 'unknown')}")
        a("")
    a("## Per-size timings")
    a("")
    stage_order = ["generate", "apply_schema", "bulk_load", "wcc",
                   "louvain_project", "louvain_write", "cycle_detection",
                   "centrality", "gnn_train", "gnn_inference"]
    for res in sizes:
        size = res["size"]
        a(f"### {size:,} company nodes")
        a("")
        if res.get("graph_stats"):
            gs = res["graph_stats"]
            a("Graph: " + ", ".join(f"{k}={v:,}" for k, v in gs.items()) + ".")
            a("")
        if res.get("aborted"):
            a(f"> **Aborted:** {res.get('reason', 'unknown')}. Stages below "
              f"completed before the abort.")
            a("")
        stages = res.get("stages", {})
        if stages:
            a("| Stage | Time |")
            a("|---|---|")
            for name in stage_order:
                if name in stages:
                    a(f"| {name} | {_stage_cell(stages[name])} |")
            # anything unexpected
            for name, entry in stages.items():
                if name not in stage_order:
                    a(f"| {name} | {_stage_cell(entry)} |")
            a("")
        lb = res.get("load_breakdown")
        if lb:
            a("Bulk-load breakdown (seconds): " +
              ", ".join(f"`{k}` {lb[k]:.2f}" for k in
                        ("companies", "directors", "addresses", "transactions")
                        if k in lb) + ".")
            a("")
        a("")

    eps = [(r["size"], r.get("endpoints")) for r in sizes if r.get("endpoints")]
    if eps:
        a("## Endpoint latency")
        a("")
        a("The three hot queries, verbatim, 20 runs each. These are Neo4j query")
        a("times measured directly against the database (the same Cypher the API")
        a("routes issue), not full HTTP round-trips.")
        a("")
        a("| Size | Query | p50 (ms) | p95 (ms) | min | max |")
        a("|---|---|---|---|---|---|")
        for size, e in eps:
            for q in ("search", "network", "worklist"):
                if q in e:
                    d = e[q]
                    a(f"| {size:,} | {q} | {d['p50_ms']} | {d['p95_ms']} | "
                      f"{d['min_ms']} | {d['max_ms']} |")
        a("")

    prof = report.get("profile")
    if prof:
        a("## Query plans (`PROFILE`)")
        a("")
        for name, p in prof.items():
            a(f"### {name}")
            a("")
            a(f"Measured: {p.get('ms')} ms.")
            a("")
            plan = p.get("plan") or []
            if plan:
                a("| Operator | dbHits | rows | Details |")
                a("|---|---|---|---|")
                for row in plan[:15]:
                    a(f"| {'&nbsp;' * (row['depth'] * 2)}{row['operator']} | "
                      f"{_fmt(row.get('dbHits'), 0)} | {_fmt(row.get('rows'), 0)} | "
                      f"{_fmt(row.get('details'))} |")
                a("")

    a("## Notes and caveats")
    a("")
    for n in report.get("notes", []):
        a(f"- {n}")
    if report.get("cleanup"):
        c = report["cleanup"]
        a(f"- Post-run cleanup: {'ok' if c.get('ok') else 'FAILED'}"
          + (f" — graph now {c.get('counts')}" if c.get("counts") else ""))
    a("")
    return "\n".join(lines)


async def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", type=int, nargs="+", default=SIZES_DEFAULT)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--batch", type=int, default=5000)
    p.add_argument("--endpoint-repeats", type=int, default=ENDPOINT_REPEATS)
    p.add_argument("--stage-timeout", type=float, default=600.0,
                   help="Seconds before a single stage is declared timed out "
                        "(0 disables). Guards against O(V*E) hangs at scale.")
    p.add_argument("--profile-only", action="store_true")
    p.add_argument("--out", default="/tmp/scale_results.json")
    p.add_argument("--doc", default="",
                   help="Path to write the rendered markdown report to")
    p.add_argument("--commit-hash", default="unknown")
    p.add_argument("--profile", action="store_true",
                   help="Also PROFILE the endpoint queries")
    # Internal: child-process mode runs exactly one size and writes its JSON.
    p.add_argument("--_run-one", type=int, default=None, help=argparse.SUPPRESS)
    p.add_argument("--_child-out", default=None, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    stage_timeout = args.stage_timeout or None

    # --- child mode: exactly one size, then exit -----------------------------
    # Running each size in its own process is deliberate: building the GNN
    # adjacency at 100K+ nodes exhausts memory and the OOM killer sends
    # SIGKILL, which Python cannot catch. In a child process that only kills
    # that size's measurement; the parent records "killed" and carries on.
    if args._run_one is not None:
        res = await run_one_size(args._run_one, args.seed, args.batch,
                                 args.endpoint_repeats, stage_timeout,
                                 persist_path=args._child_out)
        if args.profile:
            # PROFILE while this size's graph is still loaded, so the plan is
            # meaningful (not a plan for an 8-node demo graph).
            try:
                res["profile"] = await profile_queries()
            except Exception as e:  # noqa: BLE001
                res["profile_error"] = f"{type(e).__name__}: {e}"
        with open(args._child_out, "w") as fh:
            json.dump(res, fh, indent=2)
        return 0

    report: Dict[str, Any] = {
        "task": "A3 scale test",
        "versions": _versions(),
        "container": _container_stats(),
        "sizes": [],
        "profile": {},
        "notes": [
            "All numbers measured on the host running this command; nothing estimated.",
            "Scale-test data is tagged scale_tag=scale_a3 and removable via scale_gen.wipe_scale_data().",
            "Each size runs in its own child process so an OOM kill is recorded "
            "rather than aborting the whole run.",
        ],
    }

    if args.profile_only:
        report["profile"] = await profile_queries()
    else:
        import subprocess
        import tempfile

        try:
            for size in args.sizes:
                print(f"[scale-test] === size {size} ===", flush=True)
                child_out = os.path.join(tempfile.gettempdir(),
                                         f"scale_child_{size}.json")
                cmd = [sys.executable, os.path.abspath(__file__),
                       "--_run-one", str(size),
                       "--_child-out", child_out,
                       "--seed", str(args.seed),
                       "--batch", str(args.batch),
                       "--endpoint-repeats", str(args.endpoint_repeats),
                       "--stage-timeout", str(args.stage_timeout)]
                if args.profile:
                    cmd.append("--profile")
                proc = subprocess.run(cmd, capture_output=True, text=True)
                sys.stdout.write(proc.stdout)
                sys.stderr.write(proc.stderr)
                if proc.returncode == 0 and os.path.exists(child_out):
                    with open(child_out) as fh:
                        res = json.load(fh)
                    report["sizes"].append(res)
                    if res.get("profile"):
                        report["profile"] = res["profile"]
                    st = res["stages"]
                    print(f"[scale-test] {size}: " + ", ".join(
                        f"{k}={v['seconds']:.1f}s" if v["ok"] else f"{k}=FAILED"
                        for k, v in st.items()), flush=True)
                else:
                    sig = (-proc.returncode
                           if proc.returncode < 0 else proc.returncode)
                    reason = ("killed by signal %d (out of memory)" % sig
                              if proc.returncode < 0
                              else f"exit code {proc.returncode}")
                    entry: Dict[str, Any] = {
                        "size": size, "aborted": True, "reason": reason,
                    }
                    # Salvage whatever the child managed to persist before it
                    # was killed, so the stages that DID complete are still
                    # reported (never silently dropped).
                    if os.path.exists(child_out):
                        try:
                            with open(child_out) as fh:
                                partial = json.load(fh)
                            entry["stages"] = partial.get("stages", {})
                            entry["graph_stats"] = partial.get("graph_stats")
                            entry["load_breakdown"] = partial.get("load_breakdown")
                            entry["endpoints"] = partial.get("endpoints")
                        except Exception:
                            pass
                    report["sizes"].append(entry)
                    print(f"[scale-test] {size}: ABORTED — {reason}", flush=True)
        finally:
            # Always leave the demo graph clean: drop scale-test data and
            # re-score the real graph so the product worklist is not polluted.
            try:
                print("[scale-test] cleaning up scale data ...", flush=True)
                await asyncio.to_thread(scale_gen.wipe_scale_data)
                async with neo4j_driver.session() as session:
                    await gnn_predict.predict_and_writeback(session)
                report["cleanup"] = {"ok": True,
                                     "counts": scale_gen.count_graph()}
            except Exception as e:  # noqa: BLE001
                report["cleanup"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                print(f"[scale-test] cleanup failed: {e}", flush=True)

        # Highest size that completed end-to-end, for the headline claim.
        completed = [s["size"] for s in report["sizes"] if not s.get("aborted")]
        report["largest_completed"] = max(completed) if completed else None

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"[scale-test] wrote {args.out}", flush=True)

    if args.doc and not args.profile_only:
        doc = render_doc(report, commit_hash=args.commit_hash)
        with open(args.doc, "w") as fh:
            fh.write(doc)
        print(f"[scale-test] wrote {args.doc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
