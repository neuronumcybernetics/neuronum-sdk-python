import asyncio
import json
from neuronum import Cell
from model import call_model
from elements import validate_element_payload

instruction_cache: dict[str, str] = {}
metadata_cache: dict[str, dict] = {}
session_started: set[str] = set()


SYSTEM_PROMPT = """
## Identity

You are a conversational agent speaking with customers or business partners. You guide the conversation dynamically based on your instructions, gathering and exchanging information naturally step by step.

## Instruction


## Response format

You must always reply with a single JSON object. The outer response must be valid JSON — no markdown or prose outside it. Inside the "msg" value, markdown is fully supported and encouraged for formatting text responses.

The "msg" key is always required. The "element" key is optional — only include it when an interactive UI component genuinely improves the experience over plain text.

## Elements

Plain message (default — use for most replies):
{"msg": "your text"}

Confirm — binary yes/no decision. Use when the user must explicitly accept or reject something before proceeding:
{"msg": "Do you approve?", "element": "confirm"}

Choice — pick one from a fixed set of options. Use when options are known upfront and mutually exclusive:
{"msg": "Which plan suits you best?", "element": "choice", "choices": ["Starter", "Pro", "Enterprise"]}

Input — collect one specific labelled value. Use only for structured data collection, not for general chat:
{"msg": "What is your company name?", "element": "input", "placeholder": "Acme Corp"}

Form — collect multiple specific labelled values in one step. Use instead of asking questions one by one:
{"msg": "Tell us about yourself:", "element": "form", "fields": [{"name": "company", "label": "Company", "placeholder": "Acme Corp"}, {"name": "role", "label": "Role", "placeholder": "CEO"}]}

Table — present structured data clearly. "columns" must be a flat list of strings. "rows" must be a list of lists of strings:
{"msg": "Here is your summary:", "element": "table", "columns": ["Field", "Value"], "rows": [["Company", "Acme"], ["Role", "CEO"]]}

Card — combine multiple elements into one message. Use when you need to show a summary and collect a response in the same step:
{"msg": "Review and confirm:", "element": "card", "components": [{"type": "table", "columns": ["Field", "Value"], "rows": [["Company", "Acme"], ["Role", "CEO"]]}, {"type": "confirm", "name": "approved", "label": "Does this look correct?"}]}

Link — a clickable button that opens a URL. Use for payments, external pages, or next-step actions:
{"msg": "Complete your payment", "element": "link", "link": "https://checkout.stripe.com/pay/cs_live_abc123"}

File — prompt the user to upload a file:
{"msg": "Please upload your signed contract:", "element": "file"}

## Rules

- Never send a table followed immediately by a confirm as two separate messages. Use a card instead.
- Do not use "input" or "form" for general conversation — the user already has a chat input. Reserve them for collecting specific structured data.
- Do not use "choice" for open-ended questions — only when the full set of options is known.
- All row values in tables must be strings, not numbers.
- If no element genuinely improves the interaction, omit "element" entirely.
"""


async def get_session_context(cell: Cell, session_id: str) -> str:
    """Returns full system prompt built from session metadata. Caches per session."""
    if session_id not in instruction_cache:
        metadata = await cell.fetch_session_metadata(session_id)
        metadata_cache[session_id] = metadata or {}
        instruct = metadata.get("instruct", "") if metadata else ""
        instruction_cache[session_id] = SYSTEM_PROMPT.replace("## Instruction\n", f"## Instruction\n\n{instruct}\n")
    return instruction_cache[session_id]


async def build_history(cell: Cell, session_id: str) -> list[dict]:
    messages = await cell.get_session_messages(session_id)
    history = []
    for m in messages:
        data = m["data"]
        action = data.get("action")
        if action == "session_joined":
            continue
        text = data.get("msg", "")
        element = data.get("element")
        if action == "element_response" and element and isinstance(text, dict):
            text = f"[{element} response] {json.dumps(text)}"
        elif action == "element_response" and element and isinstance(text, str):
            text = f"[{element} response] {text}"
        elif isinstance(text, dict):
            text = json.dumps(text)
        elif not isinstance(text, str):
            text = str(text)
        if not text:
            continue
        role = "assistant" if m["sender"] == cell.host else "user"
        history.append({"role": role, "content": text})
    return history


def generate_reply(system: str, history: list[dict]) -> dict:
    reply = call_model(system, history)
    try:
        return validate_element_payload(reply)
    except ValueError:
        return {"msg": reply.get("msg", str(reply))}


async def listen(cell: Cell):
    async for message in cell.sync_messages():
        session_id = message["session_id"]
        sender = message["sender"]
        data = message["data"]
        action = data.get("action")
        user_text = data.get("msg", "")

        if sender == cell.host:
            continue

        # ── Session joined — start conversation immediately ───────────────────
        if action == "session_joined":
            if session_id in session_started:
                continue
            try:
                existing = await cell.get_session_messages(session_id)
                if any(m["sender"] == cell.host for m in existing):
                    session_started.add(session_id)
                    continue
            except Exception:
                pass
            session_started.add(session_id)
            try:
                system = await get_session_context(cell, session_id)
                greeting = await asyncio.to_thread(
                    generate_reply,
                    system,
                    [{"role": "user", "content": "Introduce yourself briefly and let me know how you can help."}],
                )
                await cell.send_session_message(session_id, greeting)
            except Exception as e:
                print(f"[worker] Error sending greeting in {session_id}: {e}")
            continue

        # ── Element response ──────────────────────────────────────────────────
        if action == "element_response":
            try:
                system = await get_session_context(cell, session_id)
                history = await build_history(cell, session_id)
                reply = await asyncio.to_thread(generate_reply, system, history)
                await cell.send_session_message(session_id, reply)
            except Exception as e:
                print(f"[worker] Error on element_response in {session_id}: {e}")
            continue

        # ── File uploads ──────────────────────────────────────────────────────
        if action == "file":
            continue

        # ── Regular message ───────────────────────────────────────────────────
        if not user_text:
            continue

        try:
            system = await get_session_context(cell, session_id)
            history = await build_history(cell, session_id)
            reply = await asyncio.to_thread(generate_reply, system, history)
            await cell.send_session_message(session_id, reply)
        except Exception as e:
            print(f"[worker] Error handling message in {session_id}: {e}")


async def main():
    retry_delay = 2

    async with Cell(network="testnet.neuronum.net") as cell:
        while True:
            try:
                await listen(cell)
            except Exception as e:
                print(f"[worker] SSE error: {e}")
            await asyncio.sleep(retry_delay)


asyncio.run(main())
