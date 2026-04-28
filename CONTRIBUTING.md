# Contributing to md-to-jira

Thanks for your interest. This is a small, opinionated tool — contributions that align with its scope are welcome; off-scope expansions probably aren't. Before opening a PR for anything non-trivial, open an issue to check fit.

## What's in scope

- Bug fixes (CLI behaviour, parser/validator edge cases, ADF rendering).
- Skill quality improvements grounded in citable agile/Jira authorities.
- Tenant-specific custom field plumbing that stays generic (no per-tenant hard-codes).
- Better diagnostics: error messages, lint rules, write-back matching.
- Performance: bulk paths, caching, fewer HTTP round trips.

## What's out of scope (for now)

- Sprint / board / roadmap / timeline integration (`/rest/agile/1.0`).
- Jira Data Center support — Cloud only.
- Reverse sync (Jira → markdown).
- A web UI or daemon.
- Heavy dependencies. PyYAML is the only runtime dep on purpose; please keep it that way.

## Development setup

Python 3.10+ is required. Get a clean editable install:

```bash
git clone https://github.com/mindaugasnakrosis/md-to-jira.git
cd md-to-jira
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite, lint, and type-check exactly the same way CI does:

```bash
pytest                        # unit + integration tests, all curl calls mocked
ruff check .                  # lint
ruff format --check .         # formatting (run `ruff format .` to fix)
mypy                          # type check (config in pyproject.toml)
```

All three must be green for a PR to merge — CI enforces it.

## Project layout

```
src/md_to_jira/         # the CLI package
  __init__.py           # version
  cli.py                # argparse entry point + subcommands
  schema.py             # intake YAML dataclasses + parse_intake()
  config.py             # ~/.config/md-to-jira/config.yaml load/save/merge
  jira_client.py        # curl-based REST v3 client with retry + bulk
  apply.py              # epic→story→subtask bulk batches
  preview.py            # JSON preview without HTTP
  write_back.py         # append Jira keys back into source markdown
  lint.py               # mechanical anti-pattern checker
  fields_cmd.py         # `md-to-jira fields` discovery output
  whoami.py             # `md-to-jira whoami` health-check
  adf.py                # plain-text → Atlassian Document Format
  term.py               # ANSI colour helpers (NO_COLOR-aware)
  yaml_io.py            # PyYAML wrappers
.claude/skills/md-to-jira/
  SKILL.md              # the senior-agile-coach skill loaded by Claude Code
  intake-schema.md      # YAML schema reference
tests/                  # pytest, no live network calls
examples/               # md → intake.yaml demonstrations
```

## Code style

- 110-character line limit (configured in pyproject).
- Type-annotate public functions and dataclasses. We're not on `mypy --strict` yet, but new code shouldn't make us further from it.
- Comments: explain *why*, not *what*. The "no obvious comments" rule applies — if removing the comment wouldn't confuse a future reader, don't write it.
- Errors: raise `IntakeError` for malformed YAML, `JiraError` for API problems. Anything else is a bug.

## Adding a lint rule

Lint rules live in `src/md_to_jira/lint.py` keyed by `MJxxx` codes. To add one:

1. Pick the next free code (`MJ018`, `MJ019`, ...).
2. Add the rule logic in `lint()` — return a `Diagnostic(severity, code, location, message)`.
3. Add a test in `tests/test_lint.py` exercising both the trigger case and a clean-passing case.
4. Update `SKILL.md`'s anti-patterns checklist if the rule is also a skill-time check the model should run.

Severity guideline: **error** for things that will produce an objectively bad ticket (empty summary, single-child epic, oversized story points, tooling marker on non-test runs); **warning** for style/quality smells (mixed-case labels, no AC heading, every-story-Medium).

## Adding a CLI subcommand

1. Create `src/md_to_jira/<command>.py` with the implementation.
2. In `cli.py`, add the import, an `_cmd_<command>` handler, and a sub-parser inside `build_parser()`.
3. Match the existing flag patterns: `--site`/`--project`/`--email` for HTTP-touching commands, falling back to config defaults.
4. Add tests; mock `subprocess.run` for curl calls (never make real network requests in tests).

## Releasing (for maintainers)

1. Bump `version` in `pyproject.toml` and `src/md_to_jira/__init__.py`.
2. Update `CHANGELOG.md`: move `[Unreleased]` items into a new dated section, refresh the version-link footnotes.
3. Commit, then `git tag v0.x.0` and push the tag — `.github/workflows/release.yml` will build and publish to PyPI via Trusted Publishing (configure once at <https://pypi.org/manage/account/publishing/>).

## Filing issues

- **Bugs** — please use the bug-report template; include the CLI version (`md-to-jira --version`), the failing command line, and the relevant intake YAML or markdown snippet (redact tokens / customer data).
- **Skill-quality issues** — paste the actual produced ticket and what you'd expected. The skill is opinionated; concrete examples are how it gets sharper.
- **Feature ideas** — discuss before implementing if the change touches the schema or adds a runtime dep.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind, be precise, be patient.
