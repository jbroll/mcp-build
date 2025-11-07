# MCP Build Service

A secure build and test environment that AI assistants can access remotely. This service allows AI agents like Claude to execute builds, run tests, and manage git operations on your repositories without direct file system access.

## What is this?

MCP Build Service is a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that provides AI assistants with controlled access to software build operations. Instead of giving an AI direct access to your file system, you provide access to a safe, sandboxed build environment where it can:

- Check out different git branches
- Run builds and tests
- Inspect build artifacts and test results
- Read files and check git status
- All without write access to your source code

## Why use it?

**Separation of concerns**: Your main development environment stays untouched while the AI works in a dedicated build environment.

**Safety**: The service only allows safe operations - no destructive commands, no arbitrary code execution, just builds and tests.

**Remote builds**: Perfect for CI/CD integration, container-based builds, or accessing powerful build machines remotely.

**Multi-repository support**: Work with multiple projects from a single service instance.

## Quick Start

### Installation

```bash
# Clone and install
git clone <this-repo-url>
cd mcp-build
pip install -e .
```

### Set up your build environment

Place your git repositories in a directory where you want builds to happen:

```bash
# Example structure
/home/builder/repos/
├── my-app/           # git repository
├── my-library/       # git repository
└── another-project/  # git repository
```

### Start the service

**For local use with Claude Desktop:**

```bash
cd /home/builder/repos
mcp-build
```

**For remote access:**

```bash
cd /home/builder/repos
mcp-build --transport http --host 0.0.0.0 --port 3344
```

The service will display a session key - save this for authentication.

### Configure your AI assistant

**Claude Desktop (local stdio):**

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "build": {
      "command": "mcp-build",
      "cwd": "/home/builder/repos"
    }
  }
}
```

**Claude Desktop (remote HTTP):**

```json
{
  "mcpServers": {
    "build": {
      "url": "http://your-build-server:3344/sse?key=YOUR_SESSION_KEY"
    }
  }
}
```

Restart Claude Desktop, and your AI assistant will now have access to the build service.

## Using with an AI Assistant

Once configured, you can ask your AI assistant to:

**Check what repositories are available:**
> "List the available repositories on the build server"

**Run builds and tests:**
> "Checkout the feature-123 branch in my-app and run the tests"

**Debug build failures:**
> "The tests are failing - can you check the build output and see what's wrong?"

**Verify changes:**
> "I just pushed some changes to the api-refactor branch. Can you build it and make sure all tests pass?"

**Compare branches:**
> "Show me the diff between main and feature-123 in my-app"

The AI will use the build service automatically through the MCP protocol.

## How it works

1. **You write code** in your development environment
2. **You commit and push** to a branch in git
3. **AI checks out the branch** on the build service
4. **AI runs builds/tests** and reports results
5. **You review and iterate** based on feedback

Your source files are never modified by the AI - it only reads and builds.

## Available Tools

The service provides these operations (used automatically by the AI):

- **list** - Discover available repositories
- **git** - Safe git operations (status, log, checkout, pull, fetch, diff, show, branch)
- **make** - Run make targets (build, test, clean, etc.)
- **ls** - List files and directories
- **env** - Check installed build tools and versions
- **read_file** - Read file contents from repositories

## Command-Line Options

```bash
# Show all options
mcp-build --help

# Local stdio mode (default)
mcp-build

# HTTP mode with auto-generated session key
mcp-build --transport http

# HTTP mode with custom session key
mcp-build --transport http --session-key YOUR_KEY

# Custom host and port
mcp-build --transport http --host 0.0.0.0 --port 8080
```

## Security

The service implements multiple security layers:

**Command validation:**
- Blocks dangerous operations (rm, dd, format, etc.)
- Prevents path traversal attempts
- Restricts git to safe operations only
- No arbitrary command execution

**Authentication (HTTP mode):**
- Session key required for all requests
- Constant-time comparison prevents timing attacks
- Keys can be auto-generated or provided

**Best practices:**
- Use stdio transport for local, trusted scenarios
- Use HTTP transport with TLS/reverse proxy for remote access
- Restrict network access with firewalls
- Rotate session keys regularly
- Don't expose to untrusted networks

## Troubleshooting

**AI says "no repositories found":**
- Make sure you started mcp-build in the parent directory of your repos
- Verify each repository has a `.git` directory
- Restart Claude Desktop after configuration changes

**"Repository not found" errors:**
- Repository names must match directory names exactly
- Use the `list` tool to see available names

**Build tools not found:**
- Run `mcp-build` and ask the AI to check the environment
- Install missing tools (gcc, make, cmake, etc.) on the build machine

**Permission denied:**
- Ensure the user running mcp-build has read/execute access to repositories
- Check file permissions: `ls -la /home/builder/repos`

**Connection issues (HTTP mode):**
- Verify the session key is correct
- Check firewall rules allow the port
- Test with curl: `curl -H "Authorization: Bearer KEY" http://host:3344/api/repos`

## Advanced Configuration

### Multiple Project Directories

You can run multiple service instances for different project groups:

```json
{
  "mcpServers": {
    "build-frontend": {
      "command": "mcp-build",
      "cwd": "/home/builder/frontend-projects"
    },
    "build-backend": {
      "command": "mcp-build",
      "cwd": "/home/builder/backend-projects"
    }
  }
}
```

### Docker/Container Setup

```bash
# Run in a container for isolation
docker run -v /host/repos:/repos -w /repos -p 3344:3344 \
  mcp-build-image mcp-build --transport http --host 0.0.0.0
```

### Reverse Proxy for TLS

Use nginx or caddy to add HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name build.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:3344;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

## API Access

While the MCP protocol is the primary interface, the service also provides REST and streaming APIs for direct integration:

**REST API** - Quick operations (list repos, get status, read files)
**Streaming API** - Long operations with real-time output (builds, tests)

See [MCP-BUILD.md](MCP-BUILD.md) for API details.

## Development

### Project Structure

```
mcp-build/
├── src/
│   ├── server.py         # Main MCP server
│   ├── validators.py     # Security validation
│   └── helpers/          # Helper modules
├── tests/                # Test suite
├── README.md            # This file (user docs)
└── MCP-BUILD.md         # Agent workflow docs
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

### Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- [Open an issue](https://github.com/your-org/mcp-build/issues) for bug reports
- [MCP Documentation](https://modelcontextprotocol.io) for protocol details
- [Claude Code Documentation](https://docs.claude.com) for AI integration help
