# Build Environment Dockerfile
# This container provides a complete build environment for velocipyde
# with all necessary dependencies pre-installed.

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set up build environment base directory
ENV BUILD_ENV_BASE=/build

# Install basic build tools and dependencies
RUN apt-get update && apt-get install -y \
    # Core build tools
    build-essential \
    cmake \
    make \
    ninja-build \
    autoconf \
    automake \
    libtool \
    pkg-config \
    # Compilers
    gcc \
    g++ \
    clang \
    # Version control
    git \
    # Python
    python3 \
    python3-pip \
    python3-dev \
    # Utilities
    curl \
    wget \
    vim \
    less \
    # Additional tools for Velox
    flex \
    bison \
    ccache \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Python build tools
RUN pip3 install --no-cache-dir \
    setuptools \
    wheel \
    build

# Create build directory
RUN mkdir -p ${BUILD_ENV_BASE}

# Set working directory
WORKDIR ${BUILD_ENV_BASE}

# Expose MCP HTTP server port
EXPOSE 3344

# Default command
CMD ["/bin/bash"]
