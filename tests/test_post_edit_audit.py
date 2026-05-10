#!/usr/bin/env python3
"""Integration tests for post-edit-audit.py hook.

Tests run the hook as a subprocess so the full environment (stdin/stdout,
file I/O) matches production.  The AUDIT_PATH env var controls where the hook
writes, letting tests use a temp location without relying on __file__-relative
path logic.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "post-edit-audit.py"


class TestAuditRecordFields(unittest.TestCase):
    """Tests for the JSONL record format."""

    def _run_hook(self, tool_name, tool_input, tool_response):
        """Write audit to a temp file and run the hook with AUDIT_PATH."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".audit.jsonl", delete=False
        ) as f:
            audit_path = f.name

        try:
            stdin_data = json.dumps({
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_response": tool_response,
            })
            result = subprocess.run(
                [sys.executable, str(HOOK_PATH)],
                input=stdin_data,
                capture_output=True,
                text=True,
                env={**os.environ, "AUDIT_PATH": audit_path},
            )
            records = []
            if Path(audit_path).exists():
                with open(audit_path) as f:
                    records = [json.loads(line) for line in f if line.strip()]
            return records, result.stdout, result.stderr
        finally:
            Path(audit_path).unlink(missing_ok=True)

    def test_records_timestamp_utc_iso_format(self):
        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {"success": True})
        assert len(records) == 1, f"Expected 1 record, got: {records}"
        ts = records[0]["ts"]
        assert ts.endswith("Z"), f"Timestamp should end with Z, got: {ts}"
        assert "T" in ts

    def test_records_tool_name(self):
        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {"success": True})
        assert records[0]["tool"] == "Edit"

        records, _, _ = self._run_hook("Write", {"file_path": "README.md"}, {"success": True})
        assert records[0]["tool"] == "Write"

    def test_records_file_relative_path(self):
        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {"success": True})
        assert records[0]["file"] == "src/main.go"

    def test_records_ok_from_tool_response_success(self):
        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {"success": True})
        assert records[0]["ok"] is True

        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {"success": False})
        assert records[0]["ok"] is False

    def test_defaults_ok_to_true_on_missing_success(self):
        records, _, _ = self._run_hook("Edit", {"file_path": "src/main.go"}, {})
        assert records[0]["ok"] is True


class TestNotebookEdits(unittest.TestCase):
    """Tests for NotebookEdit tool handling."""

    def _run_hook(self, tool_name, tool_input, tool_response):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".audit.jsonl", delete=False) as f:
            audit_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(HOOK_PATH)],
                input=json.dumps({"tool_name": tool_name, "tool_input": tool_input, "tool_response": tool_response}),
                capture_output=True, text=True,
                env={**os.environ, "AUDIT_PATH": audit_path},
            )
            records = []
            if Path(audit_path).exists():
                with open(audit_path) as f:
                    records = [json.loads(line) for line in f if line.strip()]
            return records
        finally:
            Path(audit_path).unlink(missing_ok=True)

    def test_handles_notebook_path(self):
        records = self._run_hook("NotebookEdit", {"notebook_path": "notebooks/analysis.ipynb"}, {"success": True})
        assert len(records) == 1
        assert records[0]["file"] == "notebooks/analysis.ipynb"

    def test_file_path_takes_precedence_over_notebook_path(self):
        records = self._run_hook(
            "Edit",
            {"file_path": "src/main.go", "notebook_path": "notebooks/old.ipynb"},
            {"success": True}
        )
        assert records[0]["file"] == "src/main.go"


class TestMissingFilePath(unittest.TestCase):
    """Tests for edge cases with missing or empty file paths."""

    def _run_hook(self, tool_input):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".audit.jsonl", delete=False) as f:
            audit_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(HOOK_PATH)],
                input=json.dumps({"tool_name": "Edit", "tool_input": tool_input, "tool_response": {"success": True}}),
                capture_output=True, text=True,
                env={**os.environ, "AUDIT_PATH": audit_path},
            )
            records = []
            if Path(audit_path).exists():
                with open(audit_path) as f:
                    records = [json.loads(line) for line in f if line.strip()]
            return records
        finally:
            Path(audit_path).unlink(missing_ok=True)

    def test_handles_empty_tool_input(self):
        records = self._run_hook({})
        assert len(records) == 1
        assert records[0]["file"] == ""

    def test_no_crash_on_missing_tool_input_key(self):
        records = self._run_hook({"other_key": "value"})
        assert len(records) == 1


class TestSilenceOnError(unittest.TestCase):
    """Tests that the hook never raises or exits non-zero on errors."""

    def test_hook_exits_zero_on_file_error(self):
        """Even if audit file can't be written, hook should exit 0."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".audit.jsonl", delete=False) as f:
            audit_path = f.name
        Path(audit_path).chmod(0o444)  # read-only
        try:
            result = subprocess.run(
                [sys.executable, str(HOOK_PATH)],
                input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/main.go"}, "tool_response": {"success": True}}),
                capture_output=True, text=True,
                env={**os.environ, "AUDIT_PATH": audit_path},
            )
            assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
        finally:
            Path(audit_path).chmod(0o644)
            Path(audit_path).unlink(missing_ok=True)

    def test_no_stdout_on_success(self):
        """Successful write should not emit stdout (unlike PreToolUse hooks)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".audit.jsonl", delete=False) as f:
            audit_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(HOOK_PATH)],
                input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/main.go"}, "tool_response": {"success": True}}),
                capture_output=True, text=True,
                env={**os.environ, "AUDIT_PATH": audit_path},
            )
            assert result.stdout.strip() == ""
        finally:
            Path(audit_path).unlink(missing_ok=True)


class TestJsonlFormat(unittest.TestCase):
    """Tests for JSONL append-only format."""

    def _audit_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".audit.jsonl", delete=False) as f:
            path = f.name
        Path(path).unlink(missing_ok=True)
        return path

    def test_writes_one_json_object_per_line(self):
        audit_path = self._audit_path()
        try:
            for path in ["a.txt", "b.txt"]:
                subprocess.run(
                    [sys.executable, str(HOOK_PATH)],
                    input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path}, "tool_response": {"success": True}}),
                    capture_output=True, text=True,
                    env={**os.environ, "AUDIT_PATH": audit_path},
                )
            with open(audit_path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 2
            for line in lines:
                obj = json.loads(line)
                assert "ts" in obj
                assert "tool" in obj
                assert "file" in obj
                assert "ok" in obj
        finally:
            Path(audit_path).unlink(missing_ok=True)

    def test_records_are_append_only(self):
        audit_path = self._audit_path()
        try:
            for path in ["x.txt", "y.txt"]:
                subprocess.run(
                    [sys.executable, str(HOOK_PATH)],
                    input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path}, "tool_response": {"success": True}}),
                    capture_output=True, text=True,
                    env={**os.environ, "AUDIT_PATH": audit_path},
                )
            with open(audit_path) as f:
                lines = [l for l in f if l.strip()]
            assert len(lines) >= 2  # appends, doesn't overwrite
        finally:
            Path(audit_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
