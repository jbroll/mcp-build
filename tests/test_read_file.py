#!/usr/bin/env python3
"""Test the read_file tool"""

import asyncio
import sys
from pathlib import Path
import tempfile
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from helpers.mcp_client import MCPClient

async def main():
    """Test read_file functionality"""
    # Create a test repo
    test_dir = Path(tempfile.gettempdir()) / "test-repo-read-file"
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)

    test_dir.mkdir()
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "gpg.format", "openpgp"], cwd=test_dir, check=True)

    # Create a test file with multiple lines
    test_file = test_dir / "test_file.txt"
    test_content = "\n".join([f"Line {i}" for i in range(1, 101)])  # 100 lines
    test_file.write_text(test_content)

    # Create a subdirectory with another file
    sub_dir = test_dir / "subdir"
    sub_dir.mkdir()
    sub_file = sub_dir / "nested.txt"
    sub_file.write_text("This is a nested file\nWith multiple lines\nFor testing")

    # Commit the files
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Add test files"], cwd=test_dir, check=True)

    # Test with MCP client
    async with MCPClient(
        ["python", "-m", "server"],
        cwd=str(test_dir.parent)
    ) as client:
        repo_name = test_dir.name

        print("=" * 80)
        print("Test 1: Read entire file with absolute path")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_file)
        })
        text = result[0]["text"]
        print(text)
        assert "Line 1" in text, "Should contain first line"
        assert "Line 100" in text, "Should contain last line"
        print("✓ Test 1 passed\n")

        print("=" * 80)
        print("Test 2: Read specific line range (lines 10-20)")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_file),
            "start_line": 10,
            "end_line": 20
        })
        text = result[0]["text"]
        print(text)
        assert "Line 10" in text, "Should contain line 10"
        assert "Line 20" in text, "Should contain line 20"
        assert "Line 9" not in text, "Should not contain line 9"
        assert "Line 21" not in text, "Should not contain line 21"
        assert "Lines 10-20 of 100" in text, "Should show line range info"
        print("✓ Test 2 passed\n")

        print("=" * 80)
        print("Test 3: Read with only start_line")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_file),
            "start_line": 95
        })
        text = result[0]["text"]
        print(text)
        assert "Line 95" in text, "Should contain line 95"
        assert "Line 100" in text, "Should contain line 100"
        assert "Line 94" not in text, "Should not contain line 94"
        print("✓ Test 3 passed\n")

        print("=" * 80)
        print("Test 4: Read with only end_line")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_file),
            "end_line": 5
        })
        text = result[0]["text"]
        print(text)
        assert "Line 1" in text, "Should contain line 1"
        assert "Line 5" in text, "Should contain line 5"
        assert "Line 6" not in text, "Should not contain line 6"
        print("✓ Test 4 passed\n")

        print("=" * 80)
        print("Test 5: Read nested file with relative path")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": "subdir/nested.txt"
        })
        text = result[0]["text"]
        print(text)
        assert "nested file" in text, "Should contain file content"
        assert "multiple lines" in text, "Should contain second line"
        print("✓ Test 5 passed\n")

        print("=" * 80)
        print("Test 6: Try to read outside repository (should fail)")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": "/etc/passwd"
        })
        text = result[0]["text"]
        print(text)
        assert "Error:" in text and "outside repository" in text, "Should return error about path outside repo"
        print("✓ Test 6 passed\n")

        print("=" * 80)
        print("Test 7: Try to read with path traversal (should fail)")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": "../../../etc/passwd"
        })
        text = result[0]["text"]
        print(text)
        assert "Error:" in text and ("outside repository" in text or "traversal" in text), "Should return error about path traversal"
        print("✓ Test 7 passed\n")

        print("=" * 80)
        print("Test 8: Try to read non-existent file (should fail)")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_dir / "nonexistent.txt")
        })
        text = result[0]["text"]
        print(text)
        assert "Error:" in text and "not found" in text, "Should return error about file not found"
        print("✓ Test 8 passed\n")

        print("=" * 80)
        print("Test 9: Invalid line range (start > end, should fail)")
        print("=" * 80)
        result = await client.call_tool("read_file", {
            "repo": repo_name,
            "path": str(test_file),
            "start_line": 50,
            "end_line": 40
        })
        text = result[0]["text"]
        print(text)
        assert "Error:" in text and ("start_line" in text or "end_line" in text), "Should return error about invalid line range"
        print("✓ Test 9 passed\n")

        print("=" * 80)
        print("ALL TESTS PASSED! ✓")
        print("=" * 80)

    # Cleanup
    import shutil
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    asyncio.run(main())
