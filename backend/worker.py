"""Persistent NatqAI media queue worker. Run with: python worker.py"""
from __future__ import annotations
import asyncio
import logging
import os
from app.db import init_db, connection
from app.main import process_due_media_jobs

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("natqai.worker")

async def main() -> None:
    init_db()
    # Recover jobs interrupted by a process or machine restart.
    with connection() as conn:
        conn.execute(
            "UPDATE media_jobs SET status='queued', next_attempt_at=CURRENT_TIMESTAMP, "
            "error=COALESCE(error,'Worker restarted before completion.'), updated_at=CURRENT_TIMESTAMP "
            "WHERE status='running'"
        )
    while True:
        try:
            count = await process_due_media_jobs(20)
            if count:
                log.info("Processed %s media queue item(s)", count)
        except Exception:
            log.exception("Media queue polling failed")
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
