# mdjira 🎫

> **Markdown in, Jira backlog out.** A Claude Code skill that turns a markdown document — a roadmap, cost review, security plan, anything — into a structured Jira Cloud backlog (Epic → Story → Subtask) with priorities, labels, descriptions, and INVEST-compliant acceptance criteria. You give it a `.md` file. It gives you Jira tickets. That's the whole interface.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-d97757.svg)](https://www.anthropic.com/claude-code)
[![Status: active](https://img.shields.io/badge/status-active-success.svg)](#)

## Why this exists

Teams keep their roadmaps, cost reviews, security plans, and feature lists in markdown — but track delivery in Jira. Copy-pasting items by hand is slow and error-prone. `mdjira` reads the markdown and creates the issues, with a reviewable preview so you see what's about to land before anything hits Jira.

## How it works

Two pieces ship together:

- **The Claude skill** — a senior agile coach that reads your markdown, decides the Epic/Story/Subtask structure, writes proper INVEST-compliant summaries, infers priorities, and applies a consistent label taxonomy.
- **The CLI** — a small Python tool that creates the issues in Jira via the REST API.

You install both and only ever interact with the skill: drop in a `.md` file, get tickets in your board. The CLI runs under the hood.

## What the skill actually knows

This isn't a "wrap GPT around Jira" tool. The skill encodes the working canon of agile and Jira practice — every rule it applies traces back to a published authority, listed here so you can audit the basis:

- **INVEST user-story checklist** — Bill Wake (2003), formalised in Mike Cohn's *User Stories Applied* (2004). [Agile Alliance: INVEST](https://agilealliance.org/glossary/invest/)
- **Three-part user-story template** ("As a `<role>`, I want `<function>` so that `<benefit>`") — Mike Cohn / Mountain Goat Software, with the explicit note that the "so that" clause is *optional but often helpful*. [User Stories | Mountain Goat](https://www.mountaingoatsoftware.com/agile/user-stories)
- **Modified Fibonacci sizing** (1, 2, 3, 5, 8, 13, 20, 40, 100) and the weight-comparison metaphor for why the gaps grow — Mike Cohn, *Agile Estimating and Planning* (2005). [Why Fibonacci Works | Mountain Goat](https://www.mountaingoatsoftware.com/blog/why-the-fibonacci-sequence-works-well-for-estimating)
- **Given/When/Then acceptance criteria** — Behaviour-Driven Development (Dan North); structure for outcome-based, testable AC. [Agile Alliance: Given/When/Then](https://agilealliance.org/glossary/given-when-then/)
- **Epic / Story / Subtask hierarchy + the "Miscellaneous Bug Fixes" anti-pattern** — Atlassian's own published guidance, including the rule that a story with 20 subtasks is too big and should be split. [Atlassian: Epics, Stories, and Initiatives](https://www.atlassian.com/agile/project-management/epics-stories-themes)
- **Compound-story decomposition** ("slicing the cake": one story per goal) — Roman Pichler. [Refining User Stories | Pichler](https://www.romanpichler.com/blog/refining-user-stories/)
- **DEEP backlog** — Detailed, Estimated, Emergent, Prioritised — Mike Cohn + Roman Pichler. [Make the Product Backlog DEEP | Mountain Goat](https://www.mountaingoatsoftware.com/blog/make-the-product-backlog-deep)
- **Acceptance criteria discipline: separate narrative from criteria** — BDD canon; AC describe testable outcomes, the description carries the *why*, they don't echo. [Acceptance Criteria | AltexSoft](https://www.altexsoft.com/blog/acceptance-criteria-purposes-formats-and-best-practices/)
- **Labels vs Components** — Atlassian's distinction: components are project-scoped, controlled, with optional ownership routing; labels are global, free-text, unvalidated, case-sensitive, no spaces. [Components vs Labels | Atlassian Community](https://community.atlassian.com/forums/Jira-articles/What-s-the-Difference-Between-Components-and-Labels-in-Jira/ba-p/2872013)
- **Jira priority semantics** — Atlassian admin docs. [Priority levels | Atlassian](https://support.atlassian.com/jira-service-management-cloud/docs/what-are-priority-levels-in-jira-service-management/)

The skill lives at [`.claude/skills/mdjira/SKILL.md`](.claude/skills/mdjira/SKILL.md) — open it. Every rule has reasoning. Disagree with one? Fork it. That's the point.

## Install

You need two things, both required: the **CLI** (Python package, runs the Jira API calls) and the **skill** (the file Claude Code loads to know how to behave as your agile coach).

Requirements: Python 3.10+, `git`, and `curl` (preinstalled on macOS and most Linux). Pure Python with minimal dependencies.

### 1. Install the CLI

Until the package is published on PyPI, install it from source:

```bash
git clone https://github.com/mindaugasnakrosis/mdjira.git
cd mdjira
pip install .
```

(Once it's on PyPI: `pip install mdjira`.)

Verify it's on your `PATH`:

```bash
mdjira --version
# mdjira 0.1.0
```

If `mdjira: command not found`, your `pip` installed it under a directory not on your `PATH`. Either:
- use `python3 -m mdjira.cli --version` instead, or
- add `python3 -m site --user-base`/`bin` to your `PATH`.

### 2. Install the Claude skill

The skill ships with the CLI but needs to be physically copied to `~/.claude/skills/mdjira/` so Claude Code can find it from any working directory. The CLI does that for you:

```bash
mdjira install-skill
```

It's idempotent — re-running only writes files whose content actually changed. **Always re-run it after `pip install -U mdjira`** so the skill stays in sync with the CLI version (every release ships an updated `SKILL.md`).

After installing or upgrading, **restart Claude Code** (or open a new session) — skills are loaded once per session, so a running session keeps the old copy until you restart.

Verify:

```bash
ls ~/.claude/skills/mdjira/SKILL.md
# /Users/you/.claude/skills/mdjira/SKILL.md
```

> **Project-local install (alternative).** If you only want the skill in one repo (e.g. shared with teammates via git), copy `.claude/skills/mdjira/` from this repo into your own and commit it. Claude Code reads project-local skills only when launched from that repo's directory; user-global skills work everywhere.

## One-time setup

Create an Atlassian API token at <https://id.atlassian.com/manage-profile/security/api-tokens>, then run two commands:

```bash
mdjira init                  # walks you through site, project, email; auto-detects Story Points field
echo 'ATATTxxxxxxx' > ~/.jira-token && chmod 600 ~/.jira-token
```

`mdjira init` writes a small config file at `~/.config/mdjira/config.yaml` with your defaults — this is the same XDG convention `gh`, `aws`, `gcloud`, and other modern CLIs use. Once it's written, every run picks up your site, project, email, and Story Points custom field automatically; you never have to repeat them.

The token is kept in a separate `~/.jira-token` file (chmod 600) because secrets have a different lifecycle than config — you rotate them separately, you back them up separately, and you definitely don't want them showing up when you `cat ~/.config/mdjira/config.yaml`.

### Non-interactive setup

For CI, dotfile management, or just speed:

```bash
mdjira init \
  --site https://your-tenant.atlassian.net \
  --project ABC \
  --email you@example.com
```

The Story Points customfield is auto-detected from the Jira API as soon as a token is in place — interactive `init` queries `/rest/api/3/field` after writing config and adds the right `customfield_xxxxx` to your config automatically. To pin a specific field id (e.g. when your tenant has multiple Story Points lookalikes), pass `--story-points-field customfield_10016`. To opt out of detection, pass `--no-story-points`.

If you ever need to inspect tenant fields directly: `mdjira fields https://your-tenant.atlassian.net`.

<details>
<summary>Alternative: environment variables</summary>

`JIRA_EMAIL` and `JIRA_API_TOKEN` work too, but they must be in your shell rc (`~/.zshrc`, `~/.bashrc`), not exported in the current terminal — Claude Code's tool subshells don't inherit interactive exports. The config-file flow above sidesteps that issue entirely.

</details>

## Usage

Open Claude Code in any directory and point the skill at your markdown file:

```
> /mdjira specs/cost-review.md
```

Or just describe what you want — Claude picks up the skill from the phrasing:

```
> turn specs/cost-review.md into Jira tickets in project ABC
```

The skill will:

1. Read your markdown.
2. Decide on the Epic → Story → Subtask structure, write INVEST-compliant summaries, infer priorities from the source language, normalise labels, and add acceptance criteria.
3. Show you a preview of what's about to be created, including any judgment calls it made.
4. On your approval, create the issues in Jira and report the keys.
5. Optionally append the new Jira keys back into the source markdown.

If Claude Code says `Unknown command: /mdjira`, the skill isn't installed where it can find it — run `mdjira install-skill` and restart Claude Code.

If the skill *is* installed but seems out of date (e.g. it claims a feature is "out of scope" that the README says works), it's a stale copy from a previous version. Run `mdjira install-skill` again and restart Claude Code; the install is idempotent and only writes files that actually changed.

### First-run walkthrough

The repo ships a realistic example at [`examples/ims-project-example.md`](examples/ims-project-example.md) — an Inventory Management System change list grouped under six themes (real-time stock, faster adjustments, audit trail, integrations, UX, defects). It's deliberately written in plain language with no Jira terminology, so it's a fair test of what the skill produces from a typical product doc.

Try it end-to-end:

```
> /mdjira examples/ims-project-example.md
```

What you should see:

1. **Plan.** The skill prints a tree: 6 Epics, ~15 Stories, ~30 Subtasks, with one-line rationale for non-obvious decisions (which themes were merged or split, which bullets were promoted to Stories vs. left as Subtasks, why the "Defects to Fix" section maps to a Bug-typed children rather than its own Epic).
2. **INVEST review.** It rewrites bullet-style summaries into proper user-story form where it has enough context, and flags ones it can't (e.g. an unowned "audit colour variables" Subtask) with a `?` for you to clarify.
3. **Preview.** It shows a JSON-y preview of every issue — summary, description, AC, priority, labels, story points — without touching Jira yet.
4. **Apply.** On approval, the CLI creates the issues in three batches (Epics → Stories → Subtasks) using `/rest/api/3/issue/bulk`, then writes a `results.json` next to the markdown so re-runs are idempotent.
5. **Write-back.** Optionally, every created issue's key is appended back into the source markdown next to the matching line (`→ ABC-123`), so the document becomes a live index of what's tracked where.

The skill uses the IMS doc to demonstrate every rule it knows: the "Mobile barcode scanning" item gets *split* into two Stories (online flow vs offline-queue) per Pichler's slicing-the-cake; the "Miscellaneous Bug Fixes" anti-pattern is avoided by giving each defect its own ticket; the "Dark mode" Story without acceptance criteria gets a `?` rather than fabricated AC. Open the `SKILL.md` if you want to see exactly which rule fired where.

## Re-running safely

If the skill is interrupted or you want to add new tickets later, just re-run it on the same markdown — already-created issues are detected and skipped automatically (a small `results.json` audit file next to your markdown remembers what was created). To force re-creation of everything, delete `results.json` first.

## Classic vs team-managed Jira projects

Jira Cloud projects come in two flavours and they wire epics to stories differently under the hood. `mdjira` detects which one your project is and handles both — you don't need to configure anything.

## What v1 does not do

- No sprint assignment, board placement, or roadmap dates.
- No Jira-to-markdown reverse sync.
- No Jira Data Center support — Cloud only.
- No GUI / web dashboard.

These are deliberate. v1 picks the smallest end-to-end loop that covers the common case.

## Development

```bash
git clone https://github.com/mindaugasnakrosis/mdjira
cd mdjira
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
