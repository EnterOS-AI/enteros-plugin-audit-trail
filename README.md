# molecule-audit-trail

Append-only audit log for every file edit. Every `Edit` / `Write` / `NotebookEdit` call is recorded to `.claude/audit.jsonl` with timestamp, agent ID, file path, tool call ID, and outcome.

## What is logged

Each JSON Lines record contains:

```json
{
  "ts": "2026-05-10T14:23:01Z",
  "agent_id": "ws-a0689c35",
  "tool": "Edit",
  "file_path": "src/main.py",
  "tool_call_id": "call_abc123",
  "ok": true
}
```

## How it works

`PostToolUse` hook reads the result of each Edit/Write. Success/failure is inferred from `tool_response.success`. The record is appended to `.claude/audit.jsonl` — never overwritten.

## Install

### In org template (org.yaml)

```yaml
plugins:
  - molecule-audit-trail
```

### From URL (community install)

```
github://Molecule-AI/molecule-ai-plugin-molecule-audit-trail
```

## Usage

No configuration needed. Install and the hook is active.

Logs are stored at `.claude/audit.jsonl`. SIEM ingestion: pipe the file to your log pipeline.

## Hooks

- **PostToolUse:Edit** — appends audit record
- **PostToolUse:Write** — same
- **PostToolUse:NotebookEdit** — same

## Architecture

```
hooks/
  post-edit-audit.py   # Reads tool_response, appends JSONL
  post-edit-audit.sh   # Shell wrapper
  _lib.py              # Shared helpers
adapters/
  claude_code.py       # Registers hooks
settings-fragment.json # Declares PostToolUse hook binding
```

## Runtime

- `claude_code` — primary

## Known issues

See [known-issues.md](known-issues.md).

## License

Business Source License 1.1 — © Molecule AI.
