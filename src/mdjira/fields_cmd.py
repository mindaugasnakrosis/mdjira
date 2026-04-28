"""`mdjira fields <SITE>` — discover tenant-specific custom fields.

Different Jira tenants use different customfield IDs for things like
"Acceptance Criteria", "Story Points", "Epic Link" etc. This subcommand
prints the full list filtered to the customfields you're most likely to
plumb through `defaults.extra_fields` or `defaults.story_points_field`
in your intake YAML.
"""

from __future__ import annotations

from collections.abc import Callable

from .jira_client import JiraClient

# Heuristics for the most useful field-name patterns. Match is
# case-insensitive substring on the human name.
_INTERESTING_NAME_PATTERNS = (
    "acceptance",
    "story point",
    "epic name",
    "epic link",
    "definition of done",
    "sprint",
    "team",
    "rank",
    "flagged",
    "release",
    "fix version",
    "components",
    "due date",
)


def detect_story_points_field(client: JiraClient) -> str | None:
    """Discover the tenant's Story Points customfield by name+type.

    Both classic ("Story Points", `customfield_10026`) and team-managed
    ("Story point estimate", `customfield_10016`) projects expose the
    same number-typed customfield. Returns the first match or None.
    """
    fields = client.list_fields()
    candidates: list[tuple[int, str]] = []
    for f in fields:
        if not f.get("custom", False):
            continue
        name = (f.get("name") or "").strip().lower()
        schema = f.get("schema") or {}
        if (schema.get("type") or "") != "number":
            continue
        # Rank by closeness of match. "Story Points" (legacy classic) is most authoritative.
        if name == "story points":
            candidates.append((0, f["id"]))
        elif name == "story point estimate":
            candidates.append((1, f["id"]))
        elif "story point" in name:
            candidates.append((2, f["id"]))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def print_fields(
    client: JiraClient,
    *,
    custom_only: bool = True,
    log: Callable[[str], None] = print,
) -> None:
    fields = client.list_fields()

    rows: list[tuple[str, str, str]] = []
    for f in fields:
        fid = f.get("id", "")
        name = f.get("name", "")
        schema = f.get("schema") or {}
        ftype = schema.get("type") or ("custom" if f.get("custom") else "system")
        if custom_only and not f.get("custom", False):
            continue
        rows.append((fid, name, ftype))

    rows.sort(key=lambda r: r[1].lower())

    log(f"{'field id':40s}  {'type':12s}  name")
    log(f"{'-' * 40}  {'-' * 12}  {'-' * 32}")
    for fid, name, ftype in rows:
        log(f"{fid:40s}  {ftype:12s}  {name}")

    log("")
    interesting = [
        (fid, name, ftype)
        for fid, name, ftype in rows
        if any(p in name.lower() for p in _INTERESTING_NAME_PATTERNS)
    ]
    if interesting:
        log("Likely useful for `defaults.extra_fields` or first-class hints:")
        for fid, name, ftype in interesting:
            log(f"  {fid}  ({ftype})  — {name}")
