"""Pretty-print what `apply` would do, without any HTTP calls."""

from __future__ import annotations

import json
from collections.abc import Callable

from .apply import (
    ProjectStyle,
    build_epic_payload,
    build_story_payload,
    build_subtask_payload,
)
from .schema import Intake


def preview(intake: Intake, *, log: Callable[[str], None] = print) -> None:
    # We render against classic style — it has the strict superset of fields
    # (Epic Name, Epic Link), so the preview is the most informative.
    style = ProjectStyle(is_team_managed=False)

    log(f"Site:    {intake.defaults.jira_site}")
    log(f"Project: {intake.defaults.project}")
    log(
        f"Counts:  {len(intake.epics)} epics, "
        f"{len(intake.stories)} stories, "
        f"{sum(len(s.subtasks) for s in intake.stories)} subtasks"
    )
    log("")

    for epic in intake.epics:
        log(f"=== Epic [{epic.id}] {epic.summary}")
        log(_pretty(build_epic_payload(epic, intake.defaults, style)))
        for story in [s for s in intake.stories if s.epic == epic.id]:
            log(f"  --- Story [{story.id}] {story.summary}")
            log(_pretty(build_story_payload(story, f"<{epic.id}>", intake.defaults, style)))
            for sub in story.subtasks:
                log(f"      --- Subtask [{sub.id}] {sub.summary}")
                log(_pretty(build_subtask_payload(sub, story, f"<{story.id}>", intake.defaults)))
        log("")


def _pretty(payload: dict) -> str:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    return "\n".join("    " + line for line in text.splitlines())
