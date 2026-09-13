#!/usr/bin/env python3
"""Run pytest for tests affected by staged changes."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = "pyfitdaysplus"
TEST_DIR = Path("tests")


def _resolve_executable(name: str) -> str:
    """Return the absolute path of ``name`` or raise if it is missing."""
    path = shutil.which(name)
    if path is None:
        msg = f"{name} executable not found on PATH"
        raise FileNotFoundError(msg)
    return path


def staged_python_files() -> list[str]:
    """Return staged Python paths from ``git diff --cached``."""
    result = subprocess.run(  # noqa: S603
        [
            _resolve_executable("git"),
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACM",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".py")]


def test_targets(changed: list[str]) -> list[str]:
    """Map changed package or test files to existing pytest paths."""
    targets: list[str] = []
    seen: set[str] = set()

    def add(target: str) -> None:
        if target not in seen and Path(target).exists():
            seen.add(target)
            targets.append(target)

    for path in changed:
        if path.startswith("tests/") and path.endswith(".py"):
            add(path)
            continue
        if not path.startswith(f"{PACKAGE}/") or not path.endswith(".py"):
            continue
        stem = Path(path).stem
        if stem == "__init__":
            add(str(TEST_DIR))
            continue
        candidate = TEST_DIR / f"test_{stem}.py"
        if candidate.exists():
            add(str(candidate))
        else:
            add(str(TEST_DIR))

    return targets


def main() -> int:
    """Run pytest for tests affected by the current staged Python files."""
    changed = staged_python_files()
    if not any(p.startswith(f"{PACKAGE}/") or p.startswith("tests/") for p in changed):
        return 0

    targets = test_targets(changed)
    if not targets:
        return 0

    cmd = [_resolve_executable("uv"), "run", "pytest", *targets, "-q", "--no-cov"]
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    sys.exit(main())
