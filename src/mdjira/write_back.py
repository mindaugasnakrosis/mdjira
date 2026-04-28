"""Append created Jira keys back into the source markdown.

Heuristic: for each intake item whose summary appears as a heading or
inside a markdown line in the source doc, append `→ <KEY>` if not
already present. Idempotent — running twice is a no-op.

Diagnostics: the caller gets back a `WriteBackResult` listing every item
that *did* match (with the source line number) and every item that
didn't. The skill rewrites summaries during INVEST cleanup, so it's
common for some items to miss; surfacing the misses is what lets the
user correct them manually.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Intake


@dataclass
class WriteBackResult:
    matched: list[tuple[str, str, int]] = field(default_factory=list)
    """Triples of (intake_local_id, jira_key, 1-indexed_line_number) that landed."""

    unmatched: list[tuple[str, str]] = field(default_factory=list)
    """Pairs of (intake_local_id, summary) that the heuristic couldn't find."""


def write_back(
    md_path: Path,
    intake: Intake,
    keys: dict[str, str],
) -> WriteBackResult:
    """Mutate the markdown file in place. Returns matched + unmatched diagnostics."""
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    result = WriteBackResult()

    items = _items_with_keys(intake, keys)
    matched_ids: set[str] = set()
    changed = False

    # Match longer summaries first so a story summary containing a
    # subtask summary as a substring still gets the right key.
    items_sorted = sorted(items, key=lambda t: -len(t[1]))

    for i, line in enumerate(lines):
        for local_id, summary, key in items_sorted:
            if local_id in matched_ids:
                continue
            if key in line:
                # Already annotated on this line — count as matched.
                matched_ids.add(local_id)
                result.matched.append((local_id, key, i + 1))
                break
            if _line_mentions(line, summary):
                lines[i] = line.rstrip() + f"  → {key}"
                matched_ids.add(local_id)
                result.matched.append((local_id, key, i + 1))
                changed = True
                break

    for local_id, summary, _key in items:
        if local_id not in matched_ids:
            result.unmatched.append((local_id, summary))

    if changed:
        md_path.write_text("\n".join(lines), encoding="utf-8")
    return result


def _items_with_keys(intake: Intake, keys: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return triples of (local_id, summary, jira_key) for everything in keys."""
    out: list[tuple[str, str, str]] = []
    for epic in intake.epics:
        if epic.id in keys:
            out.append((epic.id, epic.summary, keys[epic.id]))
    for story in intake.stories:
        if story.id in keys:
            out.append((story.id, story.summary, keys[story.id]))
        for sub in story.subtasks:
            if sub.id in keys:
                out.append((sub.id, sub.summary, keys[sub.id]))
    return out


def _line_mentions(line: str, summary: str) -> bool:
    needle = re.sub(r"\s+", " ", summary.strip().lower())
    haystack = re.sub(r"\s+", " ", line.strip().lower())
    if not needle or not haystack:
        return False
    return needle in haystack
