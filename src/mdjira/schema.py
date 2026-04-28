"""Intake YAML schema. The contract between the parser/skill and the apply step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_PRIORITIES = {"Highest", "High", "Medium", "Low", "Lowest"}


class IntakeError(ValueError):
    """Raised when the intake YAML is malformed."""


@dataclass
class Defaults:
    jira_site: str
    project: str
    assignee_account_id: str | None = None
    reporter_account_id: str | None = None
    issue_type_epic: str = "Epic"
    issue_type_story: str = "Story"
    issue_type_subtask: str = "Sub-task"
    # Tenant-specific custom field that holds Story Points. Discoverable
    # via `mdjira fields <SITE>` (look for "Story Points" or "Story
    # point estimate"). On many Cloud tenants this is `customfield_10016`;
    # on team-managed projects it may be `customfield_10026`. When set,
    # any story's `story_points` value is written through to this field.
    story_points_field: str | None = None
    # Tenant-specific custom fields applied to every created issue,
    # unless overridden per-item. Values pass through to the Jira API
    # verbatim — the caller is responsible for the correct shape (a plain
    # string for a text customfield, an ADF doc for a rich-text one, etc.).
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subtask:
    id: str
    summary: str
    description: str = ""
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    assignee_account_id: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Story:
    id: str
    epic: str
    summary: str
    description: str = ""
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    assignee_account_id: str | None = None
    subtasks: list[Subtask] = field(default_factory=list)
    # Story-points estimate on the modified Fibonacci scale: 1, 2, 3, 5,
    # 8, 13. Stories larger than 13 should be split, not estimated higher.
    # Subtasks and epics are not sized — the story carries the estimate.
    story_points: float | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Epic:
    id: str
    summary: str
    description: str = ""
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    assignee_account_id: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Intake:
    defaults: Defaults
    epics: list[Epic]
    stories: list[Story]

    def epic_ids(self) -> set[str]:
        return {e.id for e in self.epics}


def _require(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise IntakeError(f"{ctx}: missing required field '{key}'")
    return d[key]


def _check_priority(p: str | None, ctx: str) -> None:
    if p is not None and p not in VALID_PRIORITIES:
        raise IntakeError(f"{ctx}: priority '{p}' not one of {sorted(VALID_PRIORITIES)}")


def parse_intake(raw: dict[str, Any]) -> Intake:
    """Validate and convert a parsed-YAML dict into an Intake dataclass tree."""
    if not isinstance(raw, dict):
        raise IntakeError("intake YAML root must be a mapping")

    defaults_raw = _require(raw, "defaults", "intake")
    defaults = Defaults(
        jira_site=_require(defaults_raw, "jira_site", "defaults").rstrip("/"),
        project=_require(defaults_raw, "project", "defaults"),
        assignee_account_id=defaults_raw.get("assignee_account_id"),
        reporter_account_id=defaults_raw.get("reporter_account_id"),
        issue_type_epic=defaults_raw.get("issue_type_epic", "Epic"),
        issue_type_story=defaults_raw.get("issue_type_story", "Story"),
        issue_type_subtask=defaults_raw.get("issue_type_subtask", "Sub-task"),
        story_points_field=defaults_raw.get("story_points_field"),
        extra_fields=dict(defaults_raw.get("extra_fields") or {}),
    )

    epics_raw = raw.get("epics") or []
    if not isinstance(epics_raw, list):
        raise IntakeError("epics must be a list")
    epics: list[Epic] = []
    seen_epic_ids: set[str] = set()
    for i, e in enumerate(epics_raw):
        ctx = f"epics[{i}]"
        eid = _require(e, "id", ctx)
        if eid in seen_epic_ids:
            raise IntakeError(f"{ctx}: duplicate epic id '{eid}'")
        seen_epic_ids.add(eid)
        _check_priority(e.get("priority"), ctx)
        epics.append(
            Epic(
                id=eid,
                summary=_require(e, "summary", ctx),
                description=e.get("description", "") or "",
                priority=e.get("priority"),
                labels=list(e.get("labels") or []),
                assignee_account_id=e.get("assignee_account_id"),
                extra_fields=dict(e.get("extra_fields") or {}),
            )
        )

    stories_raw = raw.get("stories") or raw.get("tasks") or []
    if not isinstance(stories_raw, list):
        raise IntakeError("stories must be a list")
    stories: list[Story] = []
    seen_story_ids: set[str] = set()
    for i, s in enumerate(stories_raw):
        ctx = f"stories[{i}]"
        sid = s.get("id") or f"S{i + 1}"
        if sid in seen_story_ids:
            raise IntakeError(f"{ctx}: duplicate story id '{sid}'")
        seen_story_ids.add(sid)
        epic_ref = _require(s, "epic", ctx)
        if epic_ref not in seen_epic_ids:
            raise IntakeError(f"{ctx}: epic '{epic_ref}' is not declared in epics[]")
        _check_priority(s.get("priority"), ctx)

        subtasks: list[Subtask] = []
        seen_sub_ids: set[str] = set()
        for j, t in enumerate(s.get("subtasks") or []):
            sub_ctx = f"{ctx}.subtasks[{j}]"
            tid = t.get("id") or f"{sid}-T{j + 1}"
            if tid in seen_sub_ids:
                raise IntakeError(f"{sub_ctx}: duplicate subtask id '{tid}'")
            seen_sub_ids.add(tid)
            _check_priority(t.get("priority"), sub_ctx)
            subtasks.append(
                Subtask(
                    id=tid,
                    summary=_require(t, "summary", sub_ctx),
                    description=t.get("description", "") or "",
                    priority=t.get("priority"),
                    labels=list(t.get("labels") or []),
                    assignee_account_id=t.get("assignee_account_id"),
                    extra_fields=dict(t.get("extra_fields") or {}),
                )
            )

        story_points = s.get("story_points")
        if story_points is not None and not isinstance(story_points, (int, float)):
            raise IntakeError(f"{ctx}: story_points must be a number, got {type(story_points).__name__}")
        stories.append(
            Story(
                id=sid,
                epic=epic_ref,
                summary=_require(s, "summary", ctx),
                description=s.get("description", "") or "",
                priority=s.get("priority"),
                labels=list(s.get("labels") or []),
                assignee_account_id=s.get("assignee_account_id"),
                subtasks=subtasks,
                story_points=story_points,
                extra_fields=dict(s.get("extra_fields") or {}),
            )
        )

    return Intake(defaults=defaults, epics=epics, stories=stories)
