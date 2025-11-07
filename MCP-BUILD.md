# MCP Build Service

This is a standard MCP server providing isolated build and test environments for software development workflows.

## Purpose

The MCP Build Service provides a dedicated build environment separate from your development workspace. You can check out branches, run builds, and execute tests without modifying the user's working directory. All operations are read-only from the agent perspective - you can read files and execute builds, but cannot modify source code.

## Service Model: Development/Test Separation

This service implements a clear separation between development and testing:

- **Development (User)**: User writes code, commits changes, pushes branches to remote
- **Testing (Agent)**: Agent fetches branches in isolated environment, runs builds/tests, reports results
- **Iteration**: User fixes issues based on agent feedback, pushes again

This separation ensures the user's development workspace remains under their control while agents can validate changes in a clean, reproducible environment.

## Available Operations

All operations follow standard MCP tool protocol. Use MCP discovery (`tools/list`) for complete schemas and parameter details.

**Core capabilities:**
- **Repository enumeration** - List available repositories
- **Git operations** - Safe subset: status, log, diff, show, branch, checkout, fetch, pull
- **Build execution** - Run make targets (build, test, clean, install, etc.)
- **File reading** - Read file contents with optional line range for large files
- **Directory listing** - List directory contents and build artifacts
- **Environment introspection** - Query installed build tools and versions

## Typical Workflow

### Branch Verification
User pushes a branch and asks agent to verify it builds correctly:

1. Agent lists repositories to confirm access
2. Agent fetches latest changes from remote
3. Agent checks out the user's branch
4. Agent pulls to ensure fully up-to-date
5. Agent runs clean build
6. Agent executes tests
7. Agent reports results with analysis

### Build Debugging
User reports a failing build and asks for diagnosis:

1. Agent checks out the failing branch
2. Agent checks environment (compiler versions, tools)
3. Agent runs build and captures output
4. Agent reads relevant source files if needed
5. Agent checks git log for recent changes
6. Agent analyzes errors and suggests specific fixes

### Branch Comparison
User asks what changed between branches:

1. Agent fetches latest state for both branches
2. Agent gets commit history between branches
3. Agent gets diff summary statistics
4. Agent provides full diff if needed
5. Agent highlights significant changes

## Best Practices

### Branch Management
- **Always fetch first** - Don't assume local state matches remote
- **Explicit checkout** - Don't assume you're on the correct branch
- **Pull after checkout** - Ensure fully synchronized with remote

### File Operations
- **Use line ranges** - For large files, read specific sections (start_line, end_line)
- **Absolute paths** - The read_file tool requires absolute paths within repository
- **Read selectively** - Don't read entire codebases, target relevant files

### Build Analysis
- **Check environment first** - When debugging failures, verify tool versions
- **Parse output intelligently** - Look for exit codes, error patterns, warning counts
- **Provide context** - Don't just report pass/fail, explain what errors mean
- **Suggest specific fixes** - Based on build output and code inspection

### Git Operations
- **Use diff --stat** - Get summary before fetching full diffs
- **Check log first** - Understand commit history before diving into changes
- **Compare against base** - Use branch..branch syntax for comparisons

## Important Constraints

### Read-Only Access
You **cannot** modify source files. Your role is to:
- Run builds and tests
- Read and analyze code
- Suggest changes to the user
- Provide debugging insights

The user makes all source modifications in their development environment.

### Safe Git Commands Only
Destructive git operations are blocked:
- No `git reset --hard`
- No `git push --force`
- No `git clean -fd`
- No rebase or history modification

Only read operations and safe branch management are allowed.

### Path Requirements
- File reads require absolute paths
- Paths must be within configured repository directories
- Path traversal attempts are blocked

### Audit Trail
All operations are logged for security and debugging purposes.

## Effective Usage Tips

1. **Be proactive about synchronization** - Fetch and pull frequently to stay current
2. **Interpret, don't just report** - Explain what build errors mean and why they occurred
3. **Read strategically** - Use line ranges and target specific files rather than bulk reading
4. **Track repository state** - Know which branch you're on and when it was last updated
5. **Consider multiple repositories** - Projects may span multiple repos; coordinate branch operations
6. **Use git history** - Recent commits often explain current build state

## What to Avoid

- **Don't assume branch state** - Always explicitly checkout and pull
- **Don't try to modify files** - Suggest changes to the user instead
- **Don't use relative paths** - Always use absolute paths for file operations
- **Don't ignore exit codes** - Non-zero exit codes indicate failures even if output looks normal
- **Don't bypass the workflow** - The dev/test separation is intentional and valuable

## MCP Protocol Compliance

This service implements standard MCP protocol:
- Tool discovery via `tools/list` provides complete schemas
- All operations use standard MCP tool calling convention
- Results follow MCP response format
- Authentication via session key (if configured)

Tool schemas, parameter types, and detailed specifications are available through MCP discovery mechanisms. This document focuses on conceptual usage patterns and workflow guidance.

## Troubleshooting

If the service is not responding:
- Verify the service is running on the configured host/port
- Check that repositories exist in the configured directory
- Confirm MCP client configuration includes correct endpoint and session key
- Verify network connectivity for remote HTTP/SSE mode

For detailed operational status, check service logs on the host system.
