# MCP Build Service - Deployment Guide

This guide explains how to deploy the mcp-build service to a remote server using the deploy.sh framework.

## Overview

**What it does**: Provides AI assistants with MCP tools to list repositories, run git commands, execute make targets, and read files in your build environment.

**Deployment Stack**:
- **Web**: Apache with Let's Encrypt SSL (HTTPS)
- **Proxy**: Apache reverse proxy → mcp-build service
- **Service**: mcp-build running as systemd service
- **Transport**: HTTP with session key authentication

## Remote Server Prerequisites

Your remote server needs:

1. **Operating System**: Ubuntu/Debian Linux
2. **Apache 2.4+**: `sudo apt-get install apache2`
3. **Python 3.10+**: `sudo apt-get install python3 python3-pip`
4. **systemd**: Usually pre-installed
5. **SSH Access**: Key-based authentication
6. **sudo privileges**: Deployment user needs sudo access

### Quick Setup on Remote Server

```bash
# Install prerequisites
sudo apt-get update
sudo apt-get install -y apache2 python3 python3-pip

# Enable Apache modules
sudo a2enmod proxy proxy_http ssl rewrite headers
sudo systemctl enable apache2
sudo systemctl start apache2
```

## Deployment Architecture

```
Internet
   ↓ HTTPS (443)
Apache (reverse proxy)
   ↓ HTTP (127.0.0.1:3344)
mcp-build service (systemd)
   ↓ Working Directory
/home/john/src/*  (git repositories)
```

**Deployed Structure**:
```
/usr/local/bin/mcp-build              # Wrapper script
/usr/local/lib/mcp-build/             # Python dependencies
├── server.py                         # Main server module
├── validators.py                     # Validation functions
├── helpers/                          # Helper modules
└── [Python packages]                 # mcp, starlette, uvicorn, etc.

/home/john/src/                       # Working directory (repos live here)
├── project-a/                        # Git repository
├── project-b/                        # Git repository
└── mcp-build/                        # This project

/home/john/.mcp-build-key             # Session key file (created on startup)

/etc/systemd/system/mcp-build.service # Systemd service
/etc/apache2/sites-available/         # Apache vhost config
```

## Configuration

The deployment is configured in `deploy.conf`. Key settings:

```bash
# Remote server
export REMOTE_HOST="symon.rkroll.com"
export REMOTE_USER="john"

# Working directory (repos are in /home/john/src/*)
export BINARY_SERVICE_WORK_DIR="/home/john/src"
export BINARY_SERVICE_APPEND_APP_NAME="false"  # Don't append APP_NAME

# Run as personal account for repo access
export BINARY_SERVICE_USER="john"
export BINARY_SERVICE_GROUP="john"

# CLI arguments passed to mcp-build
# Note: No static session key - service manages its own persistent key
export BINARY_SERVICE_BINARY_ARGS="--transport http --host 127.0.0.1 --port 3344 --key-file ~/.mcp-build-key"
```

### Important Configuration Details

**Working Directory**:
- The service runs in `/home/john/src` (your repos location)
- Service discovers all git repositories in this directory
- Uses your personal account to access repositories

**Session Key Management**:
- **First startup**: Service auto-generates a secure random key and saves to `~/.mcp-build-key`
- **Subsequent startups**: Service reads existing key from `~/.mcp-build-key` (persistent across restarts)
- **No static key in config**: The key is managed by the service itself, not hardcoded
- **Retrieve key**: `ssh john@symon.rkroll.com cat ~/.mcp-build-key`
- **File permissions**: Automatically set to 600 (user read/write only)

**Security Settings**:
- `BINARY_SERVICE_PROTECT_HOME="false"` allows access to home directory
- Service runs as your user account for repository access
- SSL/TLS via Let's Encrypt

## Deployment Commands

### Build Locally

Before deploying, build the package locally:

```bash
cd /home/john/src/mcp-build
make build
```

This creates:
- `build/mcp-build` - Wrapper script
- `build/lib/` - Python dependencies and source code

### Initial Deployment (Full Setup)

```bash
cd /home/john/src/mcp-build
/home/john/src/deploy.sh/deploy.sh init
```

This will:
1. Build the mcp-build package locally
2. Deploy binary to `/usr/local/bin/mcp-build`
3. Deploy libraries to `/usr/local/lib/mcp-build/`
4. Create systemd service
5. Request Let's Encrypt SSL certificate
6. Configure Apache reverse proxy
7. Start the service
8. Write session key to `~/.mcp-build-key`

### Update Deployment (Code Only)

After making code changes:

```bash
cd /home/john/src/mcp-build
make build
/home/john/src/deploy.sh/deploy.sh update
```

This will:
1. Rebuild the package locally
2. Update binary and libraries on remote
3. Restart the service
4. Skip infrastructure setup (Apache, SSL)

## Post-Deployment

### Retrieve Session Key

```bash
ssh john@symon.rkroll.com cat ~/.mcp-build-key
```

### Check Service Status

```bash
ssh john@symon.rkroll.com 'sudo systemctl status mcp-build'
```

### View Service Logs

```bash
ssh john@symon.rkroll.com 'sudo journalctl -u mcp-build -f'
```

### Test the Service

```bash
# Get your session key first
SESSION_KEY=$(ssh john@symon.rkroll.com cat ~/.mcp-build-key)

# Test API endpoint
curl -H "Authorization: Bearer $SESSION_KEY" https://symon.rkroll.com/api/repos

# Or using query parameter
curl "https://symon.rkroll.com/api/repos?key=$SESSION_KEY"
```

## MCP Client Configuration

Add to your Claude Desktop config:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mcp-build": {
      "url": "https://symon.rkroll.com/sse?key=YOUR_SESSION_KEY_HERE"
    }
  }
}
```

Or with Authorization header:

```json
{
  "mcpServers": {
    "mcp-build": {
      "url": "https://symon.rkroll.com/sse",
      "headers": {
        "Authorization": "Bearer YOUR_SESSION_KEY_HERE"
      }
    }
  }
}
```

## How It Works

### Runtime Flow

1. systemd starts `/usr/local/bin/mcp-build` with CLI arguments
2. Wrapper script sets `PYTHONPATH=/usr/local/lib/mcp-build`
3. Executes `python3 -m server --transport http --host 127.0.0.1 --port 3344 --key-file ~/.mcp-build-key`
4. Service checks for existing key in `~/.mcp-build-key`:
   - If exists: Load and use existing key (persistent)
   - If missing: Generate new random key and save it (mode 600)
5. Service binds to `127.0.0.1:3344` (HTTP)
6. Service discovers git repos in `/home/john/src/*`
7. Apache reverse proxies `https://symon.rkroll.com` → `http://127.0.0.1:3344`
8. Clients connect via HTTPS with session key

### Available MCP Tools

- **list** - List git repositories in working directory
- **git** - Execute git commands (status, log, checkout, pull, branch, diff, fetch, show)
- **make** - Run make targets (build, test, clean, etc.)
- **ls** - List directory contents
- **env** - Show installed build tools and versions
- **read_file** - Read file contents with optional line ranges

## Troubleshooting

### Service won't start

```bash
# Check service status and logs
ssh john@symon.rkroll.com 'sudo systemctl status mcp-build'
ssh john@symon.rkroll.com 'sudo journalctl -u mcp-build -n 50'

# Check Python is available
ssh john@symon.rkroll.com 'python3 --version'

# Check libraries are deployed
ssh john@symon.rkroll.com 'ls -la /usr/local/lib/mcp-build/'
```

### No repositories found

```bash
# Check working directory
ssh john@symon.rkroll.com 'ls -la /home/john/src/'

# Each subdirectory should be a git repo with .git folder
ssh john@symon.rkroll.com 'find /home/john/src -name .git -type d'
```

### Apache errors

```bash
# Test Apache configuration
ssh john@symon.rkroll.com 'sudo apache2ctl configtest'

# Check Apache logs
ssh john@symon.rkroll.com 'sudo tail -100 /var/log/apache2/error.log'
```

### Can't retrieve session key

```bash
# Check if key file exists
ssh john@symon.rkroll.com 'ls -la ~/.mcp-build-key'

# Check service logs for key generation
ssh john@symon.rkroll.com 'sudo journalctl -u mcp-build | grep "Session key"'
```

### Connection refused

```bash
# Check if service is listening
ssh john@symon.rkroll.com 'sudo netstat -tlnp | grep 3344'

# Verify Apache is running
ssh john@symon.rkroll.com 'sudo systemctl status apache2'

# Check firewall
ssh john@symon.rkroll.com 'sudo ufw status'
```

## Maintenance

### Rotate Session Key

**Option 1: Auto-generate new key**
```bash
# Delete the key file and restart service to generate new key
ssh john@symon.rkroll.com 'rm ~/.mcp-build-key'
ssh john@symon.rkroll.com 'sudo systemctl restart mcp-build'

# Wait a moment for service to start, then retrieve new key
sleep 2
ssh john@symon.rkroll.com 'cat ~/.mcp-build-key'
```

**Option 2: Set specific key**
```bash
# Generate a specific key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Write it to the key file
ssh john@symon.rkroll.com "echo '$NEW_KEY' > ~/.mcp-build-key && chmod 600 ~/.mcp-build-key"

# Restart service to use new key
ssh john@symon.rkroll.com 'sudo systemctl restart mcp-build'
```

### Update Code

```bash
cd /home/john/src/mcp-build
# Make your code changes in src/
make build
/home/john/src/deploy.sh/deploy.sh update
```

### Restart Service

```bash
ssh john@symon.rkroll.com 'sudo systemctl restart mcp-build'
```

### View Real-time Logs

```bash
ssh john@symon.rkroll.com 'sudo journalctl -u mcp-build -f'
```

## Security Notes

1. **Session Key**: Keep it secret. Store it securely in your MCP client config.
2. **HTTPS**: Always use HTTPS in production (Let's Encrypt handles this).
3. **Firewall**: Configure firewall to allow only HTTP (80) and HTTPS (443).
4. **SSH Keys**: Use key-based authentication, disable password auth.
5. **Repository Access**: Service runs as your user account with full access to `/home/john/src`.
6. **Make Targets**: Service executes whatever is in Makefiles - ensure they're trusted.

## Files Summary

- **deploy.conf** - Deployment configuration (customize this!)
- **Makefile** - Build automation
- **src/** - Source code
- **build/** - Generated by `make build` (don't commit)
- **.env.production** - DEPRECATED (no longer used)
- **DEPLOYMENT.md** - This guide

## Next Steps

1. Ensure remote server has prerequisites installed (Apache, Python 3.10+)
2. Review `deploy.conf` configuration (domain, remote host, user)
3. Run `make build` to build locally
4. Run `/home/john/src/deploy.sh/deploy.sh init` for initial deployment
5. Wait for service to start and auto-generate session key
6. Retrieve session key: `ssh john@symon.rkroll.com cat ~/.mcp-build-key`
7. Configure your MCP client with the session key
8. Test connection

## Related Documentation

- **README.md** - User guide and local development
- **MCP-BUILD.md** - Agent usage guide
- **deploy.sh** - https://github.com/jbroll/deploy.sh
