#!/usr/bin/env python3
"""Test the read_file tool via HTTP REST API"""

import asyncio
import sys
import time
from pathlib import Path
import tempfile
import subprocess
import httpx
import json

async def wait_for_server(url: str, timeout: float = 10.0):
    """Wait for the server to be ready"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{url}/api/repos")
                if response.status_code in [200, 401]:  # Server is up (401 means auth required)
                    return True
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            await asyncio.sleep(0.5)
    return False


async def main():
    """Test read_file functionality via HTTP REST API"""
    # Create a test repo
    test_dir = Path(tempfile.gettempdir()) / "test-repo-read-file-http-rest"
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

    # Start the HTTP server
    session_key = "test-session-key-12345"
    port = 3344
    base_url = f"http://localhost:{port}"

    print("Starting MCP server with HTTP transport...")
    server_process = await asyncio.create_subprocess_exec(
        "python", "-m", "server",
        "--transport", "http",
        "--port", str(port),
        "--session-key", session_key,
        cwd=test_dir.parent,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        # Wait for server to be ready
        print("Waiting for server to be ready...")
        if not await wait_for_server(base_url, timeout=10.0):
            stderr = await server_process.stderr.read()
            raise RuntimeError(f"Server did not start in time. Stderr: {stderr.decode('utf-8', errors='replace')}")

        print("Server is ready!")
        print()

        repo_name = test_dir.name
        headers = {"Authorization": f"Bearer {session_key}"}

        async with httpx.AsyncClient() as client:
            print("=" * 80)
            print("Test 1: Read entire file with absolute path")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file)},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(data[:500] + "..." if len(data) > 500 else data)
                assert "Line 1" in data, "Should contain first line"
                assert "Line 100" in data, "Should contain last line"
                assert "Total lines: 100" in data, "Should show total lines"
                print("✓ Test 1 passed\n")
            else:
                print(f"Error: {result.get('error')}")
                raise AssertionError("Test 1 failed")

            print("=" * 80)
            print("Test 2: Read specific line range (lines 10-20)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file), "start_line": 10, "end_line": 20},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(data)
                assert "Line 10" in data, "Should contain line 10"
                assert "Line 20" in data, "Should contain line 20"
                assert "Line 9" not in data, "Should not contain line 9"
                assert "Line 21" not in data, "Should not contain line 21"
                assert "Lines 10-20 of 100" in data, "Should show line range info"
                print("✓ Test 2 passed\n")
            else:
                print(f"Error: {result.get('error')}")
                raise AssertionError("Test 2 failed")

            print("=" * 80)
            print("Test 3: Read with only start_line")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file), "start_line": 95},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(data)
                assert "Line 95" in data, "Should contain line 95"
                assert "Line 100" in data, "Should contain line 100"
                assert "Line 94" not in data, "Should not contain line 94"
                print("✓ Test 3 passed\n")
            else:
                print(f"Error: {result.get('error')}")
                raise AssertionError("Test 3 failed")

            print("=" * 80)
            print("Test 4: Read with only end_line")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file), "end_line": 5},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(data)
                assert "Line 1" in data, "Should contain line 1"
                assert "Line 5" in data, "Should contain line 5"
                assert "Line 6" not in data, "Should not contain line 6"
                print("✓ Test 4 passed\n")
            else:
                print(f"Error: {result.get('error')}")
                raise AssertionError("Test 4 failed")

            print("=" * 80)
            print("Test 5: Read nested file with relative path")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": "subdir/nested.txt"},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            if result['success']:
                data = result['data']
                print(data)
                assert "nested file" in data, "Should contain file content"
                assert "multiple lines" in data, "Should contain second line"
                print("✓ Test 5 passed\n")
            else:
                print(f"Error: {result.get('error')}")
                raise AssertionError("Test 5 failed")

            print("=" * 80)
            print("Test 6: Try to read outside repository (should fail)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": "/etc/passwd"},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            assert result['success'] == False, "Should return error"
            assert "outside repository" in result['error'].lower(), "Should mention outside repository"
            print(f"Error (expected): {result['error']}")
            print("✓ Test 6 passed\n")

            print("=" * 80)
            print("Test 7: Try to read with path traversal (should fail)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": "../../../etc/passwd"},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            assert result['success'] == False, "Should return error"
            assert "outside repository" in result['error'].lower(), "Should mention outside repository"
            print(f"Error (expected): {result['error']}")
            print("✓ Test 7 passed\n")

            print("=" * 80)
            print("Test 8: Try to read non-existent file (should fail)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_dir / "nonexistent.txt")},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            assert result['success'] == False, "Should return error"
            assert response.status_code == 404, "Should return 404"
            print(f"Error (expected): {result['error']}")
            print("✓ Test 8 passed\n")

            print("=" * 80)
            print("Test 9: Invalid line range (start > end, should fail)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file), "start_line": 50, "end_line": 40},
                headers=headers
            )
            print(f"Status: {response.status_code}")
            result = response.json()
            print(f"Success: {result['success']}")
            assert result['success'] == False, "Should return error"
            assert response.status_code == 400, "Should return 400"
            assert "start_line" in result['error'] or "end_line" in result['error'], "Should mention line range error"
            print(f"Error (expected): {result['error']}")
            print("✓ Test 9 passed\n")

            print("=" * 80)
            print("Test 10: Unauthorized request (no session key)")
            print("=" * 80)
            response = await client.post(
                f"{base_url}/api/repos/{repo_name}/read_file",
                json={"path": str(test_file)}
                # No headers with session key
            )
            print(f"Status: {response.status_code}")
            assert response.status_code == 401, "Should return 401 Unauthorized"
            print("✓ Test 10 passed\n")

            print("=" * 80)
            print("ALL TESTS PASSED! ✓")
            print("=" * 80)

    finally:
        # Clean up
        print("\nStopping server...")
        server_process.terminate()
        try:
            await asyncio.wait_for(server_process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            print("Server didn't terminate gracefully, killing...")
            server_process.kill()
            await server_process.wait()

        # Cleanup test directory
        import shutil
        shutil.rmtree(test_dir)

    print("\nHTTP REST API testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
