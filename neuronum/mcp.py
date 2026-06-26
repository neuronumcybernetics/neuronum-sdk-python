"""
Neuronum MCP server (FastMCP).

Exposes Neuronum Cell methods as MCP tools:
  - list_cells:                  list cells visible to this cell
  - list_sessions:               list all secure agent sessions for this cell
  - get_session_messages:        fetch and decrypt messages for a session
  - create_secure_agent_session: open a new secure agent session
  - send_session_message:        send an encrypted message to a session

Install the optional MCP extra to use this:
  pip install neuronum[mcp]

Run with:
  neuronum-mcp                         (stdio transport, default network)
  NEURONUM_NETWORK=testnet.neuronum.net neuronum-mcp
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP, Context

from neuronum.neuronum import Cell


# --- Lifecycle -------------------------------------------------------------

@dataclass
class AppContext:
    cell: Cell


@asynccontextmanager
async def lifespan(server: FastMCP):
    network = os.environ.get("NEURONUM_NETWORK", "neuronum.net")
    cell = Cell(network=network)
    async with cell:
        yield AppContext(cell=cell)


mcp = FastMCP("neuronum", lifespan=lifespan)


# --- Tools -----------------------------------------------------------------

@mcp.tool
async def list_cells(ctx: Context, update: bool = False) -> list[dict[str, Any]]:
    """List all Neuronum cells visible to this cell.

    Args:
        update: If True, bypass the local cache and fetch a fresh list
                from the network. If False (default), a cached result is
                returned when it is still valid.
    """
    cell: Cell = ctx.lifespan_context.cell
    return await cell.list_cells(update=update)


@mcp.tool
async def list_sessions(ctx: Context) -> list[dict[str, Any]]:
    """List all secure agent sessions for this cell.

    Returns a list of session metadata dicts, each containing at minimum
    session_id, requester_cell_id, and receiver_cell_id.
    """
    cell: Cell = ctx.lifespan_context.cell
    return await cell.list_sessions()


@mcp.tool
async def get_session_messages(ctx: Context, session_id: str) -> list[dict[str, Any]]:
    """Fetch and decrypt all messages for a secure agent session.

    Only messages encrypted for this cell are returned; messages encrypted
    for the other participant are silently skipped.

    Args:
        session_id: The ID of the session to retrieve messages from.

    Returns:
        A list of decrypted message dicts with keys: tx_id, time, sender, data.
    """
    cell: Cell = ctx.lifespan_context.cell
    messages = []
    async for msg in cell.get_session_messages(session_id):
        messages.append(msg)
    return messages


@mcp.tool
async def create_secure_agent_session(
    ctx: Context,
    email: str,
) -> dict[str, Any]:
    """Create a secure agent session and send an invitation via email.

    Args:
        email:   The email address of the receiver.

    Returns:
        Session metadata returned by the server.
    """
    cell: Cell = ctx.lifespan_context.cell
    result = await cell.create_secure_agent_session(
        email=email,
    )
    return result or {}


@mcp.tool
async def send_session_message(
    ctx: Context,
    session_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Send an encrypted message to a secure agent session.

    The payload is end-to-end encrypted (ECDH + AES-GCM) for both the
    sender and the receiver before it leaves this machine.

    Args:
        session_id: The ID of the session to send the message to.
        data:       The JSON-serializable payload to send.

    Returns:
        {"success": bool, "session_id": str}
    """
    cell: Cell = ctx.lifespan_context.cell
    success = await cell.send_session_message(session_id=session_id, data=data)
    return {"success": success, "session_id": session_id}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
