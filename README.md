# MCP Build Service

A Model Context Protocol (MCP) server that provides access to git repositories for build and test operations. This allows AI assistants to run builds, execute tests, and inspect git repositories on your behalf.

## What does it do?

This service provides AI assistants with tools to:

- List available git repositories
- Execute git commands (status, log, checkout, pull, fetch, diff, show, branch)
- Run make targets (build, test, clean, etc.)
- List directory contents
- Read files from repositories
- Query installed build tools and versions

The service runs in a directory containing git repositories and exposes them through the MCP protocol.

## Use case

The typical workflow is:

1. You develop code in your workspace and push to a git branch
2. AI assistant uses this service to checkout your branch in a build environment
3. AI assistant runs builds and tests on that branch
4. AI assistant reports results back to you
5. You make fixes based on feedback and repeat

This separates your development environment from the build/test environment that the AI uses.

## Installation

```bash
git clone <this-repo-url>
cd mcp-build
pip install -e .
```

## Setup

Create or designate a directory containing your git repositories:

```bash
/path/to/build-area/
├── project-one/    # git repository
├── project-two/    # git repository
└── project-three/  # git repository
```

## Usage

### Local mode (stdio)

Start the service in the directory containing your repositories:

```bash
cd /path/to/build-area
mcp-build
```

Configure Claude Desktop to use it. Add to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "build": {
      "command": "mcp-build",
      "cwd": "/path/to/build-area"
    }
  }
}
```

### Remote mode (HTTP)

Start with HTTP transport:

```bash
cd /path/to/build-area
mcp-build --transport http --host 0.0.0.0 --port 3344
```

The service generates a session key on startup. Configure Claude Desktop with:

```json
{
  "mcpServers": {
    "build": {
      "url": "http://your-server:3344/sse?key=SESSION_KEY"
    }
  }
}
```

## Command-line options

```bash
mcp-build --help                  # Show all options
mcp-build                         # stdio mode (default)
mcp-build --transport http        # HTTP mode, auto-generate session key
mcp-build --transport http --session-key YOUR_KEY
mcp-build --transport http --host 0.0.0.0 --port 8080
```

## Available tools

The service exposes these MCP tools:

- **list** - List available repositories
- **git** - Execute git commands (limited to: status, log, checkout, pull, branch, diff, fetch, show)
- **make** - Run make with specified arguments (executes whatever is in the Makefile)
- **ls** - List files and directories
- **env** - Show installed tools and versions
- **read_file** - Read file contents (with optional line range for large files)

## Security considerations

**Git operations:** The service restricts git commands to a whitelist (status, log, checkout, pull, branch, diff, fetch, show). Dangerous operations like `git push --force` or `git reset --hard` are blocked.

**Command validation:** The service blocks path traversal patterns (`../`) and some command injection patterns (pipes, redirects, command substitution).

**Make targets:** The service runs whatever make targets you specify. These execute the commands defined in the repository's Makefile, which could be anything. The service does not sandbox or restrict what Makefiles can do.

**Authentication (HTTP mode):** Requires a session key passed as a Bearer token or query parameter. Keys can be auto-generated or provided.

**Recommendation:** Run this service in an environment appropriate for build operations (e.g., a dedicated build VM, container, or CI environment). It validates some inputs but does not provide comprehensive sandboxing.

## Example usage with AI assistant

Once configured, you can ask your AI assistant:

- "List the available repositories"
- "Checkout the feature-branch in my-project and run make test"
- "What's the build output from the latest commit on main?"
- "Show me the diff between main and feature-branch"

The AI will use the service automatically through MCP tool calls.

## Troubleshooting

**No repositories found**
- Verify you started mcp-build in the parent directory of your git repos
- Check each directory has a `.git` subdirectory

**Repository not found**
- Repository names must match directory names exactly
- Use the list tool to see available names

**Build failures**
- Use the env tool to check installed build tools
- Verify the Makefile exists and has the target you're trying to run

**Connection issues (HTTP mode)**
- Check the session key matches what the service printed at startup
- Verify firewall allows the port
- Test with curl: `curl -H "Authorization: Bearer KEY" http://host:port/api/repos`

## HTTP API

In addition to the MCP protocol, the service provides HTTP endpoints:

**Quick operations (REST):**
- `GET /api/repos` - List repositories
- `GET /api/repos/{repo}/env` - Environment info
- `POST /api/repos/{repo}/ls` - List files
- `POST /api/repos/{repo}/read_file` - Read file contents
- `POST /api/repos/{repo}/git/quick` - Quick git operations (status, branch, log)

**Long operations (streaming SSE):**
- `POST /stream/repos/{repo}/make` - Stream build output
- `POST /stream/repos/{repo}/git` - Stream git operations (pull, fetch, diff, show, checkout)

All endpoints require authentication via session key.

## Development

Run tests:
```bash
pip install -e ".[dev]"
pytest tests/
```

Project structure:
```
mcp-build/
├── src/
│   ├── server.py       # Main server
│   └── validators.py   # Input validation
├── tests/              # Tests
├── README.md          # This file (user docs)
└── MCP-BUILD.md       # Agent usage guide
```

## License

MIT License
