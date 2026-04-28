"""Tests for the mechanical anti-pattern checker."""

from __future__ import annotations

from mdjira.lint import lint
from mdjira.schema import Defaults, Epic, Intake, Story, Subtask


def _make_intake(
    *,
    epics: list[Epic] | None = None,
    stories: list[Story] | None = None,
    story_points_field: str | None = None,
) -> Intake:
    defaults = Defaults(
        jira_site="https://x.atlassian.net",
        project="ABC",
        story_points_field=story_points_field,
    )
    return Intake(defaults=defaults, epics=list(epics or []), stories=list(stories or []))


def _codes(diagnostics) -> list[str]:
    return [d.code for d in diagnostics]


# ---------------------------------------------------------------------------
# Single-rule cases
# ---------------------------------------------------------------------------


def test_clean_intake_has_no_diagnostics():
    intake = _make_intake(
        story_points_field="customfield_10016",
        epics=[
            Epic(
                id="E1",
                summary="Cost optimisation Q1",
                description="**Why this matters**\nReal context.\n\n**Acceptance criteria**\n- result A\n- result B",
                priority="High",
                labels=["cost", "azure", "q1-2026"],
            ),
        ],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="Enable AHB on prod Windows VMs",
                description="**Why this matters**\nLicense waste.\n\n**Acceptance criteria**\n- VMs licensed\n- cost drops",
                priority="Highest",
                labels=["cost", "azure", "windows"],
                story_points=3,
            ),
            Story(
                id="S2",
                epic="E1",
                summary="Right-size UAT SQL databases",
                description="**Why this matters**\n4x capacity.\n\n**Acceptance criteria**\n- Resized to 50 DTU\n- No regression",
                priority="Medium",
                labels=["cost", "sql"],
                story_points=2,
            ),
            Story(
                id="S3",
                epic="E1",
                summary="Delete unused public IP",
                description="**Why this matters**\nOrphaned.\n\n**Acceptance criteria**\n- IP deleted\n- No alerts",
                priority="Lowest",
                labels=["cost", "cleanup"],
                story_points=1,
            ),
        ],
    )
    assert lint(intake) == []


def test_single_child_epic_is_error():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Solo epic", description="x", priority="High")],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="The only story",
                description="**Acceptance criteria**\n- done",
                priority="High",
                story_points=3,
            )
        ],
    )
    diags = lint(intake)
    assert any(d.code == "MJ002" and d.severity == "error" for d in diags)


def test_misc_bug_fixes_epic_is_error():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Miscellaneous Bug Fixes", description="x")],
        stories=[
            Story(id=f"S{i}", epic="E1", summary=f"thing {i}", description="**Acceptance criteria**\n- done")
            for i in range(3)
        ],
    )
    assert "MJ014" in _codes(lint(intake))


def test_missing_story_points_when_field_configured():
    intake = _make_intake(
        story_points_field="customfield_10016",
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(id=f"S{i}", epic="E1", summary=f"thing {i}", description="**Acceptance criteria**\n- done")
            for i in range(3)
        ],
    )
    diags = lint(intake)
    assert sum(1 for d in diags if d.code == "MJ004") == 3


def test_missing_story_points_silent_when_field_unconfigured():
    intake = _make_intake(
        story_points_field=None,
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(id=f"S{i}", epic="E1", summary=f"thing {i}", description="**Acceptance criteria**\n- done")
            for i in range(3)
        ],
    )
    assert "MJ004" not in _codes(lint(intake))


def test_oversized_story_points_is_error():
    intake = _make_intake(
        story_points_field="customfield_10016",
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="big",
                description="**Acceptance criteria**\n- done",
                story_points=21,
            ),
            Story(
                id="S2",
                epic="E1",
                summary="medium",
                description="**Acceptance criteria**\n- done",
                story_points=5,
            ),
        ],
    )
    assert any(d.code == "MJ017" and d.severity == "error" for d in lint(intake))


def test_uniform_priority_warning_when_3_or_more_stories():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id=f"S{i}",
                epic="E1",
                summary=f"thing {i}",
                description="**Acceptance criteria**\n- done",
                priority="Medium",
            )
            for i in range(3)
        ],
    )
    assert "MJ005" in _codes(lint(intake))


def test_tooling_marker_in_summary_warns():
    intake = _make_intake(
        epics=[
            Epic(id="E1", summary="[mdjira test] Some epic", description="x"),
        ],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="[mdjira test] A story",
                description="**Acceptance criteria**\n- done",
            ),
            Story(
                id="S2",
                epic="E1",
                summary="A clean story",
                description="**Acceptance criteria**\n- done",
            ),
        ],
    )
    diags = lint(intake)
    locations = {(d.code, d.location) for d in diags}
    assert ("MJ008", "epic[E1]") in locations
    assert ("MJ008", "story[S1]") in locations
    assert ("MJ008", "story[S2]") not in locations


def test_tooling_marker_label_warns():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id=f"S{i}",
                epic="E1",
                summary=f"thing {i}",
                description="**Acceptance criteria**\n- done",
                labels=["mdjira-test"],
            )
            for i in range(3)
        ],
    )
    assert sum(1 for d in lint(intake) if d.code == "MJ009") == 3


def test_too_many_labels_warns():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id=f"S{i}",
                epic="E1",
                summary=f"thing {i}",
                description="**Acceptance criteria**\n- done",
                labels=["a", "b", "c", "d", "e", "f"],
            )
            for i in range(3)
        ],
    )
    assert any(d.code == "MJ010" for d in lint(intake))


def test_padding_subtask_warns():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="thing",
                description="**Acceptance criteria**\n- done",
                subtasks=[Subtask(id="T1", summary="the only step")],
            ),
            Story(
                id="S2",
                epic="E1",
                summary="thing 2",
                description="**Acceptance criteria**\n- done",
            ),
            Story(
                id="S3",
                epic="E1",
                summary="thing 3",
                description="**Acceptance criteria**\n- done",
            ),
        ],
    )
    diags = lint(intake)
    assert any(d.code == "MJ007" and d.location == "story[S1]" for d in diags)


def test_no_acceptance_criteria_warns():
    intake = _make_intake(
        epics=[Epic(id="E1", summary="Real epic", description="x")],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="thing",
                description="Just a description, no AC heading.",
            ),
            Story(
                id="S2",
                epic="E1",
                summary="thing 2",
                description="**Acceptance criteria**\n- a real bullet",
            ),
            Story(
                id="S3",
                epic="E1",
                summary="thing 3",
                description="**Acceptance criteria**\n- another",
            ),
        ],
    )
    diags = lint(intake)
    locs = {(d.code, d.location) for d in diags}
    assert ("MJ003", "story[S1]") in locs
    assert ("MJ003", "story[S2]") not in locs
