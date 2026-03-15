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
Neuronum is a real-time, end-to-end encrypted data network. Transmit and receive data between any two points without managing backend infrastructure.

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
pip install neuronum==2026.03.1
```

> **Note:** Always activate this virtual environment (`source ~/neuronum-venv/bin/activate`) before running any `neuronum` commands.

Create a Cell (your Neuronum ID):
```sh
neuronum create-cell
```

------------------

### **How it works**

Every participant on the network is a **Cell** — a unique, encrypted identity. Every Cell can communicate with any other Cell on the network. All you need is the recipient's Cell ID.

Cells interact using four core methods:

| Method | Description |
|--------|-------------|
| `stream(cell_id, data)` | Send data to another Cell (fire-and-forget) |
| `activate_tx(cell_id, data)` | Send a request and wait for a response |
| `sync()` | Listen for incoming transmissions |
| `tx_response(transmitter_id, data, public_key)` | Send an encrypted response back |

All data is end-to-end encrypted. The network handles routing, key exchange, and delivery — you just send and receive.

------------------

### **Quick Example**

**Send data & wait for response**
```python
import asyncio
from neuronum import Cell

async def main():
    async with Cell() as cell:
        tx_response = await cell.activate_tx(
          "receiver_cell_id",
          {"msg": "Ping"}
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
                tx.get("transmitter_id"),
                {"msg": "Pong"},
                data.get("public_key", "")
            )

asyncio.run(main())
```

**TX (Transmitter) Object**

When you receive data via `sync()`, each transmission arrives as a TX object:
```python
{
    "transmitter_id": "bfd2a0d009c6f784ec97c41d3738a24e0e5ac8f1",
    "time": "1772923393",
    "operator": "1uRQdV593S91E3T2-Vj_29mxBJoI7Cvxxg6dNFDVfv4::cell",
    "data": {
        "msg": "Ping",
        "public_key": "-----BEGIN PUBLIC KEY-----\n..."
    }
}
```

------------------

### **Full Documentation**
For the complete SDK reference including the E2EE protocol, kybercell workspace setup, message types, and tools CLI, visit the [Neuronum Docs](https://neuronum.net/docs).
