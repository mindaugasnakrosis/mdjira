"""Integration test for the apply pipeline.

We mock subprocess.run (the curl call) rather than the high-level
JiraClient — this keeps the curl path under test, since that's where
real-world bugs hide (status parsing, encoding, header handling).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from md_to_jira.apply import (
    EPIC_LINK_FIELD,
    EPIC_NAME_FIELD,
    ProjectStyle,
    apply_intake,
    build_epic_payload,
    build_story_payload,
    build_subtask_payload,
)
from md_to_jira.jira_client import JiraAuth, JiraClient
from md_to_jira.preview import preview
from md_to_jira.schema import parse_intake
from md_to_jira.yaml_io import load

FIXTURE = Path(__file__).parent / "fixtures" / "intake_min.yaml"


@pytest.fixture
def intake():
    return parse_intake(load(FIXTURE))


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


def test_extra_fields_merged_with_per_item_override(intake):
    intake.defaults.extra_fields = {"customfield_10100": "Default Team", "customfield_10200": "global"}
    epic = intake.epics[0]
    epic.extra_fields = {"customfield_10100": "Platform Team"}  # per-item wins
    style = ProjectStyle(is_team_managed=False)
    payload = build_epic_payload(epic, intake.defaults, style)
    assert payload["fields"]["customfield_10100"] == "Platform Team"
    assert payload["fields"]["customfield_10200"] == "global"


def test_story_points_written_through_when_field_configured(intake):
    intake.defaults.story_points_field = "customfield_10016"
    story = intake.stories[0]
    story.story_points = 5
    style = ProjectStyle(is_team_managed=False)
    payload = build_story_payload(story, "ABC-1", intake.defaults, style)
    assert payload["fields"]["customfield_10016"] == 5


def test_story_points_omitted_when_field_unconfigured(intake):
    intake.defaults.story_points_field = None
    story = intake.stories[0]
    story.story_points = 5
    style = ProjectStyle(is_team_managed=False)
    payload = build_story_payload(story, "ABC-1", intake.defaults, style)
    # No tenant field configured → story_points is silently dropped.
    assert "customfield_10016" not in payload["fields"]


def test_classic_epic_has_epic_name_field(intake):
    style = ProjectStyle(is_team_managed=False)
    payload = build_epic_payload(intake.epics[0], intake.defaults, style)
    fields = payload["fields"]
    assert fields["issuetype"]["name"] == "Epic"
    assert fields[EPIC_NAME_FIELD] == intake.epics[0].summary
    assert fields["description"]["type"] == "doc"


def test_team_managed_epic_omits_epic_name_field(intake):
    style = ProjectStyle(is_team_managed=True)
    payload = build_epic_payload(intake.epics[0], intake.defaults, style)
    assert EPIC_NAME_FIELD not in payload["fields"]


def test_classic_story_uses_epic_link_customfield(intake):
    style = ProjectStyle(is_team_managed=False)
    story = intake.stories[0]
    payload = build_story_payload(story, "ABC-100", intake.defaults, style)
    assert payload["fields"][EPIC_LINK_FIELD] == "ABC-100"
    assert "parent" not in payload["fields"]


def test_team_managed_story_uses_parent_key(intake):
    style = ProjectStyle(is_team_managed=True)
    story = intake.stories[0]
    payload = build_story_payload(story, "ABC-100", intake.defaults, style)
    assert payload["fields"]["parent"] == {"key": "ABC-100"}
    assert EPIC_LINK_FIELD not in payload["fields"]


def test_subtask_always_uses_parent_and_inherits(intake):
    parent_story = intake.stories[0]  # AHB story, priority Highest, labels [cost, azure, windows]
    sub = parent_story.subtasks[0]  # AHB-INV — no priority/labels of its own in the fixture
    payload = build_subtask_payload(sub, parent_story, "ABC-200", intake.defaults)
    assert payload["fields"]["parent"] == {"key": "ABC-200"}
    assert payload["fields"]["issuetype"]["name"] == "Sub-task"
    # Inheritance: subtask without explicit priority/labels picks them up from the story.
    assert payload["fields"]["priority"] == {"name": "Highest"}
    assert payload["fields"]["labels"] == ["cost", "azure", "windows"]


def test_subtask_explicit_priority_overrides_parent(intake):
    parent_story = intake.stories[0]
    sub = parent_story.subtasks[0]
    sub.priority = "Low"  # explicit override
    sub.labels = ["my-own-label"]
    payload = build_subtask_payload(sub, parent_story, "ABC-200", intake.defaults)
    assert payload["fields"]["priority"] == {"name": "Low"}
    assert payload["fields"]["labels"] == ["my-own-label"]


# ---------------------------------------------------------------------------
# End-to-end with a mocked curl
# ---------------------------------------------------------------------------


def _curl_response(stdout_body: str, status: int = 200):
    """Build a fake CompletedProcess matching how curl returns data
    when invoked with `-w '\\n%{http_code}'`."""

    class FakeCompleted:
        returncode = 0
        stdout = (stdout_body + f"\n{status}").encode()
        stderr = b""

    return FakeCompleted()


def test_apply_creates_full_hierarchy_in_order(intake, tmp_path):
    """The whole tree creates: epics first, then stories, then subtasks.

    Each level becomes one bulk POST. We assert the level boundaries are
    respected (epics finish before any story is sent) and that
    subtask/story payloads reference freshly-created parent keys.
    """
    results_path = tmp_path / "results.json"

    # Sequence: GET project, then 3 bulk POSTs (epics, stories, subtasks).
    issued_keys = iter(["ABC-1", "ABC-2", "ABC-3", "ABC-4", "ABC-5"])
    sent_batches: list[list[dict]] = []

    def fake_run(cmd, *, input=None, capture_output, timeout):
        method_idx = cmd.index("-X") + 1
        method = cmd[method_idx]
        url = cmd[-1]
        if method == "GET":
            return _curl_response(json.dumps({"key": "ABC", "style": "classic"}), status=200)
        # POST — should be the bulk endpoint.
        assert url.endswith("/rest/api/3/issue/bulk"), f"expected bulk endpoint, got {url}"
        body = json.loads(input.decode())
        payloads = body["issueUpdates"]
        sent_batches.append(payloads)
        # Mint sequential keys, one per payload, in order.
        issues = [{"key": next(issued_keys)} for _ in payloads]
        return _curl_response(json.dumps({"issues": issues, "errors": []}), status=201)

    client = JiraClient(
        site="https://example.atlassian.net",
        auth=JiraAuth(email="x@example.com", token="t"),
    )

    with patch("md_to_jira.jira_client.subprocess.run", side_effect=fake_run):
        outcome = apply_intake(
            intake,
            client=client,
            results_path=results_path,
            dry_run=False,
        )

    assert not outcome.failures
    assert outcome.created == {
        "COSTS": "ABC-1",
        "AHB": "ABC-2",
        "RES": "ABC-3",
        "AHB-INV": "ABC-4",
        "AHB-RUN": "ABC-5",
    }

    # Three bulk batches, in dependency order: epics, stories, subtasks.
    assert len(sent_batches) == 3
    assert [p["fields"]["issuetype"]["name"] for p in sent_batches[0]] == ["Epic"]
    assert [p["fields"]["issuetype"]["name"] for p in sent_batches[1]] == ["Story", "Story"]
    assert [p["fields"]["issuetype"]["name"] for p in sent_batches[2]] == ["Sub-task", "Sub-task"]

    # Stories link to the freshly-created epic.
    assert sent_batches[1][0]["fields"][EPIC_LINK_FIELD] == "ABC-1"
    assert sent_batches[1][1]["fields"][EPIC_LINK_FIELD] == "ABC-1"
    # Subtasks parent on the freshly-created AHB story (ABC-2).
    assert sent_batches[2][0]["fields"]["parent"] == {"key": "ABC-2"}
    assert sent_batches[2][1]["fields"]["parent"] == {"key": "ABC-2"}

    # results.json was persisted after each batch — final state has all 5.
    persisted = json.loads(results_path.read_text())
    assert persisted == outcome.created


def test_apply_idempotent_skips_existing(intake, tmp_path):
    """A second run with results.json present should make zero HTTP calls
    and report all items as skipped."""
    results_path = tmp_path / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "COSTS": "ABC-1",
                "AHB": "ABC-2",
                "AHB-INV": "ABC-3",
                "AHB-RUN": "ABC-4",
                "RES": "ABC-5",
            }
        )
    )

    client = JiraClient(
        site="https://example.atlassian.net",
        auth=JiraAuth(email="x@example.com", token="t"),
    )

    def fake_run(cmd, **kwargs):
        # The GET project call is still made, so respond to that.
        if "-X" in cmd and cmd[cmd.index("-X") + 1] == "GET":
            return _curl_response(json.dumps({"key": "ABC", "style": "classic"}), status=200)
        raise AssertionError(f"no POSTs expected on idempotent re-run, got cmd: {cmd}")

    with patch("md_to_jira.jira_client.subprocess.run", side_effect=fake_run):
        outcome = apply_intake(
            intake,
            client=client,
            results_path=results_path,
            dry_run=False,
        )

    assert outcome.created == {}
    assert outcome.failures == []
    assert set(outcome.skipped.keys()) == {"COSTS", "AHB", "AHB-INV", "AHB-RUN", "RES"}


def test_dry_run_makes_no_http_calls(intake, tmp_path):
    """Dry-run must never invoke curl, even for project lookup."""
    results_path = tmp_path / "results.json"

    with patch("md_to_jira.jira_client.subprocess.run", side_effect=AssertionError("no http expected")):
        outcome = apply_intake(
            intake,
            client=None,  # type: ignore[arg-type]
            results_path=results_path,
            dry_run=True,
        )

    assert outcome.failures == []
    # All five intake items end up in created with DRY-* placeholder keys.
    assert set(outcome.created.keys()) == {"COSTS", "AHB", "AHB-INV", "AHB-RUN", "RES"}
    assert all(v.startswith("DRY-") for v in outcome.created.values())
    # Dry runs do not touch results.json on disk.
    assert not results_path.exists()


# ---------------------------------------------------------------------------
# Preview smoke
# ---------------------------------------------------------------------------


def test_preview_runs_without_error(intake, capsys):
    preview(intake)
    out = capsys.readouterr().out
    assert "Epic" in out
    assert "ABC" in out
