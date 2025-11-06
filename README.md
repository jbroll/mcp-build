# MCP Build Environment Service

A Model Context Protocol (MCP) server that provides secure access to build environments for software projects. This service allows AI assistants to interact with containerized build environments, execute builds, run tests, and manage git operations without requiring local installation of all dependencies.

## Features

- **Isolated Build Environment**: Docker-based environment with all build dependencies pre-installed
- **Safe Command Execution**: Validated commands to prevent accidental harmful operations
- **Git Operations**: Limited to safe operations (status, log, checkout, pull, branch, diff)
- **Build Management**: Execute make targets, run tests, and manage build artifacts
- **Environment Inspection**: Query installed tools, versions, and environment variables

## Available Commands

### `list`
List all available repositories with build environments.

**Example:**
```json
{
  "tool": "list"
}
```

### `make`
Run make command with specified arguments.

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
  "args": "test"
}
```

### `git`
Run git commands (limited to safe operations).

**Allowed operations:** status, log, checkout, pull, branch, diff, fetch, show

**Parameters:**
- `args` (required): Git command and arguments
- `repo` (optional): Repository name

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
  "args": "log --oneline -10"
}
```

### `ls`
List files and directories in the build environment.

**Parameters:**
- `args` (optional): Arguments to pass to ls (e.g., "-la", "-lh build/")
- `repo` (optional): Repository name

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
  "args": "-lh build/"
}
```

### `env`
Show build environment information including installed tools and versions.

**Parameters:**
- `repo` (optional): Repository name

**Example:**
```json
{
  "tool": "env"
}
```

## Installation

### Prerequisites

- Docker and Docker Compose
- Python 3.10 or higher
- pip

### Setup Steps

1. **Clone the repository:**
   ```bash
   cd mcp-build-environment
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -e .
   # Or for development:
   pip install -e ".[dev]"
   ```

3. **Build the Docker environment:**
   ```bash
   cd docker
   docker-compose build
   docker-compose up -d
   ```

4. **Clone your repository into the build environment:**
   ```bash
   docker-compose exec build-env git clone <your-repo-url> /build/<repo-name>
   ```

5. **Update configuration:**
   Edit `config/repos.json` to add your repositories:
   ```json
   {
     "default_repo": "velocipyde",
     "repos": {
       "velocipyde": {
         "path": "/build/velocipyde",
         "description": "Velocipyde project",
         "git_url": "https://github.com/jbroll/velocipyde.git",
         "default_branch": "main"
       }
     }
   }
   ```

## Configuration

### MCP Client Configuration

Add the server to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "build-environment": {
      "command": "python",
      "args": ["-m", "mcp_build_environment.server"],
      "env": {
        "BUILD_ENV_BASE": "/build"
      }
    }
  }
}
```

### Repository Configuration

Edit `config/repos.json` to configure available repositories:

```json
{
  "default_repo": "my-project",
  "repos": {
    "my-project": {
      "path": "/build/my-project",
      "description": "My awesome project",
      "git_url": "https://github.com/user/project.git",
      "default_branch": "main"
    },
    "another-project": {
      "path": "/build/another-project",
      "description": "Another project",
      "git_url": "https://github.com/user/another.git",
      "default_branch": "develop"
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
mcp-build-environment/
├── src/
│   └── mcp_build_environment/
│       ├── __init__.py
│       ├── server.py          # Main MCP server
│       ├── validators.py      # Argument validation
│       └── env_info.sh        # Environment info script
├── config/
│   └── repos.json             # Repository configuration
├── docker/
│   ├── Dockerfile             # Build environment image
│   └── docker-compose.yml     # Docker Compose config
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

### Checking Environment

```python
# Get environment info
await mcp.call_tool("env", {})

# Check specific directory
await mcp.call_tool("ls", {"args": "-la /build/velocipyde"})
```

## Troubleshooting

### Container not running
```bash
cd docker
docker-compose ps
docker-compose up -d
```

### Repository not found
Ensure the repository is cloned in the container:
```bash
docker-compose exec build-env ls -la /build/
```

### Permission issues
Ensure the build directory has proper permissions:
```bash
docker-compose exec build-env chmod -R 755 /build/
```

### Environment variable not set
Check that `BUILD_ENV_BASE` is set correctly:
```bash
docker-compose exec build-env echo $BUILD_ENV_BASE
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

- [ ] Support for multiple concurrent build environments
- [ ] Build caching and artifact management
- [ ] Integration with CI/CD systems
- [ ] Enhanced security controls
- [ ] Build history and logs
- [ ] Performance metrics and monitoring
