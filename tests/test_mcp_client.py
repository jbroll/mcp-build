#!/usr/bin/env python3
"""
Test suite for MCP Build Service

This test suite spawns the MCP server as a subprocess and communicates with it
over stdio using the MCP protocol to test all available tools.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import pytest


class MCPTestClient:
    """Test client for MCP protocol communication over stdio"""

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    async def start(self):
        """Start the MCP server as a subprocess"""
        # Start the server process
        self.process = subprocess.Popen(
            [sys.executable, "-m", "mcp_build_environment.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # Initialize the MCP session
        await self._send_initialize()

    async def stop(self):
        """Stop the MCP server"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request to the server"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        # Send request
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json)
        self.process.stdin.flush()

        # Read response
        response_line = self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("No response from server")

        response = json.loads(response_line)

        if "error" in response:
            raise RuntimeError(f"Server error: {response['error']}")

        return response.get("result", {})

    async def _send_initialize(self):
        """Send initialize request"""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        })

        # Send initialized notification
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self.process.stdin.write(json.dumps(notification) + "\n")
        self.process.stdin.flush()

        return result

    async def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return await self._send_request("tools/list")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool with given arguments"""
        return await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })


@pytest.fixture
async def mcp_client():
    """Fixture to create and manage an MCP test client"""
    client = MCPTestClient()
    await client.start()
    yield client
    await client.stop()


@pytest.mark.asyncio
async def test_server_initialization(mcp_client):
    """Test that the server initializes correctly"""
    # If we got here, initialization succeeded
    assert mcp_client.process is not None
    assert mcp_client.process.poll() is None  # Process is running


@pytest.mark.asyncio
async def test_list_tools(mcp_client):
    """Test listing available tools"""
    result = await mcp_client.list_tools()

    assert "tools" in result
    tools = result["tools"]
    assert isinstance(tools, list)

    # Check that expected tools are present
    tool_names = [tool["name"] for tool in tools]
    expected_tools = ["list", "make", "git", "ls", "env"]

    for expected_tool in expected_tools:
        assert expected_tool in tool_names, f"Tool '{expected_tool}' not found"

    # Check tool structure
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


@pytest.mark.asyncio
async def test_list_repositories(mcp_client):
    """Test listing repositories"""
    result = await mcp_client.call_tool("list", {})

    assert "content" in result
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) > 0

    # Check content structure
    text_content = content[0]
    assert text_content["type"] == "text"
    assert "text" in text_content

    print(f"Repositories found:\n{text_content['text']}")


@pytest.mark.asyncio
async def test_ls_command(mcp_client):
    """Test ls command"""
    result = await mcp_client.call_tool("ls", {"args": "-la"})

    assert "content" in result
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) > 0

    text_content = content[0]
    assert text_content["type"] == "text"
    assert "text" in text_content

    print(f"ls output:\n{text_content['text']}")


@pytest.mark.asyncio
async def test_git_status(mcp_client):
    """Test git status command"""
    result = await mcp_client.call_tool("git", {"args": "status"})

    assert "content" in result
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) > 0

    text_content = content[0]
    assert text_content["type"] == "text"
    assert "text" in text_content

    print(f"git status output:\n{text_content['text']}")


@pytest.mark.asyncio
async def test_git_log(mcp_client):
    """Test git log command"""
    result = await mcp_client.call_tool("git", {"args": "log --oneline -5"})

    assert "content" in result
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) > 0

    text_content = content[0]
    assert text_content["type"] == "text"
    assert "text" in text_content

    print(f"git log output:\n{text_content['text']}")


@pytest.mark.asyncio
async def test_env_command(mcp_client):
    """Test env command"""
    result = await mcp_client.call_tool("env", {})

    assert "content" in result
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) > 0

    text_content = content[0]
    assert text_content["type"] == "text"
    assert "text" in text_content

    print(f"env output:\n{text_content['text']}")


@pytest.mark.asyncio
async def test_invalid_git_command(mcp_client):
    """Test that invalid git commands are rejected"""
    try:
        result = await mcp_client.call_tool("git", {"args": "push"})
        # If we get here, check if there's an error in the content
        content = result["content"][0]["text"]
        assert "Error" in content or "not allowed" in content
    except RuntimeError as e:
        # Expected - command should be rejected
        assert "push" in str(e).lower() or "not allowed" in str(e).lower()


@pytest.mark.asyncio
async def test_make_command_in_repo_with_makefile(mcp_client):
    """Test make command (only runs if Makefile exists)"""
    # First, let's check what repos we have
    list_result = await mcp_client.call_tool("list", {})

    # Try to run make help or make without arguments
    try:
        result = await mcp_client.call_tool("make", {"args": "--version"})

        assert "content" in result
        content = result["content"]
        assert isinstance(content, list)

        text_content = content[0]
        assert text_content["type"] == "text"

        print(f"make output:\n{text_content['text']}")
    except RuntimeError as e:
        print(f"Make command failed (expected if no Makefile): {e}")


@pytest.mark.asyncio
async def test_argument_validation(mcp_client):
    """Test that dangerous arguments are rejected"""
    dangerous_commands = [
        ("git", {"args": "status; rm -rf /"}),
        ("ls", {"args": "-la ../../../etc"}),
        ("git", {"args": "status | cat"}),
    ]

    for tool_name, args in dangerous_commands:
        try:
            result = await mcp_client.call_tool(tool_name, args)
            # Check if error is in the response
            if "content" in result:
                text = result["content"][0]["text"]
                assert "Error" in text or "Invalid" in text
        except RuntimeError as e:
            # Expected - dangerous command should be rejected
            print(f"Correctly rejected dangerous command: {tool_name} {args}")


# Manual test runner for debugging
async def manual_test():
    """Manual test runner for interactive debugging"""
    print("Starting MCP server test...")

    client = MCPTestClient()
    try:
        print("Starting server...")
        await client.start()
        print("Server started successfully")

        print("\n--- Testing list_tools ---")
        tools = await client.list_tools()
        print(json.dumps(tools, indent=2))

        print("\n--- Testing list repositories ---")
        repos = await client.call_tool("list", {})
        print(json.dumps(repos, indent=2))

        print("\n--- Testing ls command ---")
        ls_result = await client.call_tool("ls", {"args": "-la"})
        print(json.dumps(ls_result, indent=2))

        print("\n--- Testing git status ---")
        git_result = await client.call_tool("git", {"args": "status"})
        print(json.dumps(git_result, indent=2))

        print("\n--- Testing env command ---")
        env_result = await client.call_tool("env", {})
        print(json.dumps(env_result, indent=2))

        print("\nAll tests passed!")

    except Exception as e:
        print(f"Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        print("\nStopping server...")
        await client.stop()
        print("Server stopped")


if __name__ == "__main__":
    # Run manual tests if executed directly
    asyncio.run(manual_test())
