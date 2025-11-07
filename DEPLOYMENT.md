# MCP Build Service - Deployment Guide

This guide explains how to deploy the mcp-build service to a remote server using the deploy.sh framework.

## What Was Created

### 1. Makefile
- Builds the mcp-build package with all Python dependencies
- Creates `build/mcp-build` executable wrapper script
- Packages dependencies in `build/lib/` directory
- Includes `env_info.sh` script for environment inspection

### 2. deploy.conf
- Deployment configuration for the deploy.sh framework
- Configures Apache reverse proxy (HTTP mode)
- Sets up systemd service via binary_service module
- Template with placeholders you need to customize

### 3. .env.production
- Production environment variables
- Deployed to `/etc/mcp-build/secrets.env` on remote server
- Contains MCP service configuration (transport, ports, session key, repos)

### 4. Enhanced binary_service Module
- Now optionally deploys `lib/` directories for dependencies
- Supports Python "binaries" and other applications needing libraries
- Backward compatible with existing Go/Rust/C++ deployments

## Remote Server Prerequisites

Before deploying, your remote server needs:

1. **Operating System**: Ubuntu/Debian Linux
2. **Apache 2.4+**: `sudo apt-get install apache2`
3. **Python 3.10+**: `sudo apt-get install python3 python3-pip`
4. **systemd**: Usually pre-installed
5. **SSH Access**: Key-based authentication for the deploy user
6. **sudo privileges**: The deploy user needs sudo access

### Quick Setup on Remote Server

```bash
# Install prerequisites
sudo apt-get update
sudo apt-get install -y apache2 python3 python3-pip

# Enable Apache
sudo systemctl enable apache2
sudo systemctl start apache2

# Create repositories directory
sudo mkdir -p /var/lib/mcp-build/repos
```

## Configuration Steps

### 1. Customize deploy.conf

Edit `/home/john/src/mcp-build/deploy.conf`:

```bash
# Set your domain name
export DOMAIN_NAME="build.your-domain.com"

# Set your remote server
export REMOTE_HOST="your-server.com"
export REMOTE_USER="deploy"

# Optional: Enable SSL with Let's Encrypt
# Uncomment these lines:
# export DEPLOY_TYPES="letsencrypt apache binary_service"
# export LETSENCRYPT_EMAIL="admin@your-domain.com"
```

### 2. Generate Session Key

Generate a secure random session key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update both files with this key:
- `deploy.conf`: Set `MCP_BUILD_SESSION_KEY`
- `.env.production`: Set `MCP_BUILD_SESSION_KEY`

### 3. Configure Repository Directory (on remote server)

After initial deployment, create and populate the repos directory:

```bash
# SSH to remote server
ssh user@your-server

# Create repos directory with proper ownership
sudo mkdir -p /var/lib/mcp-build/repos
sudo chown mcp-build:mcp-build /var/lib/mcp-build/repos
sudo chmod 755 /var/lib/mcp-build/repos

# Clone or copy your repositories there
cd /var/lib/mcp-build/repos
sudo -u mcp-build git clone <your-repo-url>
```

## Deployment Commands

### Initial Deployment (Full Setup)

```bash
cd /home/john/src/mcp-build
deploy init
```

This will:
1. Build the mcp-build package locally
2. Deploy binary to `/usr/local/bin/mcp-build`
3. Deploy libraries to `/usr/local/lib/mcp-build/`
4. Create systemd service
5. Configure Apache reverse proxy
6. Start the service

### Update Deployment (Code Only)

```bash
cd /home/john/src/mcp-build
deploy update
```

This will:
1. Rebuild the package
2. Update binary and libraries
3. Restart the service

Skip infrastructure setup (Apache, SSL certificates).

## Post-Deployment

### Check Service Status

```bash
ssh user@your-server 'sudo systemctl status mcp-build'
```

### View Service Logs

```bash
ssh user@your-server 'sudo journalctl -u mcp-build -f'
```

### View Apache Logs

```bash
ssh user@your-server 'sudo tail -f /var/log/apache2/build.your-domain.com-error.log'
```

### Test the Service

```bash
# Test with curl (replace YOUR_KEY with your session key)
curl -H "Authorization: Bearer YOUR_KEY" https://build.your-domain.com/sse

# Or using query parameter
curl "https://build.your-domain.com/sse?key=YOUR_KEY"
```

## How It Works

### Deployed Structure

```
/usr/local/bin/mcp-build           # Wrapper script
/usr/local/lib/mcp-build/          # Python libraries and dependencies
├── server.py                      # Main server module
├── validators.py                  # Validation functions
├── env_info.sh                    # Environment info script
├── helpers/                       # Helper modules
└── [all Python dependencies]      # mcp, starlette, uvicorn, etc.

/etc/mcp-build/secrets.env         # Environment variables (secure)
/var/lib/mcp-build/                # Application data
├── repos/                         # Your repositories to build
└── data/                          # Application data

/etc/systemd/system/mcp-build.service  # Systemd service
/etc/apache2/sites-available/build.your-domain.com.conf  # Apache config
```

### Runtime Flow

1. systemd starts `/usr/local/bin/mcp-build`
2. Wrapper script sets `PYTHONPATH` to `/usr/local/lib/mcp-build`
3. Executes `python3 -m server` with environment from `/etc/mcp-build/secrets.env`
4. Service binds to `127.0.0.1:3344` (HTTP transport)
5. Apache reverse proxies `https://build.your-domain.com` → `http://127.0.0.1:3344`
6. Clients authenticate with session key

## MCP Client Configuration

Add this to your MCP client (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "mcp-build-remote": {
      "url": "https://build.your-domain.com/sse",
      "headers": {
        "Authorization": "Bearer YOUR_SESSION_KEY_HERE"
      }
    }
  }
}
```

Or use query parameter:

```json
{
  "mcpServers": {
    "mcp-build-remote": {
      "url": "https://build.your-domain.com/sse?key=YOUR_SESSION_KEY_HERE"
    }
  }
}
```

## Troubleshooting

### Service won't start

```bash
# Check service status and logs
ssh user@server 'sudo systemctl status mcp-build'
ssh user@server 'sudo journalctl -u mcp-build -n 50'

# Check Python is available
ssh user@server 'python3 --version'

# Check libraries are deployed
ssh user@server 'ls -la /usr/local/lib/mcp-build/'
```

### Apache errors

```bash
# Test Apache configuration
ssh user@server 'sudo apache2ctl configtest'

# Check Apache is running
ssh user@server 'sudo systemctl status apache2'

# View Apache error logs
ssh user@server 'sudo tail -100 /var/log/apache2/error.log'
```

### Connection refused

```bash
# Check if service is listening
ssh user@server 'sudo netstat -tlnp | grep 3344'

# Verify firewall isn't blocking
ssh user@server 'sudo ufw status'
```

### No repositories found

```bash
# Check repos directory
ssh user@server 'sudo ls -la /var/lib/mcp-build/repos/'

# Check ownership
ssh user@server 'sudo ls -ld /var/lib/mcp-build/repos/'

# Should be owned by mcp-build user
```

## Security Notes

1. **Session Key**: Keep your session key secret. Rotate it regularly by:
   - Generating new key
   - Updating `.env.production`
   - Running `deploy update`
   - Restarting service

2. **HTTPS**: Always use HTTPS in production. Enable Let's Encrypt in deploy.conf.

3. **Firewall**: Configure firewall to allow only necessary ports:
   ```bash
   sudo ufw allow 80/tcp    # HTTP (for Let's Encrypt)
   sudo ufw allow 443/tcp   # HTTPS
   sudo ufw enable
   ```

4. **SSH Keys**: Use key-based authentication, disable password auth.

5. **Repository Access**: The mcp-build service runs as the `mcp-build` user and can only access repositories in `/var/lib/mcp-build/repos/`.

## Maintenance

### Update Service Code

```bash
cd /home/john/src/mcp-build
# Make your code changes
deploy update
```

### Restart Service

```bash
ssh user@server 'sudo systemctl restart mcp-build'
```

### View Real-time Logs

```bash
ssh user@server 'sudo journalctl -u mcp-build -f'
```

### Update Dependencies

Edit `requirements.txt`, then:

```bash
deploy update
```

## Files Summary

- **Makefile**: Build automation
- **deploy.conf**: Deployment configuration (customize this!)
- **.env.production**: Environment variables (customize this!)
- **DEPLOYMENT.md**: This guide
- **build/**: Generated by `make build` (auto-created)
- **src/**: Source code (deploy.sh uses this)

## Next Steps

1. ✅ Customize `deploy.conf` with your domain and server
2. ✅ Generate and set session key in both config files
3. ✅ Ensure remote server has prerequisites installed
4. ✅ Run `deploy init` for initial deployment
5. ✅ Create repos directory and populate with your repositories
6. ✅ Test connection with curl
7. ✅ Configure your MCP client
