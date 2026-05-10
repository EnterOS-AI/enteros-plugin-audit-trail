"""Common helpers for Claude Code hooks. Imported by the .py hook scripts.

Hooks receive JSON on stdin per the Claude Code hook spec, and may emit
JSON on stdout or exit with code 2 to block. This module wraps both.
"""
import json
import os
import sys


def get_repo_root(hook_file: str) -> str:
    """Resolve the repo root from a hook's __file__ path.

    The plugin is installed at <repo>/hooks/<hook>.py.  We walk up two
    levels (hooks/ → repo/ → parent-of-repo) to find the workspace root.

    When __file__ is absolute (e.g. /tmp/molecule-ai-plugin-.../hooks/hook.py),
    the naive dirname chain overshoots by one level, so we detect this by
    checking whether the resolved parent contains a 'hooks/' subdirectory.
    """
    abs_hook = os.path.abspath(hook_file)
    parent = os.path.dirname(abs_hook)
    repo = os.path.dirname(parent)          # hooks/ → repo
    workspace = os.path.dirname(repo)      # repo → workspace root

    # Detect overshoot: if repo has a 'hooks/' subdir, workspace was right.
    # Otherwise the hook was loaded with an absolute path and we walked too far.
    if os.path.isdir(os.path.join(repo, "hooks")):
        return workspace
    # Back up one: the actual repo is one level deeper
    return repo


def read_input() -> dict:
    """Parse stdin JSON. Empty input → empty dict."""
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def emit(payload: dict) -> None:
    """Print JSON payload to stdout for the harness to interpret."""
    print(json.dumps(payload))


def deny_pretooluse(reason: str) -> None:
    """Emit a PreToolUse denial with reason and exit 0."""
    emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })
    sys.exit(0)


def add_context(text: str) -> None:
    """Emit additionalContext for SessionStart / UserPromptSubmit hooks."""
    if text and text.strip():
        emit({"additionalContext": text})


def warn_to_stderr(msg: str) -> None:
    """Non-blocking warning visible to the next agent turn via stderr."""
    print(msg, file=sys.stderr)
