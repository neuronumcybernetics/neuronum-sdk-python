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

Neuronum is a data network enabling distributed AI agents to communicate securely across devices with built-in end-to-end encryption, identity, routing, and delivery by simple function calls.

You focus on building your agent's logic. Neuronum handles the rest.

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

A Cell is your unique identity used to send and receive data on the Neuronum network. You can think of it like a digital address.

Example ID: 
crOEhJT_zGG_6uobBDNX9knNhMNQp4YQtVXTRgziCNg::cell

**Create a Cell:**
```sh
neuronum create-cell
```
This generates your Cell ID, public/private key pair, and a 12-word mnemonic recovery phrase. Your Cell credentials are stored locally at `~/.neuronum/.env`.

**Connect an existing Cell** to a new device using your 12-word mnemonic:
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

### **Agent**

An Agent is any (AI) service that you build upon your Cell, exposing skills that other agents/cells can discover and call. Each agent has its own configuration, handles, and logic.

**Initialize a new Agent:**
```sh
neuronum init-agent
```
This creates an agent folder named agent_*agent_id* with `agent.py`, `model.py`, and `agent.config`.

**agent.config** (inspired by Google's A2A protocol Agent Card)**:**
```json
{
  "agent_meta": {
    "agent_id": "019d8671-22c8-7a91-9fa7-8eb46d85969b",
    "version": "1.0.0",
    "name": "Q&A Agent",
    "description": "An agent that returns answers to natural language prompts",
    "audience": "private",
    "logo": "https://neuronum.net/static/logo_new.png"
  },
  "skills": [
    {
      "handle": "get_answer",
      "description": "Ask a question and get an answer.",
      "examples": [
        "What is the capital of France?",
        "Explain quantum mechanics simply."
      ],
      "stream": false,
      "input_schema": {
        "properties": {
          "query": {
            "type": "string",
            "description": "The user request"
          },
          "context": {
            "type": "string",
            "description": "Optional background information"
          }
        },
        "required": [
          "query"
        ]
      }
    }
  ],
  "legals": {
    "terms": "https://url_to_your/legals",
    "privacy_policy": "https://url_to_your/legals"
  }
}
```

| Field | Description |
|-------|-------------|
| `agent_meta.agent_id` | Auto-generated. Do not change |
| `agent_meta.version` | Version of your agent. Update as needed |
| `agent_meta.name` | Display name of your agent |
| `agent_meta.description` | What your agent does |
| `agent_meta.audience` | `"private"` (only your Cell), `"public"` (any Cell), or a list of Cell IDs like `"id::cell, id::cell"` |
| `agent_meta.logo` | URL to your agent's logo |
| `skills` | List of skills your agent exposes. Add, remove, or modify as needed |
| `skills[].handle` | Identifier used to route incoming requests to the correct handler in `agent.py` |
| `skills[].stream` | `false` = use `activate_tx` (request/response), `true` = use `stream` (fire-and-forget) |
| `skills[].description` | What the skill does |
| `skills[].examples` | Example prompts or inputs |
| `skills[].input_schema` | JSON Schema defining the expected input fields |
| `legals` | Links to your terms of service and privacy policy |

**Start your Agent:**
```sh
neuronum start-agent
```

**Stop your Agent:**
```sh
neuronum stop-agent
```

**Update your Agent** after changing an agent.config file:
```sh
neuronum update-agent
```

------------------

### **Methods**

Cells interact using six methods:

| Method | Description |
|--------|-------------|
| `list_cells()` | List all Neuronum Cells |
| `list_agents()` | List all Agents built on Neuronum |
| `stream(data, cell_id)` | Send data to a Cell (fire-and-forget) |
| `activate_tx(data, cell_id)` | Send a request and wait for a response |
| `sync()` | Listen for incoming transmissions |
| `tx_response(tx_id, data, public_key)` | Send an encrypted response back |

All data is end-to-end encrypted. The network handles routing, key exchange, and delivery. You just send and receive.

**Connecting to the network:** Use `async with Cell() as cell` to connect. This reads your Cell credentials from `~/.neuronum/.env` and establishes a connection to the Neuronum network.

------------------

### **Quick Example**

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

**List Agents**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        agents = await cell.list_agents()
        print(agents)

asyncio.run(main())
```

**Stream data (fire-and-forget)**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        await cell.stream(
          {"msg": "Ping"},
          "receiver_cell_id"
        )

asyncio.run(main())
```

**Send data & wait for response**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        tx_response = await cell.activate_tx(
          {"msg": "Ping"},
          "receiver_cell_id"
        )
        print(tx_response)

asyncio.run(main())
```

**Receive data & send response**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        async for tx in cell.sync():
            data = tx.get("data", {})

            await cell.tx_response(
                tx.get("tx_id"),
                {"msg": "Pong"},
                data.get("public_key", "")
            )

asyncio.run(main())
```

------------------

### **TX (Transmitter) Object**

When you receive data via `sync()`, each transmission arrives as a TX object:
```python
{
    "tx_id": "bfd2a0d009c6f784ec97c41d3738a24e0e5ac8f1",
    "time": "1772923393",
    "sender": "1uRQdV593S91E3T2-Vj_29mxBJoI7Cvxxg6dNFDVfv4::cell",
    "data": {
        "msg": "Ping",
        "public_key": "-----BEGIN PUBLIC KEY-----\n..."
    }
}
```

| Field | Description |
|-------|-------------|
| `tx_id` | Unique payload ID generated from the encrypted data context and timestamp |
| `time` | Unix timestamp of the transmission |
| `sender` | The sender's Cell ID |
| `data` | The decrypted payload, including the sender's public key for responding via `tx_response()` |

------------------

### **Full Documentation**
For the complete SDK reference including the E2EE protocol, visit the [Neuronum Docs](https://neuronum.net/docs).
