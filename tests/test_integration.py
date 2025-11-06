"""
Integration tests for MCP Build Service

These tests run against a live MCP server instance to verify:
- Server startup and initialization
- All tool implementations
- Error handling
- Multi-repository support
"""

import asyncio
import os
import pytest
import pytest_asyncio
from pathlib import Path
import tempfile
import subprocess

from helpers.mcp_client import MCPClient


# Test environment
TEST_REPOS_DIR = Path(tempfile.gettempdir()) / "mcp-build-test-repos"


@pytest.fixture(scope="session")
def test_repos_dir():
    """Create a test repository directory structure"""
    # Clean up any existing test directory
    if TEST_REPOS_DIR.exists():
        import shutil
        shutil.rmtree(TEST_REPOS_DIR)

    TEST_REPOS_DIR.mkdir(parents=True, exist_ok=True)

    # Create test repo 1 with a Makefile
    repo1 = TEST_REPOS_DIR / "test-repo-1"
    repo1.mkdir()
    subprocess.run(["git", "init"], cwd=repo1, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo1, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo1, check=True)
    # Disable commit signing for tests
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo1, check=True)
    subprocess.run(["git", "config", "gpg.format", "openpgp"], cwd=repo1, check=True)

    # Create a simple Makefile (with actual tabs)
    makefile = repo1 / "Makefile"
    makefile.write_text(".PHONY: all clean test\n\n" +
                       "all:\n" +
                       "\t@echo \"Building project...\"\n" +
                       "\t@echo \"Build complete\"\n\n" +
                       "clean:\n" +
                       "\t@echo \"Cleaning build artifacts...\"\n" +
                       "\t@rm -f *.o\n\n" +
                       "test:\n" +
                       "\t@echo \"Running tests...\"\n" +
                       "\t@echo \"All tests passed\"\n")

    # Create a test file and commit
    test_file = repo1 / "test.txt"
    test_file.write_text("Hello from test repo 1")
    subprocess.run(["git", "add", "."], cwd=repo1, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo1, check=True)

    # Create test repo 2
    repo2 = TEST_REPOS_DIR / "test-repo-2"
    repo2.mkdir()
    subprocess.run(["git", "init"], cwd=repo2, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo2, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo2, check=True)
    # Disable commit signing for tests
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo2, check=True)
    subprocess.run(["git", "config", "gpg.format", "openpgp"], cwd=repo2, check=True)

    test_file2 = repo2 / "README.md"
    test_file2.write_text("# Test Repo 2")
    subprocess.run(["git", "add", "."], cwd=repo2, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo2, check=True)

    yield TEST_REPOS_DIR

    # Cleanup
    import shutil
    if TEST_REPOS_DIR.exists():
        shutil.rmtree(TEST_REPOS_DIR)


@pytest_asyncio.fixture
async def mcp_client(test_repos_dir):
    """Create and initialize an MCP client"""
    client = MCPClient(
        ["python", "-m", "server"],
        cwd=str(test_repos_dir)
    )
    await client.start()
    await client.initialize()
    yield client
    await client.stop()


@pytest.mark.asyncio
async def test_server_initialization(test_repos_dir):
    """Test that the server initializes correctly"""
    client = MCPClient(
        ["python", "-m", "server"],
        cwd=str(test_repos_dir)
    )

    try:
        await client.start()
        result = await client.initialize()

        # Check that we got a valid response
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "mcp-build"

        # Check capabilities
        assert "capabilities" in result
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_list_tools(mcp_client):
    """Test listing available tools"""
    tools = await mcp_client.list_tools()

    # Check that all expected tools are present
    tool_names = {tool["name"] for tool in tools}
    expected_tools = {"list", "make", "git", "ls", "env"}

    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    # Check that each tool has required fields
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


@pytest.mark.asyncio
async def test_list_repositories(mcp_client):
    """Test listing repositories"""
    result = await mcp_client.call_tool("list")

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    assert "test-repo-1" in text
    assert "test-repo-2" in text


@pytest.mark.asyncio
async def test_git_status(mcp_client):
    """Test git status command"""
    result = await mcp_client.call_tool("git", {"args": "status", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain git status output
    assert "branch" in text.lower() or "nothing to commit" in text.lower()


@pytest.mark.asyncio
async def test_git_log(mcp_client):
    """Test git log command"""
    result = await mcp_client.call_tool("git", {"args": "log --oneline -5", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain commit history
    assert "Initial commit" in text


@pytest.mark.asyncio
async def test_git_branch(mcp_client):
    """Test git branch command"""
    result = await mcp_client.call_tool("git", {"args": "branch", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should show at least the main/master branch
    assert "main" in text or "master" in text


@pytest.mark.asyncio
async def test_git_invalid_command(mcp_client):
    """Test that invalid git commands are rejected"""
    result = await mcp_client.call_tool("git", {"args": "push origin main", "repo": "test-repo-1"})
    assert len(result) == 1
    text = result[0]["text"]
    assert "Error:" in text and "not allowed" in text


@pytest.mark.asyncio
async def test_make_all(mcp_client):
    """Test make all command"""
    result = await mcp_client.call_tool("make", {"args": "all", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain make output
    assert "Building project" in text or "Build complete" in text


@pytest.mark.asyncio
async def test_make_test(mcp_client):
    """Test make test command"""
    result = await mcp_client.call_tool("make", {"args": "test", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain test output
    assert "Running tests" in text or "All tests passed" in text


@pytest.mark.asyncio
async def test_make_clean(mcp_client):
    """Test make clean command"""
    result = await mcp_client.call_tool("make", {"args": "clean", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain clean output
    assert "Cleaning" in text


@pytest.mark.asyncio
async def test_make_no_args(mcp_client):
    """Test make without arguments (runs default target)"""
    result = await mcp_client.call_tool("make", {"repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"


@pytest.mark.asyncio
async def test_ls_basic(mcp_client):
    """Test ls command"""
    result = await mcp_client.call_tool("ls", {"repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should list files in the repository
    assert "Makefile" in text or "test.txt" in text


@pytest.mark.asyncio
async def test_ls_with_flags(mcp_client):
    """Test ls with flags"""
    result = await mcp_client.call_tool("ls", {"args": "-la", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should include hidden files with -a flag
    assert ".git" in text


@pytest.mark.asyncio
async def test_ls_specific_path(mcp_client):
    """Test ls with specific path"""
    result = await mcp_client.call_tool("ls", {"args": "-l .git", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should list .git directory contents
    assert "config" in text or "HEAD" in text


@pytest.mark.asyncio
async def test_env_command(mcp_client):
    """Test env command"""
    result = await mcp_client.call_tool("env", {"repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"

    text = content["text"]
    # Should contain environment information
    assert "PATH" in text or "python" in text.lower()


@pytest.mark.asyncio
async def test_multi_repo_list(mcp_client):
    """Test that both repositories are discovered"""
    result = await mcp_client.call_tool("list")

    content = result[0]
    text = content["text"]

    # Both repos should be listed
    assert "test-repo-1" in text
    assert "test-repo-2" in text


@pytest.mark.asyncio
async def test_multi_repo_git_status(mcp_client):
    """Test git status on specific repository"""
    result = await mcp_client.call_tool("git", {
        "args": "status",
        "repo": "test-repo-2"
    })

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"


@pytest.mark.asyncio
async def test_multi_repo_ls(mcp_client):
    """Test ls on specific repository"""
    result = await mcp_client.call_tool("ls", {
        "args": "-l",
        "repo": "test-repo-2"
    })

    assert len(result) == 1
    content = result[0]
    text = content["text"]

    # Should list files from repo 2
    assert "README.md" in text


@pytest.mark.asyncio
async def test_invalid_repo_name(mcp_client):
    """Test that invalid repository names are rejected"""
    result = await mcp_client.call_tool("git", {
        "args": "status",
        "repo": "nonexistent-repo"
    })
    assert len(result) == 1
    text = result[0]["text"]
    assert "Error:" in text and "Unknown repository" in text


@pytest.mark.asyncio
async def test_dangerous_path_traversal(mcp_client):
    """Test that path traversal attempts are blocked"""
    result = await mcp_client.call_tool("ls", {"args": "../../../etc/passwd", "repo": "test-repo-1"})
    assert len(result) == 1
    text = result[0]["text"]
    assert "Error:" in text and ("dangerous patterns" in text or "traversal" in text)


@pytest.mark.asyncio
async def test_dangerous_command_injection(mcp_client):
    """Test that command injection attempts are blocked"""
    result = await mcp_client.call_tool("make", {"args": "all; rm -rf /", "repo": "test-repo-1"})
    assert len(result) == 1
    text = result[0]["text"]
    assert "Error:" in text and "dangerous patterns" in text


@pytest.mark.asyncio
async def test_concurrent_tool_calls(mcp_client):
    """Test that multiple tool calls work sequentially"""
    # Run multiple commands sequentially (MCP stdio doesn't support true concurrency)
    result1 = await mcp_client.call_tool("list")
    result2 = await mcp_client.call_tool("git", {"args": "status", "repo": "test-repo-1"})
    result3 = await mcp_client.call_tool("ls", {"args": "-l", "repo": "test-repo-1"})

    # All should complete successfully
    assert len(result1) == 1 and result1[0]["type"] == "text"
    assert len(result2) == 1 and result2[0]["type"] == "text"
    assert len(result3) == 1 and result3[0]["type"] == "text"


@pytest.mark.asyncio
async def test_error_handling_empty_git_args(mcp_client):
    """Test error handling for empty git arguments"""
    result = await mcp_client.call_tool("git", {"args": "", "repo": "test-repo-1"})
    assert len(result) == 1
    text = result[0]["text"]
    assert "Error:" in text


@pytest.mark.asyncio
async def test_long_running_command(mcp_client):
    """Test handling of commands that produce output"""
    # Git log can produce significant output
    result = await mcp_client.call_tool("git", {"args": "log --all --oneline", "repo": "test-repo-1"})

    assert len(result) == 1
    content = result[0]
    assert content["type"] == "text"
    # Should have received all output
    assert len(content["text"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
