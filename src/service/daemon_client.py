"""Shared Unix-socket JSON-line client for talking to the approval daemon
(src/service/discord_listener.py's socket server). Used by both the
request_boss_approval MCP tool (src/discord_mcp/server.py) and the
pre-commit pending-approval check (scripts/check_pending_approval.py) —
previously each had its own near-identical copy of this protocol.
"""

import asyncio
import json
from typing import Any


async def call_daemon(
    payload: dict[str, Any], socket_path: str, timeout: float
) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line:
            raise ConnectionError("Daemon closed the connection without a response.")
        result: dict[str, Any] = json.loads(line.decode("utf-8"))
        return result
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
