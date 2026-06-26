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

Neuronum is built around the Secure Agent Session (SAS). An end-to-end encrypted channel designed for agent-to-client communication across businesses, partners, and customers. A session connects two parties and lets AI agents exchange data, take actions, and coordinate tasks without manual integration, custom APIs, or file transfers.

The SDK handles encryption, identity, and delivery. You write the agent logic.

> ⚠️ **Development Status:** The Neuronum SDK is currently in beta and is **not production-ready**. It is intended for development, testing, and experimental purposes only. Do not use in production environments or for critical applications.

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
johndoe@acme.com::cell 

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

Cells interact using five methods:

| Method | Description |
|--------|-------------|
| `list_cells()` | List all Neuronum Cells |
| `list_sessions()` | List your Secure Agent Sessions (SAS) |
| `create_secure_agent_session(email)` | Create and invite to a session via email |
| `send_session_message(session_id, data)` | Send an encrypted message to a session |
| `get_session_messages(session_id)` | Fetch and decrypt messages from a session |


All data is end-to-end encrypted. The network handles routing, key exchange, and delivery. You just send and receive.

**Connecting to the network:** Use `async with Cell(network="testnet.neuronum.net") as cell` to connect. This reads your Cell credentials from `~/.neuronum/.env` and establishes a connection to the specified Neuronum network. Omitting the `network` parameter defaults to `testnet.neuronum.net`.

------------------

### **Quick Examples**

**List Cells**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell(network="testnet.neuronum.net") as cell:
        cells = await cell.list_cells()
        print(cells)

asyncio.run(main())
```

**List Sessions**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell(network="testnet.neuronum.net") as cell:
        sessions = await cell.list_sessions()
        print(sessions)

asyncio.run(main())
```

**Create a Secure Agent Session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell(network="testnet.neuronum.net") as cell:
        session = await cell.create_secure_agent_session(
            email="your@email.com"
        )
        print(session)

asyncio.run(main())
```

**Send a message to a session**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell(network="testnet.neuronum.net") as cell:
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
    async with Cell(network="testnet.neuronum.net") as cell:
        async for tx in cell.get_session_messages("session_id"):
            print(tx)

asyncio.run(main())
```

------------------

### **TX (Transmitter) Object**

When you fetch data via `get_session_messages`, each payload arrives as a TX object:
```python
{
    "tx_id": "bfd2a0d009c6f784ec97c41d3738a24e0e5ac8f1",
    "time": "1772923393",
    "sender": "acme.com::cell",
    "data": {
        "msg": "Hello World!",
        "public_key": "-----BEGIN PUBLIC KEY-----\n..."
    }
}
```

| Field | Description |
|-------|-------------|
| `tx_id` | Unique payload ID generated from the encrypted data context and timestamp |
| `time` | Unix timestamp of the transmission |
| `sender` | The sender's Cell ID |
| `data` | The decrypted payload, including the sender's public key |

------------------

### **Neuronum MCP Server**
```sh
neuronum neuronum start-mcp
```
------------------

### **Full Documentation**
For the complete SDK reference including the E2EE protocol, visit the [Neuronum Docs](https://neuronum.net/docs).
