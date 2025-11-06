#!/usr/bin/env python3
"""
Manual test script for debugging the MCP Build Service locally

This script starts the MCP server and provides an interactive way to test tools.
You can also run it in the background and use it for debugging.

Usage:
    # Interactive mode - test all tools
    python tests/manual_test.py

    # Test specific tool
    python tests/manual_test.py --tool list
    python tests/manual_test.py --tool git --args "status"
    python tests/manual_test.py --tool make --args "all"

    # Run with custom repo directory
    python tests/manual_test.py --repos-dir /path/to/repos
"""

import asyncio
import argparse
import sys
from pathlib import Path
import os

# Add parent directory to path to import mcp_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.mcp_client import MCPClient


async def test_all_tools(client: MCPClient):
    """Run tests for all tools"""
    print("\n" + "=" * 70)
    print("TESTING ALL MCP TOOLS")
    print("=" * 70)

    # Test 1: List tools
    print("\n[1/6] Listing available tools...")
    try:
        tools = await client.list_tools()
        print(f"✓ Found {len(tools)} tools:")
        for tool in tools:
            print(f"  • {tool['name']}: {tool['description'][:60]}...")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 2: List repositories
    print("\n[2/6] Testing 'list' tool (list repositories)...")
    try:
        result = await client.call_tool("list")
        print("✓ Response:")
        print(result[0]["text"])
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 3: Git status
    print("\n[3/6] Testing 'git' tool (git status)...")
    try:
        result = await client.call_tool("git", {"args": "status"})
        print("✓ Response:")
        print(result[0]["text"])
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 4: List files
    print("\n[4/6] Testing 'ls' tool (list files)...")
    try:
        result = await client.call_tool("ls", {"args": "-la"})
        print("✓ Response:")
        print(result[0]["text"])
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 5: Make (if Makefile exists)
    print("\n[5/6] Testing 'make' tool...")
    try:
        result = await client.call_tool("make", {"args": "--version"})
        print("✓ Response:")
        print(result[0]["text"])
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 6: Environment info
    print("\n[6/6] Testing 'env' tool (environment info)...")
    try:
        result = await client.call_tool("env")
        print("✓ Response:")
        # Only show first 500 chars to keep output manageable
        text = result[0]["text"]
        if len(text) > 500:
            print(text[:500] + "\n... (output truncated)")
        else:
            print(text)
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n" + "=" * 70)
    print("TESTING COMPLETE")
    print("=" * 70 + "\n")


async def test_specific_tool(client: MCPClient, tool_name: str, args_dict: dict):
    """Test a specific tool"""
    print(f"\nTesting tool: {tool_name}")
    print(f"Arguments: {args_dict}")
    print("-" * 70)

    try:
        result = await client.call_tool(tool_name, args_dict)
        print("✓ Success! Response:")
        print(result[0]["text"])
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


async def interactive_mode(repos_dir: str):
    """Interactive mode for testing"""
    print("\n" + "=" * 70)
    print("MCP BUILD SERVICE - INTERACTIVE TEST MODE")
    print("=" * 70)
    print(f"Repository directory: {repos_dir}")
    print()

    env = {"MCP_BUILD_REPOS_DIR": repos_dir}

    async with MCPClient(
        ["python", "-m", "mcp_build_environment.server"],
        env=env
    ) as client:
        # Run all tool tests
        await test_all_tools(client)

        # Interactive loop
        print("\nEntering interactive mode. Type 'help' for commands, 'quit' to exit.")

        while True:
            try:
                command = input("\n> ").strip()

                if not command:
                    continue

                if command in ["quit", "exit", "q"]:
                    print("Exiting...")
                    break

                if command == "help":
                    print("""
Available commands:
  list                    - List repositories
  git <args>              - Run git command (e.g., 'git status')
  make <args>             - Run make command (e.g., 'make all')
  ls <args>               - List files (e.g., 'ls -la')
  env                     - Show environment info
  tools                   - List available tools
  test-all                - Run all test cases
  quit/exit/q             - Exit interactive mode

Examples:
  > git status
  > make clean all
  > ls -lh build/
  > git log --oneline -5
""")
                    continue

                if command == "tools":
                    tools = await client.list_tools()
                    print(f"\nAvailable tools ({len(tools)}):")
                    for tool in tools:
                        print(f"  • {tool['name']}")
                        print(f"    {tool['description']}")
                    continue

                if command == "test-all":
                    await test_all_tools(client)
                    continue

                # Parse command
                parts = command.split(maxsplit=1)
                tool_name = parts[0]
                tool_args = parts[1] if len(parts) > 1 else ""

                # Call tool
                args_dict = {"args": tool_args} if tool_args else {}
                result = await client.call_tool(tool_name, args_dict)

                print("\nResponse:")
                print(result[0]["text"])

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
            except Exception as e:
                print(f"\n✗ Error: {e}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Manual test script for MCP Build Service"
    )
    parser.add_argument(
        "--repos-dir",
        default=os.getcwd(),
        help="Directory containing git repositories (default: current directory)"
    )
    parser.add_argument(
        "--tool",
        help="Test specific tool (e.g., 'list', 'git', 'make')"
    )
    parser.add_argument(
        "--args",
        default="",
        help="Arguments to pass to the tool"
    )
    parser.add_argument(
        "--repo",
        help="Specific repository to use"
    )

    args = parser.parse_args()

    if args.tool:
        # Test specific tool
        env = {"MCP_BUILD_REPOS_DIR": args.repos_dir}

        args_dict = {"args": args.args} if args.args else {}
        if args.repo:
            args_dict["repo"] = args.repo

        async with MCPClient(
            ["python", "-m", "mcp_build_environment.server"],
            env=env
        ) as client:
            await test_specific_tool(client, args.tool, args_dict)
    else:
        # Interactive mode
        await interactive_mode(args.repos_dir)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
