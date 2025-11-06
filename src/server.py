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

import argparse
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

from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse
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

# Global configuration variables (set by parse_args)
TRANSPORT_MODE = "stdio"
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 3344
SESSION_KEY = None


# Pydantic models for REST API
class LsRequest(BaseModel):
    """Request model for ls command"""
    args: str = Field(default="", description="Arguments for ls command")


class GitQuickRequest(BaseModel):
    """Request model for quick git operations"""
    operation: str = Field(..., description="Git operation (status, branch, log)")
    args: str = Field(default="", description="Additional arguments")


class MakeStreamRequest(BaseModel):
    """Request model for streaming make operations"""
    args: str = Field(default="", description="Make target and arguments")


class GitStreamRequest(BaseModel):
    """Request model for streaming git operations"""
    operation: str = Field(..., description="Git operation (pull, fetch, diff, show, checkout)")
    args: str = Field(default="", description="Additional arguments")


class ApiResponse(BaseModel):
    """Standard API response model"""
    success: bool
    data: Any = None
    error: str = None


class RepoInfo(BaseModel):
    """Repository information model"""
    name: str
    path: str
    description: str
    is_default: bool


class ReposListResponse(BaseModel):
    """Response model for list repos endpoint"""
    repos: List[RepoInfo]


class CommandResult(BaseModel):
    """Result of a command execution"""
    stdout: str
    stderr: str
    exit_code: int
    combined_output: str


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

    async def run_command_streaming(self, cmd: List[str], cwd: Path):
        """Run a command with line-by-line streaming of output"""
        try:
            # Ensure working directory exists
            if not cwd.exists():
                raise FileNotFoundError(f"Repository path does not exist: {cwd}")

            logger.info(f"Executing streaming command: {' '.join(cmd)} in {cwd}")

            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Process lines as they arrive from both streams
            stdout_done = False
            stderr_done = False

            while not (stdout_done and stderr_done):
                # Check stdout
                if not stdout_done:
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.01)
                        if line:
                            decoded_line = line.decode('utf-8', errors='replace').rstrip()
                            if decoded_line:
                                yield {"type": "stdout", "line": decoded_line}
                        else:
                            stdout_done = True
                    except asyncio.TimeoutError:
                        pass

                # Check stderr
                if not stderr_done:
                    try:
                        line = await asyncio.wait_for(process.stderr.readline(), timeout=0.01)
                        if line:
                            decoded_line = line.decode('utf-8', errors='replace').rstrip()
                            if decoded_line:
                                yield {"type": "stderr", "line": decoded_line}
                        else:
                            stderr_done = True
                    except asyncio.TimeoutError:
                        pass

                # Small sleep to prevent busy waiting
                if not (stdout_done and stderr_done):
                    await asyncio.sleep(0.01)

            # Wait for process to complete
            await process.wait()

            # Yield completion message
            yield {
                "type": "complete",
                "exit_code": process.returncode
            }

        except Exception as e:
            logger.error(f"Streaming command execution failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "message": str(e)
            }

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

    # REST API Endpoints for Quick Operations
    async def api_list_repos(self, request: Request):
        """GET /api/repos - List all repositories"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repos = [
                RepoInfo(
                    name=name,
                    path=info["path"],
                    description=info.get("description", ""),
                    is_default=(name == self.current_repo)
                )
                for name, info in self.repos.items()
            ]
            response = ReposListResponse(repos=repos)
            return JSONResponse(response.model_dump())
        except Exception as e:
            logger.error(f"Error listing repos: {e}", exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)

    async def api_get_env(self, request: Request):
        """GET /api/repos/{repo}/env - Get environment info"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            repo_path = self.get_repo_path(repo)

            if not ENV_INFO_SCRIPT.exists():
                raise FileNotFoundError(f"Environment info script not found: {ENV_INFO_SCRIPT}")

            result = await self.run_command([str(ENV_INFO_SCRIPT)], cwd=repo_path)
            return JSONResponse({"success": True, "data": result})
        except Exception as e:
            logger.error(f"Error getting env: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    async def api_ls(self, request: Request):
        """POST /api/repos/{repo}/ls - List directory contents"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            body = await request.json()
            ls_request = LsRequest(**body)

            # Validate arguments
            validate_ls_args(ls_request.args)

            # Get repository path
            repo_path = self.get_repo_path(repo)

            # Build command
            cmd = ["ls"]
            if ls_request.args:
                cmd.extend(ls_request.args.split())

            # Execute
            result = await self.run_command(cmd, cwd=repo_path)
            return JSONResponse({"success": True, "data": result})
        except Exception as e:
            logger.error(f"Error running ls: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    async def api_git_quick(self, request: Request):
        """POST /api/repos/{repo}/git/quick - Quick git operations (status, branch, log)"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            body = await request.json()
            git_request = GitQuickRequest(**body)

            # Only allow quick operations
            if git_request.operation not in ["status", "branch", "log"]:
                return JSONResponse(
                    {"success": False, "error": f"Operation '{git_request.operation}' not allowed for quick endpoint. Use /stream/repos/{{repo}}/git instead."},
                    status_code=400
                )

            # Build git arguments
            git_args = git_request.operation
            if git_request.args:
                git_args += f" {git_request.args}"

            # Validate arguments
            validate_git_args(git_args)

            # Get repository path
            repo_path = self.get_repo_path(repo)

            # Build command
            cmd = ["git"] + git_args.split()

            # Execute
            result = await self.run_command(cmd, cwd=repo_path)
            return JSONResponse({"success": True, "data": result})
        except Exception as e:
            logger.error(f"Error running git: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # Streaming SSE Endpoints for Long Operations
    async def stream_make(self, request: Request):
        """POST /stream/repos/{repo}/make - Stream make output in real-time"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            body = await request.json()
            make_request = MakeStreamRequest(**body)

            # Validate arguments
            validate_make_args(make_request.args)

            # Get repository path
            repo_path = self.get_repo_path(repo)

            # Build command
            cmd = ["make"]
            if make_request.args:
                cmd.extend(make_request.args.split())

            # Stream execution
            async def event_generator():
                """Generate SSE events from command output"""
                try:
                    async for chunk in self.run_command_streaming(cmd, cwd=repo_path):
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as e:
                    logger.error(f"Error in stream: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # Disable nginx buffering
                }
            )
        except Exception as e:
            logger.error(f"Error setting up make stream: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    async def stream_git(self, request: Request):
        """POST /stream/repos/{repo}/git - Stream git operation output in real-time"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            body = await request.json()
            git_request = GitStreamRequest(**body)

            # Build git arguments
            git_args = git_request.operation
            if git_request.args:
                git_args += f" {git_request.args}"

            # Validate arguments
            validate_git_args(git_args)

            # Get repository path
            repo_path = self.get_repo_path(repo)

            # Build command
            cmd = ["git"] + git_args.split()

            # Stream execution
            async def event_generator():
                """Generate SSE events from command output"""
                try:
                    async for chunk in self.run_command_streaming(cmd, cwd=repo_path):
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as e:
                    logger.error(f"Error in stream: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        except Exception as e:
            logger.error(f"Error setting up git stream: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    def create_http_app(self):
        """Create Starlette ASGI application for HTTP transport"""
        routes = [
            # MCP Protocol endpoint (backwards compatibility)
            Route("/sse", endpoint=self.handle_sse, methods=["GET"]),

            # REST API endpoints for quick operations
            Route("/api/repos", endpoint=self.api_list_repos, methods=["GET"]),
            Route("/api/repos/{repo}/env", endpoint=self.api_get_env, methods=["GET"]),
            Route("/api/repos/{repo}/ls", endpoint=self.api_ls, methods=["POST"]),
            Route("/api/repos/{repo}/git/quick", endpoint=self.api_git_quick, methods=["POST"]),

            # Streaming SSE endpoints for long operations
            Route("/stream/repos/{repo}/make", endpoint=self.stream_make, methods=["POST"]),
            Route("/stream/repos/{repo}/git", endpoint=self.stream_git, methods=["POST"]),
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
        logger.info(f"")
        logger.info(f"Available endpoints:")
        logger.info(f"  MCP Protocol (SSE): http://{HTTP_HOST}:{HTTP_PORT}/sse")
        logger.info(f"")
        logger.info(f"  REST API (Quick Operations):")
        logger.info(f"    GET  /api/repos - List repositories")
        logger.info(f"    GET  /api/repos/{{repo}}/env - Get environment info")
        logger.info(f"    POST /api/repos/{{repo}}/ls - List directory contents")
        logger.info(f"    POST /api/repos/{{repo}}/git/quick - Quick git operations (status, branch, log)")
        logger.info(f"")
        logger.info(f"  Streaming API (Long Operations):")
        logger.info(f"    POST /stream/repos/{{repo}}/make - Stream make output")
        logger.info(f"    POST /stream/repos/{{repo}}/git - Stream git operations (pull, fetch, diff, show, checkout)")
        logger.info(f"")
        if SESSION_KEY:
            logger.info("Authentication: Session key required")
            logger.info("  Header: Authorization: Bearer <session-key>")
            logger.info("  Or query param: ?key=<session-key>")
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


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="MCP Build Service - Provides build environment access via MCP protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default stdio transport
  %(prog)s

  # Start with HTTP transport
  %(prog)s --transport http --host 0.0.0.0 --port 3344

  # Start with HTTP transport and custom session key
  %(prog)s --transport http --session-key my-secret-key

  # Start with HTTP transport and auto-generated session key
  %(prog)s --transport http --generate-key
        """
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address for HTTP transport (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=3344,
        help="Port for HTTP transport (default: 3344)"
    )

    parser.add_argument(
        "--session-key",
        help="Session key for HTTP authentication (required for HTTP transport unless --generate-key is used)"
    )

    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Auto-generate a random session key for HTTP transport"
    )

    return parser.parse_args()


async def main():
    """Main async entry point"""
    global TRANSPORT_MODE, HTTP_HOST, HTTP_PORT, SESSION_KEY

    # Parse command-line arguments
    args = parse_args()

    # Set configuration from arguments
    TRANSPORT_MODE = args.transport.lower()
    HTTP_HOST = args.host
    HTTP_PORT = args.port

    # Handle session key
    if args.session_key:
        SESSION_KEY = args.session_key
    elif args.generate_key or TRANSPORT_MODE == "http":
        # Generate a random session key if not provided and in HTTP mode
        if TRANSPORT_MODE == "http" and not args.session_key:
            SESSION_KEY = secrets.token_urlsafe(32)
            logger.warning("=" * 80)
            logger.warning("Generated session key for HTTP transport:")
            logger.warning(f"  {SESSION_KEY}")
            logger.warning("To reuse this key, start the server with:")
            logger.warning(f"  {' '.join(['mcp-build-server', '--transport', 'http', '--session-key', SESSION_KEY])}")
            logger.warning("=" * 80)

    # Create and run server
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
