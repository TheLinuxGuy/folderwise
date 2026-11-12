---
title: Lab Notes
doc_type: overview
status: active
sensitivity: private
owner: human
created: 2026-10-25
updated: 2026-10-26
updated_by: codex/gpt-6
last_verified: null
review_every: 90d
tags: []
---

# Lab Notes

<!-- byline:start -->
> **Status:** active · **Updated:** 2026-10-26 by codex/gpt-6
<!-- byline:end -->

Fictional local bridge acceptance tests

## Contents

<!-- index:start -->
- **docs/**
  - [Acceptance 0.2.0 Markdown fixtures](docs/acceptance-020.md) - Fictional task fixtures for the 0.2.0 iPhone acceptance run (plan, active)
  - [Dataview acceptance fixtures](docs/dataview-checks.md) - Fictional tasks for phone serialization testing (plan, active)
  - [Fictional duplicate task checks](docs/duplicate-checks.md) (plan, active)
  - [iPhone Markdown checks](docs/iphone-checks.md) - Fictional tasks for mobile bridge testing (plan, active)
<!-- index:end -->

## Working here

- Agents: read `AGENTS.md` first (`CLAUDE.md` imports it).
- All dates and times use the project timezone (America/Los_Angeles), set in `.docs.yaml`.
- To read git history in that timezone: `TZ=America/Los_Angeles git log --date=format-local:'%F %R %Z'`
- Link to other docs with relative markdown links, e.g. `[Grants](docs/grants.md#vest-events)`; `docs_lint.py` rejects broken ones and warns on unlinked mentions. Move or rename with `docs_mv.py`, not `mv`, so links stay valid.
- Optional table of contents: for a long doc, run `uv run ../_tools/docs_stamp.py FILE --toc --by ... --summary "..."`. It sets `toc: true` and keeps a generated `## Contents` list current. Off by default; VS Code's Outline view covers most needs.
- What exists: `uv run ../_tools/docs_index.py`. What changed lately: `uv run ../_tools/docs_recent.py --since 7d`. New doc from a skeleton: `uv run ../_tools/docs_new.py PATH --type TYPE --title "..." --by ...`.
- Every `.md` has front matter and a Change Log; see the shared rules in `AGENTS.md`.

## Change Log

<!-- changelog:start -->
| When | By | Summary |
|------|----|---------|
| 2026-10-26 21:05 PDT | codex/gpt-6 | Index fictional Dataview acceptance tasks |
| 2026-10-26 21:05 PDT | codex/gpt-6 | Add docs/dataview-checks.md to index |
| 2026-10-26 14:43 PDT | human | Index fictional duplicate task checks |
| 2026-10-26 14:43 PDT | human | Add docs/duplicate-checks.md to index |
| 2026-10-26 01:30 PDT | claude/sonnet-5.5 | Index acceptance fixtures |
| 2026-10-26 01:30 PDT | claude/sonnet-5.5 | Add docs/acceptance-020.md to index |
| 2026-10-25 15:43 PDT | human | Index acceptance-test notes |
| 2026-10-25 15:43 PDT | human | Add docs/iphone-checks.md to index |
| 2026-10-25 15:42 PDT | human | Project scaffolded |
<!-- changelog:end -->
