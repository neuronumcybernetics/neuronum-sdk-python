<h1 align="center">
  <img src="https://neuronum.net/static/logo_new.png" alt="Neuronum" width="80">
</h1>
<h4 align="center">Neuronum SDK</h4>

<p align="center">
  <a href="https://neuronum.net">
    <img src="https://img.shields.io/badge/Website-Neuronum-blue" alt="Website">
  </a>
  <a href="https://neuronum.net/docs">
    <img src="https://img.shields.io/badge/Docs-Read%20now-green" alt="Documentation">
  </a>
  <a href="https://pypi.org/project/neuronum/">
    <img src="https://img.shields.io/pypi/v/neuronum.svg" alt="PyPI Version">
  </a><br>
  <img src="https://img.shields.io/badge/Python-3.8%2B-yellow" alt="Python Version">
  <a href="https://github.com/neuronumcybernetics/cell-sdk-python/blob/main/LICENSE.md">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License">
  </a>
</p>

------------------

### **About**

Neuronum is built around the [Secure Agent Session (SAS)](https://neuronum.net/secure-agent-session), an end-to-end encrypted channel designed for stateful agent-to-client and agent-to-agent communication across businesses, partners, and customers. A session connects two parties to automate data exchange, take actions, and coordinate tasks without manual integration, custom APIs, or file transfers.

The SDK handles encryption, identity, and delivery. You write the agent logic.

------------------

### **Requirements**
- Python >= 3.8

------------------

### **Installation**

Set up and activate a virtual environment:
```sh
python3 -m venv ~/neuronum-venv
source ~/neuronum-venv/bin/activate
```

Install the Neuronum SDK:
```sh
pip install neuronum
```

> **Note:** Always activate this virtual environment (`source ~/neuronum-venv/bin/activate`) before running any `neuronum` commands.

------------------

### **Cell**

A Cell is your address used to send and receive data on the Neuronum network. You can think of it like a unique digital identity.

Example IDs: 
acme.com::cell 

**Create a Cell:**
```sh
neuronum create-cell
```
This generates your Cell ID, public/private key pair, and a 12-word mnemonic recovery phrase. Your Cell credentials are stored locally at `~/.neuronum/.env`.

**Connect your Cell** to a device using your 12-word mnemonic:
```sh
neuronum connect-cell
```

**View** the connected Cell ID:
```sh
neuronum view-cell
```

**Verify** the connected Cell ID:
```sh
neuronum verify-cell
```

**Disconnect** Cell credentials from this device:
```sh
neuronum disconnect-cell
```

**Delete** your Cell permanently from the network:
```sh
neuronum delete-cell
```

------------------

### **Methods**

Cells interact on Neuronum using the following methods:

| Method | Description |
|--------|-------------|
| `list_cells()` | List all Neuronum Cells |
| `list_sessions()` | List your Secure Agent Sessions (SAS) |
| `create_secure_agent_session(email or cell_id, instruct=None, subject=None)` | Create and invite to a session via email or cell_id, optionally setting agent instructions and session password |
| `fetch_session_metadata(session_id)` | Fetch session metadata |
| `send_session_message(session_id, data)` | Send an encrypted message to a session |
| `get_session_messages(session_id)` | Fetch and decrypt messages from a session |
| `upload_session_file(session_id, file_path, mime_type)` | Upload an encrypted file to a session |
| `download_session_file(session_id, file_id)` | Download a file from a session by file ID |
| `sync_messages()` | Receive messages from all sessions in real-time |


All data is end-to-end encrypted. The network handles routing, key exchange, and delivery. You just send and receive.

**Connecting to the network:** Use `async with Cell() as cell` to connect. This reads your Cell credentials from `~/.neuronum/.env` and establishes a connection to the Neuronum network at `neuronum.net`. Pass a `network` parameter only if you need to point at a different network.

------------------

### **Quick Examples**

**List Cells**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        cells = await cell.list_cells()
        print(cells)

asyncio.run(main())
```

**List Sessions**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        sessions = await cell.list_sessions()
        print(sessions)

asyncio.run(main())
```

**Create a Secure Agent Session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        session = await cell.create_secure_agent_session(
            email="your@email.com",  #or cell_id="acme.com::cell"
            instruct="Set specific goals, conversation context or further instructions",  #optional
            subject="Set session subject"  #optional - !Notice: Subject is sent in plaintext!
        )
        print(session)

asyncio.run(main())
```

**Fetch Session Metadata**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        metadata = await cell.fetch_session_metadata("session_id")
        print(metadata)

asyncio.run(main())
```

**Send a message to a session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        success = await cell.send_session_message(
            "session_id",
            {"msg": "Hello"}
        )
        print(success)

asyncio.run(main())
```

**Fetch messages from a session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        messages = await cell.get_session_messages(session_id)
        print(messages)

asyncio.run(main())
```

**Upload a file to a session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        success = await cell.upload_session_file(
            "session_id",
            "/path/to/file.pdf",
            mime_type="application/pdf"
        )
        print(success)

asyncio.run(main())
```

**Download a file from a session**

The `file_id` is available in the file metadata message sent automatically after a successful upload. Retrieve it via `get_session_messages` from the `file_id` field.

```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        file_bytes = await cell.download_session_file("session_id", "file_id")
        with open("output.pdf", "wb") as f:
            f.write(file_bytes)

asyncio.run(main())
```

**Receive messages in real-time**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        async for message in cell.sync_messages():
            print(message["session_id"], message["sender"], message["data"])

asyncio.run(main())
```

------------------

### **Elements**

Elements are UI components rendered on the client's frontend. Pass an `element` key in any `send_session_message` call to trigger them.

| Element | Description |
|---------|-------------|
| `confirm` | Renders Accept / Decline buttons |
| `choice` | Renders a set of option buttons |
| `input` | Renders a single text input field |
| `form` | Renders a multi-field form |
| `table` | Renders a data table |
| `card` | Renders a composite card combining multiple elements |
| `file` | Renders a file upload prompt |
| `link` | Renders a clickable button that opens a URL in a new browser tab |

**Confirm**
```python
await cell.send_session_message(session_id, {
    "msg": "Do you accept the session terms?",
    "element": "confirm"
})
```

**Choice**
```python
await cell.send_session_message(session_id, {
    "msg": "Which report format do you prefer?",
    "element": "choice",
    "choices": ["PDF", "CSV", "JSON"]
})
```

**Input**
```python
await cell.send_session_message(session_id, {
    "msg": "What is your company name?",
    "element": "input",
    "placeholder": "e.g. Acme Corp"
})
```

**Form**
```python
await cell.send_session_message(session_id, {
    "msg": "Tell us about yourself:",
    "element": "form",
    "fields": [
        {"name": "company",  "label": "Company",  "placeholder": "Acme Corp"},
        {"name": "role",     "label": "Role",      "placeholder": "CEO"},
        {"name": "teamsize", "label": "Team size", "placeholder": "50"}
    ]
})
```

**Table**
```python
await cell.send_session_message(session_id, {
    "msg": "Here are the results:",
    "element": "table",
    "columns": ["Name", "Status", "Score"],
    "rows": [
        ["Alice", "Active", 92],
        ["Bob", "Inactive", 74],
        ["Carol", "Active", 88]
    ]
})
```

**Card**

A card combines multiple elements into a single message.

```python
await cell.send_session_message(session_id, {
    "msg": "Review this proposal:",
    "element": "card",
    "components": [
        {"type": "table", "columns": ["Item", "Cost"], "rows": [["Dev", "$5k"], ["Design", "$2k"]]},
        {"type": "input", "name": "budget", "label": "Your budget", "placeholder": "$10,000"},
        {"type": "choice", "name": "timeline", "label": "Timeline", "choices": ["1 month", "3 months", "6 months"]},
        {"type": "confirm", "name": "approved", "label": "Do you approve?"}
    ]
})
```

**File**

Renders a file upload prompt on the client.

```python
await cell.send_session_message(session_id, {
    "msg": "Please upload your contract:",
    "element": "file"
})
```

**Link**

Renders a clickable button that opens a URL in a new browser tab.

```python
await cell.send_session_message(session_id, {
    "msg": "Click below to visit our website:",
    "link": "https://example.com",
    "element": "link"
})
```

------------------

### **Neuronum MCP Server**
```sh
neuronum neuronum start-mcp
```
------------------

### **Full Documentation**
Visit the [Neuronum Docs](https://neuronum.net/docs) for the complete SDK reference.