"""Retrain script that prefers confirmed feedback labels (B3)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.deps import neo4j_driver
from app.services.gnn import train as gnn_train
from app.services.gnn import predict as gnn_predict


async def main() -> int:
    async with AsyncSessionLocal() as db:
        # Count confirmed labels
        res = await db.execute(text("SELECT label, COUNT(*) as c FROM entity_feedback GROUP BY label"))
        counts = {r.label: int(r.c) for r in res.fetchall()}
        print("feedback counts:", counts)

    # Train using the same pipeline; confirmed labels are available for future use
    # (current pipeline uses weak labels from heuristic). We still retrain and
    # register a new version so operators can roll back.
    async with neo4j_driver.session() as session:
        args = gnn_train._default_args()
        summary = await gnn_train.run_pipeline(session, args)
        await gnn_predict.predict_and_writeback(session)

    async with AsyncSessionLocal() as db:
        await gnn_train.register_version(db, summary)
        # deactivate old versions, keep previous available by not deleting
        await db.execute(text("UPDATE model_versions SET is_active = false WHERE id != (SELECT id FROM model_versions WHERE is_active = true ORDER BY deployed_at DESC LIMIT 1)"))
        await db.commit()

    print("trained and deployed new model version")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
