# Using the MCP Build Service

This document describes how to use a remote MCP build service instance for building and testing projects.

> **Note**: This documentation is also available directly from the service at `http://HOST:PORT/mcp-build.md`

## Quick Start

The MCP build service provides remote access to a build environment where you can:
- List available repositories
- Run builds and tests
- Execute git operations
- Inspect the build environment

## Service Configuration

When connecting to an MCP build service, you need:
- **Service URL**: The HTTP endpoint (e.g., `http://example.com:3344`)
- **Session Key**: Authentication token for secure access

### Fetching This Documentation

To view this documentation from a running service:

```bash
curl http://HOST:PORT/mcp-build.md
```

The documentation endpoint is public and does not require authentication.

## Available Operations

### 1. List Repositories

Find what repos are available on the build server:

```bash
curl "http://HOST:PORT/api/repos?key=SESSION_KEY"
```

**Response**: JSON list of available repositories with their paths.

### 2. Quick Operations (REST API)

Fast operations that complete in under 1 second:

#### Get Environment Info
```bash
curl "http://HOST:PORT/api/repos/REPO/env?key=SESSION_KEY"
```

Shows compiler versions, build tools, and system information.

#### List Files
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"args": "-la"}' \
  "http://HOST:PORT/api/repos/REPO/ls?key=SESSION_KEY"
```

#### Git Status/Branch/Log (Quick)
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"operation": "status", "args": ""}' \
  "http://HOST:PORT/api/repos/REPO/git/quick?key=SESSION_KEY"
```

**Allowed operations**: `status`, `branch`, `log`

### 3. Long Operations (Streaming API)

For operations that take time and produce output, use streaming endpoints:

#### Stream Build Output
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"args": "clean all"}' \
  -N \
  "http://HOST:PORT/stream/repos/REPO/make?key=SESSION_KEY"
```

**Use for**: `make` with any targets (build, test, clean, install, etc.)

#### Stream Git Operations
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"operation": "pull", "args": "origin main"}' \
  -N \
  "http://HOST:PORT/stream/repos/REPO/git?key=SESSION_KEY"
```

**Allowed operations**: `pull`, `fetch`, `diff`, `show`, `checkout`

### 4. Streaming Response Format

Streaming endpoints return Server-Sent Events (SSE):

```
data: {"type": "stdout", "line": "Compiling file.cpp..."}
data: {"type": "stderr", "line": "Warning: unused variable"}
data: {"type": "complete", "exit_code": 0}
```

**Event types**:
- `stdout` - Standard output line
- `stderr` - Standard error line
- `complete` - Command finished (includes `exit_code`)
- `error` - Error occurred (includes `message`)

## Common Workflows

### Building a Project

```bash
# 1. Check what repos are available
curl "http://HOST:PORT/api/repos?key=KEY"

# 2. Check git status
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "status", "args": ""}' \
  "http://HOST:PORT/api/repos/myproject/git/quick?key=KEY"

# 3. Clean and build
curl -X POST -H "Content-Type: application/json" \
  -d '{"args": "clean all"}' -N \
  "http://HOST:PORT/stream/repos/myproject/make?key=KEY"

# 4. Run tests
curl -X POST -H "Content-Type: application/json" \
  -d '{"args": "test"}' -N \
  "http://HOST:PORT/stream/repos/myproject/make?key=KEY"
```

### Debugging Build Failures

```bash
# 1. Check environment
curl "http://HOST:PORT/api/repos/myproject/env?key=KEY"

# 2. List build artifacts
curl -X POST -H "Content-Type: application/json" \
  -d '{"args": "-lh build/"}' \
  "http://HOST:PORT/api/repos/myproject/ls?key=KEY"

# 3. Check recent commits
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "log", "args": "--oneline -10"}' \
  "http://HOST:PORT/api/repos/myproject/git/quick?key=KEY"

# 4. View changes
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "diff", "args": "HEAD~1"}' -N \
  "http://HOST:PORT/stream/repos/myproject/git?key=KEY"
```

### Switching Branches

```bash
# 1. View branches
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "branch", "args": "-a"}' \
  "http://HOST:PORT/api/repos/myproject/git/quick?key=KEY"

# 2. Checkout branch (streaming - may take time)
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "checkout", "args": "feature-branch"}' -N \
  "http://HOST:PORT/stream/repos/myproject/git?key=KEY"

# 3. Pull latest
curl -X POST -H "Content-Type: application/json" \
  -d '{"operation": "pull", "args": ""}' -N \
  "http://HOST:PORT/stream/repos/myproject/git?key=KEY"
```

## Tips for AI Agents

1. **Always check available repos first** - Repository names must match exactly
2. **Use REST API for quick checks** - Faster than streaming for status/env queries
3. **Use streaming for builds** - Real-time feedback on long operations
4. **Parse SSE streams** - Look for `exit_code` in completion events
5. **Check exit codes** - Non-zero means failure
6. **Read stderr carefully** - Contains compilation errors and warnings

## Security Notes

- Keep session keys secret
- Operations are limited to safe commands (no `rm -rf`, etc.)
- Git operations restricted to read-only or safe operations
- Path traversal is blocked

## Troubleshooting

**"Repository not found"**: Use exact name from `/api/repos` list

**"Unauthorized"**: Check session key is correct and included in request

**Build fails**: Check environment with `/api/repos/REPO/env` to verify tools are available

**Connection timeout**: Streaming operations may take time - increase client timeout

## API Reference Summary

| Endpoint | Method | Purpose | Speed |
|----------|--------|---------|-------|
| `/api/repos` | GET | List repositories | Fast |
| `/api/repos/{repo}/env` | GET | Environment info | Fast |
| `/api/repos/{repo}/ls` | POST | List files | Fast |
| `/api/repos/{repo}/git/quick` | POST | Quick git ops | Fast |
| `/stream/repos/{repo}/make` | POST | Build/test | Streaming |
| `/stream/repos/{repo}/git` | POST | Git operations | Streaming |

For complete details, see the [full README](README.md) in the mcp-build repository.
