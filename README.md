# MCP Build Service

A Model Context Protocol (MCP) server that provides secure access to software project repositories for build operations. This service allows AI assistants to execute builds, run tests, and manage git operations across multiple repositories in a controlled manner.

## Features

- **Automatic Repository Discovery**: Discovers git repositories in the configured directory
- **Safe Command Execution**: Validated commands to prevent accidental harmful operations
- **Git Operations**: Limited to safe operations (status, log, checkout, pull, branch, diff, fetch, show)
- **Build Management**: Execute make targets, run tests, and manage build artifacts
- **Environment Inspection**: Query installed tools, versions, and environment variables
- **Multi-Repository Support**: Work with multiple repositories from a single service

## Available Commands

### `list`
List all available repositories discovered in the service directory.

**Example:**
```json
{
  "tool": "list"
}
```

### `make`
Run make command with specified arguments in a repository.

**Parameters:**
- `args` (optional): Arguments to pass to make (e.g., "clean", "all", "test")
- `repo` (optional): Repository name (uses default if not specified)

**Examples:**
```json
{
  "tool": "make",
  "args": "clean all"
}
```

```json
{
  "tool": "make",
  "args": "test",
  "repo": "my-project"
}
```

### `git`
Run git commands (limited to safe operations).

**Allowed operations:** status, log, checkout, pull, branch, diff, fetch, show

**Parameters:**
- `args` (required): Git command and arguments
- `repo` (optional): Repository name (uses default if not specified)

**Examples:**
```json
{
  "tool": "git",
  "args": "status"
}
```

```json
{
  "tool": "git",
  "args": "checkout feature-branch"
}
```

```json
{
  "tool": "git",
  "args": "log --oneline -10",
  "repo": "my-project"
}
```

### `ls`
List files and directories in a repository.

**Parameters:**
- `args` (optional): Arguments to pass to ls (e.g., "-la", "-lh build/")
- `repo` (optional): Repository name (uses default if not specified)

**Examples:**
```json
{
  "tool": "ls",
  "args": "-la"
}
```

```json
{
  "tool": "ls",
  "args": "-lh build/",
  "repo": "my-project"
}
```

### `env`
Show environment information including installed tools and versions.

**Parameters:**
- `repo` (optional): Repository name (uses default if not specified)

**Example:**
```json
{
  "tool": "env"
}
```

## Installation

### Prerequisites

- Python 3.10 or higher
- pip
- Build tools (make, gcc, etc.) installed on your system
- Git repositories you want to work with

### Setup Steps

1. **Clone the repository:**
   ```bash
   git clone <this-repo-url>
   cd mcp-build
   ```

2. **Install the service:**
   ```bash
   pip install -e .
   # Or for development:
   pip install -e ".[dev]"
   ```

3. **Organize your repositories:**
   Place your git repositories in a directory where the service can discover them. For example:
   ```
   /home/user/projects/
   ├── project-a/     (git repo)
   ├── project-b/     (git repo)
   └── project-c/     (git repo)
   ```

## Configuration

### MCP Client Configuration

Add the server to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "mcp-build": {
      "command": "python",
      "args": ["-m", "server"]
    }
  }
}
```

**Note:** The service runs in the current working directory and automatically discovers all git repositories (directories containing `.git`) in that directory.

**Command-Line Options:**

```bash
# View all available options
mcp-build --help

# Start with default stdio transport
mcp-build

# Start with HTTP transport (auto-generates session key)
mcp-build --transport http

# Start with HTTP transport and custom session key
mcp-build --transport http --session-key YOUR_SECRET_KEY

# Start with HTTP transport on custom host and port
mcp-build --transport http --host 127.0.0.1 --port 8080
```

**Available Arguments:**
- `--transport {stdio,http}`: Transport mode (default: stdio)
- `--host HOST`: Host address for HTTP transport (default: 0.0.0.0)
- `--port PORT`: Port for HTTP transport (default: 3344)
- `--session-key KEY`: Session key for HTTP authentication
- `--generate-key`: Auto-generate a random session key for HTTP transport

### HTTP Transport

The service supports HTTP transport using Server-Sent Events (SSE) for remote access. This is useful for:
- Remote access to build environments
- Running the service in containers or remote servers
- Integration with web-based MCP clients

**Authentication:**

HTTP transport requires a session key for authentication. You can either:
1. Provide your own key using `--session-key YOUR_KEY`
2. Let the server auto-generate a secure random key (displayed on startup)

**Starting with HTTP transport:**

```bash
# Start with auto-generated session key
cd /path/to/repos
mcp-build --transport http

# Or provide your own session key
cd /path/to/repos
mcp-build --transport http --session-key $(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
```

The service will start an HTTP server with an SSE endpoint at:
```
http://0.0.0.0:3344/sse
```

**MCP Client Configuration for HTTP:**

Include the session key in the URL as a query parameter:

```json
{
  "mcpServers": {
    "mcp-build-http": {
      "url": "http://localhost:3344/sse?key=YOUR_SESSION_KEY_HERE"
    }
  }
}
```

Or use the Authorization header (if your MCP client supports it):

```json
{
  "mcpServers": {
    "mcp-build-http": {
      "url": "http://localhost:3344/sse",
      "headers": {
        "Authorization": "Bearer YOUR_SESSION_KEY_HERE"
      }
    }
  }
}
```

**Testing the Connection:**

```bash
# Test with curl (replace YOUR_KEY with your session key)
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:3344/sse

# Or using query parameter
curl "http://localhost:3344/sse?key=YOUR_KEY"
```

**Security Notes:**
- Session keys provide authentication to prevent unauthorized access
- Use TLS/SSL in production by deploying behind a reverse proxy (nginx, caddy)
- Use firewall rules to restrict access to trusted networks
- Consider VPN or SSH tunneling for remote access
- Keep your session key secret and rotate it regularly

## Hybrid API Architecture

In addition to the MCP protocol over SSE, the service provides a **Hybrid REST/Streaming API** for more flexible access patterns:

### API Design

- **REST API** for quick, synchronous operations (< 1 second)
- **Streaming SSE API** for long-running operations with real-time output
- **MCP Protocol** for backwards compatibility with MCP clients

### Quick Operations (REST API)

These endpoints return immediately with complete results:

#### `GET /api/repos`
List all discovered repositories.

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_KEY" \
  http://localhost:3344/api/repos
```

**Response:**
```json
{
  "repos": [
    {
      "name": "test-repo",
      "path": "/path/to/test-repo",
      "description": "Repository at test-repo",
      "is_default": true
    }
  ]
}
```

#### `GET /api/repos/{repo}/env`
Get environment information for a repository.

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_KEY" \
  http://localhost:3344/api/repos/test-repo/env
```

**Response:**
```json
{
  "success": true,
  "data": "=== STDOUT ===\ngcc version 11.4.0\n..."
}
```

#### `POST /api/repos/{repo}/ls`
List directory contents (fast file listing).

**Request Body:**
```json
{
  "args": "-la"
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"args": "-la"}' \
  http://localhost:3344/api/repos/test-repo/ls
```

**Response:**
```json
{
  "success": true,
  "data": "=== STDOUT ===\ntotal 24\ndrwxr-xr-x 3 user user 4096...\n"
}
```

#### `POST /api/repos/{repo}/git/quick`
Quick git operations (status, branch, log only).

**Request Body:**
```json
{
  "operation": "status",
  "args": ""
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation": "status", "args": ""}' \
  http://localhost:3344/api/repos/test-repo/git/quick
```

**Response:**
```json
{
  "success": true,
  "data": "=== STDOUT ===\nOn branch main\nnothing to commit, working tree clean\n"
}
```

### Long Operations (Streaming SSE API)

These endpoints stream output line-by-line as the command executes:

#### `POST /stream/repos/{repo}/make`
Stream make command output in real-time.

**Request Body:**
```json
{
  "args": "clean all"
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"args": "test"}' \
  -N \
  http://localhost:3344/stream/repos/test-repo/make
```

**Streaming Response:**
```
data: {"type": "stdout", "line": "Starting tests..."}

data: {"type": "stdout", "line": "Running test 1..."}

data: {"type": "stdout", "line": "Running test 2..."}

data: {"type": "stdout", "line": "All tests passed!"}

data: {"type": "complete", "exit_code": 0}
```

#### `POST /stream/repos/{repo}/git`
Stream git operations with potentially large output (pull, fetch, diff, show, checkout).

**Request Body:**
```json
{
  "operation": "pull",
  "args": "origin main"
}
```

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation": "diff", "args": "HEAD~1"}' \
  -N \
  http://localhost:3344/stream/repos/test-repo/git
```

**Streaming Response:**
```
data: {"type": "stdout", "line": "diff --git a/file.txt b/file.txt"}

data: {"type": "stdout", "line": "+Added line"}

data: {"type": "complete", "exit_code": 0}
```

### Event Types in Streaming Responses

| Type | Description | Fields |
|------|-------------|--------|
| `stdout` | Standard output line | `type`, `line` |
| `stderr` | Standard error line | `type`, `line` |
| `complete` | Command completed | `type`, `exit_code` |
| `error` | Error occurred | `type`, `message` |

### When to Use Each API

**Use REST API for:**
- Repository discovery (`/api/repos`)
- Quick status checks (`/api/repos/{repo}/git/quick`)
- Environment queries (`/api/repos/{repo}/env`)
- Fast file listings (`/api/repos/{repo}/ls`)

**Use Streaming API for:**
- Long builds (`/stream/repos/{repo}/make`)
- Large git diffs (`/stream/repos/{repo}/git`)
- Operations where progress visibility is important

**Use MCP Protocol for:**
- Integration with MCP-compatible clients (Claude Desktop, etc.)
- Unified tool interface across different MCP services

### Example Configuration for Different Setups

**Single Project:**
```json
{
  "mcpServers": {
    "mcp-build": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/home/user/my-project/.."
    }
  }
}
```

**Multiple Projects Directory:**
```json
{
  "mcpServers": {
    "mcp-build": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/home/user/workspace"
    }
  }
}
```

## Security

This service implements security measures to protect your build environment:

### Authentication (HTTP Transport)
- **Session Key Authentication**: HTTP transport requires a session key (Bearer token or query parameter)
- **Auto-generated Keys**: Secure random keys are generated if not provided
- **Constant-time Comparison**: Uses `secrets.compare_digest()` to prevent timing attacks

### Command Validation
- **Path Traversal Protection**: Blocks `../` patterns and absolute paths
- **Command Injection Protection**: Blocks pipes, redirects, and command substitution
- **Git Command Whitelist**: Only allows safe git operations (status, log, checkout, pull, branch, diff, fetch, show)
- **Argument Validation**: Validates all command arguments before execution

### Best Practices
- Keep your session key secret and rotate it regularly
- Use TLS/SSL in production (deploy behind a reverse proxy)
- Restrict network access with firewall rules
- Use stdio transport for local, trusted environments
- Use HTTP transport only when remote access is required

**Important:** These security measures provide protection for typical use cases, but do not expose this service to completely untrusted users or networks without additional security controls.

## Development

### Project Structure

```
mcp-build/
├── src/
│   ├── __init__.py
│   ├── server.py              # Main MCP server
│   ├── validators.py          # Argument validation
│   ├── env_info.sh            # Environment info script
│   └── helpers/               # Helper modules
├── tests/
│   ├── __init__.py
│   └── test_validators.py    # Validator tests
├── requirements.txt
├── pyproject.toml
└── README.md
```

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
```

### Type Checking

```bash
mypy src/
```

## Usage Examples

### Building a Project

```python
# List available repos
await mcp.call_tool("list", {})

# Check current git status
await mcp.call_tool("git", {"args": "status"})

# Pull latest changes
await mcp.call_tool("git", {"args": "pull origin main"})

# Clean and build
await mcp.call_tool("make", {"args": "clean all"})

# Run tests
await mcp.call_tool("make", {"args": "test"})

# Check build artifacts
await mcp.call_tool("ls", {"args": "-lh build/"})
```

### Working with Multiple Repositories

```python
# List all discovered repositories
await mcp.call_tool("list", {})

# Check status of specific repo
await mcp.call_tool("git", {"args": "status", "repo": "project-a"})

# Build a specific repo
await mcp.call_tool("make", {"args": "all", "repo": "project-b"})

# Get environment info from specific repo
await mcp.call_tool("env", {"repo": "project-c"})
```

## Troubleshooting

### No repositories found
Check that:
1. The service is running in the correct directory (current working directory)
2. Each repository has a `.git` directory
3. The service has read permissions for the directory

```bash
# Verify repositories are git repos
ls -la /path/to/repos/*/.git

# Check current working directory
pwd
```

### Repository not found error
The specified repository name must match the directory name exactly. Use the `list` command to see available repositories:
```json
{
  "tool": "list"
}
```

### Permission issues
Ensure the service has appropriate permissions to execute commands in your repository directories:
```bash
chmod -R u+rwx /path/to/repos/my-project
```

### Build tools not found
The `env` command shows installed build tools. If tools are missing, install them on your system:
```bash
# Ubuntu/Debian
sudo apt-get install build-essential cmake

# macOS
xcode-select --install
brew install cmake
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review the MCP protocol specification

## Roadmap

- [x] Automatic repository discovery
- [x] Multi-repository support
- [ ] Build caching and artifact management
- [ ] Integration with CI/CD systems
- [ ] Enhanced security controls
- [ ] Build history and logs
- [ ] Performance metrics and monitoring
- [ ] Support for additional build systems (npm, gradle, cargo, etc.)
