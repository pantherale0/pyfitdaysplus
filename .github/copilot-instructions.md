# Copilot instructions for ICOMON Kitchen Scale

This is an async Python integration library (`icomon_kitchen`) using the
**ble** protocol.

## Before editing

1. Read `AGENTS.md` for commands and architecture.
2. For specialized workflows, check `.agents/skills/` (AG Kit + project skill
   `icomon_kitchen`).

## Commands

```bash
uv sync
uv run pytest
prek run -a
```

## Code layout

- `icomon_kitchen/client.py` — public async API
- `icomon_kitchen/adapter.py` — protocol adapter
- `icomon_kitchen/config.py` — configuration
- `tests/` — pytest tests

Keep I/O async, adapter logic in `adapter.py`, and follow conventional commits.
