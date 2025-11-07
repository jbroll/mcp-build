"""
Argument validators for build environment commands

These validators provide basic safety checks to prevent accidents,
not bulletproof security. They block obvious path traversal attempts
and dangerous command patterns.
"""

import re
from pathlib import Path


# Allowed git subcommands
ALLOWED_GIT_COMMANDS = {
    "status", "log", "checkout", "pull", "branch", "diff", "fetch", "reset", "show"
}

# Dangerous patterns to block
DANGEROUS_PATTERNS = [
    r"\.\./",  # Path traversal
    r"/\.\./",  # Path traversal
    r"^\.\.",  # Relative parent path
    r";",      # Command chaining
    r"\|",     # Pipes
    r"&",      # Background/chaining
    r"`",      # Command substitution
    r"\$\(",   # Command substitution
    r">",      # Redirection
    r"<",      # Redirection
]


def contains_dangerous_pattern(text: str) -> bool:
    """Check if text contains dangerous patterns"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def validate_path(path: str) -> None:
    """
    Validate that a path is safe (no traversal, stays in relative directory)

    Args:
        path: Path string to validate

    Raises:
        ValueError: If path contains dangerous patterns
    """
    if not path:
        return

    if contains_dangerous_pattern(path):
        raise ValueError(f"Path contains dangerous patterns: {path}")

    # Check for absolute paths (should be relative)
    if path.startswith('/'):
        raise ValueError(f"Absolute paths not allowed: {path}")

    # Ensure normalized path doesn't escape
    try:
        normalized = Path(path).resolve()
        # This is a basic check - in real usage, we'd check against the repo root
        if ".." in Path(path).parts:
            raise ValueError(f"Path traversal not allowed: {path}")
    except Exception as e:
        raise ValueError(f"Invalid path: {path} - {e}")


def validate_git_args(args: str) -> None:
    """
    Validate git command arguments

    Only allows safe read-only and branch operations:
    - status, log, branch, diff, show (read-only)
    - checkout, pull, fetch (branch operations)

    Args:
        args: Git command arguments

    Raises:
        ValueError: If arguments contain dangerous patterns or disallowed commands
    """
    if not args:
        raise ValueError("Git command requires arguments")

    # Check for dangerous patterns
    if contains_dangerous_pattern(args):
        raise ValueError(f"Git arguments contain dangerous patterns: {args}")

    # Extract the git subcommand (first word)
    parts = args.strip().split()
    if not parts:
        raise ValueError("Empty git command")

    subcommand = parts[0].lower()

    # Check if subcommand is allowed
    if subcommand not in ALLOWED_GIT_COMMANDS:
        raise ValueError(
            f"Git subcommand '{subcommand}' not allowed. "
            f"Allowed commands: {', '.join(sorted(ALLOWED_GIT_COMMANDS))}"
        )

    # Additional checks for specific commands
    if subcommand == "checkout":
        # Block checkout with -f (force) or -b with remote paths
        if "-f" in parts or "--force" in parts:
            raise ValueError("Force checkout not allowed")

    if subcommand == "pull":
        # Block force pull
        if "-f" in parts or "--force" in parts:
            raise ValueError("Force pull not allowed")


def validate_make_args(args: str) -> None:
    """
    Validate make command arguments

    Args:
        args: Make command arguments

    Raises:
        ValueError: If arguments contain dangerous patterns
    """
    if not args:
        return  # Empty args is fine (will run default target)

    # Check for dangerous patterns
    if contains_dangerous_pattern(args):
        raise ValueError(f"Make arguments contain dangerous patterns: {args}")

    # Make arguments should be targets or variable assignments
    # Allow: alphanumeric, underscore, hyphen, equals, space, slash (for paths), quotes (for values with spaces)
    if not re.match(r'^[\*a-zA-Z0-9_\-=\s/\.\'"]+$', args):
        raise ValueError(f"Make arguments contain invalid characters: {args}")


def validate_ls_args(args: str) -> None:
    """
    Validate ls command arguments

    Args:
        args: Ls command arguments

    Raises:
        ValueError: If arguments contain dangerous patterns
    """
    if not args:
        return  # Empty args is fine (will list current directory)

    # Check for dangerous patterns
    if contains_dangerous_pattern(args):
        raise ValueError(f"Ls arguments contain dangerous patterns: {args}")

    # Parse arguments to validate paths
    parts = args.split()
    for part in parts:
        # Skip flags (starting with -)
        if part.startswith('-'):
            # Validate flag is reasonable
            if not re.match(r'^-[a-zA-Z]+$', part):
                raise ValueError(f"Invalid ls flag: {part}")
            continue

        # Validate paths
        validate_path(part)


def validate_file_path(file_path: str, repo_path: Path) -> Path:
    """
    Validate a file path for reading and ensure it's within the repository.

    This validator accepts both absolute and relative paths but ensures that
    the final resolved path is within the repository directory.

    Args:
        file_path: The file path to validate (can be absolute or relative)
        repo_path: The repository root path

    Returns:
        Path: The validated absolute path to the file

    Raises:
        ValueError: If path contains dangerous patterns or escapes the repository
    """
    if not file_path:
        raise ValueError("File path cannot be empty")

    # Check for dangerous command injection patterns
    # We're less strict than validate_path since we're only reading files
    dangerous_for_file_read = [
        r";",      # Command chaining
        r"\|",     # Pipes
        r"&",      # Background/chaining
        r"`",      # Command substitution
        r"\$\(",   # Command substitution
    ]

    for pattern in dangerous_for_file_read:
        if re.search(pattern, file_path):
            raise ValueError(f"File path contains dangerous pattern: {file_path}")

    # Convert to Path object
    path_obj = Path(file_path)

    # Resolve the path to absolute
    if path_obj.is_absolute():
        # Absolute path - resolve it
        resolved_path = path_obj.resolve()
    else:
        # Relative path - resolve relative to repo
        resolved_path = (repo_path / path_obj).resolve()

    # Ensure the resolved path is within the repository
    repo_path_resolved = repo_path.resolve()
    try:
        # This will raise ValueError if resolved_path is not relative to repo_path
        resolved_path.relative_to(repo_path_resolved)
    except ValueError:
        raise ValueError(
            f"Access denied: Path '{file_path}' resolves to '{resolved_path}' "
            f"which is outside repository '{repo_path_resolved}'"
        )

    # Additional check: ensure no parent directory traversal in original path
    # This catches things like "foo/../../etc/passwd" even if they resolve safely
    if ".." in path_obj.parts:
        # But we need to verify it doesn't escape
        try:
            if path_obj.is_absolute():
                check_path = path_obj.resolve()
            else:
                check_path = (repo_path / path_obj).resolve()
            check_path.relative_to(repo_path_resolved)
        except ValueError:
            raise ValueError(f"Path traversal not allowed: {file_path}")

    return resolved_path
