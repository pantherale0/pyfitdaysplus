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

- `pyfitdaysplus/device.py` — public `Device` API
- `pyfitdaysplus/config.py` — configuration
- `tests/` — pytest tests

Keep I/O async and follow conventional commits.
Scanning is the caller's job; connections go through bleak-retry-connector.
