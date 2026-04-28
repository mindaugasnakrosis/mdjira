"""Unit tests for the ADF converter — focus on inline marks and bullet lists.

The visible bug we're guarding against: inline `**bold**` rendering as
literal asterisks in Jira because the converter only emitted plain text
nodes. These tests pin the fix.
"""

from __future__ import annotations

from mdjira.adf import to_adf


def _paragraphs(doc):
    return [b for b in doc["content"] if b["type"] == "paragraph"]


def _bullet_lists(doc):
    return [b for b in doc["content"] if b["type"] == "bulletList"]


def _content_of_first_paragraph(doc):
    return _paragraphs(doc)[0]["content"]


def test_empty_input_yields_one_empty_paragraph():
    doc = to_adf("")
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert _paragraphs(doc) == [{"type": "paragraph", "content": []}]


def test_plain_paragraph_has_no_marks():
    nodes = _content_of_first_paragraph(to_adf("hello world"))
    assert nodes == [{"type": "text", "text": "hello world"}]


def test_bold_with_asterisks():
    nodes = _content_of_first_paragraph(to_adf("a **bold** c"))
    assert nodes == [
        {"type": "text", "text": "a "},
        {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
        {"type": "text", "text": " c"},
    ]


def test_bold_with_underscores():
    nodes = _content_of_first_paragraph(to_adf("__bold__"))
    assert nodes == [{"type": "text", "text": "bold", "marks": [{"type": "strong"}]}]


def test_italic_with_asterisks():
    nodes = _content_of_first_paragraph(to_adf("an *italic* word"))
    assert nodes == [
        {"type": "text", "text": "an "},
        {"type": "text", "text": "italic", "marks": [{"type": "em"}]},
        {"type": "text", "text": " word"},
    ]


def test_italic_with_underscores_word_boundary():
    # snake_case_identifiers must NOT become italics.
    nodes = _content_of_first_paragraph(to_adf("snake_case_identifier _real_ end"))
    assert nodes == [
        {"type": "text", "text": "snake_case_identifier "},
        {"type": "text", "text": "real", "marks": [{"type": "em"}]},
        {"type": "text", "text": " end"},
    ]


def test_inline_code():
    nodes = _content_of_first_paragraph(to_adf("run `npm test` first"))
    assert nodes == [
        {"type": "text", "text": "run "},
        {"type": "text", "text": "npm test", "marks": [{"type": "code"}]},
        {"type": "text", "text": " first"},
    ]


def test_link():
    nodes = _content_of_first_paragraph(to_adf("see [docs](https://example.com/x) please"))
    assert nodes == [
        {"type": "text", "text": "see "},
        {
            "type": "text",
            "text": "docs",
            "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
        },
        {"type": "text", "text": " please"},
    ]


def test_acceptance_criteria_label_renders_bold():
    """The exact pattern from real ticket descriptions — guard against the
    visible-asterisk bug recurring."""
    nodes = _content_of_first_paragraph(to_adf("**Acceptance criteria**"))
    assert nodes == [{"type": "text", "text": "Acceptance criteria", "marks": [{"type": "strong"}]}]


def test_source_label_with_path_renders_bold_then_path():
    nodes = _content_of_first_paragraph(to_adf("**Source**: IMS_adjustments.md#defects"))
    assert nodes[0] == {
        "type": "text",
        "text": "Source",
        "marks": [{"type": "strong"}],
    }
    assert nodes[1]["text"] == ": IMS_adjustments.md#defects"
    assert "marks" not in nodes[1]


def test_two_bold_segments_in_one_paragraph():
    nodes = _content_of_first_paragraph(to_adf("**one** middle **two**"))
    assert nodes == [
        {"type": "text", "text": "one", "marks": [{"type": "strong"}]},
        {"type": "text", "text": " middle "},
        {"type": "text", "text": "two", "marks": [{"type": "strong"}]},
    ]


def test_bullet_list_with_inline_bold():
    doc = to_adf("- one **two** three\n- four")
    lists = _bullet_lists(doc)
    assert len(lists) == 1
    items = lists[0]["content"]
    assert len(items) == 2
    first_item_para = items[0]["content"][0]
    assert first_item_para["content"] == [
        {"type": "text", "text": "one "},
        {"type": "text", "text": "two", "marks": [{"type": "strong"}]},
        {"type": "text", "text": " three"},
    ]


def test_paragraphs_split_on_blank_lines():
    doc = to_adf("first paragraph\n\nsecond paragraph")
    assert len(_paragraphs(doc)) == 2


def test_bullets_after_paragraph_become_separate_blocks():
    doc = to_adf("intro line\n\n- a\n- b")
    assert len(_paragraphs(doc)) == 1
    assert len(_bullet_lists(doc)) == 1
