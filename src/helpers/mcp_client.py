"""
MCP Client for testing local MCP server via stdio

This client communicates with an MCP server using JSON-RPC 2.0 over stdio.
It handles the full MCP protocol including initialization and tool calls.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
import sys

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mcp-test-client")


class MCPClient:
    """Client for communicating with MCP server via stdio"""

    def __init__(self, server_command: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        """
        Initialize MCP client

        Args:
            server_command: Command to start the server (e.g., ["python", "-m", "mcp_build_environment.server"])
            env: Environment variables to pass to the server
            cwd: Working directory for the server process
        """
        self.server_command = server_command
        self.env = env or {}
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self._initialized = False

    async def start(self) -> None:
        """Start the MCP server subprocess"""
        logger.info(f"Starting MCP server: {' '.join(self.server_command)}")
        if self.cwd:
            logger.info(f"Working directory: {self.cwd}")

        # Merge current env with custom env
        full_env = os.environ.copy()
        full_env |= self.env

        self.process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=self.cwd
        )

        logger.info("MCP server process started")

    async def stop(self) -> None:
        """Stop the MCP server subprocess"""
        if self.process:
            logger.info("Stopping MCP server")
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Server didn't terminate gracefully, killing")
                self.process.kill()
                await self.process.wait()

            # Read any remaining stderr
            if self.process.stderr:
                stderr = await self.process.stderr.read()
                if stderr:
                    logger.debug(f"Server stderr: {stderr.decode('utf-8', errors='replace')}")

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the server

        Args:
            method: JSON-RPC method name
            params: Parameters for the method

        Returns:
            JSON-RPC response
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("Server not started")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        request_str = json.dumps(request) + "\n"
        logger.debug(f"Sending request: {request_str.strip()}")

        self.process.stdin.write(request_str.encode('utf-8'))
        await self.process.stdin.drain()

        # Read response
        response_line = await self.process.stdout.readline()
        response_str = response_line.decode('utf-8').strip()
        logger.debug(f"Received response: {response_str}")

        if not response_str:
            # Check if process died
            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                raise RuntimeError(f"Server process died: {stderr.decode('utf-8', errors='replace')}")
            raise RuntimeError("Empty response from server")

        response = json.loads(response_str)

        if "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']}")

        return response

    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize the MCP session

        Returns:
            Server capabilities and metadata
        """
        logger.info("Initializing MCP session")
        response = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "mcp-test-client",
                    "version": "1.0.0"
                }
            }
        )

        self._initialized = True
        logger.info("MCP session initialized")

        # Send initialized notification
        await self.send_notification("notifications/initialized")

        return response.get("result", {})

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Send a JSON-RPC notification (no response expected)

        Args:
            method: Notification method name
            params: Parameters for the notification
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("Server not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        notification_str = json.dumps(notification) + "\n"
        logger.debug(f"Sending notification: {notification_str.strip()}")

        self.process.stdin.write(notification_str.encode('utf-8'))
        await self.process.stdin.drain()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all available tools

        Returns:
            List of tool definitions
        """
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        response = await self.send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Call a tool

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool response content
        """
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        response = await self.send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {}
            }
        )

        return response.get("result", {}).get("content", [])

    async def __aenter__(self):
        """Context manager entry"""
        await self.start()
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.stop()


async def test_client_example():
    """Example usage of the MCP client"""
    # Set environment for testing
    test_env = {}

    # Create and use client
    async with MCPClient(
        ["python", "-m", "mcp_build_environment.server"],
        env=test_env
    ) as client:
        # List available tools
        tools = await client.list_tools()
        print("Available tools:")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description']}")

        # Call a tool
        result = await client.call_tool("list")
        print("\nRepository list:")
        for content in result:
            print(content.get("text", ""))


if __name__ == "__main__":
    asyncio.run(test_client_example())
