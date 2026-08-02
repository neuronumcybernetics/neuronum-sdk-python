"""
Neuronum MCP server (FastMCP).

Exposes Neuronum AgentIdentity methods as MCP tools:
  - list_agents:                 list agents visible to this agent
  - list_sessions:               list all secure agent sessions for this agent
  - fetch_session_metadata:      fetch metadata for a specific session
  - get_session_messages:        fetch and decrypt messages for a session
  - create_secure_agent_session: open a new secure agent session
  - send_session_message:        send an encrypted message to a session

Install the optional MCP extra to use this:
  pip install neuronum[mcp]

Run with:
  neuronum-mcp                         (stdio transport, default network)
  NEURONUM_NETWORK=your-network.neuronum.net neuronum-mcp
"""

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP, Context

from neuronum.neuronum import AgentIdentity


# --- Lifecycle -------------------------------------------------------------

@dataclass
class AppContext:
    agent: AgentIdentity


@asynccontextmanager
async def lifespan(server: FastMCP):
    network = os.environ.get("NEURONUM_NETWORK", "neuronum.net")
    agent = AgentIdentity(network=network)
    async with agent:
        yield AppContext(agent=agent)


mcp = FastMCP("neuronum", lifespan=lifespan)


# --- Tools -----------------------------------------------------------------

@mcp.tool
async def list_agents(ctx: Context, update: bool = False) -> list[dict[str, Any]]:
    """List all Neuronum agents visible to this agent.

    Args:
        update: If True, bypass the local cache and fetch a fresh list
                from the network. If False (default), a cached result is
                returned when it is still valid.
    """
    agent: AgentIdentity = ctx.lifespan_context.agent
    return await agent.list_agents(update=update)


@mcp.tool
async def list_sessions(ctx: Context) -> list[dict[str, Any]]:
    """List all secure agent sessions for this agent.

    Returns a list of session metadata dicts, each containing at minimum
    session_id, requester_agent_id, and receiver_agent_id.
    """
    agent: AgentIdentity = ctx.lifespan_context.agent
    return await agent.list_sessions()


@mcp.tool
async def fetch_session_metadata(ctx: Context, session_id: str) -> dict[str, Any]:
    """Fetch metadata for a specific secure agent session.

    Args:
        session_id: The ID of the session to retrieve metadata for.

    Returns:
        Session metadata dict, or an empty dict if not found.
    """
    agent: AgentIdentity = ctx.lifespan_context.agent
    result = await agent.fetch_session_metadata(session_id)
    return result or {}


@mcp.tool
async def get_session_messages(ctx: Context, session_id: str) -> list[dict[str, Any]]:
    """Fetch and decrypt all messages for a secure agent session.

    Only messages encrypted for this agent are returned; messages encrypted
    for the other participant are silently skipped.

    Args:
        session_id: The ID of the session to retrieve messages from.

    Returns:
        A list of decrypted message dicts with keys: tx_id, time, sender, data.
    """
    agent: AgentIdentity = ctx.lifespan_context.agent
    messages = await agent.get_session_messages(session_id)
    return messages


@mcp.tool
async def create_secure_agent_session(
    ctx: Context,
    recipient: str,
    instruct: str | None = None,
    subject: str | None = None,
) -> dict[str, Any]:
    """
    Create a secure agent session and send an invitation, optionally instructing the agent.

    Args:
        recipient: Receiver identity (email or agent_id).
        instruct: Optional instructions or goals for the agent.
        subject: Optional subject for the session.

    Returns:
        Session metadata returned by the server.
    """

    if not recipient:
        raise ValueError("recipient is required.")

    agent: AgentIdentity = ctx.lifespan_context.agent

    result = await agent.create_secure_agent_session(
        instruct=instruct,
        recipient=recipient,
        subject=subject,
    )

    return result or {}



@mcp.tool
async def send_session_message(
    ctx: Context,
    session_id: str,
    msg: str,
    element: str | None = None,
    # confirm — no extra fields needed
    # choice
    choices: Any = None,
    # input
    placeholder: str | None = None,
    # form
    fields: Any = None,
    # table
    columns: Any = None,
    rows: Any = None,
    # card
    components: Any = None,
) -> dict[str, Any]:
    """Send an encrypted message to a secure agent session.

    The payload is end-to-end encrypted (ECDH + AES-GCM) for both sender
    and receiver. Pass `element` to render interactive UI components on the
    client frontend.

    Args:
        session_id:  The ID of the session to send the message to.
        msg:         The text content of the message.
        element:     Optional UI element type. One of:
                       "confirm" — Accept / Decline buttons.
                       "choice"  — Option buttons; also pass `choices`.
                       "input"   — Single text input; optionally pass `placeholder`.
                       "form"    — Multi-field form; also pass `fields`.
                       "table"   — Data table; also pass `columns` and `rows`.
                       "card"    — Composite element; also pass `components`.
                       "file"    — File upload prompt.
        choices:     (choice) List of option labels, e.g. ["PDF", "CSV"].
        placeholder: (input) Placeholder text for the input field.
        fields:      (form) List of field dicts with keys: name, label, placeholder.
                     Example: [{"name": "company", "label": "Company", "placeholder": "Acme"}]
        columns:     (table) Column header labels, e.g. ["Name", "Status", "Score"].
        rows:        (table) List of rows, each a list of agent values.
                     Example: [["Alice", "Active", 92], ["Bob", "Inactive", 74]]
        components:  (card) List of component dicts. Each dict needs a "type" key
                     matching an element name plus its relevant fields.
                     Example: [{"type": "confirm", "label": "Approve?"},
                               {"type": "input", "name": "budget", "placeholder": "$10k"}]

    Returns:
        {"success": bool, "session_id": str}
    """
    if isinstance(choices, str):
        choices = json.loads(choices)
    if isinstance(fields, str):
        fields = json.loads(fields)
    if isinstance(columns, str):
        columns = json.loads(columns)
    if isinstance(rows, str):
        rows = json.loads(rows)
    if isinstance(components, str):
        components = json.loads(components)

    data: dict[str, Any] = {"msg": msg}

    if element:
        data["element"] = element

        if element == "choice":
            if not choices:
                raise ValueError("'choices' is required for element='choice'")
            data["choices"] = choices

        elif element == "input":
            if placeholder:
                data["placeholder"] = placeholder

        elif element == "form":
            if not fields:
                raise ValueError("'fields' is required for element='form'")
            data["fields"] = fields

        elif element == "table":
            if not columns or rows is None:
                raise ValueError("'columns' and 'rows' are required for element='table'")
            data["columns"] = columns
            data["rows"] = rows

        elif element == "card":
            if not components:
                raise ValueError("'components' is required for element='card'")
            data["components"] = components

    agent: AgentIdentity = ctx.lifespan_context.agent
    success = await agent.send_session_message(session_id=session_id, data=data)
    return {"success": success, "session_id": session_id}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
