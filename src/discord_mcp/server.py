import json
import os
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("drunken-discord-mcp")

OUTBOX_FILE = ".agents/discord_outbox.json"


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def request_boss_approval(action: str, reason: str) -> str:
    """
    Request approval or clarification from the Boss via Discord.
    
    Args:
        action: A short description of the action you want to take or what you need.
        reason: Why you need to take this action or need this clarification.
        
    Returns:
        Instructions on what to do next. You MUST follow them strictly.
    """
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    question = f"**Action:** {action}\n**Reason:** {reason}"
    
    # Read existing
    data: dict[str, Any] = {}
    if os.path.exists(OUTBOX_FILE):
        try:
            with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    # Add new request
    data[req_id] = {"question": question}
    
    # Write back
    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
    with open(OUTBOX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return (
        f"Successfully sent request {req_id} to Boss.\n\n"
        f"CRITICAL NEXT STEP: You MUST use the `schedule` tool to wait for "
        f"`.agents/discord_inbox.json` (e.g. DurationSeconds=20, Prompt=\"Check inbox for {req_id}\"), "
        f"and IMMEDIATELY STOP CALLING TOOLS to END YOUR TURN. Do NOT use `run_command`!"
    )


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
