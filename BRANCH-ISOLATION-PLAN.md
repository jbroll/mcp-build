# Branch Isolation Architecture Plan

## Overview

Modify mcp-build to support simultaneous builds on different branches by using separate repository checkouts per branch. This enables true parallelism where multiple users can trigger builds on different branches without conflicts.

## Current Architecture

- `REPOS_BASE_DIR = Path(os.getcwd())` - discovers all repos in current working directory
- Single working directory with repo discovery at startup
- `repo` parameter required in all API calls but only selects from discovered repos
- No branch isolation - all operations happen in the same working directory

## Proposed Architecture

### Branch as Required Parameter

Add `branch` as a required parameter to all API operations:
- MakeStreamRequest
- GitStreamRequest
- GitQuickRequest
- LsRequest
- ReadFileRequest
- All MCP tool schemas (make, git, ls, read_file, env)

### Checkout Directory Structure

Use git worktrees for efficient branch isolation:

```
~/build-workspaces/
  ├── my-app/
  │   ├── .git/              # Main git repository (bare or regular)
  │   ├── main/              # Worktree for main branch
  │   ├── feature-x/         # Worktree for feature-x branch
  │   └── bugfix-123/        # Worktree for bugfix-123 branch
  └── another-repo/
      ├── .git/
      └── develop/
```

### Lazy Checkout Management

Create and manage checkouts on-demand:

1. **First request** for `repo=my-app, branch=feature-x`:
   - Check if `~/workspaces/my-app/.git/` exists
   - If not, clone the repository
   - Create worktree: `git worktree add feature-x origin/feature-x`

2. **Subsequent requests**:
   - Verify worktree exists
   - Update: `git fetch && git reset --hard origin/feature-x`
   - Return path to worktree

3. **Optional cleanup**:
   - LRU cache to remove old/unused branch checkouts
   - TTL-based cleanup (e.g., remove worktrees unused for 7 days)

## Benefits

✅ **True parallelism**: Multiple users can build different branches simultaneously
✅ **No checkout conflicts**: Each branch has its own working directory
✅ **Cleaner state management**: No global "is a build running?" tracking needed
✅ **Better isolation**: Failed builds on one branch don't affect others
✅ **Disk efficient**: Git worktrees share objects, only duplicate working trees

## Trade-offs

### Disk Space
- **Issue**: Multiple checkouts consume disk space
- **Mitigation**: Git worktrees share `.git/objects/`, only working trees are duplicated
- **Typical overhead**: ~50-200MB per worktree (only source files, not git objects)

### Initial Checkout Latency
- **Issue**: First request for a new branch requires clone/worktree creation
- **Mitigation**:
  - Return "preparing workspace..." status with streaming updates
  - Pre-create worktrees for common branches (main, develop)
  - Background/async checkout operations

### Stale Checkout Management
- **Issue**: Old branch checkouts accumulate over time
- **Mitigation**:
  - LRU eviction (keep N most recent)
  - TTL-based cleanup (remove after X days)
  - Manual cleanup endpoint: `DELETE /api/repos/{repo}/branches/{branch}`

## Implementation Strategy

### Option A: Separate Clones (Simpler)

**Approach**: Full `git clone` for each branch

**Pros**:
- Simple to implement
- Each branch is completely independent

**Cons**:
- High disk usage (full `.git` directory per branch)
- Slower initial setup
- More network traffic

### Option B: Git Worktrees (Recommended)

**Approach**: One main repository with `git worktree add` for branches

**Pros**:
- Much lower disk usage (shared `.git/objects/`)
- Built-in git feature designed for this use case
- Complete isolation of working trees
- Fast worktree creation (no re-download of objects)

**Cons**:
- Slightly more complex setup logic
- Need to manage worktree lifecycle

**Recommendation**: Use **Option B (Git Worktrees)** for efficiency and scalability.

## Implementation Steps

### 1. Update Request Models

Add `branch` parameter to all Pydantic models:

```python
class MakeStreamRequest(BaseModel):
    repo: str = Field(..., description="Repository name")
    branch: str = Field(..., description="Git branch name")
    args: str = Field(default="", description="Make target and arguments")

class GitStreamRequest(BaseModel):
    repo: str = Field(..., description="Repository name")
    branch: str = Field(..., description="Git branch name")
    operation: str = Field(..., description="Git operation")
    args: str = Field(default="", description="Additional arguments")

# Similar updates for:
# - GitQuickRequest
# - LsRequest
# - ReadFileRequest
```

### 2. Update MCP Tool Schemas

Modify `get_tools_list()` to require `branch` parameter:

```python
Tool(
    name="make",
    description="Run make command with specified arguments in a specific branch.",
    inputSchema={
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name (required)"
            },
            "branch": {
                "type": "string",
                "description": "Git branch name (required)"
            },
            "args": {
                "type": "string",
                "description": "Arguments to pass to make"
            }
        },
        "required": ["repo", "branch"]
    }
)
```

### 3. Implement Workspace Management

Add new methods to `BuildEnvironmentServer`:

```python
class BuildEnvironmentServer:
    def __init__(self):
        self.server = Server("mcp-build")
        self.repos: Dict[str, Dict[str, str]] = {}
        self.workspaces_base = Path.home() / "build-workspaces"
        self._register_handlers()

    async def _ensure_worktree(self, repo_name: str, branch: str) -> Path:
        """Ensure a git worktree exists for the given repo and branch"""
        repo_base = self.workspaces_base / repo_name
        worktree_path = repo_base / branch

        # Create workspace base if needed
        repo_base.mkdir(parents=True, exist_ok=True)

        # Check if main repository exists
        git_dir = repo_base / ".git"
        if not git_dir.exists():
            # Initial clone - need to get repo URL from config
            repo_url = self.repos[repo_name].get("url")
            if not repo_url:
                raise ValueError(f"No URL configured for repository: {repo_name}")

            # Clone as bare or regular repository
            await self._run_command_simple(
                ["git", "clone", repo_url, str(repo_base / "main")],
                cwd=self.workspaces_base
            )

        # Check if worktree exists
        if not worktree_path.exists():
            # Create new worktree
            await self._run_command_simple(
                ["git", "worktree", "add", branch, f"origin/{branch}"],
                cwd=repo_base / "main"
            )
        else:
            # Update existing worktree
            await self._run_command_simple(
                ["git", "fetch", "origin"],
                cwd=worktree_path
            )
            await self._run_command_simple(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=worktree_path
            )

        return worktree_path

    async def _run_command_simple(self, cmd: List[str], cwd: Path) -> None:
        """Run a command without capturing output (for setup operations)"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\n"
                f"Stderr: {stderr.decode('utf-8', errors='replace')}"
            )

    def get_repo_path(self, repo_name: str, branch: str) -> Path:
        """Get the path to a repository worktree (async preparation required)"""
        # Note: This returns the expected path, but caller must
        # call _ensure_worktree() first
        return self.workspaces_base / repo_name / branch
```

### 4. Update Handler Methods

Modify all handler methods to use branch parameter:

```python
async def handle_make(self, args: Dict[str, Any]) -> List[TextContent]:
    """Handle make command"""
    repo = args.get("repo")
    branch = args.get("branch")
    make_args = args.get("args", "")

    # Validate arguments
    validate_make_args(make_args)

    # Ensure worktree exists and is up-to-date
    repo_path = await self._ensure_worktree(repo, branch)

    # Build command
    cmd = ["make"]
    if make_args:
        cmd.extend(shlex.split(make_args))

    # Execute
    result = await self.run_command(cmd, cwd=repo_path)
    return [TextContent(type="text", text=result)]
```

### 5. Update API Endpoints

Modify route definitions to include branch:

```python
routes = [
    # ... existing routes ...

    # Update all endpoints to include branch in path
    Route("/api/repos/{repo}/branches/{branch}/env",
          endpoint=self.api_get_env, methods=["GET"]),
    Route("/api/repos/{repo}/branches/{branch}/ls",
          endpoint=self.api_ls, methods=["POST"]),
    Route("/stream/repos/{repo}/branches/{branch}/make",
          endpoint=self.stream_make, methods=["POST"]),
    Route("/stream/repos/{repo}/branches/{branch}/git",
          endpoint=self.stream_git, methods=["POST"]),
]
```

### 6. Repository Discovery Changes

Update `discover_repos()` to also discover repository URLs:

```python
async def discover_repos(self):
    """Discover repositories and their remote URLs"""
    self.repos = {}

    # Scan for existing worktrees in workspaces directory
    if self.workspaces_base.exists():
        for repo_dir in self.workspaces_base.iterdir():
            if repo_dir.is_dir():
                # Find main worktree or any worktree to get remote URL
                main_tree = repo_dir / "main"
                if main_tree.exists():
                    try:
                        result = await self._run_command_simple(
                            ["git", "config", "--get", "remote.origin.url"],
                            cwd=main_tree
                        )
                        repo_url = result.strip()
                        self.repos[repo_dir.name] = {
                            "url": repo_url,
                            "path": str(repo_dir),
                            "description": f"Repository: {repo_url}"
                        }
                    except Exception as e:
                        logger.warning(f"Could not get URL for {repo_dir.name}: {e}")

    logger.info(f"Discovered {len(self.repos)} repositories")
```

### 7. Add Cleanup Endpoints

Optional: Add endpoints for managing worktrees:

```python
async def api_list_branches(self, request: Request):
    """GET /api/repos/{repo}/branches - List active worktrees"""
    if not verify_session_key(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    repo = request.path_params.get("repo")
    repo_base = self.workspaces_base / repo

    branches = []
    if repo_base.exists():
        for item in repo_base.iterdir():
            if item.is_dir() and item.name != ".git":
                branches.append({
                    "name": item.name,
                    "path": str(item)
                })

    return JSONResponse({"branches": branches})

async def api_delete_branch_workspace(self, request: Request):
    """DELETE /api/repos/{repo}/branches/{branch} - Remove a worktree"""
    if not verify_session_key(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    repo = request.path_params.get("repo")
    branch = request.path_params.get("branch")

    worktree_path = self.workspaces_base / repo / branch

    # Remove worktree using git
    await self._run_command_simple(
        ["git", "worktree", "remove", branch],
        cwd=self.workspaces_base / repo / "main"
    )

    return JSONResponse({"success": True, "message": f"Removed worktree: {branch}"})
```

## Migration Path

### Phase 1: Add branch parameter (backward compatible)
- Add `branch` parameter as optional with default value
- If not provided, use discovered repos in current directory (legacy behavior)
- Update documentation to recommend using branch parameter

### Phase 2: Make branch required
- Change `branch` from optional to required
- Remove repo discovery from current directory
- All operations now use worktree-based isolation

### Phase 3: Optimize and cleanup
- Add LRU cache for worktrees
- Add background cleanup jobs
- Add metrics/monitoring for disk usage

## Configuration

Add new configuration options:

```python
# In server.py
WORKSPACES_BASE_DIR = Path.home() / "build-workspaces"  # Configurable via env var
MAX_WORKTREES_PER_REPO = 10  # LRU limit
WORKTREE_TTL_DAYS = 7  # Auto-cleanup after N days
```

## Testing Plan

1. **Unit tests**:
   - Test worktree creation
   - Test worktree updates
   - Test concurrent builds on different branches

2. **Integration tests**:
   - Clone a test repo
   - Create multiple worktrees
   - Run simultaneous builds
   - Verify isolation

3. **Performance tests**:
   - Measure disk usage with N worktrees
   - Measure checkout time
   - Measure build times (should be unchanged)

## Documentation Updates

- Update MCP-BUILD.md with new branch parameter
- Add examples showing multi-branch builds
- Document worktree management endpoints
- Add troubleshooting section for worktree issues

## Open Questions

1. **Repo URL discovery**: How should the system know the git URL for initial clones?
   - Option A: Config file with repo definitions
   - Option B: Environment variables
   - Option C: API endpoint to register repos

2. **Default branch**: Should there be a "default" branch per repo?
   - Useful for backward compatibility
   - Could auto-create on startup

3. **Branch naming**: How to handle special characters in branch names?
   - Sanitize for filesystem (e.g., `feature/foo` → `feature-foo`)
   - Or use branch hash/ID for directory names

4. **Concurrent updates**: What if two requests try to update the same branch worktree?
   - Add per-worktree locks
   - Queue requests for same repo+branch
   - Document as "last write wins"
