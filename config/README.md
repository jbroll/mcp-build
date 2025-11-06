# Configuration Directory

## Note: Repository Configuration No Longer Required

As of version 0.2.0, the MCP Build service **automatically discovers repositories** by scanning the directory specified in the `MCP_BUILD_REPOS_DIR` environment variable (or the current working directory if not set).

The `repos.json` configuration file is **no longer used or required**.

### Migration from repos.json

If you were using `repos.json` previously:

**Old approach (deprecated):**
```json
{
  "default_repo": "my-project",
  "repos": {
    "my-project": {
      "path": "/build/my-project",
      "description": "My project",
      "git_url": "https://github.com/user/project.git",
      "default_branch": "main"
    }
  }
}
```

**New approach (automatic discovery):**
1. Place your git repositories in a directory
2. Set `MCP_BUILD_REPOS_DIR` environment variable to that directory
3. The service will automatically discover all git repositories (directories containing `.git`)

### Benefits of Automatic Discovery

- No manual configuration needed
- Repositories are discovered dynamically
- Easy to add or remove repositories (just add/remove directories)
- No need to restart the service when adding new repos
- Simpler setup and maintenance
