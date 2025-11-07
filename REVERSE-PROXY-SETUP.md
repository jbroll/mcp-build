# Reverse Proxy Deployment Guide

This document explains how to deploy a reverse proxy server for the mcp-build service using the deploy.sh framework.

## Overview

The mcp-build service runs on `symon.rkroll.com:3344` (HTTPS). To provide access via a standard HTTPS port (443), we deploy a reverse proxy on `build.rkroll.com` that forwards all traffic to the backend service.

## Architecture

```
Client
  ↓
  HTTPS (port 443)
  ↓
build.rkroll.com (Apache + LetsEncrypt)
  ↓
  HTTPS (port 3344)
  ↓
symon.rkroll.com (mcp-build service)
```

## Configuration Files

### Main Service: `deploy.conf`
Deploys the mcp-build service to `symon.rkroll.com`:
- Apache reverse proxy on port 3344 (HTTPS)
- mcp-build service on localhost:3345
- LetsEncrypt certificate for symon.rkroll.com

### Reverse Proxy: `deploy-proxy.conf`
Deploys the reverse proxy to `build.rkroll.com`:
- Apache reverse proxy on port 443 (HTTPS)
- LetsEncrypt certificate for build.rkroll.com
- Forwards all traffic to symon.rkroll.com:3344

## Deployment

### Initial Setup (First Time)

Deploy the reverse proxy to build.rkroll.com:

```bash
cd /home/john/src/mcp-build
DEPLOY_SH_CONF=./deploy-proxy.conf ../deploy.sh/deploy.sh init
```

This will:
1. Install Apache and Certbot on build.rkroll.com
2. Obtain a LetsEncrypt certificate for build.rkroll.com
3. Configure Apache to proxy all traffic to symon.rkroll.com:3344
4. Enable HTTPS redirection and security headers

### Updates

To update the reverse proxy configuration:

```bash
cd /home/john/src/mcp-build
DEPLOY_SH_CONF=./deploy-proxy.conf ../deploy.sh/deploy.sh update
```

### Update Main Service

The main service deployment remains unchanged:

```bash
cd /home/john/src/mcp-build
../deploy.sh/deploy.sh update
```

## Configuration Options

### SSL Verification

The reverse proxy can be configured to verify the backend SSL certificate:

```bash
# Disable SSL verification (for self-signed certs)
export REVERSE_PROXY_SSL_VERIFY="no"

# Enable SSL verification (for valid certs)
export REVERSE_PROXY_SSL_VERIFY="yes"
```

### Custom Ports

To use different ports on the reverse proxy:

```bash
export REVERSE_PROXY_HTTP_PORT="80"     # Default
export REVERSE_PROXY_HTTPS_PORT="443"   # Default
```

### Security Headers

Security headers are enabled by default but can be disabled:

```bash
export REVERSE_PROXY_SECURITY_HEADERS="yes"  # Default
```

## Testing

### Test Certificate

Verify the LetsEncrypt certificate on build.rkroll.com:

```bash
openssl s_client -connect build.rkroll.com:443 -servername build.rkroll.com < /dev/null 2>/dev/null | openssl x509 -noout -dates -subject -issuer
```

### Test Proxy

Access the service through the reverse proxy:

```bash
curl -v https://build.rkroll.com/sse?key=YOUR_SESSION_KEY
```

### Check Logs

View Apache logs on build.rkroll.com:

```bash
ssh john@build.rkroll.com 'sudo tail -f /var/log/apache2/mcp-build-proxy-ssl-access.log'
ssh john@build.rkroll.com 'sudo tail -f /var/log/apache2/mcp-build-proxy-ssl-error.log'
```

## Certificate Renewal

LetsEncrypt certificates auto-renew via certbot. To manually renew:

```bash
ssh john@build.rkroll.com 'sudo certbot renew'
ssh john@build.rkroll.com 'sudo systemctl reload apache2'
```

## Troubleshooting

### Apache Configuration Test

```bash
ssh john@build.rkroll.com 'sudo apache2ctl configtest'
```

### Check Apache Status

```bash
ssh john@build.rkroll.com 'sudo systemctl status apache2'
```

### View Current Configuration

```bash
ssh john@build.rkroll.com 'sudo cat /etc/apache2/sites-available/mcp-build-proxy.conf'
```

### Backend Connection Test

Test if build.rkroll.com can reach symon.rkroll.com:3344:

```bash
ssh john@build.rkroll.com 'curl -v -k https://symon.rkroll.com:3344/sse?key=test'
```

## Module Details

The `reverse_proxy` module is located at:
```
/home/john/src/deploy.sh/modules/reverse_proxy/
```

It includes:
- `module.info` - Module description
- `defaults.conf` - Default configuration variables
- `build.sh` - Build stage (no-op)
- `install.sh` - Installs Apache and Certbot
- `configure.sh` - Configures Apache and obtains LetsEncrypt certificate
- `start.sh` - Starts/restarts Apache

## See Also

- [deploy.sh documentation](https://github.com/jbroll/deploy.sh)
- Main service configuration: `deploy.conf`
- Reverse proxy configuration: `deploy-proxy.conf`
