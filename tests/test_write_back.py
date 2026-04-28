"""Tests for write-back diagnostics: matched line numbers + unmatched IDs."""

from __future__ import annotations

from mdjira.schema import Defaults, Epic, Intake, Story
from mdjira.write_back import write_back


def _make_intake() -> Intake:
    return Intake(
        defaults=Defaults(jira_site="https://x.atlassian.net", project="ABC"),
        epics=[Epic(id="E1", summary="Cost review", description="x")],
        stories=[
            Story(
                id="S1",
                epic="E1",
                summary="Enable hybrid benefit",
                description="**Acceptance criteria**\n- done",
            ),
            Story(
                id="S2",
                epic="E1",
                summary="Right-size UAT SQL",
                description="**Acceptance criteria**\n- done",
            ),
        ],
    )


def test_write_back_matches_summaries_and_records_line_numbers(tmp_path):
    md = tmp_path / "src.md"
    md.write_text(
        "\n".join(
            [
                "# Cost review",
                "",
                "## Items",
                "",
                "- Enable hybrid benefit on prod VMs",
                "- Right-size UAT SQL databases",
            ]
        )
    )
    intake = _make_intake()
    keys = {"E1": "ABC-100", "S1": "ABC-101", "S2": "ABC-102"}
    result = write_back(md, intake, keys)
    matched_ids = {m[0] for m in result.matched}
    assert matched_ids == {"E1", "S1", "S2"}
    line_by_id = {m[0]: m[2] for m in result.matched}
    assert line_by_id["E1"] == 1  # heading "# Cost review"
    assert line_by_id["S1"] == 5  # bullet line
    assert line_by_id["S2"] == 6
    text = md.read_text()
    assert "→ ABC-100" in text
    assert "→ ABC-101" in text
    assert "→ ABC-102" in text


def test_write_back_reports_unmatched(tmp_path):
    md = tmp_path / "src.md"
    md.write_text("# Totally different content here\n\nNothing recognisable.\n")
    intake = _make_intake()
    keys = {"E1": "ABC-100", "S1": "ABC-101"}
    result = write_back(md, intake, keys)
    assert result.matched == []
    unmatched_ids = {u[0] for u in result.unmatched}
    assert unmatched_ids == {"E1", "S1"}


def test_write_back_idempotent(tmp_path):
    md = tmp_path / "src.md"
    md.write_text("- Enable hybrid benefit on prod VMs\n")
    intake = _make_intake()
    keys = {"S1": "ABC-101"}
    write_back(md, intake, keys)
    first = md.read_text()
    # Run again — should be a no-op (key already present on the line).
    result2 = write_back(md, intake, keys)
    second = md.read_text()
    assert first == second
    assert result2.matched and result2.matched[0][0] == "S1"
