# Copilot instructions for pyfitdaysplus

This is an async Python integration library (`pyfitdaysplus`) using the
**ble** protocol.

## Before editing

1. Read `AGENTS.md` for commands and architecture.
2. For specialized workflows, check `.agents/skills/` (AG Kit + project skill
   `pyfitdaysplus`).

## Commands

```bash
uv sync
uv run pytest
prek run -a
```

## Code layout

- `pyfitdaysplus/client.py` — public async API
- `pyfitdaysplus/device.py` — connected scale
- `pyfitdaysplus/config.py` — configuration
- `tests/` — pytest tests

Keep I/O async and follow conventional commits.
