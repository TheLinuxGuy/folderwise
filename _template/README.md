---
title: {{PROJECT_TITLE_YAML}}
doc_type: overview
status: active
sensitivity: {{SENSITIVITY}}
owner: human
created: {{DATE}}
updated: {{DATE}}
updated_by: {{BY}}
last_verified: null
review_every: 90d
tags: []
---

# {{PROJECT_TITLE}}

{{DESCRIPTION}}

## Contents

<!-- index:start -->
No docs yet.
<!-- index:end -->

## Working here

- Agents: read `AGENTS.md` first (`CLAUDE.md` imports it).
- All dates and times use the project timezone ({{TIMEZONE}}), set in `.docs.yaml`.
- To read git history in that timezone: `TZ={{TIMEZONE}} git log --date=format-local:'%F %R %Z'`
- Link to other docs with relative markdown links, e.g. `[Grants](docs/grants.md#vest-events)`; `docs_lint.py` rejects broken ones and warns on unlinked mentions. Move or rename with `docs_mv.py`, not `mv`, so links stay valid.
- Optional table of contents: for a long doc, run `uv run ../_tools/docs_stamp.py FILE --toc --by ... --summary "..."`. It sets `toc: true` and keeps a generated `## Contents` list current. Off by default; VS Code's Outline view covers most needs.
- What exists: `uv run ../_tools/docs_index.py`. What changed lately: `uv run ../_tools/docs_recent.py --since 7d`. New doc from a skeleton: `uv run ../_tools/docs_new.py PATH --type TYPE --title "..." --by ...`.
- Every `.md` has front matter and a Change Log; see the shared rules in `AGENTS.md`.

## Change Log

<!-- changelog:start -->
| When | By | Summary |
|------|----|---------|
<!-- changelog:end -->
