"""Build Jira issue payloads from an Intake and POST them in dependency order.

Hierarchy: Epic → Story → Subtask. Order matters because stories link to
their epic key (or set parent, depending on project style), and subtasks
link to their story.

Idempotency: a `results.json` map of intake-local-id → Jira key is
written next to the intake file. On re-run we skip any id already present
unless `force=True`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adf import to_adf
from .jira_client import MAX_BULK_BATCH, JiraClient
from .schema import Defaults, Epic, Intake, Story, Subtask

# Jira customfield IDs used by classic / company-managed projects.
# These are tenant-stable: 10011 = Epic Name, 10014 = Epic Link.
EPIC_NAME_FIELD = "customfield_10011"
EPIC_LINK_FIELD = "customfield_10014"


@dataclass
class ProjectStyle:
    """Tells us which schema variant to use for a project."""

    is_team_managed: bool

    @classmethod
    def from_project(cls, project: dict[str, Any]) -> ProjectStyle:
        # Jira returns "next-gen" or "classic" historically; current API
        # uses style: "classic" or "next-gen". Team-managed projects also
        # have simplified=True. We trust both signals.
        style = project.get("style", "")
        simplified = project.get("simplified", False)
        return cls(is_team_managed=(style == "next-gen" or simplified))


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _common_fields(
    *,
    project_key: str,
    issue_type: str,
    summary: str,
    description: str,
    priority: str | None,
    labels: list[str],
    assignee_account_id: str | None,
    extra_fields: dict[str, Any] | None = None,
    defaults_extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "issuetype": {"name": issue_type},
        "summary": summary,
        "description": to_adf(description),
    }
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = list(labels)
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    # Tenant-specific custom fields. Item-level extra_fields override
    # defaults entry-by-entry; values pass through to Jira verbatim.
    merged_extra: dict[str, Any] = {}
    if defaults_extra_fields:
        merged_extra.update(defaults_extra_fields)
    if extra_fields:
        merged_extra.update(extra_fields)
    fields.update(merged_extra)
    return fields


def build_epic_payload(epic: Epic, defaults: Defaults, style: ProjectStyle) -> dict[str, Any]:
    fields = _common_fields(
        project_key=defaults.project,
        issue_type=defaults.issue_type_epic,
        summary=epic.summary,
        description=epic.description,
        priority=epic.priority,
        labels=epic.labels,
        assignee_account_id=epic.assignee_account_id or defaults.assignee_account_id,
        extra_fields=epic.extra_fields,
        defaults_extra_fields=defaults.extra_fields,
    )
    if not style.is_team_managed:
        # Classic projects require Epic Name on creation.
        fields[EPIC_NAME_FIELD] = epic.summary
    return {"fields": fields}


def build_story_payload(
    story: Story,
    epic_key: str,
    defaults: Defaults,
    style: ProjectStyle,
) -> dict[str, Any]:
    fields = _common_fields(
        project_key=defaults.project,
        issue_type=defaults.issue_type_story,
        summary=story.summary,
        description=story.description,
        priority=story.priority,
        labels=story.labels,
        assignee_account_id=story.assignee_account_id or defaults.assignee_account_id,
        extra_fields=story.extra_fields,
        defaults_extra_fields=defaults.extra_fields,
    )
    if style.is_team_managed:
        fields["parent"] = {"key": epic_key}
    else:
        fields[EPIC_LINK_FIELD] = epic_key
    # Story points: typed convenience over extra_fields. If both the
    # tenant's story_points_field and a per-story story_points value are
    # set, write through. We don't fail if only one is set — the user
    # may be experimenting.
    if story.story_points is not None and defaults.story_points_field:
        fields[defaults.story_points_field] = story.story_points
    return {"fields": fields}


def build_subtask_payload(
    subtask: Subtask,
    parent_story: Story,
    parent_story_key: str,
    defaults: Defaults,
) -> dict[str, Any]:
    """Build a sub-task payload, inheriting priority and labels from
    the parent story when the sub-task itself doesn't set them.

    Inheritance rationale: when a coach drafts a story like "fix the X
    bug" with priority High and labels [defect, ims], the implementation
    sub-tasks ("write the migration", "update the index") inherit the
    same priority and at least the domain labels by default — that's
    almost always what's wanted, and forcing the user to repeat them
    only invites drift between sibling sub-tasks.
    """
    inherited_priority = subtask.priority or parent_story.priority
    inherited_labels = list(subtask.labels) if subtask.labels else list(parent_story.labels)
    fields = _common_fields(
        project_key=defaults.project,
        issue_type=defaults.issue_type_subtask,
        summary=subtask.summary,
        description=subtask.description,
        priority=inherited_priority,
        labels=inherited_labels,
        assignee_account_id=subtask.assignee_account_id or defaults.assignee_account_id,
        extra_fields=subtask.extra_fields,
        defaults_extra_fields=defaults.extra_fields,
    )
    # Subtasks always link via parent.key, regardless of project style.
    fields["parent"] = {"key": parent_story_key}
    return {"fields": fields}


# ---------------------------------------------------------------------------
# Apply orchestration
# ---------------------------------------------------------------------------


@dataclass
class ApplyOutcome:
    created: dict[str, str]  # intake-local id → Jira key created this run
    skipped: dict[str, str]  # intake-local id → existing Jira key (idempotency)
    failures: list[tuple[str, str]]  # (intake-local id, error message)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.failures)


def load_results(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_results(path: Path, results: dict[str, str]) -> None:
    path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def apply_intake(
    intake: Intake,
    client: JiraClient,
    *,
    results_path: Path,
    dry_run: bool = False,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> ApplyOutcome:
    """Create Epics → Stories → Subtasks in three bulk batches.

    Hierarchy means we can't bulk everything in one shot — stories
    reference the epic key, subtasks reference the story key. But within
    a level, items are independent, so each level becomes one (or, for
    >50 items, a few chunked) bulk POSTs. That turns a 30-issue run from
    30 sequential round-trips into 3.

    Idempotency is preserved: results.json is rewritten after every
    successful chunk so a crash mid-run doesn't lose the already-created
    keys. Items already present in results.json are skipped (unless
    `force=True`).

    On dry_run, no HTTP is performed at all (the project style is also
    not fetched — assumes classic for payload preview, since that path
    has more fields and is the more useful preview).
    """
    style = (
        ProjectStyle(is_team_managed=False)
        if dry_run
        else ProjectStyle.from_project(client.get_project(intake.defaults.project))
    )
    if not dry_run:
        log(
            f"Project {intake.defaults.project} detected as "
            f"{'team-managed' if style.is_team_managed else 'classic / company-managed'}."
        )

    existing = load_results(results_path) if not force else {}
    created: dict[str, str] = {}
    skipped: dict[str, str] = {}
    failures: list[tuple[str, str]] = []
    keys_by_local_id: dict[str, str] = dict(existing)

    def persist() -> None:
        if not dry_run:
            save_results(results_path, {**existing, **created})

    def already_done(local_id: str) -> bool:
        if local_id in existing:
            log(f"  · {local_id}: skipped (exists as {existing[local_id]})")
            skipped[local_id] = existing[local_id]
            keys_by_local_id[local_id] = existing[local_id]
            return True
        return False

    def dry_record(local_id: str, payload: dict[str, Any], label: str) -> None:
        log(f"  · would create {label} {local_id}")
        log(_indent(json.dumps(payload, indent=2)))
        dry_key = f"DRY-{local_id}"
        created[local_id] = dry_key
        keys_by_local_id[local_id] = dry_key

    def submit_batch(items: list[tuple[str, dict[str, Any]]]) -> None:
        """Send `items` to Jira via bulk_create_issues, in chunks of 50."""
        for chunk_start in range(0, len(items), MAX_BULK_BATCH):
            chunk = items[chunk_start : chunk_start + MAX_BULK_BATCH]
            payloads = [p for _id, p in chunk]
            try:
                keys, error_pairs = client.bulk_create_issues(payloads)
            except Exception as exc:  # JiraError or transport
                # Whole batch failed (network, auth, schema) — every
                # item in the chunk is a failure.
                for local_id, _ in chunk:
                    log(f"  ! {local_id}: FAILED — {exc}")
                    failures.append((local_id, str(exc)))
                continue
            error_by_index = dict(error_pairs)
            for i, (local_id, _payload) in enumerate(chunk):
                if i in error_by_index:
                    msg = error_by_index[i]
                    log(f"  ! {local_id}: FAILED — {msg}")
                    failures.append((local_id, msg))
                    continue
                key = keys[i]
                if not key:
                    failures.append((local_id, "no key returned by bulk endpoint"))
                    continue
                created[local_id] = key
                keys_by_local_id[local_id] = key
                log(f"  ✓ {local_id} → {key}")
            persist()

    # Level 1: Epics ------------------------------------------------
    log(f"\nEpics ({len(intake.epics)}):")
    epic_batch: list[tuple[str, dict[str, Any]]] = []
    for epic in intake.epics:
        if already_done(epic.id):
            continue
        payload = build_epic_payload(epic, intake.defaults, style)
        if dry_run:
            dry_record(epic.id, payload, "Epic")
        else:
            epic_batch.append((epic.id, payload))
    if epic_batch:
        submit_batch(epic_batch)

    # Level 2: Stories ----------------------------------------------
    log(f"\nStories ({len(intake.stories)}):")
    story_batch: list[tuple[str, dict[str, Any]]] = []
    for story in intake.stories:
        epic_key = keys_by_local_id.get(story.epic)
        if not epic_key:
            failures.append((story.id, f"epic '{story.epic}' was not created (skipped or failed)"))
            log(f"  ! {story.id}: parent epic '{story.epic}' missing — skipping story and its subtasks")
            continue
        if already_done(story.id):
            continue
        payload = build_story_payload(story, epic_key, intake.defaults, style)
        if dry_run:
            dry_record(story.id, payload, "Story")
        else:
            story_batch.append((story.id, payload))
    if story_batch:
        submit_batch(story_batch)

    # Level 3: Subtasks ---------------------------------------------
    total_subtasks = sum(len(s.subtasks) for s in intake.stories)
    log(f"\nSubtasks ({total_subtasks}):")
    subtask_batch: list[tuple[str, dict[str, Any]]] = []
    for story in intake.stories:
        story_key = keys_by_local_id.get(story.id)
        if not story_key:
            continue
        for sub in story.subtasks:
            if already_done(sub.id):
                continue
            payload = build_subtask_payload(sub, story, story_key, intake.defaults)
            if dry_run:
                dry_record(sub.id, payload, "Sub-task")
            else:
                subtask_batch.append((sub.id, payload))
    if subtask_batch:
        submit_batch(subtask_batch)

    return ApplyOutcome(created=created, skipped=skipped, failures=failures)


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())
