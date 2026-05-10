# Test Coverage — molecule-audit-trail

## What We Test

This plugin has **executable hooks** (Python), so it warrants real unit tests.

| File | What | How |
|------|------|-----|
| `hooks/post-edit-audit.py` | JSONL record format, tool name, file path, success flag, notebook path, edge cases, append-only guarantee | pytest integration tests (subprocess with `AUDIT_PATH` env var) |

## Key Design Decisions

### `AUDIT_PATH` env var

The hook accepts an `AUDIT_PATH` environment variable to control the audit log
location. This decouples tests from `__file__`-relative path logic, which behaves
differently depending on whether the Python interpreter resolves `__file__` as
relative or absolute (which varies by how the script is invoked).

### Path resolution in `_lib.get_repo_root`

When `__file__` is absolute (e.g. `/tmp/molecule-ai-plugin-.../hooks/hook.py`),
a naive `dirname(dirname(dirname(__file__)))` chain overshoots by one level.
`get_repo_root` detects this by checking whether the resolved parent contains a
`hooks/` subdirectory and adjusts accordingly.

## Running Tests

```bash
python -m pytest tests/ -v
```
