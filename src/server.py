#!/usr/bin/env python3
"""
MCP Build Service

Provides build environment access via MCP protocol with commands:
- list: Show available repos
- make: Run make with specified arguments
- git: Run git commands (limited to safe operations)
- ls: List files/directories in repository
- env: Show environment information and tool versions
"""

import asyncio
import json
import logging
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
import uvicorn

from validators import validate_git_args, validate_make_args, validate_ls_args, validate_path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-build")

# Configuration
ENV_INFO_SCRIPT = Path(__file__).parent / "env_info.sh"

# Base directory for repositories - always uses current working directory
REPOS_BASE_DIR = Path(os.getcwd())

# HTTP Transport Configuration
TRANSPORT_MODE = os.environ.get("MCP_BUILD_TRANSPORT", "stdio").lower()
HTTP_HOST = os.environ.get("MCP_BUILD_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("MCP_BUILD_PORT", "3344"))

# Session Key for HTTP Authentication
# Generate a random session key if not provided
_SESSION_KEY = os.environ.get("MCP_BUILD_SESSION_KEY")
if not _SESSION_KEY and TRANSPORT_MODE == "http":
    _SESSION_KEY = secrets.token_urlsafe(32)
    logger.warning("=" * 80)
    logger.warning("No MCP_BUILD_SESSION_KEY provided. Generated session key:")
    logger.warning(f"  {_SESSION_KEY}")
    logger.warning("Set this in your environment to persist across restarts:")
    logger.warning(f"  export MCP_BUILD_SESSION_KEY={_SESSION_KEY}")
    logger.warning("=" * 80)

SESSION_KEY = _SESSION_KEY


def verify_session_key(request: Request) -> bool:
    """Verify the session key from request headers or query parameters"""
    if not SESSION_KEY:
        # If no session key is configured, allow access (stdio mode)
        return True

    # Check Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        if secrets.compare_digest(token, SESSION_KEY):
            return True

    # Check query parameter
    query_key = request.query_params.get("key", "")
    if query_key and secrets.compare_digest(query_key, SESSION_KEY):
        return True

    return False


class BuildEnvironmentServer:
    """MCP Server for build operations"""

    def __init__(self):
        self.server = Server("mcp-build")
        self.repos: Dict[str, Dict[str, str]] = {}
        self.current_repo: str | None = None

        # Register handlers using decorators
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers"""

        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available MCP tools"""
            return await self.get_tools_list()

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Any) -> List[TextContent]:
            """Handle tool execution"""
            return await self.execute_tool(name, arguments)

    async def discover_repos(self):
        """Discover repositories by scanning the base directory for git repos"""
        self.repos = {}

        try:
            # Scan the base directory for subdirectories containing .git
            for item in REPOS_BASE_DIR.iterdir():
                if item.is_dir():
                    git_dir = item / ".git"
                    if git_dir.exists():
                        # This is a git repository
                        repo_name = item.name
                        self.repos[repo_name] = {
                            "path": str(item),
                            "description": f"Repository at {item.relative_to(REPOS_BASE_DIR)}"
                        }
                        # Set first repo as default if none is set
                        if self.current_repo is None:
                            self.current_repo = repo_name

            logger.info(f"Discovered {len(self.repos)} repositories in {REPOS_BASE_DIR}")
            if self.current_repo:
                logger.info(f"Default repository: {self.current_repo}")
        except Exception as e:
            logger.error(f"Error discovering repositories: {e}", exc_info=True)
            self.repos = {}

    def get_repo_path(self, repo_name: str | None = None) -> Path:
        """Get the path to a repository"""
        repo = repo_name or self.current_repo
        if not repo:
            raise ValueError("No repository specified and no default set")
        if repo not in self.repos:
            raise ValueError(f"Unknown repository: {repo}")
        return Path(self.repos[repo]["path"])

    async def get_tools_list(self) -> List[Tool]:
        """List available MCP tools"""
        return [
            Tool(
                name="list",
                description="List available repositories discovered in the current directory",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="make",
                description="Run make command with specified arguments. "
                           "Executes make in the root of the specified repository.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "string",
                            "description": "Arguments to pass to make (e.g., 'clean', 'all', 'test')"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name (optional, uses default if not specified)"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="git",
                description="Run git commands in a repository. "
                           "Limited to safe operations: status, log, checkout, pull, branch, diff, fetch, show",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "string",
                            "description": "Git command and arguments (e.g., 'status', 'checkout main', 'pull origin main')"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name (optional, uses default if not specified)"
                        }
                    },
                    "required": ["args"]
                }
            ),
            Tool(
                name="ls",
                description="List files and directories in a repository. "
                           "Limited to paths within the repository to prevent path traversal.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "string",
                            "description": "Arguments to pass to ls (e.g., '-la', '-lh build/')"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name (optional, uses default if not specified)"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="env",
                description="Show environment information including environment variables "
                           "and versions of key build tools (gcc, g++, python, make, cmake, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "Repository name (optional, uses default if not specified)"
                        }
                    },
                    "required": []
                }
            )
        ]

    async def execute_tool(self, name: str, arguments: Any) -> List[TextContent]:
        """Handle tool execution"""
        try:
            if name == "list":
                return await self.handle_list()
            elif name == "make":
                return await self.handle_make(arguments)
            elif name == "git":
                return await self.handle_git(arguments)
            elif name == "ls":
                return await self.handle_ls(arguments)
            elif name == "env":
                return await self.handle_env(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def handle_list(self) -> List[TextContent]:
        """Handle list command"""
        if not self.repos:
            return [TextContent(type="text", text="No repositories configured")]

        output = "Available repositories:\n\n"
        for name, info in self.repos.items():
            marker = " (default)" if name == self.current_repo else ""
            output += f"- {name}{marker}\n"
            output += f"  Path: {info.get('path', 'N/A')}\n"
            output += f"  Description: {info.get('description', 'N/A')}\n\n"

        return [TextContent(type="text", text=output)]

    async def handle_make(self, args: Dict[str, Any]) -> List[TextContent]:
        """Handle make command"""
        repo = args.get("repo")
        make_args = args.get("args", "")

        # Validate arguments
        validate_make_args(make_args)

        # Get repository path
        repo_path = self.get_repo_path(repo)

        # Build command
        cmd = ["make"]
        if make_args:
            cmd.extend(make_args.split())

        # Execute
        result = await self.run_command(cmd, cwd=repo_path)
        return [TextContent(type="text", text=result)]

    async def handle_git(self, args: Dict[str, Any]) -> List[TextContent]:
        """Handle git command"""
        repo = args.get("repo")
        git_args = args.get("args", "")

        if not git_args:
            raise ValueError("git command requires arguments")

        # Validate arguments
        validate_git_args(git_args)

        # Get repository path
        repo_path = self.get_repo_path(repo)

        # Build command
        cmd = ["git"] + git_args.split()

        # Execute
        result = await self.run_command(cmd, cwd=repo_path)
        return [TextContent(type="text", text=result)]

    async def handle_ls(self, args: Dict[str, Any]) -> List[TextContent]:
        """Handle ls command"""
        repo = args.get("repo")
        ls_args = args.get("args", "")

        # Validate arguments
        validate_ls_args(ls_args)

        # Get repository path
        repo_path = self.get_repo_path(repo)

        # Build command
        cmd = ["ls"]
        if ls_args:
            cmd.extend(ls_args.split())

        # Execute
        result = await self.run_command(cmd, cwd=repo_path)
        return [TextContent(type="text", text=result)]

    async def handle_env(self, args: Dict[str, Any]) -> List[TextContent]:
        """Handle env command"""
        repo = args.get("repo")
        repo_path = self.get_repo_path(repo)

        # Execute env info script
        if not ENV_INFO_SCRIPT.exists():
            raise FileNotFoundError(f"Environment info script not found: {ENV_INFO_SCRIPT}")

        result = await self.run_command([str(ENV_INFO_SCRIPT)], cwd=repo_path)
        return [TextContent(type="text", text=result)]

    async def run_command(self, cmd: List[str], cwd: Path) -> str:
        """Run a command in a repository directory"""
        try:
            # Ensure working directory exists
            if not cwd.exists():
                raise FileNotFoundError(f"Repository path does not exist: {cwd}")

            logger.info(f"Executing command: {' '.join(cmd)} in {cwd}")

            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            # Format output
            output = []
            if stdout:
                output.append("=== STDOUT ===")
                output.append(stdout.decode('utf-8', errors='replace'))
            if stderr:
                output.append("=== STDERR ===")
                output.append(stderr.decode('utf-8', errors='replace'))
            if process.returncode != 0:
                output.append(f"\n=== EXIT CODE: {process.returncode} ===")

            return "\n".join(output) if output else "(no output)"

        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            raise

    async def run(self):
        """Start the MCP server with stdio transport"""
        await self.discover_repos()
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP Build Server starting with stdio transport...")
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

    async def handle_sse(self, request):
        """Handle SSE endpoint for HTTP transport"""
        # Verify authentication
        if not verify_session_key(request):
            logger.warning(f"Unauthorized SSE connection attempt from {request.client.host}")
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing session key"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"}
            )

        logger.info(f"SSE connection established from {request.client.host}")
        sse_transport = SseServerTransport("/messages")

        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send
        ) as (read_stream, write_stream):
            init_options = self.server.create_initialization_options()
            await self.server.run(read_stream, write_stream, init_options)

    def create_http_app(self):
        """Create Starlette ASGI application for HTTP transport"""
        routes = [
            Route("/sse", endpoint=self.handle_sse, methods=["GET"])
        ]

        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"]
            )
        ]

        return Starlette(debug=True, routes=routes, middleware=middleware)

    async def run_http(self):
        """Start the MCP server with HTTP transport"""
        await self.discover_repos()
        app = self.create_http_app()

        logger.info(f"MCP Build Server starting with HTTP transport on {HTTP_HOST}:{HTTP_PORT}")
        logger.info(f"SSE endpoint: http://{HTTP_HOST}:{HTTP_PORT}/sse")
        if SESSION_KEY:
            logger.info("Authentication: Session key required")
            logger.info("Connect with: Authorization: Bearer <session-key>")
            logger.info("Or use query parameter: ?key=<session-key>")
        else:
            logger.warning("Authentication: DISABLED (no session key configured)")

        config = uvicorn.Config(
            app,
            host=HTTP_HOST,
            port=HTTP_PORT,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


async def main():
    """Main async entry point"""
    server = BuildEnvironmentServer()

    if TRANSPORT_MODE == "http":
        await server.run_http()
    else:
        # Default to stdio
        await server.run()


def cli():
    """Synchronous entry point for setuptools console_scripts"""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
