#!/usr/bin/env python3
"""
Test HTTP client for MCP Build Service
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-http-test-client")


class MCPHTTPClient:
    """Client for communicating with MCP server via HTTP SSE"""

    def __init__(self, base_url: str, session_key: str):
        """
        Initialize MCP HTTP client

        Args:
            base_url: Base URL of the MCP service (e.g., "http://100.4.213.68:3344")
            session_key: Session key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.session_key = session_key
        self.session_id: Optional[str] = None
        self.request_id = 0
        self._initialized = False
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        """Connect to the MCP service and get session endpoint"""
        logger.info(f"Connecting to MCP service at {self.base_url}")

        self.http_session = aiohttp.ClientSession()

        # Connect to SSE endpoint to get session
        url = f"{self.base_url}/sse?key={self.session_key}"
        logger.info(f"Requesting SSE endpoint: {url}")

        async with self.http_session.get(url) as response:
            if response.status != 200:
                raise RuntimeError(f"Failed to connect: HTTP {response.status}")

            # Read the first SSE event to get the session endpoint
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    endpoint = line_str[6:]  # Remove "data: " prefix
                    # Extract session ID from endpoint like "/messages?session_id=xxx"
                    if '?session_id=' in endpoint:
                        self.session_id = endpoint.split('?session_id=')[1]
                        logger.info(f"Got session ID: {self.session_id}")
                        break

        if not self.session_id:
            raise RuntimeError("Failed to get session ID from SSE endpoint")

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the server

        Args:
            method: JSON-RPC method name
            params: Parameters for the method

        Returns:
            JSON-RPC response
        """
        if not self.http_session or not self.session_id:
            raise RuntimeError("Not connected. Call connect() first.")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        logger.info(f"Sending request: {method}")
        logger.debug(f"Request body: {json.dumps(request, indent=2)}")

        url = f"{self.base_url}/messages?session_id={self.session_id}"
        headers = {
            "Authorization": f"Bearer {self.session_key}",
            "Content-Type": "application/json"
        }

        async with self.http_session.post(url, json=request, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"Request failed: HTTP {response.status} - {text}")

            response_data = await response.json()
            logger.debug(f"Response: {json.dumps(response_data, indent=2)}")

            if "error" in response_data:
                raise RuntimeError(f"JSON-RPC error: {response_data['error']}")

            return response_data

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
                    "name": "mcp-http-test-client",
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
        if not self.http_session or not self.session_id:
            raise RuntimeError("Not connected. Call connect() first.")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        logger.debug(f"Sending notification: {method}")

        url = f"{self.base_url}/messages?session_id={self.session_id}"
        headers = {
            "Authorization": f"Bearer {self.session_key}",
            "Content-Type": "application/json"
        }

        async with self.http_session.post(url, json=notification, headers=headers) as response:
            if response.status != 200:
                text = await response.text()
                logger.warning(f"Notification failed: HTTP {response.status} - {text}")

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

    async def close(self) -> None:
        """Close the HTTP session"""
        if self.http_session:
            await self.http_session.close()
            logger.info("HTTP session closed")


async def main():
    """Test the MCP HTTP client"""
    # Configuration
    base_url = "http://100.4.213.68:3344"
    session_key = "1234321"

    client = MCPHTTPClient(base_url, session_key)

    try:
        # Connect and initialize
        await client.connect()
        init_result = await client.initialize()

        print("\n=== Server Info ===")
        print(f"Server: {init_result.get('serverInfo', {}).get('name', 'unknown')}")
        print(f"Version: {init_result.get('serverInfo', {}).get('version', 'unknown')}")
        print(f"Protocol: {init_result.get('protocolVersion', 'unknown')}")

        # List available tools
        print("\n=== Available Tools ===")
        tools = await client.list_tools()
        for tool in tools:
            print(f"\n{tool['name']}")
            print(f"  Description: {tool.get('description', 'N/A')}")
            if 'inputSchema' in tool:
                props = tool['inputSchema'].get('properties', {})
                if props:
                    print(f"  Parameters: {', '.join(props.keys())}")

        # Test: List repositories
        print("\n=== Testing: list ===")
        result = await client.call_tool("list")
        for content in result:
            if content.get('type') == 'text':
                print(content.get('text', ''))

        # Test: Check environment
        print("\n=== Testing: env ===")
        result = await client.call_tool("env")
        for content in result:
            if content.get('type') == 'text':
                print(content.get('text', ''))

        print("\n=== Tests completed successfully! ===")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1
    finally:
        await client.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
