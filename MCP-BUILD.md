# MCP Build Service - Agent Guide

This document describes the intended workflow and usage patterns for AI agents working with the MCP Build Service.

## Overview

The MCP Build Service provides a dedicated build environment where you can check out branches, run builds, and execute tests without modifying the user's development workspace. The service is read-only from your perspective - you can read files and execute builds, but all source changes must be made by the user in their development environment.

## Available Tools

The service exposes these MCP tools (detailed schemas available via protocol discovery):

- **list** - Enumerate available repositories
- **git** - Execute safe git operations (status, log, branch, checkout, pull, fetch, diff, show)
- **make** - Run make targets (build, test, clean, install, etc.)
- **ls** - List directory contents and build artifacts
- **env** - Query installed build tools and their versions
- **read_file** - Read file contents (with optional line range for large files)

## Core Workflow: Branch Testing

The intended workflow separates development from testing:

### 1. User develops in their workspace

The user writes code in their development environment. This is NOT the build service environment.

### 2. User creates a feature branch and pushes

```bash
# User's workspace
git checkout -b feature/new-api
# ... make changes ...
git commit -m "Add new API endpoint"
git push origin feature/new-api
```

### 3. Agent checks out the branch on build service

Use the `git` tool to switch to the user's branch:

```python
# List available repositories
repos = await call_tool("list", {})

# Check current branch
status = await call_tool("git", {
    "repo": "my-project",
    "args": "branch --show-current"
})

# Fetch latest changes
await call_tool("git", {
    "repo": "my-project",
    "args": "fetch origin"
})

# Checkout the feature branch
await call_tool("git", {
    "repo": "my-project",
    "args": "checkout feature/new-api"
})

# Pull to ensure up-to-date
await call_tool("git", {
    "repo": "my-project",
    "args": "pull origin feature/new-api"
})
```

### 4. Agent runs builds and tests

Execute the build process to verify the changes:

```python
# Clean previous builds
await call_tool("make", {
    "repo": "my-project",
    "args": "clean"
})

# Build the project
build_result = await call_tool("make", {
    "repo": "my-project",
    "args": "all"
})

# Run tests
test_result = await call_tool("make", {
    "repo": "my-project",
    "args": "test"
})
```

### 5. Agent inspects results and reports back

Check build artifacts and provide feedback:

```python
# List build artifacts
artifacts = await call_tool("ls", {
    "repo": "my-project",
    "args": "-lh build/"
})

# Read test output or logs if needed
test_log = await call_tool("read_file", {
    "repo": "my-project",
    "path": "/absolute/path/to/my-project/test/results.log"
})

# Check git diff to understand changes
diff = await call_tool("git", {
    "repo": "my-project",
    "args": "diff main..feature/new-api"
})
```

Report findings to the user, including:
- Build success/failure
- Test results
- Any warnings or errors
- Build artifact details

### 6. User iterates based on feedback

If issues are found, the user fixes them in their workspace, commits, and pushes. Return to step 3.

## Best Practices

### Always check repository availability first

Before operating on a repository, verify it exists:

```python
repos = await call_tool("list", {})
if "my-project" not in [r["name"] for r in repos["repos"]]:
    # Handle missing repo
```

### Use explicit branch operations

Don't assume you're on the right branch. Always:
1. Fetch to get latest remote state
2. Checkout the specific branch
3. Pull to ensure up-to-date

### Read files efficiently

For large files, use line ranges:

```python
# Read specific sections
section = await call_tool("read_file", {
    "repo": "my-project",
    "path": "/absolute/path/to/large-file.cpp",
    "start_line": 100,
    "end_line": 200
})
```

### Check environment before diagnosing build failures

If builds fail, check what tools are available:

```python
env_info = await call_tool("env", {
    "repo": "my-project"
})
```

This shows compiler versions, make version, and other installed tools that may affect the build.

### Parse build output carefully

Build and test output appears in the tool results. Look for:
- Exit codes (non-zero = failure)
- Error messages (often in stderr)
- Warning counts
- Test statistics (passed/failed/skipped)

### Handle large diffs intelligently

When reviewing changes between branches, diffs can be large. Consider:
- Using `git log` first to understand commit history
- Checking `git diff --stat` for a summary before full diff
- Reading specific files that changed rather than full diffs

## Common Patterns

### Verify a pushed branch

```python
# User: "I just pushed feature-xyz, can you verify it builds?"

# 1. List repos to confirm access
repos = await call_tool("list", {})

# 2. Fetch latest
await call_tool("git", {"repo": "project", "args": "fetch origin"})

# 3. Checkout branch
await call_tool("git", {"repo": "project", "args": "checkout feature-xyz"})

# 4. Pull to ensure up-to-date
await call_tool("git", {"repo": "project", "args": "pull"})

# 5. Build
result = await call_tool("make", {"repo": "project", "args": "all"})

# 6. Test
test_result = await call_tool("make", {"repo": "project", "args": "test"})

# 7. Report findings
```

### Compare branches

```python
# User: "What changed between main and my feature branch?"

# 1. Ensure both branches are up-to-date
await call_tool("git", {"repo": "project", "args": "fetch origin"})

# 2. Get commit history
log = await call_tool("git", {
    "repo": "project",
    "args": "log --oneline main..feature-branch"
})

# 3. Get diff summary
stat = await call_tool("git", {
    "repo": "project",
    "args": "diff --stat main..feature-branch"
})

# 4. Get full diff if needed
diff = await call_tool("git", {
    "repo": "project",
    "args": "diff main..feature-branch"
})
```

### Debug build failure

```python
# User: "The build is failing on my branch"

# 1. Checkout the branch
await call_tool("git", {"repo": "project", "args": "checkout failing-branch"})
await call_tool("git", {"repo": "project", "args": "pull"})

# 2. Check environment
env = await call_tool("env", {"repo": "project"})

# 3. Try building with verbose output
result = await call_tool("make", {"repo": "project", "args": "clean all"})

# 4. Read relevant source files if needed
if "undefined reference" in result:
    # Read the file mentioned in error
    source = await call_tool("read_file", {
        "repo": "project",
        "path": "/absolute/path/to/problematic/file.cpp"
    })

# 5. Check git log for recent changes
recent = await call_tool("git", {
    "repo": "project",
    "args": "log --oneline -10"
})

# 6. Provide analysis and suggestions
```

## What NOT to do

**Don't try to modify source files** - You have read-only access. Suggest changes to the user instead.

**Don't assume branch state** - Always explicitly checkout and pull the branch you want to test.

**Don't run destructive commands** - The service blocks them, but don't attempt `git reset --hard`, `rm -rf`, etc.

**Don't use relative paths for read_file** - Always use absolute paths within the repository.

**Don't bypass the workflow** - The separation between development (user) and testing (agent) is intentional.

## Tips for Effective Usage

1. **Be proactive about branch management** - Fetch and pull frequently to stay synchronized
2. **Read selectively** - Use line ranges for large files to reduce data transfer
3. **Interpret build output** - Don't just report pass/fail, explain what the errors mean
4. **Suggest specific fixes** - Based on build errors, provide actionable suggestions to the user
5. **Track multiple repos** - If a project spans multiple repos, coordinate branch checkouts across them
6. **Use git history** - Understanding recent commits helps diagnose issues

## Security Notes

- All git operations are restricted to safe commands (no force-push, reset --hard, etc.)
- No arbitrary command execution is allowed
- Path traversal attempts are blocked
- You cannot write files or modify the repository
- All operations are logged for audit purposes

## Getting Help

If the MCP Build Service is not available or not responding:
1. Ask the user to verify the service is running
2. Check if the repository exists in the configured directory
3. Confirm the MCP client configuration is correct
4. Verify network connectivity for remote HTTP mode

For detailed API specifications, use the MCP protocol's tool discovery mechanisms rather than relying solely on this document.
