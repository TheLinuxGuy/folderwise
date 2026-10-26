# Folderwise usage guide

Commands, configuration, and troubleshooting. [Back to the project overview](../README.md).

## Framework checkout setup

`framework_checkout.py` configures an existing clone as a minimal pull-only installation. It keeps all tracked underscore-prefixed root folders and essential root files (including README.md and LICENSE by default); public guides, images and CI files stay out of the working tree. It preserves independent topic repositories and refuses tracked edits. `--minimal --omit README.md LICENSE` makes those optional files stay absent; `--minimal --include README.md LICENSE` restores them. If either is deleted manually, `--update` remembers the deletion before pulling. Run the updater once before returning to bare Git pulls.

```bash
cd ~/folderwise && python3 _tools/framework_checkout.py --minimal --dry-run
cd ~/folderwise && python3 _tools/framework_checkout.py --minimal
cd ~/folderwise && python3 _tools/framework_checkout.py --update
cd ~/folderwise && python3 _tools/framework_checkout.py --full
```

Ordinary `git pull --ff-only` also preserves the minimal layout. `--full` restores all tracked files while retaining pull-only safeguards. Read the [setup, safety checks and update details](framework-checkout.md#minimal-pull-only-checkout) before converting an existing clone.

## Quick start

Every block below is complete: paste it into a terminal from any folder (they start with `cd`). Examples use the `homelab-inventory` project; swap in your project folder name. Use `--by human` when you run a tool yourself; agents use `--by <agent>/<model>`, for example `--by codex/gpt-5.5`.

### Create a new project

Makes the folder, its own git repo (branch `main`), shared agent rules, the pre-commit hook and a first commit. Folder names are lowercase letters, digits and hyphens.

```bash
cd ~/folderwise && uv run _tools/new_project.py --name homelab-inventory --description "Inventory of home network hardware and software to allow for homelab v3 planning" --sensitivity private --by human
```

Prefer to be asked the questions instead:

```bash
cd ~/folderwise && uv run _tools/new_project.py
```

When it finishes it prints a ready-made prompt. Start an agent in the new project (the `cd ... && claude` / `codex` line is printed for you), paste the prompt, and let it run the setup. The agent reads the project files first, then asks you for **one batch of context** (what it tracks, who uses it, how often it changes, recurring agent tasks, what it must never do without your OK, sensitive data, material to import). You answer once, free-form; partial is fine. It then restates what it understood and asks up to 5 follow-ups (8 if essential), each with a recommended default you can accept. After that it proposes 3 genuinely different folder structures; you pick one, and it writes short rules in the project's `AGENTS.md` (never the managed block), creates the folders and starter docs, shows you the diff, and commits once you agree. Add `--no-prompt` to hide the prompt. If you lose the output, this is the prompt for the example above (change the name and purpose):

```text
Set up the docs project "homelab-inventory" (purpose: Inventory of home network hardware and software to allow for homelab v3 planning). Read AGENTS.md and .docs.yaml first; never ask what files answer. Then ask nothing yet: list a short fill-in (what it tracks, who uses it, how often it changes, recurring agent tasks, what agents must never do without my OK, sensitive data, material to import) for me to answer once, free-form, partial is fine. Then restate your understanding, flag assumptions, and ask at most 5 follow-ups (8 if essential), one at a time, each with a recommended default and only on gaps that change the structure. Then propose 3 genuinely different folder structures with trade-offs, recommend one, and wait for my choice. After I choose: write short, non-obvious project rules in AGENTS.md (never the managed block), set .docs.yaml extra_fields if useful, create the folders and starter docs with ../_tools/docs_new.py, run ../_tools/docs_lint.py, show me the diff, and commit once I agree.
```

To skip the pasting, add `--start claude` (or `--start codex`): after creating the project it starts that agent inside the new folder with the prompt already filled in. It needs an interactive terminal and the agent on your PATH; otherwise it just prints what to run.

```bash
cd ~/folderwise && uv run _tools/new_project.py --name homelab-inventory --description "Inventory of home network hardware and software to allow for homelab v3 planning" --sensitivity private --by human --start claude
```

### Open a project

In VS Code:

```bash
code ~/folderwise/homelab-inventory
```

With Claude Code:

```bash
cd ~/folderwise/homelab-inventory && claude
```

With Codex:

```bash
cd ~/folderwise/homelab-inventory && codex
```

### Start a new doc

Creates `docs/hosts/nas.md` from the skeleton for its type (as a `draft`) and adds it to the README index. Types: `overview`, `reference`, `runbook`, `decision`, `inventory`, `plan`, `log`.

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_new.py docs/hosts/nas.md --type inventory --title "NAS inventory" --about "Disks, volumes and shares on the NAS" --by human
```

### After you edit a doc

Stamp it: updates `updated`, `updated_by`, the status line and the Change Log. Every edit needs a stamp.

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/hosts/nas.md --by human --summary "Add disk table"
```

Same, but also record that you checked the content against the real thing (sets `last_verified`):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/hosts/nas.md --by human --summary "Verified against the NAS UI" --verified
```

A file you wrote by hand that has no front matter yet:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/notes.md --init --type reference --by human --summary "Initial draft"
```

If you changed a doc's title, summary or status, refresh the README index too:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_index.py --write --by human --summary "Refresh index"
```

### Check and commit

Validate every doc (front matter, status line, Change Log, links, tables, index):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_lint.py
```

Commit (the pre-commit hook runs the same check on what you staged):

```bash
cd ~/folderwise/homelab-inventory && git add -A && git commit -m "Describe what changed"
```

### See what exists, what changed, what is stale

What docs exist (type, status, dates, summary):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_index.py
```

What changed in the last 7 days, newest first, from the Change Logs (no git needed):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_recent.py --since 7d
```

What is overdue for re-verification, plus what falls due in the next 14 days:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stale.py --within 14
```

Git history with times in Los Angeles time:

```bash
cd ~/folderwise/homelab-inventory && TZ=America/Los_Angeles git log --date=format-local:'%F %R %Z' --format='%h %ad %an  %s'
```

### Health check

One project (hook installed, rules in sync, config valid, git clean, lint, overdue docs):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_doctor.py
```

Every project:

```bash
cd ~/folderwise && uv run _tools/docs_doctor.py --all
```

### Move or rename a doc (keeps links working)

Never use `mv` for docs. Preview first, then run it again without `--dry-run`:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_mv.py mv docs/hosts/nas.md docs/storage/nas.md --by human --dry-run
```

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_mv.py mv docs/hosts/nas.md docs/storage/nas.md --by human
```

Rename a heading (fixes `#anchor` links to it):

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_mv.py heading docs/storage/nas.md "Old heading" "New heading" --by human
```

### Edit a table that comes from a CSV

Change the CSV in `data/`, then re-render every doc that embeds it:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/render_tables.py --by human --summary "Update hosts table"
```

Only check whether any table is out of date:

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/render_tables.py --check
```

### Add or remove a table of contents on one doc

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/storage/nas.md --toc --by human --summary "Add contents"
```

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/storage/nas.md --no-toc --by human --summary "Remove contents"
```

### Update shared rules and config in your projects

After the template changes (`_template/`), see which projects drifted:

```bash
cd ~/folderwise && uv run _tools/sync_rules.py --check
```

Apply it to one project, or to all (then review and commit inside each project):

```bash
cd ~/folderwise && uv run _tools/sync_rules.py homelab-inventory
```

```bash
cd ~/folderwise && uv run _tools/sync_rules.py
```

### Verify the tools themselves

Run after any change to `_tools/` or `_template/` (about 15 seconds; it must say all checks passed):

```bash
cd ~/folderwise && uv run _tools/selftest.py
```

### Weekly routine

```bash
cd ~/folderwise
uv run _tools/docs_doctor.py --all
uv run _tools/docs_stale.py --all
uv run _tools/docs_recent.py --all --since 7d
```

## If a commit is blocked

The pre-commit hook lints what you staged and prints the problem. Fix, `git add -A`, commit again. To see every problem at once, run `docs_lint.py` (see "Check and commit").

**`edited but Change Log unchanged`** or **`byline is out of date`**: you edited a doc without stamping it.

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_stamp.py docs/hosts/nas.md --by human --summary "Describe the edit"
```

**`index block is out of date`** (README): a doc was added, renamed, or its title, summary or status changed.

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/docs_index.py --write --by human --summary "Refresh index"
```

**`Contents is out of date`**: a doc with a table of contents had its headings changed; stamp it again (command above).

**`generated table block(s) out of date`**: a CSV changed.

```bash
cd ~/folderwise/homelab-inventory && uv run ../_tools/render_tables.py --by human --summary "Re-render tables"
```

**`broken link`**: the message names the file and line. Fix the link, or if you moved a file by hand put it back and use `docs_mv.py` (see "Move or rename a doc").

**`docs tools not found`** or **`uv not found`**: the project folder must sit directly inside `Folderwise` (next to `_tools/`), and `uv` must be installed. As a last resort, bypass the check for one commit (this skips lint, so use it deliberately):

```bash
cd ~/folderwise/homelab-inventory && DOCS_SKIP_HOOK=1 git commit -m "Describe what changed"
```

**Hook missing** (for example after cloning a project, since git does not copy hooks): reinstall it.

```bash
cd ~/folderwise && uv run _tools/sync_rules.py homelab-inventory
```

## Values you will be asked for

| Option | Allowed values |
|---|---|
| `--name` | lowercase letters, digits and hyphens, for example `homelab-inventory` |
| `--sensitivity` | `public`, `private` or `restricted` (use `restricted` for account details; the doctor then warns if a remote is added) |
| `--by` | `human` or `<agent>/<model>`, for example `codex/gpt-5.5` or `claude/sonnet-5-5` |
| `--type` (docs) | `overview`, `reference`, `runbook`, `decision`, `inventory`, `plan`, `log` |
| doc `status` | `draft`, `active`, `deprecated`, `archived` (closed period: frozen, skipped by staleness reports) |
| `review_every` | `30d`, `12w`, `6m` |
| `--timezone` (new project) | an IANA name; default `America/Los_Angeles` |

Never put passwords, tokens or keys in docs; name where they are stored instead (for example "password manager item X").

## Reference

### How it fits together

All tools are single-file Python scripts run with `uv run`. Inside a project they are `../_tools/<name>`; from the Folderwise root they are `_tools/<name>`.

uv uses its platform-default cache location. The committed `uv.toml` contains no machine-specific cache path. You can set `UV_CACHE_DIR` locally when needed; `selftest.py -k uv_cache` checks portability and override behavior.

| Tool | Use it to | Where |
|---|---|---|
| `new_project.py` | create a project (own git repo, rules, hook, README) | root |
| `docs_new.py` | start a doc from the skeleton for its type | project |
| `docs_stamp.py` | after any edit: update `updated`, `updated_by`, byline, Change Log (`--verified`, `--toc`, `--init`) | project |
| `docs_lint.py` | validate front matter, byline, Change Log, tables, links, README index | project |
| `docs_index.py` | list what docs exist; `--write` refreshes the README index | project |
| `docs_recent.py` | list what changed lately from the Change Logs (no git needed) | project / `--all` |
| `docs_stale.py` | list docs overdue for re-verification | project / `--all` |
| `docs_mv.py` | move or rename a doc/folder or a heading and keep links valid | project |
| `render_tables.py` | render CSV-backed tables into docs | project |
| `docs_doctor.py` | health check of a project's setup (hook, sync, config, git, lint, staleness) | project / `--all` |
| `sync_rules.py` | push the template's rules, hook and config files into projects | root |
| `selftest.py` | verify the tools themselves | root |
| `framework_guard.py` | prevent knowledge folders, secrets, symlinks, or nested repositories from entering the framework index | root |

Every agent rule lives in each project's `AGENTS.md` (shared block from `_template/AGENTS.md`); this README is the human guide. See the root `AGENTS.md` for the layout and the rules for changing the tools.

### Project settings (`.docs.yaml`)

Each project has a `.docs.yaml` at its root. Unknown keys are reported by `docs_doctor.py`.

| Key | Default | Meaning |
|---|---|---|
| `schema_version`, `project`, `description` | set by `new_project.py` | identity of the project |
| `sensitivity` | asked at creation (`private`) | default `sensitivity` for new docs: `public`, `private` or `restricted` |
| `owner` | `human` | default `owner` for new docs |
| `timezone` | `America/Los_Angeles` | IANA zone for every date and Change Log time in the project |
| `review_every_default` | `90d` | default `review_every` for new docs (`30d`, `12w`, `6m`) |
| `byline` | `true` | generated `Status · Updated` line under each title |
| `doc_types` | overview, reference, runbook, decision, inventory, plan, log | allowed `doc_type` values |
| `extra_fields` | none | project-specific front matter fields (`type`: string, int, bool, list, date; optional `values`, `required`) |
| `max_doc_lines` | `400` | lint warns (does not fail) above this many lines |
| `toc_depth` | `2` | for docs with `toc: true`: 2 = `##` only, 3 adds `###` |
| `inline_table_max_rows` | `8` | larger markdown tables must come from a CSV (0 = every table) |
| `exclude` | `AGENTS.md`, `CLAUDE.md`, `_*`, `.*`, `node_modules` | file and folder name patterns the docs tools skip |

### Health check (what the doctor looks at)

It prints OK / WARN / FAIL per item with the command that fixes it, and exits 1 on any FAIL (`--strict` also fails on warnings). It checks that the tools and `uv` are reachable, no `CLAUDE.md` exists above the project (see below), the project is a git repo with the current pre-commit hook (git does not copy hooks when you clone, so a fresh clone needs `sync_rules.py`), the `AGENTS.md` block and config files match the template, `.docs.yaml` is valid, there are no uncommitted files, a `restricted` project has no remotes, lint is clean (plus orphan, size and placeholder warnings), and nothing is overdue for re-verification. Good first step after cloning or moving a project, and a good weekly agent task.

The pre-commit hook fails closed: if a project cannot find `../_tools` or `uv`, its commits are blocked. `DOCS_SKIP_HOOK=1 git commit ...` bypasses it once; use it only deliberately.

### Instruction files: Codex and Claude Code

- Each project has an `AGENTS.md` (your project-specific rules plus the shared managed block) and a `CLAUDE.md` containing only `@AGENTS.md`. Codex reads `AGENTS.md`; Claude Code reads `CLAUDE.md`, which pulls `AGENTS.md` in.
- The Folderwise root has an `AGENTS.md` for maintaining the tools, and deliberately **no `CLAUDE.md`**. Claude Code loads `CLAUDE.md` files from the working directory and every directory above it, so a root one would load into every project session and trigger the "imports files outside the current working directory" approval prompt. With none at the root, a project session loads only its own rules, and a session at the root reads the root `AGENTS.md` natively (Claude Code v2.1.277 or later).
- Do not create `CLAUDE.md`, `CLAUDE.local.md` or `.claude/CLAUDE.md` at the root or above it. `docs_doctor.py` warns and `selftest.py` fails if one appears. Your personal `~/.claude/CLAUDE.md` is unaffected.
- Claude Code's `/config` setting **Project instructions** should stay at its default; `claude-md-and-agents-md` would load the root `AGENTS.md` into project sessions again.

### Claude Code settings in each project (`.claude/settings.json`)

`new_project.py` creates `.claude/settings.json` from the template, `sync_rules.py` merges template changes into existing projects (template values win; keys and rules only the project has are kept), and `.claude/settings.local.json` (your personal overrides) is git-ignored.

| Setting | Value | Why |
|---|---|---|
| `permissions.defaultMode` | `acceptEdits` | file edits and common filesystem commands run without prompting |
| `permissions.allow` | `uv run ../_tools/*`, `git add *`, `git commit *` | the doc workflow (stamp, lint, commit) never prompts |
| `permissions.ask` | `git push *`, `mv *`, `git mv *` | pushing needs a decision; moves of docs should go through `docs_mv.py` |
| `model` | `sonnet` | default to the Sonnet alias (currently Sonnet 5.5); switch for one session with `/model` |
| `effortLevel` | `low` | default reasoning effort: faster and cheaper for routine doc edits. `/effort high` (or `--effort`) overrides it for the session; the project default returns next session. To change it for good, set `effortLevel` in `.claude/settings.local.json` (git-ignored). Do not use the `CLAUDE_CODE_EFFORT_LEVEL` env var: it outranks `/effort` and locks the level |
| `autoMemoryEnabled` | `false` | `AGENTS.md` and the docs are the single source of truth; unversioned per-machine memory can contradict them and is loaded every session |
| `attribution` | commit and PR `""` | no extra `Co-Authored-By` trailer; commits already carry `Agent:` and `Model:` trailers |

**Skipping permission prompts entirely:** Claude Code ignores `bypassPermissions` and `auto` as `defaultMode` in a *project's* settings files (since Aug 2026), so a project cannot enable it for itself. Options: start a session with `claude --permission-mode bypassPermissions`, or set it in your user-level `~/.claude/settings.json` (applies to every project on this machine). No deny rules are shipped; any you add under `permissions.deny` still apply in bypass mode, but prefix rules do not match variants such as `git -C . push`.

### Generated tables from CSV

Tables of records (inventories, ledgers, lots, hosts) live in `data/*.csv` and are embedded in docs as generated blocks:

```markdown
<!-- table:start src=data/hosts.csv cols=name,ip sort=name -->
<!-- table:end -->
```

- Options after `src=`: `cols=a,b`, `where=col=value`, `sort=col,-col2`, plus the opt-in money options below.
- Never edit inside a block. Edit the CSV, then run `render_tables.py` (see "Edit a table that comes from a CSV"), which re-renders and stamps the affected docs. `docs_lint.py` fails if a block is stale.
- Markdown tables longer than `inline_table_max_rows` (default 8) fail lint; move them to a CSV. The Change Log table is exempt.
- Computed columns (totals, gains) come from a project script under `scripts/` that writes derived CSVs, never from hand calculation.
- Moving a CSV with `docs_mv.py` updates the `src=` paths.

#### Money columns (opt-in display)

Keep ledger values as plain decimals in the CSV (`21000`, `3500.50`; no `$`, no thousands separators). A table directive can ask for currency-aware display of chosen columns:

```markdown
<!-- table:start src=data/accounts.csv cols=id,balance,currency,rate money=balance -->
<!-- table:end -->
```

- `money=col1,col2` turns formatting on for exactly those columns. Without it, output is identical to before; every other column is shown verbatim. Unknown column names are an error.
- Format: USD as `$21,000.00` (negatives `-$1,234.50`); any other currency as `1,234,567.50 EUR` (thousands separators, two decimals, ISO code after the amount). Rounding is half-up to two places, display only; the CSV keeps the exact value.
- Currency comes from the row's `currency` column (`currency_col=name` picks another column). A blank cell there falls back to `currency=XXX` when given.
- Tables with no currency column must set `currency=XXX` (3-letter ISO code), or the block fails to render. `currency=` and `currency_col=` do nothing without `money=`.
- Only a plain decimal (`-?digits[.digits]`) is formatted. Blank, `unknown`, `n/a`, already-formatted (`$5`, `1,000`), percentages, and values whose row currency is missing (with no `currency=`) or not a 3-letter code stay unchanged.
- Never list rates, quantities, dates, IDs, account numbers or percentages in `money=`; nothing is inferred from column names or values.
- `where=` and `sort=` use the raw CSV values, so ordering and filtering do not change when `money=` is added.

### Links between docs

Refer to other docs with relative markdown links so a click in VS Code (Cmd+click) opens them: `[RSU grants](../rsu/grants.md#vest-events)`.

- Path is relative to the file containing the link, with forward slashes, the `.md` extension and exact letter case. `#anchor` is the heading in lowercase with hyphens.
- No absolute paths, `file://` URLs or links that leave the project repo (name other projects in plain text).
- `docs_lint.py` (also run by the pre-commit hook) fails on broken links and warns when prose names an existing doc without linking it.
- To move or rename a doc or folder, or rename a heading, use `docs_mv.py` instead of `mv` (see "Move or rename a doc"): it rewrites the links (and `#anchors`) that point to it, stamps the touched docs and lints.
- It lists plain-text mentions and scripts/CSVs that still name the old path (`NOTE` lines); fix those by hand.

### Optional table of contents

Off by default: VS Code's Outline panel (Explorer sidebar, or `Cmd+Shift+O`) already lists a doc's headings. For a long doc you can opt in per file (see "Add or remove a table of contents on one doc").

- The setting is `toc: true` in the doc's front matter. It adds a `## Contents` list between `<!-- toc:start -->` and `<!-- toc:end -->`, before the first `##` section.
- Never edit the list by hand. Every stamp regenerates it, and `docs_lint.py` fails if it is stale (for example after renaming a heading), so re-stamp the doc after changing headings.
- Depth comes from `toc_depth` in the project's `.docs.yaml`: 2 (default) lists `##` headings, 3 also lists `###`.

### Human-readable extras

- **Byline:** a generated `> Status · Updated (date and who)` line sits under each doc's title (`byline: true` in `.docs.yaml`, the template default). The VS Code preview hides front matter, so this is where you see status and last update. Verification, review dates and sensitivity stay in the front matter (use `docs_index.py` or `docs_stale.py` for those). Never edit it; stamping regenerates it and lint fails if it is stale.
- **README index:** `## Contents` in each project README is generated between `<!-- index:start -->` and `<!-- index:end -->` from every doc's title, optional front matter `summary`, type and status. Refresh with `docs_index.py --write`; lint fails if stale and warns about docs nothing links to.
- **Skeletons:** `docs_new.py` starts a doc from `_tools/skeletons/<type>.md` (override per project with `_skeletons/<type>.md`) as `draft`; lint warns about leftover ``TODO: fill in`` in non-draft docs.
- **VS Code:** each project ships `.vscode/settings.json` (hides front matter in the preview, validates Markdown links, offers to update links when you move files in the Explorer, wraps lines), `.vscode/extensions.json` (recommended extensions) and `.markdownlint.json`.


## Framework versus knowledge

The root `.gitignore` ignores every root entry unless explicitly allowed. The public roots are `_tools/`, `_template/`, `docs/` (framework guides), and the named root files. A new topic folder is ignored automatically, including its independent Git repository. Do not place personal knowledge inside an allowed framework root.

`_tools/framework_guard.py` validates the entire staged framework index. The framework pre-commit and pre-push hooks run it when `core.hooksPath` is configured as shown above. Git ignore rules and local hooks prevent routine mistakes; they can be bypassed deliberately and are not an access-control boundary. Never store credentials in knowledge documents.


## Optional Obsidian and iCloud bridge

A fresh Folderwise installation creates no Obsidian vault and leaves bridge sync off. Run `icloud_bridge.py setup` to initialize a local parent vault and a separate iCloud vault with reviewed defaults, enroll existing unconfigured projects, set the default for future `new_project.py` projects, perform the first sync and enable the Mac schedule. The default interval is five minutes. See [the full setup, defaults, uninstall and recovery guide](obsidian.md).

```sh
uv run _tools/icloud_bridge.py setup --source ~/folderwise --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise" --dry-run
uv run _tools/icloud_bridge.py setup --source ~/folderwise --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise"
uv run _tools/icloud_bridge.py configure --mode lean --interval-minutes 5
uv run _tools/icloud_bridge.py plan            # also previews pending phone edits
uv run _tools/icloud_bridge.py sync
uv run _tools/icloud_bridge.py configure --text-edits on --edit-settle-seconds 120   # opt-in phone note edits (see folderwise-ibridgeedit)
uv run _tools/icloud_bridge.py resolve         # list vault files with pending phone edits
uv run _tools/icloud_bridge.py resolve "_Folderwise Tasks/alpha.md"  # save its phone text, restore the Mac version
uv run _tools/icloud_bridge.py status
uv run _tools/icloud_bridge.py doctor
uv run _tools/icloud_bridge.py logs
uv run _tools/icloud_bridge.py notify-test
uv run _tools/icloud_bridge.py notify-test --setup-message  # replay setup text with configured interval
uv run _tools/icloud_bridge.py vault-init
uv run _tools/icloud_bridge.py schedule-prepare
uv run _tools/icloud_bridge.py schedule-disable
uv run _tools/new_project.py --name offline-notes --description "Local-only notes" --icloud-disabled
```

The `.docs.yaml` setting `folderwise-ibridgesync` is a positive boolean: true enables participation; false or a missing key disables it. Before setup, new projects omit the key and remain disabled. After setup, a persistent private root profile makes new projects write `folderwise-ibridgesync: true`, including when created by another process; `--icloud-disabled` writes false. Setup enrolls existing projects with no setting, preserving explicit false opt-outs and true opt-ins. It commits each enrollment in an isolated clone after hooks pass. Existing project source changes must be committed before enrollment. The enable/disable helpers change a single project's setting without changing the default for future projects.

Reviewed JSON/CSS defaults ship under `_tools/obsidian_defaults/`. Setup writes missing files into both root `.obsidian/` directories, preserving existing settings. It includes core navigation, appearance, graph, property types, a small CSS snippet, plugin IDs and compatible Tasks/Dataview settings. Install community-plugin code through Obsidian; workspace layouts, plugin binaries, private data and live `.obsidian/` directories are not published. `vault-init` can fill missing defaults again. Use `--no-schedule` with setup for a foreground-only or non-Mac installation.

Uninstall resets the future-project default, disables the scheduled bridge, and removes only unchanged setup-owned setting files. Customized settings, plugin code, project documents, explicit project flags and recovery state remain intact. The checkout helper supports removal together with optional framework files:

```sh
uv run _tools/icloud_bridge.py uninstall
python3 _tools/framework_checkout.py --minimal --omit README.md --remove-obsidian
```

The `.docs.yaml` setting `folderwise-ibridgeedit` is a list of project-relative path patterns (`*` within a folder, `**` across folders; default none) naming the copied `.md` notes that may accept phone text edits, and it only takes effect when the bridge's `text_edits` switch is on. A quiet period (`edit_settle_seconds`), protected front matter and generated blocks, size and change limits, fast-forward-only application and Mac-conflict pausing apply; see [Edit notes from iPhone](obsidian.md#edit-notes-from-iphone-opt-in). Recent imports in the status report also show an *Edited* count.

The `.docs.yaml` setting `folderwise-ibridgerename` is a boolean that defaults to false. When true, the project's generated task view also accepts task title edits from the phone (Markdown tasks and adapter tasks that advertise `editable: ["title"]`); see [Rename tasks from iPhone](obsidian.md#rename-tasks-from-iphone-opt-in) for the validation rules, commit provenance and conflict handling. A non-boolean value is rejected. A rejected edit to a generated view is saved privately on the Mac under the bridge state's `rejected/` folder (30 days), the view is restored, and the status report lists it; bridge state also keeps a small `ledger.json` of recent imports and rejections and records a `schema` version. The status report additionally lists recent imports and iCloud conflict copies. Brief iCloud file locks are retried on the next run instead of alerting.

The bridge also generates `Tasks.md` and `_Folderwise Tasks/<project-folder-name>.md` in the iCloud vault: one combined task view per enabled project, refreshed after imports on each sync. These are interactive views; Mac project files and adapter-managed records remain authoritative. Checkbox toggles are supported everywhere; title edits only for projects with `folderwise-ibridgerename: true`. See [generated task folder ownership, naming, and lifecycle](obsidian.md#generated-task-folder-and-naming).

Bridge-local JSON configuration is separate from `.docs.yaml`: `version` is 1; `enabled` records installed integration state; `source` and `vault` are separate absolute directories; `mode` is full/lean; `interval_minutes` defaults to 5; `text_edits` (boolean, default false) and `edit_settle_seconds` (default 120) control phone note edits; `notifications` is errors (default), imports (errors plus a counts-only note when phone edits are applied) or off; `max_image_bytes` and `max_images_total_bytes` are null for unlimited (zero means zero bytes). `adapters` maps project names to local argv arrays implementing list/apply/validate. `launchagents_dir` is an optional override for isolated scheduling tests. Configure limits with `--max-image-bytes` and `--max-images-total-bytes`, clear both with `--unlimited-images`, and inspect omissions/estimated export size in root-vault `_folderwise-sync-status.md`. These are file-size estimates, not actual iCloud account usage or billing.

The scheduled entry point is named `folderwise-ibridgesync`, so macOS Login Items identifies the Folderwise helper instead of `uv`. Normal macOS background-item notifications and controls remain enabled. `schedule-prepare` writes the private executable and a reviewable `launchagent-preview.plist` without registering a job; `schedule-enable` does that automatically. Uninstall removes the unchanged generated entry point but preserves customizations. Setup, issue, and test notifications use a locally compiled Folderwise iBridge app with the Folderwise logo; macOS’s own background-activity notice retains its System Settings icon. A successful notification request does not prove a desktop banner appeared: macOS can silently route it to Notification Center while Focus or shared-display suppression is active. The test command prints the relevant settings path without changing system preferences. See the Obsidian guide for visibility troubleshooting, attribution and file-access considerations.
