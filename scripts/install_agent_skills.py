#!/usr/bin/env python3
"""Install project agent skills and bridge them for multiple AI tools."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PACKAGE_NAME = "pyfitdaysplus"
STAGING_DIR = Path("agent-skills")
AGENTS_DIR = Path(".agents")
SKILLS_DIR = AGENTS_DIR / "skills"
CURSOR_SKILLS_DIR = Path(".cursor") / "skills"
CUSTOM_SKILL = PACKAGE_NAME


def copy_custom_skill() -> None:
    """Copy the project skill from the AG Kit staging directory."""
    source = STAGING_DIR / CUSTOM_SKILL
    if not source.is_dir():
        return

    destination = SKILLS_DIR / CUSTOM_SKILL
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def link_skill(skill_name: str, source: Path) -> None:
    """Expose ``source`` under ``.cursor/skills`` as a symlink or stub."""
    destination = CURSOR_SKILLS_DIR / skill_name
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_symlink() or destination.exists():
        if destination.is_symlink():
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    try:
        destination.symlink_to(source.resolve(), target_is_directory=source.is_dir())
    except OSError:
        destination.mkdir(parents=True, exist_ok=True)
        stub = destination / "SKILL.md"
        stub.write_text(
            "\n".join(
                [
                    "---",
                    f"name: {skill_name}",
                    (
                        "description: Project skill sourced from "
                        f".agents/skills/{skill_name}/"
                    ),
                    "---",
                    "",
                    f"Read the full skill at [.agents/skills/{skill_name}/SKILL.md]"
                    f"(../../.agents/skills/{skill_name}/SKILL.md).",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def sync_cursor_skills() -> None:
    """Link each agent skill into Cursor's skills directory."""
    if not SKILLS_DIR.is_dir():
        return

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
            link_skill(skill_dir.name, skill_dir)


def cleanup() -> None:
    """Remove the temporary AG Kit staging directory if it exists."""
    if STAGING_DIR.is_dir():
        shutil.rmtree(STAGING_DIR)


def main() -> int:
    """Install project skills and bridge them for Cursor."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    copy_custom_skill()
    sync_cursor_skills()
    cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
