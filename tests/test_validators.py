"""
Tests for argument validators
"""

import pytest
from validators import (
    validate_git_args,
    validate_make_args,
    validate_ls_args,
    validate_path,
)


class TestPathValidation:
    """Tests for path validation"""

    def test_valid_relative_paths(self):
        """Test that valid relative paths are accepted"""
        validate_path("src/main.c")
        validate_path("build/output")
        validate_path("test.txt")
        validate_path("dir/subdir/file.txt")

    def test_reject_absolute_paths(self):
        """Test that absolute paths are rejected"""
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            validate_path("/etc/passwd")

    def test_reject_parent_traversal(self):
        """Test that parent directory traversal is rejected"""
        with pytest.raises(ValueError):
            validate_path("../etc/passwd")
        with pytest.raises(ValueError):
            validate_path("dir/../../etc")

    def test_reject_dangerous_patterns(self):
        """Test that dangerous patterns are rejected"""
        with pytest.raises(ValueError):
            validate_path("file;rm -rf /")
        with pytest.raises(ValueError):
            validate_path("file|cat")


class TestGitValidation:
    """Tests for git command validation"""

    def test_allowed_git_commands(self):
        """Test that allowed git commands pass validation"""
        validate_git_args("status")
        validate_git_args("log --oneline")
        validate_git_args("checkout main")
        validate_git_args("pull origin main")
        validate_git_args("branch -a")
        validate_git_args("diff HEAD~1")

    def test_reject_disallowed_commands(self):
        """Test that disallowed git commands are rejected"""
        with pytest.raises(ValueError, match="not allowed"):
            validate_git_args("push origin main")
        with pytest.raises(ValueError, match="not allowed"):
            validate_git_args("reset --hard")
        with pytest.raises(ValueError, match="not allowed"):
            validate_git_args("rebase -i")

    def test_reject_force_operations(self):
        """Test that force operations are rejected"""
        with pytest.raises(ValueError, match="Force checkout not allowed"):
            validate_git_args("checkout -f main")
        with pytest.raises(ValueError, match="Force pull not allowed"):
            validate_git_args("pull --force")

    def test_reject_dangerous_patterns(self):
        """Test that dangerous patterns in git args are rejected"""
        with pytest.raises(ValueError):
            validate_git_args("status; rm -rf /")
        with pytest.raises(ValueError):
            validate_git_args("log | grep secret")

    def test_empty_args(self):
        """Test that empty git args are rejected"""
        with pytest.raises(ValueError, match="requires arguments"):
            validate_git_args("")


class TestMakeValidation:
    """Tests for make command validation"""

    def test_valid_make_args(self):
        """Test that valid make arguments pass"""
        validate_make_args("")
        validate_make_args("clean")
        validate_make_args("all")
        validate_make_args("test")
        validate_make_args("clean all")
        validate_make_args("VAR=value target")
        validate_make_args("CC=gcc BUILD=release")

    def test_reject_dangerous_patterns(self):
        """Test that dangerous patterns are rejected"""
        with pytest.raises(ValueError):
            validate_make_args("target; rm -rf /")
        with pytest.raises(ValueError):
            validate_make_args("target | tee log")
        with pytest.raises(ValueError):
            validate_make_args("target && evil")

    def test_reject_invalid_characters(self):
        """Test that invalid characters are rejected"""
        with pytest.raises(ValueError):
            validate_make_args("target$")
        with pytest.raises(ValueError):
            validate_make_args("target`whoami`")


class TestLsValidation:
    """Tests for ls command validation"""

    def test_valid_ls_args(self):
        """Test that valid ls arguments pass"""
        validate_ls_args("")
        validate_ls_args("-la")
        validate_ls_args("-lh")
        validate_ls_args("-la src/")
        validate_ls_args("build/")

    def test_reject_dangerous_patterns(self):
        """Test that dangerous patterns are rejected"""
        with pytest.raises(ValueError):
            validate_ls_args("-la; rm -rf /")
        with pytest.raises(ValueError):
            validate_ls_args("-la | grep secret")

    def test_reject_path_traversal(self):
        """Test that path traversal in ls args is rejected"""
        with pytest.raises(ValueError):
            validate_ls_args("../../../etc/passwd")
        with pytest.raises(ValueError):
            validate_ls_args("-la /etc/passwd")

    def test_reject_invalid_flags(self):
        """Test that invalid flags are rejected"""
        with pytest.raises(ValueError):
            validate_ls_args("-la$")
