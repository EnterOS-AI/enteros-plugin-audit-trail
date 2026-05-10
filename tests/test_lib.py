#!/usr/bin/env python3
"""Unit tests for audit-trail hooks _lib.py helpers."""
import io
import json
import os
import sys
from unittest import mock

# Add hooks/ dir to path so _lib imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks"))


class TestReadInput:
    """Tests for read_input helper (imported from _lib)."""

    def test_parses_valid_json(self):
        """read_input should parse valid Claude Code hook JSON from stdin."""
        from _lib import read_input

        stdin = io.StringIO('{"tool_input": {"file_path": "src/main.py"}}')
        with mock.patch("sys.stdin", stdin):
            result = read_input()
        assert result["tool_input"]["file_path"] == "src/main.py"

    def test_empty_stdin_returns_empty_dict(self):
        """read_input with empty stdin should return an empty dict."""
        from _lib import read_input

        with mock.patch("sys.stdin", io.StringIO("")):
            result = read_input()
        assert result == {}

    def test_malformed_json_returns_empty_dict(self):
        """read_input with invalid JSON should return empty dict, not raise."""
        from _lib import read_input

        with mock.patch("sys.stdin", io.StringIO("not valid json")):
            result = read_input()
        assert result == {}


class TestEmit:
    """Tests for emit helper (imported from _lib)."""

    def test_emit_prints_json_to_stdout(self):
        """emit should print a JSON-encoded dict to stdout."""
        from _lib import emit

        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            emit({"foo": "bar"})
        output = stdout.getvalue()
        assert json.loads(output) == {"foo": "bar"}


class TestWarnToStderr:
    """Tests for warn_to_stderr (imported from _lib)."""

    def test_warn_to_stderr_writes_to_stderr(self):
        """warn_to_stderr should write to stderr."""
        from _lib import warn_to_stderr

        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            warn_to_stderr("warning message")
        assert "warning message" in stderr.getvalue()


class TestGetRepoRoot:
    """Tests for get_repo_root helper (imported from _lib)."""

    def test_production_layout_returns_repo(self):
        """Production: hook at <workspace>/<plugin>/hooks/hook.py → return the plugin repo."""
        from _lib import get_repo_root

        # /tmp/my-repo/hooks/hook.py → workspace=/tmp, relpath="my-repo/hooks/hook.py"
        # relpath does NOT start with "hooks/" → production → return repo
        result = get_repo_root("/tmp/my-repo/hooks/post-edit-audit.py")
        assert result == "/tmp/my-repo"

    def test_dev_layout_returns_workspace(self):
        """Dev layout: hook at <workspace>/hooks/hook.py → workspace IS the repo."""
        from _lib import get_repo_root

        # /workspace/hooks/hook.py → workspace=/workspace, relpath="hooks/hook.py"
        # relpath starts with "hooks/" → dev layout → return workspace
        result = get_repo_root("/workspace/hooks/post-edit-audit.py")
        assert result == "/workspace"

    def test_real_repo_path_in_this_repo(self):
        """Verify get_repo_root on the actual repo resolves to a valid root."""
        from _lib import get_repo_root

        # Hook is at: <repo>/hooks/post-edit-audit.py
        hooks_dir = os.path.join(os.path.dirname(__file__), "..", "hooks")
        hook_file = os.path.join(hooks_dir, "post-edit-audit.py")
        result = get_repo_root(hook_file)
        # Sanity: result is an absolute path and is a directory
        assert os.path.isabs(result), f"result {result!r} is not absolute"
        assert os.path.isdir(result), f"result {result!r} is not a directory"
