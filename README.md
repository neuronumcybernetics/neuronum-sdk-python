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

Neuronum is an end-to-end encrypted data network for system-to-system communication. You use it to stream, request, and respond to data between AI agents, services, or devices across different servers.

It handles encryption, identity, routing, and delivery automatically. You can focus on building your application instead of managing backend infrastructure.

Whether you're connecting two AI agents, orchestrating a distributed system, or streaming sensor data from an IoT device, Neuronum gives you a simple API to move encrypted data between any two points.

> ⚠️ **Development Status:** The Neuronum SDK is currently in beta and is **not production-ready**. It is intended for development, testing, and experimental purposes only. Do not use in production environments or for critical applications.

------------------

### **Requirements**
- Python >= 3.8

------------------

### **Installation**

Setup and activate a virtual environment:
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

A Cell is your unique identity on the Neuronum network. Every participant, whether an agent, a service, or a device is a Cell. Cells are addresses you can send data to on the network.

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

### **Methods**

Cells interact using five methods:

| Method | Description |
|--------|-------------|
| `list_cells()` | List all Neuronum Cells |
| `stream(data, cell_id)` | Send data to a Cell (fire-and-forget). Defaults to own Cell |
| `activate_tx(data, cell_id)` | Send a request and wait for a response. Defaults to own Cell |
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
