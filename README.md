<h1 align="center">
  <img src="https://neuronum.net/static/logo_new.png" alt="Neuronum" width="80">
</h1>
<h4 align="center">Neuronum SDK</h4>

<p align="center">
  <a href="https://neuronum.net">
    <img src="https://img.shields.io/badge/Website-Neuronum-blue" alt="Website">
  </a>
  <a href="https://github.com/neuronumcybernetics/cell-sdk-python">
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


### **About the Neuronum SDK**
The Neuronum SDK provides everything you need to setup your favorite AI model as self-hosted agentic backend. It includes the [Neuronum Server](#neuronum-server), an open source agent-wrapper that transforms your model into an executable assistant that can be managed and called with the [Neuronum Client API](#neuronum-client-api) and the [Neuronum Tools CLI](#neuronum-tools-cli) to develop and publish MCP-compliant Tools that can be installed locally on your [Neuronum Server](#neuronum-server)

> **Protocol Note:** The Neuronum SDK is powered by an end-to-end encrypted communication protocol based on public/private key pairs derived from a randomly generated 12-word mnemonic. All data is relayed through neuronum.net, providing secure communication without the need to set up public web servers or expose your infrastructure to the public internet.

> ⚠️ **Development Status:** The Neuronum SDK is currently in early stages of development and is **not production-ready**. It is intended for development, testing, and experimental purposes only. Do not use in production environments or for critical applications.

------------------

### **Requirements**
- Python >= 3.8
- **Linux/NVIDIA GPU:** CUDA-compatible GPU + CUDA Toolkit (uses vLLM for model serving)
- **macOS Apple Silicon:** Ollama installed (uses Ollama for model serving)

------------------

### **Table of Contents**
In this programmers guide, you will learn how to:
- [Connect to the Neuronum Network](#connect-to-neuronum)
- [Deploy a Model with Neuronum Server](#neuronum-server)
- [Call your Agent with the Neuronum Client API](#neuronum-client-api)
- [Create & Manage a Custom Tool with the Neuronum Tools CLI](#neuronum-tools-cli)

------------------

### **Connect To Neuronum**
**Installation**

Create and activate a virtual environment:
```sh
python3 -m venv ~/neuronum-venv
source ~/neuronum-venv/bin/activate
```

Install the Neuronum SDK:
```sh
pip install neuronum==2026.01.0.dev2
```

> **Note:** Always activate this virtual environment (`source ~/neuronum-venv/bin/activate`) before running any `neuronum` commands.

**Create a Neuronum Cell (secure Identity)**
```sh
neuronum create-cell
```

**Connect your Cell**
```sh
neuronum connect-cell
```

------------------

### **Neuronum Server**
Neuronum Server is an agent-wrapper that transforms your model into an agentic backend server that can interact with the [Neuronum Client API](#neuronum-client-api) and installed tools

------------------

**Start the Server**

```sh
neuronum start-server
```

This command will:
- Clone the neuronum-server repository (if not already present)
- Detect your hardware platform (Apple Silicon or NVIDIA GPU)
- Create a Python virtual environment
- Install platform-specific dependencies
- **Apple Silicon:** Verify Ollama is installed, start the Ollama server, and pull the configured model
- **NVIDIA GPU:** Start the vLLM server in the background and wait for model loading
- Launch the Neuronum Server

**Check Server Status**

```sh
neuronum status
```

This will show if the Neuronum Server and vLLM Server are currently running with their PIDs.

**Viewing Logs**

```sh
tail -f neuronum-server/server.log       # Main server log
tail -f neuronum-server/vllm_server.log  # vLLM log (NVIDIA GPU only)
```

**Stopping the Server**

```sh
neuronum stop-server
```

**What the Server Does**

Once running, the server will:
- Connect to the Neuronum network using your Cell credentials
- Initialize a local SQLite database for conversation memory and auto-indexes files in the `templates/` directory
- Auto-discover and launch any MCP servers in the `tools/` directory
- Process messages from clients via the Neuronum network

**Server Configuration**

The server can be customized by editing the `neuronum-server/server.config` file. Here are the available options:

**File Paths:**
```python
LOG_FILE = "server.log"              # Server log file location
DB_PATH = "agent_memory.db"          # SQLite database for conversations and knowledge
TEMPLATES_DIR = "./templates"        # HTML templates to auto-index on startup and serve
```

**Model Configuration:**
```python
MODEL_MAX_TOKENS = 512               # Maximum tokens in responses (higher = longer answers)
MODEL_TEMPERATURE = 0.3              # Creativity (0.0 = deterministic, 1.0 = creative)
MODEL_TOP_P = 0.85                   # Nucleus sampling (lower = more predictable)
```

**vLLM Server (NVIDIA GPU):**
```python
VLLM_MODEL_NAME = "Qwen/Qwen2.5-3B-Instruct"  # Model to load
                                               # Examples: "Qwen/Qwen2.5-1.5B-Instruct",
                                               #           "meta-llama/Llama-3.2-3B-Instruct"
VLLM_HOST = "127.0.0.1"              # Server host (127.0.0.1 = local only)
VLLM_PORT = 8000                     # Server port
VLLM_API_BASE = "http://127.0.0.1:8000/v1"  # Full API URL
```

**Ollama (Apple Silicon):**
```python
OLLAMA_MODEL_NAME = "llama3.1:8b"    # Model to load
                                     # Examples: "llama3.2:3b", "qwen2.5:3b", "qwen2.5:7b"
OLLAMA_API_BASE = "http://127.0.0.1:11434/v1"  # Ollama API URL (default port: 11434)
```

**Conversation & Knowledge:**
```python
CONVERSATION_HISTORY_LIMIT = 10      # Recent messages to include in context
KNOWLEDGE_RETRIEVAL_LIMIT = 5        # Max knowledge chunks to retrieve
FTS5_STOPWORDS = {...}               # Words to exclude from knowledge search
```

After modifying the configuration, restart the server for changes to take effect:
```sh
neuronum stop-server
neuronum start-server
```

------------------


### **Neuronum Client API**
**Manage and call your Agent with ["kybercell" (official Neuronum Client)](https://neuronum.net/kybercell) or build your own custom Client using the Neuronum Client API**

**Python API**
```python
import asyncio
from neuronum import Cell

async def main():

    async with Cell() as cell:

        # ============================================
        # Target Cell ID
        # ============================================
        cell_id = "id::cell"

        # ============================================
        # Core Methods
        # ============================================
        # cell.activate_tx(cell_id, data)  - Send request and wait for response
        # cell.stream(cell_id, data)       - Send request via WebSocket (no response)
        # cell.sync()                      - Receive incoming requests
        # cell.tx_response(transmitter_id, data, public_key)  - Send response to a request

        # ============================================
        # Example 1: Send a prompt to your Agent
        # ============================================
        # The agent will answer questions using its knowledge base
        # and can execute tools conversationally when needed
        prompt_data = {
            "type": "prompt",
            "prompt": "Explain what a black hole is in one sentence"
        }
        tx_response = await cell.activate_tx(cell_id, prompt_data)
        print(tx_response)

        # ============================================
        # Example 2: Action Approval Flow
        # ============================================
        # When the agent suggests a tool action, it returns an action_id
        # The client can then approve or decline the action

        # Approve a pending action
        approve_data = {
            "type": "approve",
            "action_id": 123  # ID returned from prompt response
        }
        tx_response = await cell.activate_tx(cell_id, approve_data)
        print(tx_response)

        # Decline a pending action
        decline_data = {
            "type": "decline",
            "action_id": 123
        }
        tx_response = await cell.activate_tx(cell_id, decline_data)
        print(tx_response)

        # ============================================
        # Example 3: Sitemap Management
        # ============================================
        # Note: Sitemap entries are auto-indexed from templates on startup.
        # Use these endpoints to manage existing entries.

        # Update existing sitemap entry
        update_sitemap_data = {
            "type": "update_sitemap",
            "sitemap_id": "abc123...",  # SHA256 hash ID from previous add
            "file_content": "Updated pricing page content."
        }
        tx_response = await cell.activate_tx(cell_id, update_sitemap_data)

        # Fetch all sitemap entries
        get_sitemap_data = {"type": "get_sitemap"}
        sitemap_list = await cell.activate_tx(cell_id, get_sitemap_data)
        print(sitemap_list)
        # Returns: [{"sitemap_id": "...", "file_name": "...", "file_content": "..."}, ...]

        # Delete a sitemap entry
        delete_sitemap_data = {
            "type": "delete_sitemap",
            "sitemap_id": "abc123..."
        }
        tx_response = await cell.activate_tx(cell_id, delete_sitemap_data)

        # ============================================
        # Example 4: Index (Welcome Page)
        # ============================================

        # Get the index/welcome page
        get_index_data = {"type": "get_index"}
        index = await cell.activate_tx(cell_id, get_index_data)
        print(index)

        # Update the index message
        update_index_data = {
            "type": "update_index",
            "index": "Welcome! How can I help you today?"
        }
        tx_response = await cell.activate_tx(cell_id, update_index_data)

        # ============================================
        # Example 5: Tool Management
        # ============================================

        # List all available tools on Neuronum network
        available_tools = await cell.list_tools()
        print(available_tools)
        # Returns list of tools with metadata: [{"tool_id": "...", "name": "...", "description": "..."}, ...]

        # Get all installed tools on your agent
        get_tools_data = {"type": "get_tools"}
        tools_info = await cell.activate_tx(cell_id, get_tools_data)
        print(tools_info)
        # Returns: {"tools": {"tool_id": {config_data}, ...}}

        # Install a tool (requires tool to be published)
        # Use stream() instead of activate_tx() to listen for agent restart
        install_tool_data = {
            "type": "install_tool",
            "tool_id": "019ac60e-cccc-7af5-b087-f6fcf1ba1299",
            "variables": {"API_TOKEN": "your-token"}  # Optional: tool variables
        }
        await cell.stream(cell_id, install_tool_data)
        # Agent will restart and send "ping" when ready

        # Delete a tool
        delete_tool_data = {
            "type": "delete_tool",
            "tool_id": "019ac60e-cccc-7af5-b087-f6fcf1ba1299"
        }
        await cell.stream(cell_id, delete_tool_data)
        # Agent will restart after deletion

        # ============================================
        # Example 6: Actions Audit Log
        # ============================================

        # Get all actions (audit log)
        get_actions_data = {"type": "get_actions"}
        actions = await cell.activate_tx(cell_id, get_actions_data)
        print(actions)
        # Returns list of actions with status, tool info, timestamps, etc.

        # ============================================
        # Example 7: Agent Status
        # ============================================

        # Check if agent is running
        status_data = {"type": "get_agent_status"}
        status = await cell.activate_tx(cell_id, status_data)
        print(status)  # Returns: {"json": "running"}

        # ============================================
        # Example 8: Receiving Requests (Server-side)
        # ============================================

        # Listen for incoming requests using sync()
        async for transmitter in cell.sync():
            data = transmitter.get("data", {})
            message_type = data.get("type")

            # Send encrypted response back to the client
            await cell.tx_response(
                transmitter_id=transmitter.get("transmitter_id"),
                data={"json": "Response message"},
                client_public_key_str=data.get("public_key", "")
            )

if __name__ == '__main__':
    asyncio.run(main())
```

----------------------

### **Neuronum Tools CLI**
Neuronum Tools are MCP-compliant (Model Context Protocol) plugins that can be installed on the Neuronum Server and extend your Agent's functionality, enabling it to interact with external data sources and your system.

> **Tools Note:** Tools are not stored encrypted on neuronum.net. **Do not include credentials, API keys, secure tokens, passwords, or any sensitive data directly in your tool code.** Use environment variables or the `variables` configuration field (when available) to handle sensitive information securely. 

### **Initialize a Tool** 
```sh
neuronum init-tool
```
You will be prompted to enter a tool name and description (e.g., "Test Tool" and "A simple test tool"). This will create a new folder named using the format: `Tool Name_ToolID` (e.g., `Test Tool_019ac60e-cccc-7af5-b087-f6fcf1ba1299`)

This folder will contain 2 files:
1. **tool.config** - Configuration and metadata for your tool
2. **tool.py** - Your Tool/MCP server implementation

**Example tool.config:**
```config
{
  "tool_meta": {
    "tool_id": "019ac60e-cccc-7af5-b087-f6fcf1ba1299",
    "version": "1.0.0",
    "name": "Test Tool",
    "description": "A simple test tool",
    "audience": "private",
    "auto_approve": false,
    "logo": "https://neuronum.net/static/logo_new.png"
  },
  "legals": {
    "terms": "https://url_to_your/terms",
    "privacy_policy": "https://url_to_your/privacy_policy"
  },
  "requirements": [],
  "variables": []
}
```

**Example tool.py:**
```python
from mcp.server.fastmcp import FastMCP

# Create server instance
mcp = FastMCP("simple-example")

@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message"""
    return f"Echo: {message}"

if __name__ == "__main__":
    mcp.run()
```

### **Tool Configuration Fields**

**audience**
- Controls who can install and use your tool
- Options:
  - `"private"` - Only you can use this tool
  - `"public"` - Anyone on the Neuronum network can install this tool
  - `"id::cell"` - Share with specific cells (comma-separated list)

Examples:
```json
"audience": "private"
```
```json
"audience": "public"
```
```json
"audience": "acme::cell, community::cell, business::cell"
```

**auto_approve**
- Controls whether tool execution requires operator approval
- Options:
  - `false` (default) - The agent proposes the tool action and waits for the operator to approve or decline before executing
  - `true` - The tool executes immediately without requiring operator approval (useful for read-only tools like search or information lookups)

Examples:
```json
"auto_approve": false
```
```json
"auto_approve": true
```

**page (tool return value)**
- Tools can optionally return a `"page"` key in their result to specify which HTML template the server should render and serve to the client
- The returned data from the tool is passed into the Jinja2 template, so all keys in the tool's return dict are available as template variables
- If no `"page"` key is returned, the server defaults to serving `index.html`

Example tool returning a page with dynamic data:
```python
@mcp.tool()
def view_orders(status: str = "pending", operator: str = None) -> dict:
    """View orders filtered by status"""
    orders = [{"id": 1, "item": "Laptop", "status": "pending"},
              {"id": 2, "item": "Monitor", "status": "pending"}]
    return {
        "success": True,
        "page": "orders.html",
        "total_orders": len(orders),
        "orders": orders
    }
```

Example Jinja2 template (`templates/orders.html`):
```html
<h1>Orders ({{ total_orders }})</h1>
{% for order in orders %}
<div>
  <p>#{{ order.id }} - {{ order.item }} ({{ order.status }})</p>
</div>
{% endfor %}
```

**requirements**
- List of Python packages your tool needs
- Automatically installed by the Neuronum Server when the tool is added
- Use the same format as pip requirements (e.g., `"requests"`, `"pandas>=2.0.0"`)

Example:
```json
"requirements": [
  "requests",
  "pandas>=2.0.0",
  "openai==1.12.0"
]
```

**variables**
- List of variable names that users need to provide when installing your tool
- When installing the tool, users are prompted to manually set each variable one by one
- Values are sent encrypted to the server and automatically placed into your tool.py code
- **Important:** You don't need to add lines like `API_TOKEN = "value"` to your tool.py - the server automatically sets these variables based on user inputs

Example in tool.config:
```json
"variables": [
  "API_TOKEN",
  "DB_PASSWORD",
  "SERVICE_URL"
]
```

**How to use variables in your tool.py:**

❌ **Wrong - Don't hardcode sensitive values:**
```python
from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP("api-tool")

# DON'T DO THIS - Never hardcode credentials!
API_TOKEN = "sk-1234567890abcdef"  # This will be exposed in your tool code!

@mcp.tool()
def call_api(endpoint: str) -> str:
    """Call external API"""
    response = requests.get(f"https://api.example.com/{endpoint}",
                           headers={"Authorization": f"Bearer {API_TOKEN}"})
    return response.text
```

✅ **Correct - Use variables (server auto-injects values):**

First, declare the variable in your tool.config:
```json
{
  ...
  "requirements": ["requests"],
  "variables": ["API_TOKEN"]
}
```

Then use it in your tool.py without defining it:
```python
from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP("api-tool")

# The server automatically sets API_TOKEN based on user input during installation
# You just use it directly - no need to define it!

@mcp.tool()
def call_api(endpoint: str) -> str:
    """Call external API"""
    response = requests.get(f"https://api.example.com/{endpoint}",
                           headers={"Authorization": f"Bearer {API_TOKEN}"})
    return response.text
```

> **Note:** This feature is only available when using the official Neuronum client.

### **Update a Tool**
After modifying your `tool.config` or `tool.py` files, submit the updates using:
```sh
neuronum update-tool
```

### **Delete a Tool**
```sh
neuronum delete-tool
```


