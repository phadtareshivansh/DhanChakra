"""Apply a Neo4j schema file (constraints/indexes) idempotently.

The repo ships ``graph/cypher/constraints.cypher`` and ``indexes.cypher``, but
nothing applied them to the running database -- so for a long time the live DB
had no property indexes at all and every property lookup was a full scan
(see ``docs/performance.md``). This script closes that gap.

Every statement in these files uses ``IF NOT EXISTS``, so re-running is a no-op.
Comment lines (``#``) and blank lines are ignored; statements are separated by
``;``. A statement that fails is reported and the run exits non-zero.

Usage (inside the api container, where Neo4j is reachable):

    python /benchmarks/apply_schema.py /cypher/constraints.cypher /cypher/indexes.cypher
    python /benchmarks/apply_schema.py --list
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import List

for candidate in ("/app", "/benchmarks"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.deps import neo4j_driver  # noqa: E402


def parse_statements(path: str) -> List[str]:
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    lines = [ln for ln in raw.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    text = "\n".join(lines)
    return [s.strip() for s in text.split(";") if s.strip()]


async def apply_files(paths: List[str]) -> int:
    failures = 0
    async with neo4j_driver.session() as session:
        for path in paths:
            stmts = parse_statements(path)
            print(f"[schema] {path}: {len(stmts)} statements", flush=True)
            for stmt in stmts:
                label = " ".join(stmt.split())[:70]
                try:
                    await (await session.run(stmt)).consume()
                    print(f"[schema]   OK   {label}", flush=True)
                except Exception as e:  # noqa: BLE001
                    failures += 1
                    print(f"[schema]   FAIL {label} -> {type(e).__name__}: {e}",
                          flush=True)
    return failures


async def list_schema() -> None:
    async with neo4j_driver.session() as session:
        print("--- indexes ---")
        for r in await (await session.run(
            "SHOW INDEXES YIELD name, labelsOrTypes, properties, type, state "
            "RETURN name, labelsOrTypes, properties, type, state"
        )).data():
            print(r)
        print("--- constraints ---")
        for r in await (await session.run(
            "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties, type "
            "RETURN name, labelsOrTypes, properties, type"
        )).data():
            print(r)


def _default_paths() -> List[str]:
    out: List[str] = []
    for pattern in ("/cypher/constraints.cypher", "/cypher/indexes.cypher"):
        out.extend(sorted(glob.glob(pattern)))
    return out


async def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("files", nargs="*", help="Cypher files to apply")
    p.add_argument("--list", action="store_true", help="List current schema")
    args = p.parse_args(argv)

    if args.list:
        await list_schema()
        return 0

    paths = args.files or _default_paths()
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("[schema] no schema files found", file=sys.stderr)
        return 1
    failures = await apply_files(paths)
    await list_schema()
    return 1 if failures else 0


if __name__ == "__main__":
    import asyncio
    raise SystemExit(asyncio.run(main()))
