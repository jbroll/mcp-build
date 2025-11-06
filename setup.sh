#!/bin/bash
#
# Setup script for MCP Build Service
#

set -e

echo "=== MCP Build Service Setup ==="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

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

# Check for basic build tools (optional but recommended)
if command -v make &> /dev/null; then
    echo "✓ make found"
else
    echo "⚠ make not found - you may want to install build tools"
fi

if command -v git &> /dev/null; then
    echo "✓ git found"
else
    echo "⚠ git not found - git is required for repository operations"
fi

echo ""
echo "Installing Python package..."
pip3 install -e .

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "1. Organize your git repositories in a directory, for example:"
echo "   /home/user/projects/"
echo "   ├── project-a/"
echo "   ├── project-b/"
echo "   └── project-c/"
echo ""
echo "2. Configure your MCP client (e.g., Claude Desktop config):"
echo "   {"
echo "     \"mcpServers\": {"
echo "       \"mcp-build\": {"
echo "         \"command\": \"python\","
echo "         \"args\": [\"-m\", \"mcp_build.server\"],"
echo "         \"env\": {"
echo "           \"MCP_BUILD_REPOS_DIR\": \"/path/to/your/projects\""
echo "         }"
echo "       }"
echo "     }"
echo "   }"
echo ""
echo "3. The service will automatically discover all git repositories"
echo "   in the configured directory."
echo ""
echo "For more information, see README.md"
echo ""
