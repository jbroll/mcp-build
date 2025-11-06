# MCP Build Service - Testing Documentation

This directory contains comprehensive tests and debugging tools for the MCP Build Service.

## Overview

The testing infrastructure includes:
- **Integration Tests**: Full end-to-end tests of all MCP tools
- **MCP Client Library**: Reusable client for testing MCP servers via stdio
- **Manual Testing Tools**: Interactive debugging scripts
- **Protocol Debugging**: Low-level protocol testing utilities

## Quick Start

### Running All Tests

```bash
# Run all integration tests
pytest tests/test_integration.py -v

# Run with detailed output
pytest tests/test_integration.py -v -s

# Run specific test
pytest tests/test_integration.py::test_git_status -v
```

### Manual Interactive Testing

```bash
# Interactive mode - test all tools and get interactive shell
python tests/manual_test.py

# Test specific tool
python tests/manual_test.py --tool list
python tests/manual_test.py --tool git --args "status"
python tests/manual_test.py --tool make --args "all"

# Use with custom repository directory
python tests/manual_test.py --repos-dir /path/to/your/repos
```

### Protocol Debugging

```bash
# Debug low-level JSON-RPC communication
python tests/debug_protocol.py
```

## Test Files

### `test_integration.py`

Comprehensive integration test suite with 24 tests covering:

1. **Server Initialization**
   - Protocol handshake
   - Capability negotiation
   - Repository discovery

2. **Tool Listing**
   - Available tools enumeration
   - Tool schema validation

3. **Repository Management**
   - Multi-repository support
   - Repository listing
   - Default repository handling

4. **Git Operations**
   - status, log, branch, diff, show, fetch, pull, checkout
   - Command validation and security
   - Invalid command rejection

5. **Build Operations**
   - make with various targets
   - Build output capture
   - Error handling

6. **File Operations**
   - ls with various flags
   - Path validation
   - Directory traversal prevention

7. **Environment Information**
   - Tool version detection
   - Environment variable inspection

8. **Security Testing**
   - Path traversal attempts
   - Command injection attempts
   - Dangerous pattern blocking

9. **Error Handling**
   - Invalid arguments
   - Missing repositories
   - Empty parameters

10. **Multi-Repository Operations**
    - Operations on specific repos
    - Repository switching

### `mcp_client.py`

Reusable MCP client implementation for testing:

```python
from tests.mcp_client import MCPClient

# Context manager usage
async with MCPClient(
    ["python", "-m", "mcp_build_environment.server"],
    env={"MCP_BUILD_REPOS_DIR": "/path/to/repos"}
) as client:
    # List available tools
    tools = await client.list_tools()

    # Call a tool
    result = await client.call_tool("git", {"args": "status"})
    print(result[0]["text"])
```

**Features:**
- Full MCP protocol implementation
- Automatic initialization
- Clean subprocess management
- Detailed logging (DEBUG level)
- Error handling and validation

### `manual_test.py`

Interactive testing script with two modes:

**1. Interactive Mode (default)**
```bash
python tests/manual_test.py
```
Provides an interactive shell where you can:
- Run tool commands directly
- Test different repositories
- View detailed output
- Debug issues in real-time

Available commands:
- `list` - List repositories
- `git <args>` - Run git commands
- `make <args>` - Run make commands
- `ls <args>` - List files
- `env` - Show environment info
- `tools` - List available tools
- `test-all` - Run all test cases
- `help` - Show help message
- `quit` - Exit

**2. Single Tool Mode**
```bash
# Test specific tool
python tests/manual_test.py --tool git --args "status"
python tests/manual_test.py --tool make --args "clean all"
python tests/manual_test.py --tool ls --args "-la"

# Test with specific repository
python tests/manual_test.py --tool git --args "log" --repo my-project
```

### `debug_protocol.py`

Low-level protocol debugging tool that shows raw JSON-RPC messages:

```bash
python tests/debug_protocol.py
```

**Output includes:**
- Raw request messages
- Raw response messages
- Server initialization
- Protocol negotiation
- Tool list retrieval
- Server stderr output

Useful for:
- Debugging protocol issues
- Understanding MCP message flow
- Testing new server implementations

## Test Coverage

The test suite covers:

### Tools Tested
- ✅ `list` - Repository listing
- ✅ `git` - All safe git operations (status, log, branch, diff, show, fetch, pull, checkout)
- ✅ `make` - Build system operations
- ✅ `ls` - File listing
- ✅ `env` - Environment information

### Scenarios Tested
- ✅ Server startup and initialization
- ✅ Tool discovery and schema validation
- ✅ Single repository operations
- ✅ Multi-repository operations
- ✅ Command validation and sanitization
- ✅ Error handling and reporting
- ✅ Security: path traversal prevention
- ✅ Security: command injection prevention
- ✅ Security: dangerous pattern blocking
- ✅ Output capture (stdout and stderr)
- ✅ Exit code handling
- ✅ Empty and invalid parameters

## Development Workflow

### Adding New Tests

1. **Add test function to `test_integration.py`:**
```python
@pytest.mark.asyncio
async def test_my_new_feature(mcp_client):
    """Test description"""
    result = await mcp_client.call_tool("tool_name", {"args": "..."})
    assert result[0]["type"] == "text"
    assert "expected output" in result[0]["text"]
```

2. **Run the new test:**
```bash
pytest tests/test_integration.py::test_my_new_feature -v -s
```

### Debugging Failed Tests

1. **Run single test with verbose output:**
```bash
pytest tests/test_integration.py::test_name -v -s
```

2. **Use manual test script for interactive debugging:**
```bash
python tests/manual_test.py
> tool_name args
```

3. **Check protocol-level communication:**
```bash
python tests/debug_protocol.py
```

4. **Review server logs:**
The MCP server logs are captured during tests. Check stderr output in test failures.

### Running Local Server for Manual Testing

```bash
# Start server with current directory as repos dir
MCP_BUILD_REPOS_DIR=. python -m mcp_build_environment.server

# Or with specific directory
MCP_BUILD_REPOS_DIR=/path/to/repos python -m mcp_build_environment.server

# Then use the manual test client to connect
python tests/manual_test.py --repos-dir /path/to/repos
```

## Test Environment

### Requirements
- Python 3.10+
- pytest
- pytest-asyncio
- mcp (SDK)
- Git
- Make (for make-related tests)

### Test Data
Tests automatically create temporary repositories in `/tmp/mcp-build-test-repos/`:
- `test-repo-1`: Contains Makefile and test.txt
- `test-repo-2`: Contains README.md

These are cleaned up after tests complete.

## Continuous Integration

To run tests in CI:

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest tests/test_integration.py -v --tb=short

# Run with coverage report
pytest tests/test_integration.py --cov=mcp_build_environment --cov-report=html
```

## Troubleshooting

### Tests Fail with "Server process died"
- Check that mcp-build package is installed: `pip install -e .`
- Verify Python version: `python --version` (needs 3.10+)
- Check for port conflicts if using network mode

### Git Commit Signing Issues
Tests automatically disable commit signing in test repositories. If you still see signing errors, check your global git config:
```bash
git config --global commit.gpgsign
```

### Make Tests Fail
Ensure `make` is installed:
```bash
make --version
```

### Permission Errors
Test repositories are created in /tmp. Ensure you have write permissions:
```bash
ls -ld /tmp
```

## Performance Notes

- Full test suite runs in ~25 seconds
- Each test creates a fresh MCP server instance
- Tests run sequentially (not in parallel) due to stdio limitations
- Temporary repositories are reused within a test session

## Security Testing

The test suite includes specific tests for security features:

1. **Path Traversal Prevention**
   - Tests attempts to access files outside repo: `../../../etc/passwd`
   - Validates path sanitization

2. **Command Injection Prevention**
   - Tests shell metacharacters: `;`, `|`, `&`, `$()`, etc.
   - Validates argument escaping

3. **Git Command Whitelist**
   - Tests that dangerous commands are blocked: `push`, `reset`, `rebase`
   - Tests force operations are blocked: `--force`, `-f`

## Future Enhancements

Potential test improvements:
- [ ] Performance benchmarks
- [ ] Concurrent client testing (multiple clients)
- [ ] Network transport tests (HTTP/SSE)
- [ ] Resource usage monitoring
- [ ] Stress testing with large repositories
- [ ] Additional build systems (npm, gradle, cargo)

## Contributing

When adding new features to mcp-build:
1. Add corresponding tests to `test_integration.py`
2. Update this README if new test utilities are added
3. Ensure all tests pass: `pytest tests/test_integration.py`
4. Update manual_test.py if new tools are added

## License

Same as mcp-build project (MIT)
