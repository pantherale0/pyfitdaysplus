# CLAUDE.md

Guidance for Claude Code when working in this repository.

Read [AGENTS.md](AGENTS.md) for project commands, architecture, and conventions.

## Skills

- **Project skill**: `.agents/skills/pyfitdaysplus/SKILL.md`
- **Shared skills**: `.agents/skills/*/SKILL.md` from
  [AG Kit](https://github.com/vudovn/ag-kit)

Load the project skill when editing `pyfitdaysplus/`, tests, or tooling.
Use AG Kit skills such as `python-patterns`, `testing-patterns`, and
`verify-changes` for general engineering tasks.

## Quick reference

```bash
uv sync && uv run pytest
prek run -a
```

Protocol: `ble` · Package: `pyfitdaysplus`
