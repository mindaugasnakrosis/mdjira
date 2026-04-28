"""`md-to-jira whoami` — verify credentials + project access.

This is the cheapest possible round-trip to Jira. Run it after `init`,
or any time you suspect your token has expired or you're talking to the
wrong tenant. Returns non-zero on any failure so it's safe to use as a
CI healthcheck.
"""

from __future__ import annotations

from collections.abc import Callable

from .jira_client import JiraClient, JiraError
from .term import bold, cross, dim, tick, value


def whoami(
    client: JiraClient,
    *,
    project_key: str | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Print identity + (optionally) project info. Returns shell exit code."""
    try:
        me = client.myself()
    except JiraError as exc:
        log(cross(bold("Authentication failed:")) + f" {exc}")
        log(dim("  Check ~/.jira-token (chmod 600) and your config email."))
        return 1

    name = me.get("displayName") or "(unknown)"
    email = me.get("emailAddress") or "(hidden by privacy settings)"
    account_id = me.get("accountId") or "(missing)"
    tz = me.get("timeZone") or "?"
    site = client.site

    log(tick(f"Authenticated as {bold(name)} <{email}>"))
    log(f"  {dim('site:')}       {value(site)}")
    log(f"  {dim('accountId:')}  {account_id}")
    log(f"  {dim('timeZone:')}   {tz}")

    if not project_key:
        return 0

    try:
        project = client.get_project(project_key)
    except JiraError as exc:
        log(cross(bold(f"Project '{project_key}' not accessible:")) + f" {exc}")
        log(dim("  Confirm the project key, or that your account has been added to the project."))
        return 2

    style = project.get("style") or "?"
    simplified = project.get("simplified", False)
    style_label = "team-managed" if (style == "next-gen" or simplified) else "classic / company-managed"
    log("")
    log(tick(f"Project {value(project_key)} accessible"))
    log(f"  {dim('name:')}       {project.get('name', '?')}")
    log(f"  {dim('type:')}       {style_label}")
    log(f"  {dim('lead:')}       {(project.get('lead') or {}).get('displayName', '?')}")
    return 0
