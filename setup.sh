#!/bin/bash
#
# Setup script for MCP Build Environment Service
#

set -e

echo "=== MCP Build Environment Setup ==="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Please install Docker first."
    exit 1
fi
echo "✓ Docker found"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
echo "✓ Docker Compose found"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Python $PYTHON_VERSION found"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 is not installed. Please install pip3 first."
    exit 1
fi
echo "✓ pip3 found"

echo ""
echo "Installing Python package..."
pip3 install -e .

echo ""
echo "Building Docker image..."
cd docker
docker-compose build

echo ""
echo "Starting Docker container..."
docker-compose up -d

echo ""
echo "Waiting for container to be ready..."
sleep 2

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Clone your repository into the build environment:"
echo "   docker-compose exec build-env git clone <repo-url> /build/<repo-name>"
echo ""
echo "2. Update config/repos.json with your repository information"
echo ""
echo "3. Configure your MCP client to use this server"
echo ""
echo "To check the build environment:"
echo "   docker-compose exec build-env bash"
echo ""
