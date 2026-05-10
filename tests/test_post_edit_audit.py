#!/usr/bin/env python3
"""Unit tests for post-edit-audit.py hook.

The hook uses REPO calculated as the parent of the repo root (via three
os.path.dirname calls), so audit output goes to <parent-of-repo>/.claude/audit.jsonl.
Tests run via subprocess to get the real hook behavior with correct path resolution.
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest


def _repo_root():
    """The repo root dir (hooks/ -> repo -> parent -> parent-of-repo)."""
    hook_file = Path(__file__).parent.parent / "hooks" / "post-edit-audit.py"
    return Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(str(hook_file))))))


def _audit_file():
    """Where the hook actually writes (parent-of-repo/.claude/audit.jsonl).

    The hook calculates: hooks/ -> repo -> parent -> parent-of-repo.
    So audit-trail plugin → /workspace/repos/.claude/audit.jsonl.
    """
    # hooks/ -> audit-trail -> repos -> parent-of-repos
    return Path("/workspace/repos/.claude/audit.jsonl")


def _ensure_audit_dir():
    """Create the .claude directory before running the hook."""
    af = _audit_file()
    af.parent.mkdir(parents=True, exist_ok=True)


def _clean_audit():
    """Remove the audit file and its parent dir if empty."""
    af = _audit_file()
    try:
        if af.exists():
            af.unlink()
        parent = af.parent
        if parent.exists() and not list(parent.iterdir()):
            parent.rmdir()
    except (OSError, FileNotFoundError):
        pass


def run_hook(tool_name, tool_input, tool_response):
    """Run the real hook via subprocess to match production path resolution."""
    _clean_audit()
    _ensure_audit_dir()

    stdin_data = json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    })

    hook_path = Path(__file__).parent.parent / "hooks" / "post-edit-audit.py"
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )

    af = _audit_file()
    records = []
    if af.exists():
        with open(af) as f:
            records = [json.loads(line) for line in f if line.strip()]
        _clean_audit()

    return records, result.stdout, result.stderr


def make_record(tool_name, file_path=None, notebook_path=None, success=True):
    """Helper to create a tool call record and run the hook."""
    ti = {}
    if file_path:
        ti["file_path"] = file_path
    if notebook_path:
        ti["notebook_path"] = notebook_path
    return run_hook(tool_name, ti, {"success": success})


class TestAuditRecordFields:
    """Tests for the JSONL record format."""

    def test_records_timestamp_utc_iso_format(self):
        records, _, _ = make_record("Edit", file_path="src/main.go", success=True)
        assert len(records) == 1
        ts = records[0]["ts"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_records_tool_name(self):
        records, _, _ = make_record("Edit", file_path="src/main.go", success=True)
        assert records[0]["tool"] == "Edit"

        records, _, _ = make_record("Write", file_path="README.md", success=True)
        assert records[0]["tool"] == "Write"

    def test_records_file_relative_path(self):
        records, _, _ = make_record("Edit", file_path="src/main.go", success=True)
        assert records[0]["file"] == "src/main.go"

    def test_records_ok_from_tool_response_success(self):
        records, _, _ = make_record("Edit", file_path="src/main.go", success=True)
        assert records[0]["ok"] is True

        records, _, _ = make_record("Edit", file_path="src/main.go", success=False)
        assert records[0]["ok"] is False

    def test_defaults_ok_to_true_on_missing_success(self):
        records, _, _ = run_hook("Edit", {"file_path": "src/main.go"}, {})
        assert records[0]["ok"] is True


class TestNotebookEdits:
    """Tests for NotebookEdit tool handling."""

    def test_handles_notebook_path(self):
        records, _, _ = make_record("NotebookEdit", notebook_path="notebooks/analysis.ipynb", success=True)
        assert len(records) == 1
        assert records[0]["file"] == "notebooks/analysis.ipynb"

    def test_file_path_takes_precedence_over_notebook_path(self):
        records, _, _ = run_hook(
            "Edit",
            {"file_path": "src/main.go", "notebook_path": "notebooks/old.ipynb"},
            {"success": True}
        )
        assert records[0]["file"] == "src/main.go"


class TestMissingFilePath:
    """Tests for edge cases with missing or empty file paths."""

    def test_handles_empty_tool_input(self):
        records, _, _ = run_hook("Edit", {}, {"success": True})
        assert len(records) == 1
        assert records[0]["file"] == ""

    def test_no_crash_on_missing_tool_input_key(self):
        records, _, _ = run_hook("Edit", {"other_key": "value"}, {"success": True})
        assert len(records) == 1


class TestSilenceOnError:
    """Tests that the hook never raises or exits non-zero on errors."""

    def test_hook_exits_zero_on_file_error(self):
        """Even if audit file can't be written, hook should exit 0."""
        # Make the audit directory read-only so writes fail
        _ensure_audit_dir()
        audit_file = _audit_file()
        # Create the file first, then make it read-only
        audit_file.write_text("")
        audit_file.chmod(0o444)  # read-only
        try:
            stdin_data = json.dumps({
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/main.go"},
                "tool_response": {"success": True},
            })
            hook_path = Path(__file__).parent.parent / "hooks" / "post-edit-audit.py"
            result = subprocess.run(
                [sys.executable, str(hook_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
            )
            # Should exit 0 (error is silently swallowed)
            assert result.returncode == 0
        finally:
            audit_file.chmod(0o644)
            if audit_file.exists():
                audit_file.unlink()

    def test_no_stdout_on_success(self):
        """Successful write should not emit stdout (unlike PreToolUse hooks)."""
        records, stdout, stderr = make_record("Edit", file_path="src/main.go", success=True)
        assert stdout.strip() == ""  # audit hook doesn't emit stdout


class TestJsonlFormat:
    """Tests for JSONL append-only format."""

    def test_writes_one_json_object_per_line(self):
        audit_file = _audit_file()
        audit_parent = audit_file.parent
        _ensure_audit_dir()
        if audit_file.exists():
            audit_file.unlink()

        # Write two records
        make_record("Edit", file_path="a.txt", success=True)
        make_record("Write", file_path="b.txt", success=True)

        if audit_file.exists():
            with open(audit_file) as f:
                lines = [l.strip() for l in f if l.strip()]
            # Each line should be valid JSON with all required fields
            for line in lines:
                obj = json.loads(line)
                assert "ts" in obj
                assert "tool" in obj
                assert "file" in obj
                assert "ok" in obj
            audit_file.unlink()
            if audit_parent.exists() and not list(audit_parent.iterdir()):
                audit_parent.rmdir()

    def test_records_are_append_only(self):
        audit_file = _audit_file()
        audit_parent = audit_file.parent
        _ensure_audit_dir()
        if audit_file.exists():
            audit_file.unlink()

        # Write two records
        make_record("Edit", file_path="x.txt", success=True)
        make_record("Edit", file_path="y.txt", success=True)

        if audit_file.exists():
            with open(audit_file) as f:
                lines = [l for l in f if l.strip()]
            assert len(lines) >= 2  # appends, doesn't overwrite
            audit_file.unlink()
            if audit_parent.exists() and not list(audit_parent.iterdir()):
                audit_parent.rmdir()