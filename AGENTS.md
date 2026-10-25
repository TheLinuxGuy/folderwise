# Folderwise — Framework Instructions

This is the Folderwise framework repository. Knowledge projects coexist as ignored sibling folders, each with its own Git repository, `AGENTS.md`, `CLAUDE.md` and `.docs.yaml`. Only directories containing `.docs.yaml` are knowledge projects; `docs/` contains public framework guides.

The root `.gitignore` is an allowlist. Never add knowledge projects, caches, credentials, `.obsidian/`, or nested repositories to this repository. Do not bypass `_tools/framework_guard.py`. In a pull-only deployment (`git config --get folderwise.pullOnly` is `true`), publish from the separate development checkout; do not enable pushes here.

## Layout
- `_template/` — source for new projects. `_template/AGENTS.md` holds the shared rules (managed block).
- `_tools/` — shared single-file Python tools (run with `uv run`):
  - `new_project.py` — create a project (asks name, purpose, sensitivity; git init; installs hook)
  - `docs_lint.py` — validate front matter + Change Log
  - `docs_stamp.py` — stamp `updated`, `updated_by`, Change Log after an edit
  - `docs_stale.py` — list docs overdue for re-verification (`--all` for every project)
  - `docs_new.py` — create a doc from the skeleton for its type (runbook, decision, inventory, ...)
  - `docs_index.py` — catalogue of docs (what exists); `--write` refreshes the generated README index
  - `docs_recent.py` — merged Change Logs: what changed lately, across docs or projects
  - `render_tables.py` — render CSV-backed tables in docs and stamp changed docs (`--check` for drift)
    - Opt-in money display: `money=col,col2` (+ `currency=XXX` when the CSV has no `currency` column, or `currency_col=name`) formats only those columns (`$21,000.00`; `1,234.50 EUR`); CSVs stay plain decimals and directives without `money=` render exactly as before. Details: docs/guide.md "Money columns"
  - `docs_mv.py` — move/rename a doc or folder, or rename a heading, rewriting links and anchors (`--dry-run` to preview)
  - `docs_doctor.py` — health check of a project's setup (hook, template sync, config, git, lint, staleness); `--all` for every project
  - `sync_rules.py` — push the template's shared rules, hook and config files (`.vscode/*`, `.markdownlint.json`, `_doc-template.md`) into all projects (`--check` for drift)
  - `selftest.py` — automated self-test of all the tools in an isolated temp copy (about 15 seconds)
- `uv.toml` — portable uv defaults; no machine-specific paths. Optional `UV_CACHE_DIR` is local to the environment, not committed.
- `_tools/framework_guard.py` — validates the public framework index; `_tools/framework-hooks/` contains root hooks.
- `.github/` — CI (`workflows/ci.yml`), manual draft-release preparation (`workflows/release.yml`), their helper scripts and tests (`scripts/`), and `release-manifest.txt`. Root `.coveragerc`, `codecov.yml` and `ruff.toml` hold coverage, Codecov and lint policy. These are allowed by **exact path** in both `.gitignore` and `framework_guard.py` (`CI_FILES`); adding one means editing both, and `selftest.py -k ci_allowlist` verifies they agree.
- `docs/` — public framework guides, including Obsidian/iCloud and framework-only deployments.
- `<project>/` — a project repo. Work inside it; follow its `AGENTS.md`.

## Rules for work at this level
- Work on one project at a time; run its tools from that project's root.
- Do not edit a project's managed block (between `BEGIN/END MANAGED` markers). Change `_template/AGENTS.md`, then run `uv run _tools/sync_rules.py` and commit the result in each project.
- Codex stops reading `AGENTS.md` at the git root, so shared rules must be inside each project's own file. Claude Code reads each project's `CLAUDE.md`, which contains only `@AGENTS.md`.
- Never create `CLAUDE.md`, `CLAUDE.local.md` or `.claude/CLAUDE.md` in this folder or above it. Claude Code loads parent-directory `CLAUDE.md` files into every project session (and asks to approve imports outside the project). With none here, Claude Code (v2.1.277+) reads this `AGENTS.md` natively when working at this level, and each project's own `CLAUDE.md` keeps this file out of project sessions. `docs_doctor.py` and `selftest.py` warn/fail if one appears.
- Creating a project: `uv run _tools/new_project.py` (never copy folders by hand).

## Changing the tools or template (verification required)
- Before editing anything in `_tools/` or `_template/`, make sure no other session is editing them (one writer at a time). Snapshot shared inputs and check for concurrent changes before deploying a release.
- Run `uv run _tools/selftest.py` before you start (to know the baseline) and again when you finish. It must report all checks passed. Use `-k <section>` while iterating (sections: create, new_doc, stamp, hook, lint, timezone, links, toc, mv, tables, stale, sync, doctor, layout, cli_errors, failure_paths, uv_cache, docs_coverage, readme_commands, framework_index, ci_allowlist).
- Every new tool, setting or behaviour gets a check in `_tools/selftest.py` and an entry in the public documentation: keep README.md concise and place detailed commands/configuration in docs/guide.md (the `docs_coverage` section checks both and fails if a tool or `.docs.yaml` setting is undocumented) in the same change. A tool change without a passing self-test is not done.
- When managed template rules change, sync them into affected projects only with the owner's authorization, then validate and commit in each independent project repository. Publishing the framework alone does not authorize modifying knowledge projects.
- The pre-commit hook fails closed: if a project cannot find `../_tools` or `uv`, its commits are blocked (`DOCS_SKIP_HOOK=1` bypasses once, only when the user says so).
- CI enforces the same suite plus coverage: at least 85% production line coverage (`uv run .github/scripts/ci_coverage.py`) and at least 90% of changed lines (Codecov `codecov/patch`). Cover new behavior with real CLI/hook tests, not artificial ones; never lower a threshold, widen an omit, or add `pragma: no cover` to pass. Changes to workflows, `.github/scripts/`, `.coveragerc`, `codecov.yml`, `ruff.toml`, `.gitignore` or `framework_guard.py` need explicit mention in the PR and careful review. Releases are prepared only by the manual **Prepare release** workflow (`docs/maintainers.md`); never publish one or create tags yourself.
