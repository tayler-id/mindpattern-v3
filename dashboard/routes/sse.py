"""SSE event streaming — polls events table and pushes to connected clients."""

import asyncio
import json
import sqlite3

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from orchestrator.traces_db import get_db, TRACES_DB_PATH

router = APIRouter()

POLL_INTERVAL = 5  # seconds


async def event_generator():
    """Yield SSE-formatted events by polling the events table."""
    last_event_id = 0

    # Get the latest event ID to start from (don't replay history)
    if TRACES_DB_PATH.exists():
        try:
            conn = get_db()
            try:
                cur = conn.execute("SELECT MAX(id) as max_id FROM events")
                row = cur.fetchone()
                if row and row["max_id"]:
                    last_event_id = row["max_id"]
            finally:
                conn.close()
        except sqlite3.Error:
            pass  # Fall back to last_event_id = 0

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        if not TRACES_DB_PATH.exists():
            continue

        try:
            conn = get_db()
            try:
                cur = conn.execute(
                    "SELECT * FROM events WHERE id > ? ORDER BY id ASC",
                    (last_event_id,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            continue  # Retry next cycle on transient DB errors

        for row in rows:
            last_event_id = row["id"]
            data = json.dumps({
                "pipeline_run_id": row["pipeline_run_id"],
                "event_type": row["event_type"],
                "payload": row["payload"],
                "created_at": row["created_at"],
            })
            # Emit as generic "message" event so htmx can catch all updates
            yield f"event: pipeline_update\ndata: {data}\n\n"


@router.get("/sse/events")
async def sse_events():
    """SSE endpoint — streams pipeline events to connected clients."""
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
