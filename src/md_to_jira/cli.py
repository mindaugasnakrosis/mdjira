"""md-to-jira CLI entry point.

Subcommands:

  md-to-jira preview INTAKE.yaml
  md-to-jira apply   INTAKE.yaml [--dry-run] [--force] [--results PATH] [--email EMAIL]
  md-to-jira write-back INTAKE.yaml RESULTS.json SOURCE.md

The CLI is deliberately small. Producing the YAML from raw markdown is
the job of the md-to-jira Claude skill (see .claude/skills/md-to-jira),
not this binary.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .apply import apply_intake
from .config import config_path, load_config, merge_intake_with_config, save_config
from .fields_cmd import detect_story_points_field, print_fields
from .install_skill import install_skill
from .jira_client import JiraClient, JiraError, load_auth
from .lint import format_report, lint
from .preview import preview
from .schema import IntakeError, parse_intake
from .term import bold, cyan, dim, green, header, hint, prompt_label, tick, value, warn, yellow
from .whoami import whoami
from .write_back import write_back
from .yaml_io import load


def _load_intake(path: str):
    p = Path(path)
    if not p.exists():
        raise IntakeError(f"intake file not found: {path}")
    if p.suffix.lower() in {".md", ".markdown"}:
        raise IntakeError(
            f"{path} looks like a markdown file, not a YAML intake. "
            f"The `md-to-jira` CLI takes the structured YAML intake produced "
            f"by the md-to-jira Claude skill, not raw markdown. "
            f"In Claude Code: run `/md-to-jira {path}` and the skill will "
            f"draft the intake YAML, preview it, and apply it for you."
        )
    raw = load(path)
    cfg = load_config()
    merged = merge_intake_with_config(raw, cfg)
    return parse_intake(merged)


def _cmd_preview(args: argparse.Namespace) -> int:
    intake = _load_intake(args.intake)
    preview(intake)
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    intake = _load_intake(args.intake)
    results_path = Path(args.results) if args.results else Path(args.intake).with_name("results.json")

    if args.dry_run:
        # No auth required for dry run — same code path, no HTTP.
        outcome = apply_intake(
            intake,
            client=None,  # type: ignore[arg-type]
            results_path=results_path,
            dry_run=True,
            force=args.force,
        )
    else:
        auth = load_auth(email=args.email)
        client = JiraClient(site=intake.defaults.jira_site, auth=auth)
        outcome = apply_intake(
            intake,
            client=client,
            results_path=results_path,
            dry_run=False,
            force=args.force,
        )

    print()
    print(f"Created: {len(outcome.created)}")
    print(f"Skipped: {len(outcome.skipped)} (already in {results_path.name})")
    if outcome.failures:
        print(f"Failed:  {len(outcome.failures)}")
        for local_id, msg in outcome.failures:
            print(f"  - {local_id}: {msg}")
        return 1
    return 0


def _cmd_write_back(args: argparse.Namespace) -> int:
    import json

    intake = _load_intake(args.intake)
    keys = json.loads(Path(args.results).read_text(encoding="utf-8"))
    result = write_back(Path(args.source), intake, keys)
    if result.matched:
        print(tick(f"Matched {len(result.matched)}/{len(keys)} items in {args.source}"))
        for local_id, jira_key, line_no in result.matched:
            print(f"  {dim(f'line {line_no}:')} {local_id} → {bold(jira_key)}")
    if result.unmatched:
        print()
        print(
            warn(
                f"Unmatched {len(result.unmatched)} item(s) — heading text in source "
                f"diverged from intake summary:"
            )
        )
        for local_id, summary in result.unmatched:
            print(f"  {dim(local_id)}: {summary}")
        print()
        print(dim("Copy the Jira keys manually from the printed mapping above."))
    if not result.matched and not result.unmatched:
        print(dim("Nothing to do — results.json had no entries."))
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    intake = _load_intake(args.intake)
    diagnostics = lint(intake)
    print(format_report(diagnostics))
    if not diagnostics:
        return 0
    error_count = sum(1 for d in diagnostics if d.severity == "error")
    warning_count = len(diagnostics) - error_count
    if error_count:
        return 1
    if args.strict and warning_count:
        return 1
    return 0


def _cmd_install_skill(args: argparse.Namespace) -> int:
    try:
        target, copied = install_skill(force=args.force)
    except FileNotFoundError as exc:
        print(warn(str(exc)), file=sys.stderr)
        return 2

    print()
    if copied:
        print(tick(f"Installed skill to {value(str(target))}"))
        for name in copied:
            print(f"  {dim('→')} {name}")
    else:
        print(tick(f"Skill already up to date at {value(str(target))}"))
    print()
    print(yellow(bold("Restart Claude Code")) + " for the skill changes to take effect.")
    print(dim("  Skills are loaded once per session; running sessions keep the old version."))
    return 0


def _cmd_fields(args: argparse.Namespace) -> int:
    auth = load_auth(email=args.email)
    client = JiraClient(site=args.site, auth=auth)
    print_fields(client, custom_only=not args.all)
    return 0


def _cmd_whoami(args: argparse.Namespace) -> int:
    site, project = _resolve_site_and_project(args)
    if not site:
        print(
            "error: no Jira site configured. Run `md-to-jira init` or pass --site.",
            file=sys.stderr,
        )
        return 2
    auth = load_auth(email=args.email)
    client = JiraClient(site=site, auth=auth)
    return whoami(client, project_key=args.project or project)


def _resolve_site_and_project(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve site/project from CLI flags falling back to config defaults."""
    cfg_defaults = load_config().get("defaults") or {}
    site = getattr(args, "site", None) or cfg_defaults.get("jira_site")
    project = getattr(args, "project", None) or cfg_defaults.get("project")
    return site, project


def _prompt(question: str, *, default: str | None = None) -> str:
    suffix = f" {dim(f'[{default}]')}" if default else ""
    while True:
        try:
            answer = input(f"{prompt_label(question)}{suffix}: ").strip()
        except EOFError:
            answer = ""
        if answer:
            return answer
        if default is not None:
            return default
        print(dim("  (required — please enter a value)"))


def _cmd_init(args: argparse.Namespace) -> int:
    """Interactive first-run setup. Writes ~/.config/md-to-jira/config.yaml.

    Non-interactive use is also supported via flags: any flag value is
    accepted as-is and skips the prompt. If all required values are
    given as flags, no prompts are shown. If a token is already in
    ~/.jira-token at the end, runs `whoami` to verify the setup.
    """
    target = config_path()
    existing = load_config() if target.exists() else {}
    existing_defaults = (existing.get("defaults") or {}) if isinstance(existing, dict) else {}

    if existing_defaults and not args.force:
        print()
        print(header("Existing configuration found"))
        print(dim(f"  {target}"))
        print()
        for k, v in existing_defaults.items():
            print(f"  {bold(k)}: {v}")
        print()
        print(yellow("Re-run with --force to overwrite, or edit the file directly."))
        return 0

    print()
    print(header("Setting up md-to-jira"))
    print(dim("Press Enter to accept the default shown in [brackets]."))
    print()

    site = args.site or _prompt(
        f"Jira site URL {hint('(e.g. https://yourtenant.atlassian.net)')}",
        default=existing_defaults.get("jira_site"),
    )
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    site = site.rstrip("/")

    project = args.project or _prompt(
        f"Default project key {hint('(e.g. ABC, CW)')}",
        default=existing_defaults.get("project"),
    )

    email = args.email or _prompt(
        "Atlassian email",
        default=existing_defaults.get("email"),
    )

    # Story Points customfield: prefer explicit flag, then auto-detect via API,
    # then existing config value. Never prompt for it — the ID is opaque to
    # users and `GET /rest/api/3/field` answers definitively when a token
    # is present.
    story_points_field: str | None = args.story_points_field or existing_defaults.get("story_points_field")

    new_defaults: dict[str, object] = {
        "jira_site": site,
        "project": project,
        "email": email,
    }
    if story_points_field:
        new_defaults["story_points_field"] = story_points_field

    # Preserve any unrelated keys the user had in the file.
    merged_defaults = {**existing_defaults, **new_defaults}
    saved = save_config({"defaults": merged_defaults})

    print()
    print(tick(f"Wrote {value(str(saved))}"))
    token_path = Path.home() / ".jira-token"
    if not token_path.exists():
        print()
        print(yellow("Next: write your Atlassian API token to ~/.jira-token"))
        print(f"  Create one at {cyan('https://id.atlassian.com/manage-profile/security/api-tokens')}, then:")
        print(f"    {bold('echo')} 'YOUR_TOKEN' > {bold('~/.jira-token')} && chmod 600 ~/.jira-token")
        print(
            f"  Then re-run {bold('md-to-jira init')} — Story Points field will be auto-detected, "
            f"and credentials verified."
        )
        return 0

    # Token + config both present — verify end-to-end and (if not already
    # configured or overridden) auto-detect the Story Points customfield.
    print()
    print(header("Verifying credentials and project access"))
    print()
    try:
        auth = load_auth()
        client = JiraClient(site=site, auth=auth)
        rc = whoami(client, project_key=project)
    except JiraError as exc:
        print(warn(f"Verification failed: {exc}"))
        print(dim("  Config was saved; fix the issue and run `md-to-jira whoami` to re-check."))
        return 0

    if not args.no_story_points and not args.story_points_field and not story_points_field:
        try:
            detected = detect_story_points_field(client)
        except JiraError as exc:
            detected = None
            print(dim(f"  (could not query field list to auto-detect Story Points: {exc})"))
        if detected:
            merged_defaults["story_points_field"] = detected
            save_config({"defaults": merged_defaults})
            print(tick(f"Auto-detected Story Points field: {value(detected)}"))
        else:
            print(
                dim(
                    "  Story Points field not auto-detected (no number-typed customfield "
                    "named 'Story Points' or 'Story point estimate' visible to your account). "
                    "Run `md-to-jira fields <site>` to inspect manually, then add "
                    "`story_points_field: customfield_xxxxx` to ~/.config/md-to-jira/config.yaml."
                )
            )

    if rc == 0:
        print()
        print(green(bold("All set.")) + " You can now use the md-to-jira skill in Claude Code.")
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="md-to-jira",
        description="Create Jira Cloud Epic → Story → Subtask issues from a structured YAML intake.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("preview", help="Print payloads without calling Jira.")
    pv.add_argument("intake", help="Path to intake.yaml")
    pv.set_defaults(func=_cmd_preview)

    ap = sub.add_parser("apply", help="Create issues in Jira (or dry-run).")
    ap.add_argument("intake", help="Path to intake.yaml")
    ap.add_argument("--dry-run", action="store_true", help="Print payloads, do not POST.")
    ap.add_argument("--force", action="store_true", help="Re-create items already in results.json.")
    ap.add_argument("--results", help="Override path to results.json (default: alongside intake).")
    ap.add_argument("--email", help="Atlassian email (or set JIRA_EMAIL).")
    ap.set_defaults(func=_cmd_apply)

    wb = sub.add_parser("write-back", help="Append Jira keys into the source markdown.")
    wb.add_argument("intake", help="Path to intake.yaml")
    wb.add_argument("results", help="Path to results.json produced by apply")
    wb.add_argument("source", help="Path to the source markdown file")
    wb.set_defaults(func=_cmd_write_back)

    lt = sub.add_parser(
        "lint",
        help="Mechanically check intake.yaml for senior-coach anti-patterns.",
    )
    lt.add_argument("intake", help="Path to intake.yaml")
    lt.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as errors.",
    )
    lt.set_defaults(func=_cmd_lint)

    isk = sub.add_parser(
        "install-skill",
        help="Copy the bundled Claude skill into ~/.claude/skills/md-to-jira/.",
    )
    isk.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files even if content matches (rarely useful).",
    )
    isk.set_defaults(func=_cmd_install_skill)

    fl = sub.add_parser(
        "fields",
        help="List Jira custom fields for tenant-specific configuration discovery.",
    )
    fl.add_argument("site", help="Jira site URL (e.g. https://example.atlassian.net)")
    fl.add_argument("--email", help="Atlassian email (or set JIRA_EMAIL).")
    fl.add_argument(
        "--all",
        action="store_true",
        help="Include system fields too (default: customfields only).",
    )
    fl.set_defaults(func=_cmd_fields)

    wh = sub.add_parser(
        "whoami",
        help="Verify Jira credentials and project access.",
    )
    wh.add_argument("--site", help="Override site from config")
    wh.add_argument("--project", help="Override project key from config")
    wh.add_argument("--email", help="Atlassian email (or set JIRA_EMAIL).")
    wh.set_defaults(func=_cmd_whoami)

    it = sub.add_parser(
        "init",
        help="Set up ~/.config/md-to-jira/config.yaml interactively.",
    )
    it.add_argument("--site", help="Jira site URL (skip prompt)")
    it.add_argument("--project", help="Default project key (skip prompt)")
    it.add_argument("--email", help="Atlassian email (skip prompt)")
    it.add_argument(
        "--story-points-field",
        help="Customfield ID for Story Points (e.g. customfield_10016) — skip prompt",
    )
    it.add_argument(
        "--no-story-points",
        action="store_true",
        help="Skip the Story Points customfield prompt entirely.",
    )
    it.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing config without prompting.",
    )
    it.set_defaults(func=_cmd_init)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (IntakeError, JiraError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
