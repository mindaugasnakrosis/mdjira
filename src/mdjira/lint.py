"""Mechanical anti-pattern checker for `intake.yaml`.

This is the rule-based half of what the skill enforces. Where the skill
applies judgment, lint applies grep — it catches the things any senior
agile coach would point at on a review pass without needing to read the
source markdown.

The two layers are intentional:

* The skill drafts the YAML applying judgment that lint can't easily
  encode (priority *reasoning*, sizing calibration, AC quality).
* Lint catches mechanical drift — empty descriptions, missing story
  points, single-child epics, label spam, tooling markers — so the
  skill can be re-run on its own output and converge.

Rules are stable identifiers (MJxxx) so users can tune severity per
team in `config.yaml` (a future addition; for now ignore-via `# noqa:
MJxxx` is not supported — keep the bar high).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .schema import Intake, Story

Severity = Literal["error", "warning"]


@dataclass
class Diagnostic:
    severity: Severity
    code: str
    location: str
    message: str


# ---------------------------------------------------------------------------
# Patterns we look for repeatedly
# ---------------------------------------------------------------------------

_TOOLING_MARKERS_IN_SUMMARY = (
    re.compile(r"^\s*\[mdjira[^\]]*\]", re.IGNORECASE),
    re.compile(r"^\s*\[test\b[^\]]*\]", re.IGNORECASE),
    re.compile(r"^\s*\[claude[^\]]*\]", re.IGNORECASE),
    re.compile(r"^\s*\[auto[^\]]*\]", re.IGNORECASE),
)

_TOOLING_MARKER_LABELS = (
    re.compile(r"^mdjira", re.IGNORECASE),
    re.compile(r"^claude-", re.IGNORECASE),
    re.compile(r"^auto-import", re.IGNORECASE),
    re.compile(r"^test-only$", re.IGNORECASE),
)

_MISC_EPIC_NAMES = re.compile(
    r"\b(?:miscellaneous|misc|various|cleanup|bug\s*fixes?|odds\s*and\s*ends)\b",
    re.IGNORECASE,
)

_AC_HEADING = re.compile(
    r"\b(?:acceptance\s*criteria|ac:?|\*\*ac\*\*)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------


def _has_ac_block(description: str) -> bool:
    """Heuristic: description contains an Acceptance Criteria heading
    followed by at least one bullet line."""
    if not description.strip():
        return False
    if not _AC_HEADING.search(description):
        return False
    # Look for at least one bullet after any AC heading.
    found_heading = False
    for line in description.splitlines():
        if _AC_HEADING.search(line):
            found_heading = True
            continue
        if found_heading and line.lstrip().startswith(("- ", "* ")):
            return True
    return False


def _looks_mixed_case(label: str) -> bool:
    """A label that mixes upper and lower case is a smell — convention is kebab."""
    return label != label.lower() and label != label.upper()


def _summary_duplicates_description(summary: str, description: str) -> bool:
    s = summary.strip().lower()
    if not s or not description.strip():
        return False
    first_line = description.strip().splitlines()[0].strip().lower()
    return first_line == s


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def lint(intake: Intake) -> list[Diagnostic]:
    """Run all anti-pattern rules. Returns diagnostics in source order."""
    diags: list[Diagnostic] = []

    # ----- Epic-level rules -----
    children_by_epic: dict[str, list[Story]] = {e.id: [] for e in intake.epics}
    for s in intake.stories:
        children_by_epic.setdefault(s.epic, []).append(s)

    for epic in intake.epics:
        loc = f"epic[{epic.id}]"

        if not epic.summary.strip():
            diags.append(Diagnostic("error", "MJ001", loc, "summary is empty"))
        else:
            for marker in _TOOLING_MARKERS_IN_SUMMARY:
                if marker.search(epic.summary):
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ008",
                            loc,
                            f"summary has a tooling-marker prefix: {epic.summary!r}",
                        )
                    )
                    break

        if _MISC_EPIC_NAMES.search(epic.summary):
            diags.append(
                Diagnostic(
                    "error",
                    "MJ014",
                    loc,
                    "epic name suggests a 'Miscellaneous Bug Fixes'-style "
                    "anti-pattern — Atlassian flags this explicitly. Rename "
                    "to a real outcome, or split into per-bug stories under "
                    "a real epic.",
                )
            )

        if not epic.description.strip():
            diags.append(Diagnostic("warning", "MJ001", loc, "description is empty"))

        n_children = len(children_by_epic.get(epic.id, []))
        if n_children == 0:
            diags.append(
                Diagnostic("error", "MJ002", loc, "epic has zero stories — drop the epic or add stories")
            )
        elif n_children == 1:
            diags.append(
                Diagnostic(
                    "error",
                    "MJ002",
                    loc,
                    "epic has only 1 story — promote the story up and drop the epic",
                )
            )

        for label in epic.labels:
            for marker in _TOOLING_MARKER_LABELS:
                if marker.search(label):
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ009",
                            loc,
                            f"tooling-marker label: {label!r}",
                        )
                    )
                    break
            if _looks_mixed_case(label):
                diags.append(
                    Diagnostic(
                        "warning",
                        "MJ011",
                        loc,
                        f"label not in kebab-case: {label!r}",
                    )
                )
        if len(epic.labels) > 5:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ010",
                    loc,
                    f"{len(epic.labels)} labels (max recommended is 5) — over-tagging dilutes filters",
                )
            )

    # ----- Story-level rules -----
    points_field_configured = bool(intake.defaults.story_points_field)
    priorities_seen = {s.priority for s in intake.stories if s.priority}
    points_seen = {s.story_points for s in intake.stories if s.story_points is not None}

    for story in intake.stories:
        loc = f"story[{story.id}]"

        if not story.summary.strip():
            diags.append(Diagnostic("error", "MJ001", loc, "summary is empty"))
        else:
            if len(story.summary) > 100:
                diags.append(
                    Diagnostic(
                        "warning",
                        "MJ013",
                        loc,
                        f"summary is {len(story.summary)} chars (>100); consider tightening",
                    )
                )
            for marker in _TOOLING_MARKERS_IN_SUMMARY:
                if marker.search(story.summary):
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ008",
                            loc,
                            f"summary has a tooling-marker prefix: {story.summary!r}",
                        )
                    )
                    break

        if not story.description.strip():
            diags.append(Diagnostic("warning", "MJ001", loc, "description is empty"))
        else:
            if _summary_duplicates_description(story.summary, story.description):
                diags.append(
                    Diagnostic(
                        "warning",
                        "MJ015",
                        loc,
                        "first line of description duplicates the summary verbatim",
                    )
                )
            if not _has_ac_block(story.description):
                diags.append(
                    Diagnostic(
                        "warning",
                        "MJ003",
                        loc,
                        "no acceptance criteria found in description "
                        "(expected an 'Acceptance criteria' heading + bullets)",
                    )
                )

        if points_field_configured and story.story_points is None:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ004",
                    loc,
                    "no story_points (defaults.story_points_field is configured)",
                )
            )
        if story.story_points is not None and story.story_points > 13:
            diags.append(
                Diagnostic(
                    "error",
                    "MJ017",
                    loc,
                    f"story_points={story.story_points} > 13 — split into smaller stories instead of "
                    f"sizing higher (Cohn: anything ≥20 is a placeholder, not an estimate)",
                )
            )

        for label in story.labels:
            for marker in _TOOLING_MARKER_LABELS:
                if marker.search(label):
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ009",
                            loc,
                            f"tooling-marker label: {label!r}",
                        )
                    )
                    break
            if _looks_mixed_case(label):
                diags.append(
                    Diagnostic(
                        "warning",
                        "MJ011",
                        loc,
                        f"label not in kebab-case: {label!r}",
                    )
                )
        if len(story.labels) > 5:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ010",
                    loc,
                    f"{len(story.labels)} labels (max recommended is 5)",
                )
            )

        # Padding subtasks: a single subtask under a story is almost
        # always indicative of fragmentation. The story should absorb it.
        if len(story.subtasks) == 1:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ007",
                    loc,
                    "story has a single subtask — usually a sign of fragmentation; "
                    "fold the subtask into the story description",
                )
            )

        for sub in story.subtasks:
            sub_loc = f"subtask[{sub.id}]"
            if not sub.summary.strip():
                diags.append(Diagnostic("error", "MJ001", sub_loc, "summary is empty"))
            for marker in _TOOLING_MARKERS_IN_SUMMARY:
                if marker.search(sub.summary):
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ008",
                            sub_loc,
                            f"summary has a tooling-marker prefix: {sub.summary!r}",
                        )
                    )
                    break
            # Subtask descriptions should be 1-2 short sentences, not multi-paragraph.
            if sub.description.strip():
                sentence_count = len(re.findall(r"[.!?]+(?:\s|$)", sub.description))
                if sentence_count > 4:
                    diags.append(
                        Diagnostic(
                            "warning",
                            "MJ016",
                            sub_loc,
                            f"{sentence_count}-sentence subtask description — "
                            f"if it needs that much context, it's probably a story",
                        )
                    )

    # ----- Cross-story patterns -----
    if len(intake.stories) >= 3:
        if len(priorities_seen) <= 1:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ005",
                    "intake",
                    f"{len(intake.stories)} stories all share priority "
                    f"{next(iter(priorities_seen), None)!r} — real backlogs spread "
                    f"across 2-3 levels; re-read the source for signal",
                )
            )
        if points_field_configured and len(points_seen) <= 1 and len(intake.stories) >= 4:
            diags.append(
                Diagnostic(
                    "warning",
                    "MJ006",
                    "intake",
                    f"{len(intake.stories)} stories all share story_points "
                    f"{next(iter(points_seen), None)!r} — sizing should vary",
                )
            )

    return diags


def format_report(diagnostics: list[Diagnostic]) -> str:
    """Render diagnostics as plain text, grouped by severity."""
    if not diagnostics:
        return "No issues found."
    lines: list[str] = []
    errors = [d for d in diagnostics if d.severity == "error"]
    warnings = [d for d in diagnostics if d.severity == "warning"]
    for d in diagnostics:
        lines.append(f"  {d.location} {d.code} {d.severity}: {d.message}")
    lines.append("")
    lines.append(f"{len(errors)} error(s), {len(warnings)} warning(s).")
    return "\n".join(lines)
