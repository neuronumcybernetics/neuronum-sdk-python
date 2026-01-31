"""MCP Client Registry for managing MCP servers as subprocesses."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class MCPServerClient:
    """Client for communicating with a single MCP server subprocess."""

    def __init__(self, server_name: str, server_path: str):
        self.server_name = server_name
        self.server_path = server_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._logger = logging.getLogger(f"MCP.{server_name}")

    async def start(self):
        """Launch the MCP server as a subprocess."""
        if self.process is not None:
            self._logger.warning(f"Server {self.server_name} already running")
            return

        self._logger.info(f"Starting MCP server: {self.server_name}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable,
                self.server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Initialize the server
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "neuronum-server",
                    "version": "1.0.0"
                }
            })

            self._logger.info(f"Server {self.server_name} started successfully")

        except Exception as e:
            self._logger.error(f"Failed to start server {self.server_name}: {e}")
            raise

    async def stop(self):
        if self.process is None:
            return

        self._logger.info(f"Stopping server {self.server_name}")

        try:
            self.process.terminate()
            await self.process.wait()
        except Exception as e:
            self._logger.error(f"Error stopping server {self.server_name}: {e}")
        finally:
            self.process = None

    async def _send_request(self, method: str, params: dict = None) -> dict:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError(f"Server {self.server_name} not started")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        try:
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json.encode())
            await self.process.stdin.drain()

            response_line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=30.0
            )

            if not response_line:
                raise RuntimeError(f"Server {self.server_name} closed connection")

            response = json.loads(response_line.decode())

            if "error" in response:
                error = response["error"]
                raise RuntimeError(f"JSON-RPC error: {error.get('message', error)}")

            return response

        except asyncio.TimeoutError:
            self._logger.error(f"Request to {self.server_name} timed out: {method}")
            raise
        except Exception as e:
            self._logger.error(f"Error communicating with {self.server_name}: {e}")
            raise

    async def list_tools(self) -> List[Dict[str, Any]]:
        response = await self._send_request("tools/list")
        tools = response.get("result", {}).get("tools", [])

        for tool in tools:
            tool["server"] = self.server_name

        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], operator: str = None) -> Any:
        # Inject operator into arguments so tools can access it securely
        injected_arguments = {**arguments, "operator": operator} if operator else arguments
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": injected_arguments
        })

        result = response.get("result", {})

        if result.get("isError", False):
            content = result.get("content", [])
            error_text = content[0].get("text", "Unknown error") if content else "Unknown error"
            raise RuntimeError(f"Tool error: {error_text}")

        return result


class MCPRegistry:

    def __init__(self):
        self.servers: Dict[str, MCPServerClient] = {}
        self._initialized = False
        self._logger = logging.getLogger("MCPRegistry")

    async def initialize(self, cell=None, logger=None):
        if self._initialized:
            self._logger.warning("MCP Registry already initialized")
            return

        if logger:
            self._logger = logger

        self._logger.info("Initializing Tool Registry...")
        self._logger.info("Auto-discovering Tools...")

        server_files = self._discover_server_files()

        if not server_files:
            self._logger.warning("No Tools found in tools/ directory")
            return

        self._logger.info(f"Found {len(server_files)} server file(s)")

        for server_name, server_path in server_files.items():
            try:
                client = MCPServerClient(server_name, server_path)
                self.servers[server_name] = client
                self._logger.info(f"Registered server: {server_name}")
            except Exception as e:
                self._logger.error(f"Failed to register {server_name}: {e}")

        for server_name, client in self.servers.items():
            try:
                await client.start()
            except Exception as e:
                self._logger.error(f"Failed to start {server_name}: {e}")

        self._initialized = True
        self._logger.info(f"MCP Registry initialized with {len(self.servers)} servers")

    def _discover_server_files(self) -> Dict[str, str]:
        server_files = {}
        tools_dir = Path(__file__).parent / "tools"

        if not tools_dir.exists():
            tools_dir.mkdir(parents=True, exist_ok=True)
            self._logger.info(f"Created tools directory: {tools_dir}")
            return server_files

        for file_path in tools_dir.glob("*.py"):
            if file_path.stem in ["template_server", "simple_mcp_example"]:
                self._logger.debug(f"Skipping template/example: {file_path.stem}")
                continue

            server_name = file_path.stem.replace("_server", "")
            server_files[server_name] = str(file_path.resolve())
            self._logger.debug(f"Discovered: {server_name} -> {file_path}")

        return server_files

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        tools_dir = Path(__file__).parent / "tools"

        for server_name, client in self.servers.items():
            try:
                tools = await client.list_tools()

                # Try to enrich with .config data
                config_path = tools_dir / f"{server_name}.config"
                if config_path.exists():
                    try:
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                        tool_meta = config.get("tool_meta", {})

                        # Enrich tools with package-level metadata from config
                        for tool in tools:
                            tool["tool_id"] = tool_meta.get("tool_id", server_name)
                            tool["package_name"] = tool_meta.get("name")
                            tool["package_description"] = tool_meta.get("description")
                            tool["auto_approve"] = tool_meta.get("auto_approve", False)
                    except Exception as e:
                        self._logger.warning(f"Could not load config for {server_name}: {e}")

                all_tools.extend(tools)
            except Exception as e:
                self._logger.error(f"Error getting tools from {server_name}: {e}")

        return all_tools

    async def find_tool(self, tool_name: str) -> Optional[MCPServerClient]:
        for server_name, client in self.servers.items():
            try:
                tools = await client.list_tools()
                if any(tool["name"] == tool_name for tool in tools):
                    return client
            except Exception as e:
                self._logger.error(f"Error checking {server_name} for tool {tool_name}: {e}")

        return None

    async def call_tool(self, tool_name: str, parameters: Dict[str, Any], operator: str = None) -> Any:
        client = await self.find_tool(tool_name)

        if client is None:
            available = [tool["name"] for tool in await self.get_all_tools()]
            raise ValueError(
                f"Tool '{tool_name}' not found. "
                f"Available tools: {', '.join(available)}"
            )

        self._logger.debug(f"Calling {tool_name} from {client.server_name} server (operator: {operator})")

        return await client.call_tool(tool_name, parameters, operator)

    async def get_server_info(self) -> Dict[str, Any]:
        info = {
            "total_servers": len(self.servers),
            "servers": {}
        }

        for server_name, client in self.servers.items():
            try:
                tools = await client.list_tools()
                info["servers"][server_name] = {
                    "tool_count": len(tools),
                    "tools": [tool["name"] for tool in tools],
                    "running": client.process is not None
                }
            except Exception as e:
                info["servers"][server_name] = {
                    "error": str(e),
                    "running": False
                }

        return info

    async def shutdown(self):
        self._logger.info("Shutting down all MCP servers...")

        for server_name, client in self.servers.items():
            try:
                await client.stop()
            except Exception as e:
                self._logger.error(f"Error stopping {server_name}: {e}")

        self.servers.clear()
        self._initialized = False
        self._logger.info("All servers shut down")


_registry: Optional[MCPRegistry] = None


async def get_registry(cell=None, logger=None) -> MCPRegistry:
    global _registry

    if _registry is None:
        _registry = MCPRegistry()
        await _registry.initialize(cell, logger)

    return _registry


async def initialize_registry(cell=None, logger=None) -> MCPRegistry:
    return await get_registry(cell, logger)
