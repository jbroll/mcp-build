#!/usr/bin/env python3
"""
Debug script to test the MCP protocol communication
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    """Test basic MCP communication"""
    import subprocess
    import os

    # Start server in the current directory
    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "mcp_build.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd()
    )

    print("Server started...")

    # Send initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "debug-client",
                "version": "1.0.0"
            }
        }
    }

    print(f"\nSending: {json.dumps(init_req)}")
    proc.stdin.write((json.dumps(init_req) + "\n").encode())
    await proc.stdin.drain()

    # Read response
    response = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
    print(f"Response: {response.decode()}")

    # Send initialized notification
    notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    print(f"\nSending: {json.dumps(notif)}")
    proc.stdin.write((json.dumps(notif) + "\n").encode())
    await proc.stdin.drain()

    # Wait a bit for notification to be processed
    await asyncio.sleep(0.5)

    # Send tools/list
    tools_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    print(f"\nSending: {json.dumps(tools_req)}")
    proc.stdin.write((json.dumps(tools_req) + "\n").encode())
    await proc.stdin.drain()

    # Read response
    response = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
    print(f"Response: {response.decode()}")

    # Clean up
    proc.terminate()
    await proc.wait()

    # Print any stderr
    stderr = await proc.stderr.read()
    if stderr:
        print(f"\nServer stderr:\n{stderr.decode()}")

if __name__ == "__main__":
    asyncio.run(main())
