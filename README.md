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
      "args": ["-m", "server"],
      "env": {
        "MCP_BUILD_REPOS_DIR": "/home/user/projects"
      }
    }
  }
}
```

**Configuration Options:**
- `MCP_BUILD_REPOS_DIR`: Directory containing your git repositories (defaults to current working directory)

The service will automatically discover all git repositories (directories containing `.git`) in the configured directory.

### Example Configuration for Different Setups

**Single Project:**
```json
{
  "mcpServers": {
    "mcp-build": {
      "command": "python",
      "args": ["-m", "server"],
      "env": {
        "MCP_BUILD_REPOS_DIR": "/home/user/my-project/.."
      }
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
      "env": {
        "MCP_BUILD_REPOS_DIR": "/home/user/workspace"
      }
    }
  }
}
```

## Security

This service implements basic security measures to prevent accidents:

- **Path Traversal Protection**: Blocks `../` patterns and absolute paths
- **Command Injection Protection**: Blocks pipes, redirects, and command substitution
- **Git Command Whitelist**: Only allows safe git operations
- **Argument Validation**: Validates all command arguments before execution

**Important:** These are safety measures to prevent accidents, not comprehensive security controls. Do not expose this service to untrusted users or networks.

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
├── docker/                    # Optional Docker setup
│   ├── Dockerfile
│   └── docker-compose.yml
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
1. Your repositories are in the directory specified by `MCP_BUILD_REPOS_DIR`
2. Each repository has a `.git` directory
3. The service has read permissions for the directory

```bash
# Verify repositories are git repos
ls -la /path/to/repos/*/.git

# Check environment variable
echo $MCP_BUILD_REPOS_DIR
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
