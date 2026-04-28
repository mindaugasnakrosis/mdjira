"""Plain-text → Atlassian Document Format (ADF) converter.

Supported block-level elements:
  - paragraphs (split on blank lines)
  - bullet lists (lines beginning with `- ` or `* `)

Supported inline marks:
  - **bold** / __bold__
  - *italic* / _italic_
  - `code`
  - [text](url) links

Anything fancier (tables, nested lists, images, headings) is intentionally
out of scope. The point is that block content is preserved verbatim and
inline emphasis renders correctly in Jira instead of leaking literal
asterisks into ticket descriptions.
"""

from __future__ import annotations

import re
from typing import Any

# Order matters: longer / more specific patterns first so that ** isn't
# eaten by *. Code spans are first because their contents must not be
# re-parsed for other marks. Links come before emphasis because the
# bracket text could otherwise hit emphasis patterns.
_INLINE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"`([^`\n]+)`"), "code"),
    (re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)"), "link"),
    (re.compile(r"\*\*([^*\n]+)\*\*"), "strong"),
    (re.compile(r"__([^_\n]+)__"), "strong"),
    (re.compile(r"(?<![A-Za-z0-9])\*([^*\n]+)\*(?![A-Za-z0-9])"), "em"),
    (re.compile(r"(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])"), "em"),
]


def _text_node(text: str, marks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _inline_to_nodes(text: str) -> list[dict[str, Any]]:
    """Convert one logical line of text to a list of ADF inline nodes."""
    if not text:
        return []
    nodes: list[dict[str, Any]] = []
    while text:
        # Find the leftmost match across all patterns. Ties broken by
        # pattern order (already prioritised: code > link > bold > em).
        best: tuple[re.Match[str], str] | None = None
        for pattern, kind in _INLINE_PATTERNS:
            m = pattern.search(text)
            if m is None:
                continue
            if best is None or m.start() < best[0].start():
                best = (m, kind)

        if best is None:
            nodes.append(_text_node(text))
            break

        match, kind = best
        if match.start() > 0:
            nodes.append(_text_node(text[: match.start()]))

        if kind == "link":
            label, href = match.group(1), match.group(2)
            nodes.append(_text_node(label, marks=[{"type": "link", "attrs": {"href": href}}]))
        elif kind == "code":
            nodes.append(_text_node(match.group(1), marks=[{"type": "code"}]))
        elif kind == "strong":
            # Recurse into the bolded body so that **foo `bar`** still highlights `bar`.
            for inner in _inline_to_nodes(match.group(1)):
                inner_marks = list(inner.get("marks") or [])
                inner_marks.append({"type": "strong"})
                nodes.append(_text_node(inner["text"], marks=inner_marks))
        elif kind == "em":
            for inner in _inline_to_nodes(match.group(1)):
                inner_marks = list(inner.get("marks") or [])
                inner_marks.append({"type": "em"})
                nodes.append(_text_node(inner["text"], marks=inner_marks))

        text = text[match.end() :]
    return [n for n in nodes if n["text"] != ""]


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": _inline_to_nodes(text)}


def _bullet_list(items: list[str]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [_paragraph(item)],
            }
            for item in items
        ],
    }


def _block_for(lines: list[str]) -> list[dict[str, Any]]:
    """Convert a contiguous group of non-blank lines into ADF blocks."""
    bullets: list[str] = []
    blocks: list[dict[str, Any]] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if para_lines:
            blocks.append(_paragraph(" ".join(para_lines).strip()))
            para_lines.clear()

    def flush_bullets() -> None:
        if bullets:
            blocks.append(_bullet_list(list(bullets)))
            bullets.clear()

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ")):
            flush_para()
            bullets.append(stripped[2:].rstrip())
        else:
            flush_bullets()
            para_lines.append(stripped.rstrip())

    flush_para()
    flush_bullets()
    return blocks


def to_adf(text: str) -> dict[str, Any]:
    """Convert plain text (with simple markdown-ish inline marks) to an ADF document."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return {"type": "doc", "version": 1, "content": [_paragraph("")]}

    content: list[dict[str, Any]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if current:
                content.extend(_block_for(current))
                current = []
        else:
            current.append(line)
    if current:
        content.extend(_block_for(current))

    if not content:
        content = [_paragraph("")]
    return {"type": "doc", "version": 1, "content": content}
