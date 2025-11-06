#!/usr/bin/env python3
"""Quick test to debug specific issue"""

import asyncio
import sys
from pathlib import Path
import tempfile
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.mcp_client import MCPClient

async def main():
    """Test git invalid command"""
    # Create a test repo
    test_dir = Path(tempfile.gettempdir()) / "test-repo-debug"
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)

    test_dir.mkdir()
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=test_dir, check=True)

    test_file = test_dir / "test.txt"
    test_file.write_text("test")
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True)
    subprocess.run(["git", "commit", "-m", "test"], cwd=test_dir, check=True)

    # Test with MCP client
    async with MCPClient(
        ["python", "-m", "mcp_build_environment.server"],
        env={"MCP_BUILD_REPOS_DIR": str(test_dir.parent)}
    ) as client:
        print("Testing invalid git command (push)...")
        try:
            result = await client.call_tool("git", {"args": "push origin main"})
            print(f"Result: {result}")
            print("ERROR: Should have raised an exception!")
        except RuntimeError as e:
            print(f"SUCCESS: Got expected error: {e}")
        except Exception as e:
            print(f"Got different exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
