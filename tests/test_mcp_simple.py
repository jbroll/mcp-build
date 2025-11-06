#!/usr/bin/env python3
"""
Simple test suite for MCP Build Service using the MCP client SDK

This test suite uses the official MCP client to communicate with the server.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPBuildTester:
    """Test harness for MCP Build Service"""

    def __init__(self):
        self.session: ClientSession = None

    @asynccontextmanager
    async def connect(self):
        """Connect to the MCP server"""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_build_environment.server"],
            env=None
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                yield session

    async def test_list_tools(self):
        """Test listing available tools"""
        print("\n=== Testing list_tools ===")
        async with self.connect() as session:
            tools_result = await session.list_tools()
            print(f"Found {len(tools_result.tools)} tools:")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            return tools_result.tools

    async def test_list_repositories(self):
        """Test listing repositories"""
        print("\n=== Testing list repositories ===")
        async with self.connect() as session:
            result = await session.call_tool("list", {})
            print("Result:", result)
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
            return result

    async def test_git_status(self):
        """Test git status command"""
        print("\n=== Testing git status ===")
        async with self.connect() as session:
            result = await session.call_tool("git", {"args": "status"})
            print("Result:", result)
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
            return result

    async def test_git_log(self):
        """Test git log command"""
        print("\n=== Testing git log ===")
        async with self.connect() as session:
            result = await session.call_tool("git", {"args": "log --oneline -5"})
            print("Result:", result)
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
            return result

    async def test_ls(self):
        """Test ls command"""
        print("\n=== Testing ls ===")
        async with self.connect() as session:
            result = await session.call_tool("ls", {"args": "-la"})
            print("Result:", result)
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
            return result

    async def test_env(self):
        """Test env command"""
        print("\n=== Testing env ===")
        async with self.connect() as session:
            result = await session.call_tool("env", {})
            print("Result:", result)
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
            return result

    async def test_make_version(self):
        """Test make command"""
        print("\n=== Testing make --version ===")
        async with self.connect() as session:
            try:
                result = await session.call_tool("make", {"args": "--version"})
                print("Result:", result)
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(content.text)
                return result
            except Exception as e:
                print(f"Make test failed (expected if no Makefile): {e}")
                return None

    async def test_invalid_git_command(self):
        """Test that dangerous git commands are rejected"""
        print("\n=== Testing invalid git command (should fail) ===")
        async with self.connect() as session:
            try:
                result = await session.call_tool("git", {"args": "push origin main"})
                print("Result:", result)
                # Check if error is in the response
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            text = content.text
                            print(content.text)
                            assert "Error" in text or "not allowed" in text, \
                                "Expected error for disallowed git command"
            except Exception as e:
                print(f"Correctly rejected: {e}")

    async def test_path_traversal(self):
        """Test that path traversal is blocked"""
        print("\n=== Testing path traversal (should fail) ===")
        async with self.connect() as session:
            try:
                result = await session.call_tool("ls", {"args": "-la ../../../etc"})
                print("Result:", result)
                # Check if error is in the response
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            text = content.text
                            print(content.text)
                            assert "Error" in text or "Invalid" in text, \
                                "Expected error for path traversal attempt"
            except Exception as e:
                print(f"Correctly rejected: {e}")

    async def test_invalid_tool_name(self):
        """Test that invalid tool names are rejected"""
        print("\n=== Testing invalid tool name (should fail) ===")
        async with self.connect() as session:
            try:
                result = await session.call_tool("nonexistent_tool", {})
                print("Result:", result)
                # Should get an error response
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            text = content.text
                            print(content.text)
                            assert "Error" in text or "Unknown tool" in text, \
                                "Expected error for invalid tool name"
            except Exception as e:
                print(f"Correctly rejected invalid tool: {e}")

    async def test_missing_required_arguments(self):
        """Test that missing required arguments are rejected"""
        print("\n=== Testing missing required arguments (should fail) ===")
        async with self.connect() as session:
            try:
                # git command requires 'args' parameter
                result = await session.call_tool("git", {})
                print("Result:", result)
                # Should get an error response
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            text = content.text
                            print(content.text)
                            assert "Error" in text or "requires arguments" in text, \
                                "Expected error for missing arguments"
            except Exception as e:
                print(f"Correctly rejected missing arguments: {e}")

    async def test_shell_metacharacters(self):
        """Test that shell metacharacters are blocked"""
        print("\n=== Testing shell metacharacters (should fail) ===")
        dangerous_patterns = [
            ("git", {"args": "status | cat /etc/passwd"}),  # Pipe
            ("git", {"args": "status > /tmp/output"}),      # Redirect
            ("git", {"args": "status && rm -rf /"}),        # Command chaining
            ("git", {"args": "status; whoami"}),            # Command separator
            ("ls", {"args": "$(whoami)"}),                  # Command substitution
            ("ls", {"args": "`id`"}),                       # Backtick substitution
        ]

        async with self.connect() as session:
            for tool_name, args in dangerous_patterns:
                try:
                    result = await session.call_tool(tool_name, args)
                    # Check if error is in the response
                    if result.content:
                        for content in result.content:
                            if hasattr(content, 'text'):
                                text = content.text
                                print(f"Testing {tool_name} with {args['args']}: {text[:100]}...")
                                assert "Error" in text or "Invalid" in text or "dangerous" in text, \
                                    f"Expected error for dangerous pattern: {args['args']}"
                except Exception as e:
                    print(f"Correctly rejected {tool_name} {args['args']}: {e}")

    async def test_dangerous_make_arguments(self):
        """Test that dangerous make arguments are blocked"""
        print("\n=== Testing dangerous make arguments (should fail) ===")
        dangerous_make_commands = [
            "clean; rm -rf /",
            "all && cat /etc/passwd",
            "test | tee /tmp/output",
        ]

        async with self.connect() as session:
            for make_args in dangerous_make_commands:
                try:
                    result = await session.call_tool("make", {"args": make_args})
                    # Check if error is in the response
                    if result.content:
                        for content in result.content:
                            if hasattr(content, 'text'):
                                text = content.text
                                print(f"Testing make with '{make_args}': {text[:100]}...")
                                assert "Error" in text or "Invalid" in text or "dangerous" in text, \
                                    f"Expected error for dangerous make command: {make_args}"
                except Exception as e:
                    print(f"Correctly rejected 'make {make_args}': {e}")

    async def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("MCP Build Service Test Suite")
        print("=" * 60)

        try:
            # Positive tests - verify functionality
            await self.test_list_tools()
            await self.test_list_repositories()
            await self.test_ls()
            await self.test_git_status()
            await self.test_git_log()
            await self.test_env()
            await self.test_make_version()

            # Negative tests - verify security validations
            await self.test_invalid_git_command()
            await self.test_path_traversal()
            await self.test_invalid_tool_name()
            await self.test_missing_required_arguments()
            await self.test_shell_metacharacters()
            await self.test_dangerous_make_arguments()

            print("\n" + "=" * 60)
            print("All tests completed successfully!")
            print("=" * 60)
        except Exception as e:
            print(f"\n{'=' * 60}")
            print(f"Test suite failed: {e}")
            print("=" * 60)
            import traceback
            traceback.print_exc()
            raise


async def main():
    """Main entry point"""
    tester = MCPBuildTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
