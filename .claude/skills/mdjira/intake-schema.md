# `intake.yaml` schema

Authoritative shape consumed by `mdjira preview` and `mdjira apply`. Keep this in sync with `src/mdjira/schema.py`.

## Where defaults come from

The CLI merges three sources, lowest priority first:

1. **`~/.config/mdjira/config.yaml`** — written by `mdjira init`. Holds `jira_site`, `project`, `email`, and `story_points_field` so you don't repeat them per project.
2. **The intake YAML's `defaults:` block** — overrides the config per key.
3. **CLI flags / env vars** — override everything for a single run.

A typical intake YAML can have `defaults: {}` and rely on the global config; only spell out a default when this particular run differs.

```yaml
defaults:
  jira_site: https://example.atlassian.net   # required, no trailing slash
  project: ABC                                # required, project key
  assignee_account_id: "712020:..."           # optional Atlassian Cloud accountId
  reporter_account_id: "712020:..."           # optional, ignored on classic projects
  issue_type_epic: Epic                       # tenant rename overrides
  issue_type_story: Story
  issue_type_subtask: Sub-task

  # Tenant-specific custom field that holds Story Points. Discover via
  # `mdjira fields <site-url>` and look for "Story Points" or
  # "Story point estimate". When set, every story's `story_points` value
  # is written through to this field on create.
  story_points_field: customfield_10016

  # Arbitrary tenant-specific custom fields applied to every issue.
  # Item-level `extra_fields` overrides per key.
  extra_fields:
    customfield_10100: "Cult Wines IT"        # e.g. a "Team" customfield

epics:
  - id: COSTS                                 # local id, referenced by stories[].epic
    summary: "Cloud cost optimisation — Q1 2026"
    priority: High                            # Highest | High | Medium | Low | Lowest
    labels: [cost-optimisation, q1-2026, azure]
    description: |
      **Why this matters**
      The Q1 cost review identified £4-6k/month in achievable savings...

      **Acceptance criteria**
      - Monthly cloud spend reduced by ≥£1,500 by 2026-06-30
      - VM Licenses line on the cost report < £500
    extra_fields:                             # optional per-item override
      customfield_10100: "Platform team"

stories:
  - id: AHB
    epic: COSTS                               # must match an epics[].id
    summary: "Enable Azure Hybrid Benefit on production Windows VMs"
    priority: Highest
    story_points: 3                           # Fibonacci: 1, 2, 3, 5, 8, 13
    labels: [cost-optimisation, azure, windows, licensing]
    description: |
      **Why this matters**
      7 production Windows VMs run without AHUB, costing ~£1,500/month
      in licensing that's already covered by Software Assurance.

      **Scope**
      - All 7 production Windows VMs (CULT-SQL-VMP01, cult-sqldw-p01, ...)

      **Acceptance criteria**
      - All 7 VMs report `licenseType: Windows_Server`
      - Next monthly cost report shows VM Licenses < £500
      - No service downtime during rollout (uptime monitor green)

      **Source**: `examples/cost-review.md#1`
    subtasks:
      - id: AHB-INV
        summary: "Inventory eligible Windows Server licenses with Software Assurance"
        description: "Confirm with IT procurement before applying AHUB."
      - id: AHB-RUN
        summary: "Run az vm update --license-type Windows_Server on each VM"
        description: "Apply to the 7 VMs from the inventory step, verify in Azure Portal."
```

## Field rules

- **`id`** — intake-local stable identifier; appears in `results.json` mapping to the Jira key.
- **`epic` reference on stories** — must match an `epics[].id`.
- **`priority`** — exactly one of `Highest`, `High`, `Medium`, `Low`, `Lowest`, or omitted.
- **`story_points`** — number on the modified Fibonacci scale (1, 2, 3, 5, 8, 13). Stories above 13 should be split. Subtasks and epics are not sized.
- **`labels`** — passed through verbatim. The skill normalises (kebab-case, dedup, ≤5).
- **`description`** — markdown. The CLI converts `**bold**`, `*italic*`, `` `code` ``, `[text](url)` to ADF marks.
- **`extra_fields`** — dict of customfield-id → value. Per-item overrides per-key over `defaults.extra_fields`. Values pass through to the Jira API verbatim — for rich-text customfields, pass an ADF doc; for text/number fields, pass the raw value.
- **`assignee_account_id`** — Atlassian Cloud accountId only (e.g. `712020:abcd-...`). Email addresses do not work.

## Subtask inheritance (automatic)

If a subtask omits `priority` or has empty `labels`, it inherits the parent story's. To break inheritance, set the field explicitly on the subtask.

## Discovery

Find tenant-specific customfield IDs:

```
mdjira fields https://your-tenant.atlassian.net
```

The output highlights likely-useful fields (Story Points, Acceptance Criteria, Sprint, Team, etc.) — copy the relevant `customfield_*` IDs into `defaults.story_points_field` or `defaults.extra_fields`.

## Customfield value shapes (by field type)

`extra_fields` and `story_points_field` values pass through to Jira's REST API verbatim — there's no client-side coercion. That means **the shape you pass has to match the customfield's type**, and Jira's customfield types each take a different JSON shape. Use this table when you set up a tenant the first time:

| Field type (in Jira admin)                 | Discover via `mdjira fields`        | YAML value shape                                                      |
| ------------------------------------------ | --------------------------------------- | --------------------------------------------------------------------- |
| **Number** (story points, effort, cost)    | `schema.type: number`                   | Bare number: `3` or `3.5`.                                            |
| **Short text** (single-line)               | `schema.type: string`                   | Bare string: `"Platform team"`.                                       |
| **Paragraph** (rich text / multi-line)     | `schema.type: string`, custom: `...textarea` | ADF document object (see below). Plain string also accepted on most tenants but renders as a single line. |
| **Single-select** (dropdown)               | `schema.type: option`                   | `{ value: "In progress" }`. Use the option's `value` field as shown in the dropdown UI; case-sensitive. |
| **Multi-select** / **Checkboxes**          | `schema.type: array`, items: `option`   | `[{ value: "Frontend" }, { value: "Backend" }]`.                       |
| **Cascading select**                       | `schema.type: option-with-child`        | `{ value: "Parent", child: { value: "Child" } }`.                     |
| **Radio buttons**                          | `schema.type: option`                   | Same as single-select: `{ value: "Yes" }`.                            |
| **User picker** (single)                   | `schema.type: user`                     | `{ accountId: "712020:abcd-..." }`. **Email addresses don't work** on Cloud. |
| **User picker** (multi)                    | `schema.type: array`, items: `user`     | `[{ accountId: "712020:abcd-..." }, { accountId: "712020:..." }]`.    |
| **Group picker** (single)                  | `schema.type: group`                    | `{ name: "jira-administrators" }`.                                    |
| **Date** (date only)                       | `schema.type: date`                     | ISO-8601 date string: `"2026-04-30"`.                                  |
| **Datetime**                               | `schema.type: datetime`                 | ISO-8601 with offset: `"2026-04-30T15:00:00.000+0000"`.                |
| **Labels** (custom labels field)           | `schema.type: array`, items: `string`   | Array of strings: `["q1", "platform"]`.                               |
| **URL**                                    | `schema.type: string`, custom: `...url` | Bare string: `"https://example.com/runbook"`.                          |
| **Sprint**                                 | `schema.type: array`, items: `string`   | Array containing the **sprint id** as a number: `[42]`. Names don't resolve via REST. |
| **Epic Link** (classic projects only)      | `schema.type: any`, custom: `...epic-link` | Bare epic key string: `"ABC-100"`. mdjira already handles this — don't set it manually. |

ADF (Atlassian Document Format) shape for paragraph fields is:

```yaml
extra_fields:
  customfield_12345:
    type: doc
    version: 1
    content:
      - type: paragraph
        content:
          - { type: text, text: "Plain content here." }
```

The CLI's own `description` field accepts plain markdown and gets converted to ADF for you — only paragraph **customfields** need the explicit ADF shape.

**Rule of thumb when in doubt:** post a single issue manually via the Jira UI with the customfield set, then `GET /rest/api/3/issue/<KEY>?fields=customfield_xxxxx` and copy the exact JSON shape from the response back into `extra_fields`.

## Source links (`defaults.source_base_url`)

Optional. When set, the skill auto-emits a `**Source**: <url>` line at the bottom of every Story description, pointing at the relevant section of the source markdown:

```yaml
defaults:
  source_base_url: https://github.com/your-org/your-repo/blob/main/specs/cost-review.md
```

The skill appends `#anchor-or-line-number` per Story so reviewers can jump straight from the Jira ticket to the markdown bullet that produced it. Leave unset and Stories use a relative `examples/...` path instead, which still survives a `git grep`.

## Things the schema does not have (by design)

- Sprint assignment / board placement
- Start/end dates / timelines  
- Comments
- Jira-to-markdown reverse sync

These are out of scope for v1.
