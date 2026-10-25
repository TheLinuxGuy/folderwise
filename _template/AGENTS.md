# {{PROJECT}} — Agent Instructions

## Purpose

{{DESCRIPTION}}

## Project-specific rules

- _(add rules that only apply to this project)_

<!-- BEGIN MANAGED: docs-rules -->
<!-- Managed by ../_tools/sync_rules.py — do not edit inside this block. -->
## Documentation rules (shared across all projects)

Run all commands from this project's root. Tools live in `../_tools/` and run with `uv run`.
Project config: `.docs.yaml`.

### Scope
- Applies to every `.md` file except `AGENTS.md`, `CLAUDE.md`, and any file or directory whose name starts with `_` or `.`.
- Docs are written for humans first. Be concrete, current, and brief. One topic per file.
- Never invent facts. If something is unverified, say so inline (`> Unverified: ...`) and do not use `--verified`.
- Never write credential values (passwords, tokens, API keys, private keys). Name where they are stored instead.

### Required front matter
Every doc starts with YAML front matter containing exactly these core fields (plus any `extra_fields` declared in `.docs.yaml`):

| Field | Rule |
|---|---|
| `title` | Non-empty string |
| `doc_type` | One of: overview, reference, runbook, decision, inventory, plan, log |
| `status` | `draft`, `active`, `deprecated`, or `archived` (closed period: frozen, skipped by staleness reports) |
| `sensitivity` | `public`, `private`, or `restricted` (default: the project's value) |
| `owner` | Person responsible (usually `human`) |
| `created` / `updated` | ISO dates (`YYYY-MM-DD`) in the project timezone |
| `updated_by` | `human` or `<agent>/<model>`, e.g. `codex/gpt-5.5`, `claude/opus-5-5` |
| `last_verified` | ISO date (project timezone), or `null` if never checked against reality |
| `review_every` | Interval like `30d`, `12w`, `6m` |
| `tags` | List (may be empty) |
| `toc` | Optional. `true` adds a generated `## Contents` list; omit for none (the default) |
| `summary` | Optional one-line description (1-160 chars); shown in the README index and `docs_index.py` output |

`updated` = any edit. `last_verified` = you confirmed the content against the real system or source. Only set it with `--verified` when you actually did.

### Timezone
All dates and times use the `timezone` set in `.docs.yaml` (default `America/Los_Angeles`), never the machine's local timezone, which may change while traveling. The tools handle this; do not compute dates yourself.

### Size and splitting
- Keep each doc under ~400 lines (lint warns above `max_doc_lines`). Agents read whole files, so size is cost.
- Keep current state (open positions, active config) separate from history.
- Append-only history (sales, purchases, incidents) goes in one file per year under `history/YYYY.md`, plus a short index or summary doc with per-year totals.
- When a period closes, set that doc to `status: archived` and stop editing it (corrections only, with a Change Log entry).
- Very large raw tables (thousands of rows) belong in a CSV next to the docs; keep markdown for summaries and narrative.

### Tables
- Tables of records (rows that grow or change: inventories, ledgers, lots, hosts) live in CSV files under `data/` and are embedded in docs as generated blocks:
  `<!-- table:start src=data/x.csv [cols=a,b] [where=col=val] [sort=col,-col2] -->` then `<!-- table:end -->`.
- Never hand-edit inside a generated block. Edit the CSV, then run `uv run ../_tools/render_tables.py --by <agent>/<model> --summary "<what changed>" [--verified]`. It re-renders and stamps the affected docs.
- CSV rules: header row, UTF-8, comma-separated, quote cells that contain commas, one record per line, append new records at the end. Fix mistakes by editing the row and saying so in the commit message.
- Small static tables (at most `inline_table_max_rows`, default 8, rows) may stay inline. Lint fails on larger inline tables. The Change Log table is exempt.
- Computed columns (totals, gains, statuses) come from a project script under `scripts/` that writes derived CSVs (for example `data/views/`), never from hand calculation.

### Links between docs
- Whenever a doc refers to another doc, CSV or asset, write a clickable markdown link, never a bare or backticked filename: `[RSU grants](../rsu/grants.md)`. In VS Code, Cmd+click follows it.
- Format: path relative to the file containing the link, forward slashes, the `.md` extension, exact letter case. An optional `#anchor` is the target heading in lowercase with spaces as hyphens and punctuation dropped (repeats get `-1`, `-2`): `[Vest events](../rsu/grants.md#vest-events-ordinary-income)`.
- Not allowed: absolute paths (`/Users/...`), `file://` URLs, root-relative `/docs/x.md`, backslashes, or links that leave this repo. Each project is its own repo, so name other projects in plain text (for example "investments: docs/tax-summary.md").
- Link text is the target's title or a short description, never "here".
- `docs_lint.py` fails on broken links (missing file or anchor, wrong format) and warns when prose names an existing doc without linking it. Fix a warning by adding the link.
- Never move or rename a doc, folder or data file with plain `mv`/`git mv`, and never rename a heading by hand when other docs link to it. Use:
  `uv run ../_tools/docs_mv.py mv <src> <dst> --by <agent>/<model>` (moves with git history, rewrites links and `table:start src=` paths, recomputes relative links inside moved docs, stamps touched docs, lints), or
  `uv run ../_tools/docs_mv.py heading <file> "Old heading" "New heading" --by <agent>/<model> [--nth N]` (rewrites `#anchor` links). Add `--dry-run` to preview.
  It prints `NOTE` lines for plain-text mentions and for scripts or CSVs that still name the old path; fix those by hand. Deleting a doc: remove or redirect every link to it first (lint will list them).
- Links inside generated blocks (tables, contents) come from their tools; do not hand-edit them.

### Byline (visible status line)
- With `byline: true` in `.docs.yaml` (the template default), each doc shows a generated line under its H1, between `<!-- byline:start -->` and `<!-- byline:end -->`: `> **Status:** ... · **Updated:** date by who`. It exists because the VS Code preview hides front matter; verification, review dates and sensitivity are only in the front matter.
- Never edit it. `docs_stamp.py` regenerates it from the front matter; lint fails if it is stale (for example after you hand-edit `status:`, so re-stamp).

### Finding, creating and indexing docs
- To see what exists, run `uv run ../_tools/docs_index.py` (one line per doc: path, type, status, dates, summary) instead of opening files.
- To see what changed lately, run `uv run ../_tools/docs_recent.py --since 7d` (merged Change Logs; options `--by`, `--limit`, `--all`).
- New doc: `uv run ../_tools/docs_new.py docs/<area>/<name>.md --type <doc_type> --title "..." --about "<one line>" --by <agent>/<model>`. It starts from the skeleton for that type as `status: draft` and adds front matter, byline and Change Log. Replace every ``TODO: fill in``, set `status: active` in the front matter, then re-stamp. Lint warns about leftover placeholders in non-draft docs.
- README `## Contents` holds a generated index between `<!-- index:start -->` and `<!-- index:end -->`. After adding, removing or retitling a doc, or changing its `doc_type`, `status` or `summary`, run `uv run ../_tools/docs_index.py --write --by <agent>/<model> --summary "..."`. Lint fails when the index is stale.
- Every doc except README should be linked from at least one other doc (the index counts). Lint warns about orphans.

### Table of contents (optional, off by default)
- Most docs need no TOC: VS Code's Outline view and Forgejo already show headings. Enable one only for long docs.
- Enable: `uv run ../_tools/docs_stamp.py <file> --toc --by <agent>/<model> --summary "..."` (this sets `toc: true` in front matter). Disable with `--no-toc`.
- The list lives under `## Contents` between `<!-- toc:start -->` and `<!-- toc:end -->`, placed before the first `##` section. Never edit it by hand.
- It is regenerated on every stamp, and lint fails if it is stale. After adding, renaming or removing a heading in a `toc: true` doc, re-stamp it.
- Depth: `toc_depth` in `.docs.yaml` (default 2 = `##` only; 3 also lists `###`). Headings inside code fences are ignored, as are `Contents` and `Change Log`.

### Change Log
Every doc ends with a `## Change Log` section holding a table between `<!-- changelog:start -->` and `<!-- changelog:end -->`.
Newest row first, max 10 rows. Each row's time looks like `2026-10-24 14:32 PDT` (24-hour clock, zone abbreviation).
The newest row must match `updated` (date part) and `updated_by`. Do not edit rows or type dates and times by hand; use the stamp tool.

### After editing any doc (required)
1. Stamp it (updates `updated`, `updated_by`, the Change Log, and optionally `last_verified`):
   `uv run ../_tools/docs_stamp.py <file> --by <agent>/<model> --summary "<what changed, <= 80 chars>" [--verified]`
2. Brand-new doc: use `docs_new.py` (see below). A file that already exists without front matter: stamp it with `--init --type <doc_type>`.
3. Validate: `uv run ../_tools/docs_lint.py` (a pre-commit hook runs the same check on staged files).

### Git
- Each project is its own git repo. Commit only inside this repo, one logical change per commit, imperative subject line.
- Add trailers to every agent commit:
  ```
  Agent: <agent name>
  Model: <model id>
  ```
- Never use `--no-verify`, never rewrite published history, never commit credentials.
- Keep one writer at a time: this folder is synced by Synology Drive, so concurrent edits from two machines can corrupt the repo.

### Maintenance tasks
- Find docs due for re-verification: `uv run ../_tools/docs_stale.py` (add `--within 14` to include upcoming).
- After verifying a doc against reality, stamp it with `--verified`.
- Check this project's setup (hook, template sync, config, lint, overdue docs): `uv run ../_tools/docs_doctor.py`.
- Never edit `../_tools` or `../_template` from inside a project. Tool and template changes are made at the Folderwise root level and must pass `uv run ../_tools/selftest.py`.
- If a commit is blocked with "docs tools not found" or "uv not found", fix the cause (project must sit next to `_tools/`; install `uv`). Do not bypass with `DOCS_SKIP_HOOK=1` unless the user says so.
<!-- END MANAGED: docs-rules -->
