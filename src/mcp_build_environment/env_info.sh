#!/bin/bash
#
# Build Environment Information Script
#
# Gathers and displays information about the build environment including:
# - Environment variables
# - Versions of key build tools
# - System information
#

set -e

echo "=== BUILD ENVIRONMENT INFORMATION ==="
echo ""

# System Information
echo "--- System Information ---"
echo "Hostname: $(hostname)"
echo "OS: $(uname -s)"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "Distribution: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"' || echo 'Unknown')"
echo ""

# Key Environment Variables
echo "--- Key Environment Variables ---"
echo "PATH: $PATH"
echo "HOME: $HOME"
echo "USER: $USER"
echo "PWD: $PWD"
echo "SHELL: $SHELL"
echo ""

# Compiler Versions
echo "--- Compiler Versions ---"

# GCC
if command -v gcc &> /dev/null; then
    echo "GCC: $(gcc --version | head -n 1)"
else
    echo "GCC: Not installed"
fi

# G++
if command -v g++ &> /dev/null; then
    echo "G++: $(g++ --version | head -n 1)"
else
    echo "G++: Not installed"
fi

# Clang
if command -v clang &> /dev/null; then
    echo "Clang: $(clang --version | head -n 1)"
else
    echo "Clang: Not installed"
fi

# Clang++
if command -v clang++ &> /dev/null; then
    echo "Clang++: $(clang++ --version | head -n 1)"
else
    echo "Clang++: Not installed"
fi

echo ""

# Build Tools
echo "--- Build Tools ---"

# Make
if command -v make &> /dev/null; then
    echo "Make: $(make --version | head -n 1)"
else
    echo "Make: Not installed"
fi

# CMake
if command -v cmake &> /dev/null; then
    echo "CMake: $(cmake --version | head -n 1)"
else
    echo "CMake: Not installed"
fi

# Ninja
if command -v ninja &> /dev/null; then
    echo "Ninja: $(ninja --version 2>&1 | head -n 1)"
else
    echo "Ninja: Not installed"
fi

# Autoconf
if command -v autoconf &> /dev/null; then
    echo "Autoconf: $(autoconf --version | head -n 1)"
else
    echo "Autoconf: Not installed"
fi

# Automake
if command -v automake &> /dev/null; then
    echo "Automake: $(automake --version | head -n 1)"
else
    echo "Automake: Not installed"
fi

echo ""

# Programming Languages
echo "--- Programming Languages ---"

# Python
if command -v python3 &> /dev/null; then
    echo "Python3: $(python3 --version)"
else
    echo "Python3: Not installed"
fi

if command -v python &> /dev/null; then
    echo "Python: $(python --version 2>&1)"
else
    echo "Python: Not installed"
fi

# Node.js
if command -v node &> /dev/null; then
    echo "Node.js: $(node --version)"
else
    echo "Node.js: Not installed"
fi

# Go
if command -v go &> /dev/null; then
    echo "Go: $(go version)"
else
    echo "Go: Not installed"
fi

# Rust
if command -v rustc &> /dev/null; then
    echo "Rust: $(rustc --version)"
else
    echo "Rust: Not installed"
fi

echo ""

# Version Control
echo "--- Version Control ---"

# Git
if command -v git &> /dev/null; then
    echo "Git: $(git --version)"
else
    echo "Git: Not installed"
fi

echo ""

# Package Managers
echo "--- Package Managers ---"

# apt
if command -v apt &> /dev/null; then
    echo "APT: $(apt --version 2>&1 | head -n 1)"
fi

# yum
if command -v yum &> /dev/null; then
    echo "YUM: $(yum --version 2>&1 | head -n 1)"
fi

# pip
if command -v pip3 &> /dev/null; then
    echo "pip3: $(pip3 --version)"
fi

echo ""

# Build-Specific Tools (Velox related)
echo "--- Specialized Tools ---"

# pkg-config
if command -v pkg-config &> /dev/null; then
    echo "pkg-config: $(pkg-config --version)"
else
    echo "pkg-config: Not installed"
fi

# ccache
if command -v ccache &> /dev/null; then
    echo "ccache: $(ccache --version | head -n 1)"
else
    echo "ccache: Not installed"
fi

# Flex
if command -v flex &> /dev/null; then
    echo "Flex: $(flex --version | head -n 1)"
else
    echo "Flex: Not installed"
fi

# Bison
if command -v bison &> /dev/null; then
    echo "Bison: $(bison --version | head -n 1)"
else
    echo "Bison: Not installed"
fi

echo ""
echo "=== END OF ENVIRONMENT INFORMATION ==="
