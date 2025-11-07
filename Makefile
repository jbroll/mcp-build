.PHONY: build clean test

# Build target for deploy.sh binary_service module
build:
	@echo "Building mcp-build package..."

	# Create build directory structure
	mkdir -p build/lib
	mkdir -p build/bin

	# Install Python dependencies to build/lib
	pip install --target build/lib -r requirements.txt
	pip install --target build/lib starlette uvicorn pyarrow pytest

	# Copy source files (Python modules and scripts)
	cp -r src/* build/lib/

	# Copy documentation
	cp MCP-BUILD.md build/lib/

	# Ensure env_info.sh is executable
	if [ -f build/lib/env_info.sh ]; then \
		chmod +x build/lib/env_info.sh; \
	fi

	# Create wrapper script
	echo '#!/bin/bash' > build/mcp-build
	echo '# MCP Build Service Launcher' >> build/mcp-build
	echo 'set -euo pipefail' >> build/mcp-build
	echo '' >> build/mcp-build
	echo '# Determine installation directory' >> build/mcp-build
	echo 'SCRIPT_DIR="$$(dirname "$$(readlink -f "$$0")")"' >> build/mcp-build
	echo 'LIB_DIR="$${SCRIPT_DIR}/../lib/mcp-build"' >> build/mcp-build
	echo '' >> build/mcp-build
	echo '# Set Python path to include installed dependencies' >> build/mcp-build
	echo 'export PYTHONPATH="$${LIB_DIR}:$${PYTHONPATH:-}"' >> build/mcp-build
	echo '' >> build/mcp-build
	echo '# Execute the server' >> build/mcp-build
	echo 'exec python3 -m server "$$@"' >> build/mcp-build
	chmod +x build/mcp-build

	@echo "Build complete! Binary: build/mcp-build"

clean:
	rm -rf build/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

test:
	pytest tests/ -v

# Development target - install in editable mode
dev:
	pip install -e ".[dev]"

# Show what will be deployed
show:
	@echo "Files that will be deployed:"
	@echo "  Binary: build/mcp-build"
	@echo "  Libraries: build/lib/"
	@if [ -f build/lib/env_info.sh ]; then echo "  Script: build/lib/env_info.sh"; fi
