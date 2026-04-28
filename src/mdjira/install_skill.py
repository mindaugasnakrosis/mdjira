"""`mdjira install-skill` — copy the bundled Claude skill into ~/.claude/skills/.

The Claude Code runtime loads skills from `~/.claude/skills/<name>/SKILL.md`
(user-global) or `<repo>/.claude/skills/<name>/SKILL.md` (project-local).
Most users want the global install so the skill works from any directory.

This subcommand exists because the skill ships alongside the CLI but
needs to be physically copied to a location Claude Code reads. Without
it, every `pip install -U mdjira` would silently leave the user on a
stale skill — the exact failure mode that prompted this command.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SKILL_DIR_NAME = "mdjira"


def _find_skill_source() -> Path | None:
    """Locate the bundled skill files.

    Priority:
      1. The canonical project location at `<repo-root>/.claude/skills/mdjira/`
         when running from a source checkout (editable install).
      2. `<package>/skill_data/` when shipped inside a wheel (future).
    """
    here = Path(__file__).resolve()
    for parent in [here.parent.parent.parent, here.parent.parent, here.parent]:
        candidate = parent / ".claude" / "skills" / SKILL_DIR_NAME
        if (candidate / "SKILL.md").is_file():
            return candidate
    bundled = here.parent / "skill_data"
    if (bundled / "SKILL.md").is_file():
        return bundled
    return None


def install_skill(*, target_dir: Path | None = None, force: bool = False) -> tuple[Path, list[str]]:
    """Copy bundled skill files into the user's ~/.claude/skills/<skill>/ directory.

    Returns (target_path, copied_filenames). Raises FileNotFoundError if the
    bundled skill source can't be located.
    """
    source = _find_skill_source()
    if source is None:
        raise FileNotFoundError(
            "could not find bundled skill files. Reinstall the package or run from a source checkout."
        )

    target = target_dir or (Path.home() / ".claude" / "skills" / SKILL_DIR_NAME)
    target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for src_file in source.iterdir():
        if not src_file.is_file():
            continue
        dst_file = target / src_file.name
        if dst_file.exists() and not force and dst_file.read_bytes() == src_file.read_bytes():
            continue  # already up to date
        shutil.copy2(src_file, dst_file)
        copied.append(src_file.name)

    return target, copied
