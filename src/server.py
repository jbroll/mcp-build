#!/usr/bin/env python3
"""
MCP Build Service

Provides build environment access via MCP protocol with commands:
- list: Show available repos
- make: Run make with specified arguments
- git: Run git commands (limited to safe operations)
- ls: List files/directories in repository
- read_file: Read file contents with optional line range
- env: Show environment information and tool versions
"""

import argparse
import asyncio
import json
import logging
import os
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import urllib.request
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
from starlette.responses import JSONResponse, StreamingResponse, PlainTextResponse
from starlette.requests import Request
import uvicorn

from validators import validate_git_args, validate_make_args, validate_ls_args, validate_path, validate_file_path

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
EXTERNAL_HOST = None  # External hostname for display/docs (defaults to socket.gethostname())
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


class ReadFileRequest(BaseModel):
    """Request model for read_file command"""
    path: str = Field(..., description="Path to the file to read")
    start_line: int | None = Field(default=None, description="Starting line number (1-indexed, optional)")
    end_line: int | None = Field(default=None, description="Ending line number (1-indexed, optional)")


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
        logger.info(f"Try Key: {token} : {SESSION_KEY}")
        if secrets.compare_digest(token, SESSION_KEY):
            return True

    # Check query parameter
    token = request.query_params.get("key", "")
    logger.info(f"Try Key: {token} : {SESSION_KEY}")
    if token and secrets.compare_digest(token, SESSION_KEY):
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

            logger.info(f"Discovered {len(self.repos)} repositories in {REPOS_BASE_DIR}")
        except Exception as e:
            logger.error(f"Error discovering repositories: {e}", exc_info=True)
            self.repos = {}

    def get_repo_path(self, repo_name: str) -> Path:
        """Get the path to a repository. Repository name is required."""
        if not repo_name:
            raise ValueError("Repository name is required")
        if repo_name not in self.repos:
            raise ValueError(f"Unknown repository: {repo_name}")
        return Path(self.repos[repo_name]["path"])

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
                            "description": "Repository name (required)"
                        }
                    },
                    "required": ["repo"]
                }
            ),
            Tool(
                name="git",
                description="Run git commands in a repository. "
                           "Limited to safe operations: status, log, checkout, pull, branch, diff, fetch, reset, show",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "string",
                            "description": "Git command and arguments (e.g., 'status', 'checkout main', 'pull origin main')"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name (required)"
                        }
                    },
                    "required": ["args", "repo"]
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
                            "description": "Repository name (required)"
                        }
                    },
                    "required": ["repo"]
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
                            "description": "Repository name (required)"
                        }
                    },
                    "required": ["repo"]
                }
            ),
            Tool(
                name="read_file",
                description="Read the contents of a file in a repository. "
                           "Supports reading specific line ranges for large files.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "Repository name (required)"
                        },
                        "path": {
                            "type": "string",
                            "description": "Absolute path to the file to read (required)"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Starting line number (1-indexed, optional). If provided, only lines from start_line to end_line will be returned."
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Ending line number (1-indexed, optional). If provided, only lines from start_line to end_line will be returned."
                        }
                    },
                    "required": ["repo", "path"]
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
            elif name == "read_file":
                return await self.handle_read_file(arguments)
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
            output += f"- {name}\n"
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
            cmd.extend(shlex.split(make_args))

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
        cmd = ["git"] + shlex.split(git_args)

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
            cmd.extend(shlex.split(ls_args))

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

    async def handle_read_file(self, args: Dict[str, Any]) -> List[TextContent]:
        """Handle read_file command"""
        repo = args.get("repo")
        file_path = args.get("path")
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        if not file_path:
            raise ValueError("File path is required")

        # Get repository path
        repo_path = self.get_repo_path(repo)

        # Validate and resolve the file path
        validated_path = validate_file_path(file_path, repo_path)

        # Read the file
        try:
            with open(validated_path, 'r', encoding='utf-8', errors='replace') as f:
                if start_line is not None or end_line is not None:
                    # Read specific line range
                    lines = f.readlines()
                    total_lines = len(lines)

                    # Validate line numbers
                    if start_line is not None and start_line < 1:
                        raise ValueError(f"start_line must be >= 1, got {start_line}")
                    if end_line is not None and end_line < 1:
                        raise ValueError(f"end_line must be >= 1, got {end_line}")
                    if start_line is not None and end_line is not None and start_line > end_line:
                        raise ValueError(f"start_line ({start_line}) must be <= end_line ({end_line})")

                    # Default values
                    start_idx = (start_line - 1) if start_line is not None else 0
                    end_idx = end_line if end_line is not None else total_lines

                    # Clamp to valid range
                    start_idx = max(0, min(start_idx, total_lines))
                    end_idx = max(0, min(end_idx, total_lines))

                    # Extract the requested lines
                    selected_lines = lines[start_idx:end_idx]

                    # Format output with line numbers
                    output = f"File: {validated_path}\n"
                    output += f"Lines {start_idx + 1}-{end_idx} of {total_lines}\n"
                    output += "=" * 80 + "\n"
                    for i, line in enumerate(selected_lines, start=start_idx + 1):
                        output += f"{i:6d}: {line.rstrip()}\n"

                    return [TextContent(type="text", text=output)]
                else:
                    # Read entire file
                    content = f.read()
                    lines_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)

                    output = f"File: {validated_path}\n"
                    output += f"Total lines: {lines_count}\n"
                    output += "=" * 80 + "\n"

                    # Add line numbers to entire file
                    for i, line in enumerate(content.splitlines(), start=1):
                        output += f"{i:6d}: {line}\n"

                    return [TextContent(type="text", text=output)]

        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {validated_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied reading file: {validated_path}")
        except Exception as e:
            raise Exception(f"Error reading file {validated_path}: {str(e)}")

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

        # SSE connection has been handled through the transport's send callback
        # We don't need to return a response as the ASGI protocol was handled directly
        # However, to satisfy Starlette's routing, we should not return None
        # The connection is already closed by the context manager above
        return None

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
                    is_default=False  # No default repository
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
                cmd.extend(shlex.split(ls_request.args))

            # Execute
            result = await self.run_command(cmd, cwd=repo_path)
            return JSONResponse({"success": True, "data": result})
        except Exception as e:
            logger.error(f"Error running ls: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    async def api_read_file(self, request: Request):
        """POST /api/repos/{repo}/read_file - Read file contents"""
        if not verify_session_key(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            repo = request.path_params.get("repo")
            body = await request.json()
            read_file_request = ReadFileRequest(**body)

            # Get repository path
            repo_path = self.get_repo_path(repo)

            # Validate and resolve the file path
            validated_path = validate_file_path(read_file_request.path, repo_path)

            # Read the file (reuse the logic from handle_read_file)
            with open(validated_path, 'r', encoding='utf-8', errors='replace') as f:
                if read_file_request.start_line is not None or read_file_request.end_line is not None:
                    # Read specific line range
                    lines = f.readlines()
                    total_lines = len(lines)

                    # Validate line numbers
                    if read_file_request.start_line is not None and read_file_request.start_line < 1:
                        raise ValueError(f"start_line must be >= 1, got {read_file_request.start_line}")
                    if read_file_request.end_line is not None and read_file_request.end_line < 1:
                        raise ValueError(f"end_line must be >= 1, got {read_file_request.end_line}")
                    if (read_file_request.start_line is not None and
                        read_file_request.end_line is not None and
                        read_file_request.start_line > read_file_request.end_line):
                        raise ValueError(
                            f"start_line ({read_file_request.start_line}) must be <= "
                            f"end_line ({read_file_request.end_line})"
                        )

                    # Default values
                    start_idx = (read_file_request.start_line - 1) if read_file_request.start_line is not None else 0
                    end_idx = read_file_request.end_line if read_file_request.end_line is not None else total_lines

                    # Clamp to valid range
                    start_idx = max(0, min(start_idx, total_lines))
                    end_idx = max(0, min(end_idx, total_lines))

                    # Extract the requested lines
                    selected_lines = lines[start_idx:end_idx]

                    # Format output with line numbers
                    output = f"File: {validated_path}\n"
                    output += f"Lines {start_idx + 1}-{end_idx} of {total_lines}\n"
                    output += "=" * 80 + "\n"
                    for i, line in enumerate(selected_lines, start=start_idx + 1):
                        output += f"{i:6d}: {line.rstrip()}\n"

                    return JSONResponse({"success": True, "data": output})
                else:
                    # Read entire file
                    content = f.read()
                    lines_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)

                    output = f"File: {validated_path}\n"
                    output += f"Total lines: {lines_count}\n"
                    output += "=" * 80 + "\n"

                    # Add line numbers to entire file
                    for i, line in enumerate(content.splitlines(), start=1):
                        output += f"{i:6d}: {line}\n"

                    return JSONResponse({"success": True, "data": output})

        except FileNotFoundError as e:
            logger.error(f"File not found: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=404)
        except ValueError as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)
        except Exception as e:
            logger.error(f"Error reading file: {e}", exc_info=True)
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
            cmd = ["git"] + shlex.split(git_args)

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
                cmd.extend(shlex.split(make_request.args))

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
            cmd = ["git"] + shlex.split(git_args)

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

    async def serve_documentation(self, request: Request):
        """GET /mcp-build.md?key=SESSION_KEY - Serve dynamically generated documentation"""
        # Documentation endpoint requires authentication
        if not verify_session_key(request):
            logger.warning(f"Unauthorized documentation access attempt from {request.client.host}")
            return PlainTextResponse("Unauthorized", status_code=403)

        try:
            doc_path = Path(__file__).parent / "MCP-BUILD.md"
            if not doc_path.exists():
                return PlainTextResponse(
                    "Documentation not found. Please see README.md in the mcp-build repository.",
                    status_code=404
                )

            # Read base documentation
            content = doc_path.read_text()

            # Extract session key from request
            session_key = request.query_params.get("key", "")
            if not session_key and self.session_key:
                # Fall back to session_key from self if not in query params
                session_key = self.session_key

            # Construct SSE endpoint URL dynamically
            # Use HTTPS scheme (service is always deployed behind HTTPS proxy)
            host = request.headers.get("host", f"{request.url.hostname}:{request.url.port}")
            sse_endpoint = f"https://{host}/sse?key={session_key}"

            # Inject connection information at the top of the document
            connection_header = f"""# MCP Build Service

**Connect to this service:** `{sse_endpoint}`

---

"""

            # Replace the first heading with our dynamic version
            # Find the first line starting with "# " and replace it with our header
            lines = content.split('\n')
            new_lines = []
            header_replaced = False

            for line in lines:
                if not header_replaced and line.startswith('# '):
                    # Skip the original title, we'll use our dynamic header
                    new_lines.append(connection_header.rstrip())
                    header_replaced = True
                else:
                    new_lines.append(line)

            dynamic_content = '\n'.join(new_lines)

            return PlainTextResponse(
                dynamic_content,
                media_type="text/markdown",
                headers={
                    "Cache-Control": "private, no-cache",  # Don't cache personalized content
                }
            )
        except Exception as e:
            logger.error(f"Error serving documentation: {e}", exc_info=True)
            return PlainTextResponse(f"Error loading documentation: {str(e)}", status_code=500)

    def create_http_app(self):
        """Create Starlette ASGI application for HTTP transport"""
        routes = [
            # Documentation endpoint (public, no auth required)
            Route("/mcp-build.md", endpoint=self.serve_documentation, methods=["GET"]),

            # MCP Protocol endpoint (backwards compatibility)
            Route("/sse", endpoint=self.handle_sse, methods=["GET"]),

            # REST API endpoints for quick operations
            Route("/api/repos", endpoint=self.api_list_repos, methods=["GET"]),
            Route("/api/repos/{repo}/env", endpoint=self.api_get_env, methods=["GET"]),
            Route("/api/repos/{repo}/ls", endpoint=self.api_ls, methods=["POST"]),
            Route("/api/repos/{repo}/read_file", endpoint=self.api_read_file, methods=["POST"]),
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

        # Use external hostname for display (not bind address)
        display_host = EXTERNAL_HOST if EXTERNAL_HOST else HTTP_HOST

        logger.info(f"MCP Build Server starting with HTTP transport on {HTTP_HOST}:{HTTP_PORT}")
        logger.info(f"")
        logger.info(f"Documentation: http://{display_host}:{HTTP_PORT}/mcp-build.md")
        logger.info(f"")
        logger.info(f"Available endpoints:")
        logger.info(f"  MCP Protocol (SSE): http://{display_host}:{HTTP_PORT}/sse")
        logger.info(f"")
        logger.info(f"  REST API (Quick Operations):")
        logger.info(f"    GET  /api/repos - List repositories")
        logger.info(f"    GET  /api/repos/{{repo}}/env - Get environment info")
        logger.info(f"    POST /api/repos/{{repo}}/ls - List directory contents")
        logger.info(f"    POST /api/repos/{{repo}}/read_file - Read file contents")
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
            logger.info("")
            logger.info("=" * 80)
            logger.info("Copy-paste this message to AI agents:")
            logger.info("")
            print(f"\n\nUse the MCP build service http://{display_host}:{HTTP_PORT}/mcp-build.md\nSession key: {SESSION_KEY}\n\n")
            logger.info("=" * 80)
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


def detect_public_ip(timeout=5):
    """Detect public IP address using external service"""
    services = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com"
    ]

    for service in services:
        try:
            logger.info(f"Detecting public IP from {service}...")
            with urllib.request.urlopen(service, timeout=timeout) as response:
                ip = response.read().decode('utf-8').strip()
                logger.info(f"Detected public IP: {ip}")
                return ip
        except Exception as e:
            logger.debug(f"Failed to get IP from {service}: {e}")
            continue

    logger.warning("Could not detect public IP address")
    return None


def setup_signal_handlers():
    """Set up signal handlers for immediate shutdown"""
    def signal_handler(signum, frame):
        """Handle shutdown signals in a signal-safe way"""
        sig_name = signal.Signals(signum).name
        # Use os.write for signal-safe output (logger is not signal-safe)
        msg = f"\nReceived {sig_name}, shutting down...\n".encode('utf-8')
        os.write(sys.stderr.fileno(), msg)

        # Stop the event loop gracefully instead of forcing sys.exit(0)
        try:
            loop = asyncio.get_running_loop()
            loop.stop()
        except RuntimeError:
            # No event loop running, exit immediately
            sys.exit(0)

    # Register handlers for SIGINT (Ctrl+C) and SIGTERM
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="MCP Build Service - Provides build environment access via MCP protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default stdio transport
  %(prog)s

  # Start with HTTP transport (auto-generates session key)
  %(prog)s --transport http

  # Start with HTTP transport and custom session key
  %(prog)s --transport http --session-key my-secret-key

  # Start with HTTP transport and specify external hostname for display
  %(prog)s --transport http --external-host example.com

  # Start with HTTP and auto-detect public IP (useful behind NAT/router)
  %(prog)s --transport http --detect-public-ip

  # Combine: use public IP detection with custom session key
  %(prog)s --transport http --detect-public-ip --session-key my-key

  # Use persistent session key with file-based storage
  # First run: generates and saves key to file
  # Subsequent runs: loads existing key from file
  %(prog)s --transport http --key-file ~/.mcp-build-key

  # Override with specific session key (and save to file)
  %(prog)s --transport http --session-key my-secret --key-file ~/.mcp-build-key
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
        "--external-host",
        help="External hostname/IP for documentation URLs (default: auto-detected from system hostname)"
    )

    parser.add_argument(
        "--detect-public-ip",
        action="store_true",
        help="Auto-detect public IP address using external service (useful when behind NAT/router)"
    )

    parser.add_argument(
        "--session-key",
        help="Session key for HTTP authentication (overrides key from --key-file if both provided)"
    )

    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Auto-generate a random session key for HTTP transport"
    )

    parser.add_argument(
        "--key-file",
        help="File path for persistent session key storage (reads existing key or generates new one)"
    )

    return parser.parse_args()


async def main():
    """Main async entry point"""
    global TRANSPORT_MODE, HTTP_HOST, HTTP_PORT, EXTERNAL_HOST, SESSION_KEY

    # Parse command-line arguments
    args = parse_args()

    # Set configuration from arguments
    TRANSPORT_MODE = args.transport.lower()
    HTTP_HOST = args.host
    HTTP_PORT = args.port

    # Set external hostname for display purposes
    if args.external_host:
        EXTERNAL_HOST = args.external_host
    elif args.detect_public_ip:
        # Detect public IP address
        EXTERNAL_HOST = detect_public_ip()
        if not EXTERNAL_HOST:
            # Fallback to local hostname if detection fails
            try:
                EXTERNAL_HOST = socket.gethostname()
            except Exception:
                EXTERNAL_HOST = "localhost"
    else:
        # Auto-detect local hostname
        try:
            EXTERNAL_HOST = socket.gethostname()
        except Exception:
            EXTERNAL_HOST = "localhost"

    # Handle session key with file-based persistence
    import os
    key_from_file = None

    # Try to read existing key from file if --key-file is provided
    if args.key_file:
        key_path = os.path.expanduser(args.key_file)
        if os.path.exists(key_path):
            try:
                with open(key_path, 'r') as f:
                    key_from_file = f.read().strip()
                if key_from_file:
                    logger.info(f"Loaded existing session key from: {key_path}")
            except Exception as e:
                logger.warning(f"Failed to read session key from {key_path}: {e}")
                key_from_file = None

    # Determine session key (priority: explicit arg > file > generate)
    if args.session_key:
        # Explicit session key takes highest priority
        SESSION_KEY = args.session_key
        logger.info("Using session key from command-line argument")
    elif key_from_file:
        # Use existing key from file
        SESSION_KEY = key_from_file
    elif args.generate_key or TRANSPORT_MODE == "http":
        # Generate a new key if in HTTP mode and no key provided
        if TRANSPORT_MODE == "http":
            SESSION_KEY = secrets.token_urlsafe(32)
            logger.warning("=" * 80)
            logger.warning("Generated NEW session key for HTTP transport:")
            logger.warning(f"  {SESSION_KEY}")
            logger.warning("")
            if args.key_file:
                logger.warning(f"Key will be persisted to: {args.key_file}")
            else:
                logger.warning("To reuse this key, start the server with:")
                logger.warning(f"  mcp-build --transport http --session-key {SESSION_KEY}")
            logger.warning("=" * 80)

    # Write session key to file if requested (whether read, provided, or generated)
    if args.key_file and SESSION_KEY:
        try:
            key_path = os.path.expanduser(args.key_file)

            # Only write if key changed or file doesn't exist
            should_write = True
            if os.path.exists(key_path):
                try:
                    with open(key_path, 'r') as f:
                        existing_key = f.read().strip()
                    if existing_key == SESSION_KEY:
                        should_write = False  # Key unchanged, no need to write
                except Exception:
                    pass  # Write anyway if we can't read

            if should_write:
                with open(key_path, 'w') as f:
                    f.write(SESSION_KEY)
                os.chmod(key_path, 0o600)  # Set to user-read-write only
                logger.info(f"Session key written to: {key_path}")
        except Exception as e:
            logger.error(f"Failed to write session key to {args.key_file}: {e}")
            sys.exit(1)

    # Set up signal handlers for immediate shutdown
    setup_signal_handlers()

    # Create and run server
    server = BuildEnvironmentServer()

    try:
        if TRANSPORT_MODE == "http":
            await server.run_http()
        else:
            # Default to stdio
            await server.run()
    except KeyboardInterrupt:
        # This will be caught if the signal handler doesn't stop the loop first
        logger.info("\nShutdown complete")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


def cli():
    """Synchronous entry point for setuptools console_scripts"""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
