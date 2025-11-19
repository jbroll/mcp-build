# Branch Isolation Implementation Plan

## Problem Statement

Currently, the MCP Build Service operates directly on repositories in their current state. When multiple clients (AI agents, users, or sessions) access the same repository:
- They share the same working directory
- Git operations can conflict (e.g., one client checks out a different branch)
- Build operations might interfere with each other
- No isolation between concurrent sessions

## Goals

1. **Session Isolation**: Each client session should have its own isolated workspace
2. **Branch-Based Isolation**: Use git branches or worktrees to provide isolation
3. **Safety**: Prevent one session from disrupting another
4. **Clean Cleanup**: Automatically clean up session workspaces when done
5. **Backward Compatibility**: Maintain existing API/tool interfaces

## Implementation Options

### Option 1: Git Worktrees (Recommended)

**How it works:**
- When a new MCP session starts, create a git worktree for that session
- Each worktree is a separate checkout of a branch in its own directory
- Sessions operate in their isolated worktree directories
- Cleanup removes the worktree when the session ends

**Pros:**
- True filesystem isolation - no shared working directory
- Multiple branches can be checked out simultaneously
- Git handles most of the complexity
- Build artifacts don't interfere between sessions

**Cons:**
- Requires disk space for each worktree
- Slightly more complex setup
- Need to handle worktree lifecycle

**Implementation Details:**
```python
# On session initialization
session_id = generate_session_id()  # Could use existing SESSION_KEY
worktree_path = REPOS_BASE_DIR / repo_name / f".worktrees/{session_id}"
branch_name = f"session/{session_id}"

# Create worktree with new branch
subprocess.run([
    "git", "worktree", "add",
    str(worktree_path),
    "-b", branch_name
], cwd=repo_path)

# All operations for this session use worktree_path as cwd
```

### Option 2: Session Branches (Simpler)

**How it works:**
- Each session creates a dedicated branch (e.g., `session/abc123`)
- Session starts by checking out its branch
- All git operations happen on that branch
- Still share the same working directory (less isolation)

**Pros:**
- Simpler to implement
- Less disk usage
- Easier cleanup (just delete the branch)

**Cons:**
- Working directory is still shared (potential file conflicts)
- Can't have concurrent builds in the same repo
- Git checkout operations block each other
- Build artifacts shared between sessions

**Not Recommended** for true isolation, but could be a stepping stone.

### Option 3: Repository Clones

**How it works:**
- Clone the repository for each session into a temporary location
- Session operates on its own complete clone

**Pros:**
- Complete isolation
- Simple to understand and implement

**Cons:**
- High disk usage (full clone per session)
- Slower startup (clone operation)
- More complex to sync changes back to main repo

### Option 4: Docker Containers (Advanced)

**How it works:**
- Each session runs in its own Docker container
- Container has a mounted clone/worktree of the repository
- Complete process-level isolation

**Pros:**
- Maximum isolation
- Can enforce resource limits
- Clean environment per session

**Cons:**
- Requires Docker
- More complex infrastructure
- Higher overhead

## Recommended Approach: Git Worktrees

**Architecture:**

```
repos/
  my-project/           # Main repository
    .git/
    .worktrees/         # Session worktrees
      session-abc123/   # Worktree for session abc123
        (full checkout on session/abc123 branch)
      session-def456/   # Worktree for session def456
        (full checkout on session/def456 branch)
```

**Implementation Steps:**

### 1. Session Management

Add session tracking to `BuildEnvironmentServer`:

```python
class BuildEnvironmentServer:
    def __init__(self):
        self.server = Server("mcp-build")
        self.repos: Dict[str, Dict[str, str]] = {}
        self.session_id = generate_session_id()  # Unique per server instance
        self.worktrees: Dict[str, Path] = {}  # repo_name -> worktree_path
```

### 2. Worktree Creation

```python
async def setup_session_worktree(self, repo_name: str) -> Path:
    """Create a git worktree for this session"""
    if repo_name in self.worktrees:
        return self.worktrees[repo_name]

    repo_path = self.get_repo_path(repo_name)
    worktree_dir = repo_path / ".worktrees"
    worktree_dir.mkdir(exist_ok=True)

    worktree_path = worktree_dir / self.session_id
    branch_name = f"session/{self.session_id}"

    # Check if worktree already exists (from previous crashed session)
    if worktree_path.exists():
        # Try to remove stale worktree
        await self.cleanup_worktree(repo_name)

    # Create new worktree
    try:
        # Get current branch as base
        result = await self.run_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path
        )
        base_branch = result.strip()

        # Create worktree with new branch based on current
        await self.run_command(
            ["git", "worktree", "add", str(worktree_path),
             "-b", branch_name, base_branch],
            cwd=repo_path
        )

        self.worktrees[repo_name] = worktree_path
        logger.info(f"Created worktree for session {self.session_id} at {worktree_path}")

        return worktree_path

    except Exception as e:
        logger.error(f"Failed to create worktree: {e}")
        raise
```

### 3. Update Command Execution

Modify `get_repo_path` to return worktree path when available:

```python
def get_repo_path(self, repo_name: str) -> Path:
    """Get the path to a repository (worktree if available, else main repo)"""
    if not repo_name:
        raise ValueError("Repository name is required")
    if repo_name not in self.repos:
        raise ValueError(f"Unknown repository: {repo_name}")

    # Use worktree if available for this session
    if repo_name in self.worktrees:
        return self.worktrees[repo_name]

    # Otherwise use main repository
    return Path(self.repos[repo_name]["path"])
```

### 4. Cleanup on Shutdown

```python
async def cleanup_worktree(self, repo_name: str):
    """Remove session worktree"""
    if repo_name not in self.worktrees:
        return

    worktree_path = self.worktrees[repo_name]
    repo_path = Path(self.repos[repo_name]["path"])
    branch_name = f"session/{self.session_id}"

    try:
        # Remove worktree
        await self.run_command(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            cwd=repo_path
        )

        # Delete the session branch (optional - could keep for debugging)
        await self.run_command(
            ["git", "branch", "-D", branch_name],
            cwd=repo_path
        )

        del self.worktrees[repo_name]
        logger.info(f"Cleaned up worktree for session {self.session_id}")

    except Exception as e:
        logger.warning(f"Failed to cleanup worktree: {e}")

async def cleanup_all_worktrees(self):
    """Cleanup all session worktrees"""
    for repo_name in list(self.worktrees.keys()):
        await self.cleanup_worktree(repo_name)
```

Add cleanup to server shutdown:

```python
async def run(self):
    """Start the MCP server with stdio transport"""
    await self.discover_repos()
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP Build Server starting with stdio transport...")
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )
    finally:
        await self.cleanup_all_worktrees()
```

### 5. Configuration Options

Add command-line flags to control behavior:

```python
parser.add_argument(
    "--enable-isolation",
    action="store_true",
    help="Enable branch isolation using git worktrees (one worktree per session)"
)

parser.add_argument(
    "--isolation-base-branch",
    default=None,
    help="Base branch to use for session branches (default: current branch)"
)

parser.add_argument(
    "--keep-session-branches",
    action="store_true",
    help="Keep session branches after cleanup (for debugging)"
)
```

### 6. Session ID Generation

Use the existing session key or generate a new unique identifier:

```python
def generate_session_id() -> str:
    """Generate unique session identifier"""
    # Use existing SESSION_KEY if available (for HTTP mode)
    if SESSION_KEY:
        # Hash the session key to create a shorter ID
        import hashlib
        return hashlib.sha256(SESSION_KEY.encode()).hexdigest()[:12]

    # Otherwise generate a random ID (for stdio mode)
    import secrets
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"{timestamp}-{random_suffix}"
```

## Testing Strategy

### Unit Tests

1. Test worktree creation
2. Test worktree cleanup
3. Test operation in isolated worktree
4. Test concurrent sessions (multiple server instances)

### Integration Tests

```python
@pytest.mark.asyncio
async def test_isolated_sessions():
    """Test that two sessions work independently"""
    # Create two server instances with different session IDs
    server1 = BuildEnvironmentServer()
    server1.session_id = "session-001"

    server2 = BuildEnvironmentServer()
    server2.session_id = "session-002"

    # Both create worktrees for same repo
    await server1.discover_repos()
    await server2.discover_repos()

    repo_name = list(server1.repos.keys())[0]

    worktree1 = await server1.setup_session_worktree(repo_name)
    worktree2 = await server2.setup_session_worktree(repo_name)

    # Worktrees should be different
    assert worktree1 != worktree2
    assert worktree1.exists()
    assert worktree2.exists()

    # Operations should be isolated
    # Session 1 creates a file
    (worktree1 / "file1.txt").write_text("session 1")

    # Session 2 should not see it
    assert not (worktree2 / "file1.txt").exists()

    # Cleanup
    await server1.cleanup_all_worktrees()
    await server2.cleanup_all_worktrees()

    assert not worktree1.exists()
    assert not worktree2.exists()
```

## Migration Plan

### Phase 1: Add Feature Flag (Week 1)
- Implement worktree creation/cleanup
- Add `--enable-isolation` flag (default: disabled)
- Test with existing clients (should work unchanged)

### Phase 2: Testing & Documentation (Week 2)
- Add comprehensive tests
- Document the feature in README
- Test with real AI agent workloads

### Phase 3: Default Enable (Week 3)
- Make isolation enabled by default
- Provide `--disable-isolation` flag for backward compatibility
- Monitor for issues

### Phase 4: Remove Legacy Mode (Week 4+)
- Once stable, remove non-isolated mode
- Simplify code

## Security Considerations

1. **Path Traversal**: Ensure worktree paths cannot escape repos directory
2. **Disk Space**: Implement monitoring/limits on worktree creation
3. **Stale Worktrees**: Handle crashed sessions that don't cleanup
4. **Branch Naming**: Ensure session IDs are safe for branch names

## Performance Considerations

1. **Disk Usage**: Each worktree duplicates working files (~= repo size)
2. **Creation Time**: `git worktree add` is fast (seconds)
3. **Cleanup Time**: Should be quick but do it asynchronously

## Alternative: Lazy Worktree Creation

Instead of creating worktrees at session start, create them on-demand when first command is executed:

```python
async def get_repo_path(self, repo_name: str) -> Path:
    """Get the path to a repository (creates worktree on first access)"""
    if not repo_name:
        raise ValueError("Repository name is required")
    if repo_name not in self.repos:
        raise ValueError(f"Unknown repository: {repo_name}")

    # Create worktree on first access if isolation is enabled
    if ENABLE_ISOLATION and repo_name not in self.worktrees:
        await self.setup_session_worktree(repo_name)

    # Use worktree if available
    if repo_name in self.worktrees:
        return self.worktrees[repo_name]

    # Otherwise use main repository
    return Path(self.repos[repo_name]["path"])
```

This delays the cost until needed and avoids creating worktrees for repos that aren't accessed.

## Open Questions

1. **Should we sync changes back to main branch?**
   - Pro: Preserves work from crashed sessions
   - Con: Automatic merging could cause conflicts
   - Recommendation: Let users explicitly merge if needed

2. **What about HTTP mode with multiple clients?**
   - Each client connection might need its own session ID
   - Current implementation uses one SESSION_KEY per server
   - May need to generate per-connection session IDs

3. **Should worktrees be in .worktrees/ or somewhere else?**
   - Inside repo: Easy to find, but clutters repo
   - Outside repo (e.g., /tmp): Cleaner, but harder to track
   - Recommendation: Inside repo with .gitignore entry

4. **How to handle long-lived sessions?**
   - HTTP mode servers might run for days/weeks
   - Should we periodically cleanup old worktrees?
   - Add max-age for worktrees?

## Summary

**Recommended Implementation**: Git Worktrees with lazy creation
- Most robust isolation
- Good performance characteristics
- Clean cleanup semantics
- Backward compatible with feature flag

**Timeline**: 2-4 weeks for full implementation and testing

**Risks**:
- Disk space usage for multiple concurrent sessions
- Stale worktrees from crashed sessions (mitigated by cleanup on start)
