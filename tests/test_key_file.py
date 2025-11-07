"""
Tests for session key file persistence

Verifies that the --key-file option correctly:
1. Generates and saves a new key on first run
2. Loads existing key on subsequent runs
3. Allows explicit --session-key to override file-based key
4. Handles key rotation workflows
"""

import asyncio
import os
import pytest
import tempfile
from pathlib import Path
import subprocess
import time
import httpx


@pytest.mark.asyncio
async def test_key_file_generates_on_first_run():
    """Test that a new key is generated and saved when key file doesn't exist"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test-repo"
        test_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_dir, check=True)

        key_file = Path(tmpdir) / "session.key"

        # Ensure key file doesn't exist
        assert not key_file.exists()

        # Start server with --key-file
        port = 3345
        process = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            # Wait for server to start and generate key
            await asyncio.sleep(2)

            # Verify key file was created
            assert key_file.exists(), "Key file should be created on first run"

            # Verify file permissions are secure (600)
            stat_info = os.stat(key_file)
            permissions = oct(stat_info.st_mode)[-3:]
            assert permissions == '600', f"Key file should have 600 permissions, got {permissions}"

            # Read the generated key
            with open(key_file, 'r') as f:
                generated_key = f.read().strip()

            assert len(generated_key) > 20, "Generated key should be a reasonable length"
            assert generated_key != "", "Generated key should not be empty"

            # Verify server responds with the generated key
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {generated_key}"}
                )
                assert response.status_code == 200, "Server should accept generated key"

        finally:
            process.terminate()
            await process.wait()


@pytest.mark.asyncio
async def test_key_file_reused_on_subsequent_runs():
    """Test that existing key is loaded from file on subsequent server starts"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test-repo"
        test_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_dir, check=True)

        key_file = Path(tmpdir) / "session.key"
        port = 3346

        # First run - generate key
        process1 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)

            # Read the first generated key
            with open(key_file, 'r') as f:
                first_key = f.read().strip()

        finally:
            process1.terminate()
            await process1.wait()

        # Wait a moment to ensure port is released
        await asyncio.sleep(1)

        # Second run - should reuse existing key
        process2 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)

            # Read the key again
            with open(key_file, 'r') as f:
                second_key = f.read().strip()

            # Keys should match - persistence works!
            assert first_key == second_key, "Key should persist across server restarts"

            # Verify server accepts the persisted key
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {second_key}"}
                )
                assert response.status_code == 200, "Server should accept persisted key"

        finally:
            process2.terminate()
            await process2.wait()


@pytest.mark.asyncio
async def test_explicit_session_key_overrides_file():
    """Test that --session-key argument takes priority over key file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test-repo"
        test_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_dir, check=True)

        key_file = Path(tmpdir) / "session.key"

        # Pre-populate key file with a known key
        existing_key = "existing-key-in-file"
        key_file.write_text(existing_key)
        os.chmod(key_file, 0o600)

        # Start server with explicit --session-key that differs from file
        explicit_key = "explicit-override-key"
        port = 3347

        process = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--session-key", explicit_key,
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)

            # Verify server uses the explicit key, not the file key
            async with httpx.AsyncClient() as client:
                # Explicit key should work
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {explicit_key}"}
                )
                assert response.status_code == 200, "Server should accept explicit session key"

                # File key should NOT work
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {existing_key}"}
                )
                assert response.status_code == 403, "Server should reject file key when explicit key provided"

            # Verify file is updated with the explicit key
            with open(key_file, 'r') as f:
                updated_key = f.read().strip()
            assert updated_key == explicit_key, "Key file should be updated with explicit key"

        finally:
            process.terminate()
            await process.wait()


@pytest.mark.asyncio
async def test_key_rotation_workflow():
    """Test the key rotation workflow: delete file, restart, new key generated"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test-repo"
        test_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_dir, check=True)

        key_file = Path(tmpdir) / "session.key"
        port = 3348

        # First run - generate initial key
        process1 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)
            with open(key_file, 'r') as f:
                original_key = f.read().strip()
        finally:
            process1.terminate()
            await process1.wait()

        # Simulate key rotation: delete the key file
        key_file.unlink()
        assert not key_file.exists(), "Key file should be deleted"

        # Wait for port to be released
        await asyncio.sleep(1)

        # Second run - should generate NEW key
        process2 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)

            # Verify new key file was created
            assert key_file.exists(), "New key file should be created"

            with open(key_file, 'r') as f:
                new_key = f.read().strip()

            # Keys should be different - rotation successful!
            assert original_key != new_key, "New key should be different from original (rotation)"

            # Verify server accepts new key but not old key
            async with httpx.AsyncClient() as client:
                # New key should work
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {new_key}"}
                )
                assert response.status_code == 200, "Server should accept new key"

                # Old key should NOT work
                response = await client.get(
                    f"http://localhost:{port}/api/repos",
                    headers={"Authorization": f"Bearer {original_key}"}
                )
                assert response.status_code == 403, "Server should reject old key after rotation"

        finally:
            process2.terminate()
            await process2.wait()


@pytest.mark.asyncio
async def test_key_file_not_modified_if_unchanged():
    """Test that key file is not rewritten if key hasn't changed"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test-repo"
        test_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=test_dir, check=True)

        key_file = Path(tmpdir) / "session.key"
        port = 3349

        # First run - generate key
        process1 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)
        finally:
            process1.terminate()
            await process1.wait()

        # Get modification time of key file
        original_mtime = key_file.stat().st_mtime

        # Wait to ensure any file modification would have a different timestamp
        await asyncio.sleep(1)

        # Second run - should load existing key without modifying file
        process2 = await asyncio.create_subprocess_exec(
            "python", "-m", "server",
            "--transport", "http",
            "--port", str(port),
            "--key-file", str(key_file),
            cwd=test_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.sleep(2)

            # Verify file was NOT modified (mtime unchanged)
            new_mtime = key_file.stat().st_mtime
            assert original_mtime == new_mtime, "Key file should not be rewritten if key unchanged"

        finally:
            process2.terminate()
            await process2.wait()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
