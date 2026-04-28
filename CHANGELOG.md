# Changelog

All notable changes to `md-to-jira` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(no changes yet)

## [0.1.0] — 2026-04-28

Initial release. Turns a markdown product/engineering doc into a structured Jira Cloud backlog (Epic → Story → Subtask) with priorities, story points, labels, descriptions, and acceptance criteria written to a senior agile coach standard.

### Added

#### CLI

- `md-to-jira init` — interactive (or flag-driven) first-run setup that writes `~/.config/md-to-jira/config.yaml`, auto-detects the tenant's Story Points customfield via `GET /rest/api/3/field`, and runs an end-to-end credential verification when a token is already in place. Override with `--story-points-field`, opt out with `--no-story-points`.
- `md-to-jira whoami` — verify credentials and project access via `GET /rest/api/3/myself` plus `GET /rest/api/3/project/<KEY>`. Prints identity + project type (classic / team-managed).
- `md-to-jira preview` — print Jira payloads from a YAML intake without making any HTTP calls.
- `md-to-jira apply` — create issues in Jira via three sequential bulk batches (Epics → Stories → Subtasks) using `POST /rest/api/3/issue/bulk` (≤50 per request), with idempotent `results.json` persistence per batch.
- `md-to-jira apply --dry-run` — same code path as `apply`, no HTTP calls; safe to chain into `preview` for a full audit.
- `md-to-jira apply --force` — re-create items already in `results.json`.
- `md-to-jira lint` — mechanical anti-pattern checker over an intake YAML covering 17 rules (`MJ001`–`MJ017`): empty summaries, single-child epics, "Miscellaneous Bug Fixes" anti-pattern, missing/oversized story points, uniform priority/sizing, padding subtasks, tooling-marker prefixes and labels, label hygiene, AC-heading absence, over-long subtask descriptions, summary length, description duplicating summary. `--strict` exits non-zero on warnings as well as errors.
- `md-to-jira fields <site>` — list tenant custom fields with a "likely useful" call-out for Story Points, Acceptance Criteria, Sprint, etc.
- `md-to-jira install-skill` — copies the bundled Claude skill (`SKILL.md`, `intake-schema.md`) into `~/.claude/skills/md-to-jira/`. Idempotent; only rewrites files whose content actually changed. Surfaces a "restart Claude Code" reminder so users notice when a running session is on a stale skill.
- `md-to-jira write-back` — append created Jira keys back into the source markdown. Returns a `WriteBackResult` with matched line numbers and an explicit list of unmatched intake items, surfaced through the CLI so the user can hand-fix misses.

#### Configuration

- XDG-compliant config file at `~/.config/md-to-jira/config.yaml` for non-secret defaults (site, project, email, story-points field). Mirrors the convention used by `gh`, `aws`, and `gcloud`.
- Secret-token file at `~/.jira-token` (chmod 600 enforced) — kept separate from config because secrets have a different lifecycle.
- Optional `~/.jira-email` legacy fallback for users on the original setup flow.
- Auth resolution order, highest priority first: CLI flag → environment variable → config file → legacy dotfile.

#### Schema

- Epic → Story → Subtask hierarchy with explicit `epic` references.
- Per-item `priority`, `labels`, `description`, `assignee_account_id`.
- First-class `Story.story_points` (modified Fibonacci 1, 2, 3, 5, 8, 13). Subtasks and epics are not sized.
- `defaults.story_points_field` — tenant-specific custom field id where points are written.
- `extra_fields` map at every level (defaults / epic / story / subtask) for arbitrary tenant-specific custom fields. Per-item overrides defaults per key.
- Automatic subtask inheritance of priority and labels from the parent story when not explicitly set.
- Automatic detection of classic vs team-managed projects via `GET /rest/api/3/project/<KEY>`, branching the epic-link wiring (`customfield_10014` vs `parent.key`).

#### ADF rendering

- Plain text → Atlassian Document Format converter supporting paragraphs, bullet lists, and inline marks: `**bold**` / `__bold__`, `*italic*` / `_italic_`, `` `code` ``, `[text](url)` links.
- Word-boundary handling so `snake_case_identifier` does not become italic.
- Recursive inner-mark application so `**foo `bar`**` keeps both bold and code.

#### Claude skill

- Senior-agile-coach skill at `.claude/skills/md-to-jira/SKILL.md` with citations to the working canon: INVEST (Wake / Cohn), three-part user-story template (Cohn), modified Fibonacci sizing (Cohn), Given/When/Then AC (BDD), Atlassian's epic-story-subtask hierarchy and "Miscellaneous Bug Fixes" anti-pattern, Pichler's compound-story decomposition, DEEP backlog.
- Title patterns by ticket type, mandatory description template (Why this matters / Scope / AC / Source), AC discipline (3–5, observable outcomes, Given/When/Then vs bullet-list choice), Fibonacci sizing calibration table, priority semantics with anti-inflation rules, layered label taxonomy, components-vs-labels guidance, anti-patterns checklist run before every preview.
- Hard rule preventing the CLI being passed raw markdown (CLI also enforces this with a fast-fail).
- Schema reference at `.claude/skills/md-to-jira/intake-schema.md` with a customfield value-shape appendix covering number / text / paragraph (ADF) / single-select / multi-select / cascading / radio / user-picker / group / date / datetime / labels / URL / sprint / epic-link fields.
- `defaults.source_base_url` — when set (or auto-detectable from a GitHub `origin` remote), the skill emits absolute Source links in every Story description so reviewers can jump from a Jira ticket back to the markdown bullet that produced it.

#### Reliability

- Exponential-backoff retry on `429` and `5xx` responses across all Jira HTTP calls. Configurable via `max_attempts`, `backoff_base`, `backoff_cap` on `JiraClient`.
- `_load_intake` rejects `.md` / `.markdown` files with a helpful error directing the user to the skill flow, rather than letting PyYAML fail cryptically.
- Subtask payload construction inherits parent priority/labels when the subtask omits them.
- `term.py` — ANSI colour helpers honouring `NO_COLOR` / `FORCE_COLOR` and TTY detection. `init` and `whoami` are colourised (✓ / ✗ / ! markers, dim hints, bold values).

#### Project plumbing

- MIT license.
- `pyproject.toml` configured for PyPI distribution: classifiers, entry point (`md-to-jira`), runtime dependency on PyYAML.
- GitHub Actions CI: `pytest` matrix on Python 3.10/3.11/3.12/3.13, `ruff check` + `ruff format --check`, `mypy`, build + `twine check` of distributables.
- GitHub Actions release workflow: tag-triggered PyPI publish via Trusted Publishing (OIDC).
- OSS hygiene files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), GitHub bug-report and feature-request issue templates, pull-request template.
- `examples/ims-project-example.md` — a realistic Inventory Management System change list used as the README walkthrough fixture.
- 59 unit and integration tests covering schema validation, ADF conversion, payload construction (classic + team-managed), full-hierarchy creation order with mocked curl, idempotent re-runs, dry-run isolation, config merging, subtask inheritance, retry/backoff, bulk endpoints, lint rules, and write-back diagnostics.

### Out of scope for v0.1

- Sprint assignment / board placement.
- Comments on issues.
- Jira-to-markdown reverse sync.
- Jira Data Center support — Cloud only.

[Unreleased]: https://github.com/mindaugasnakrosis/md-to-jira/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mindaugasnakrosis/md-to-jira/releases/tag/v0.1.0
