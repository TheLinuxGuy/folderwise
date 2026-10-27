# Folderwise 0.2.0 real-iPhone acceptance record

This page is the public, reproducible record of the real-iPhone acceptance run for **Folderwise 0.2.0**. It has two jobs:

- **Evidence.** What was tested on a real iPhone, how, and what happened, so you can judge what 0.2.0 does and does not claim.
- **A runbook.** Everything needed to rebuild the fictional fixtures and repeat the 88-row matrix after a refactor, by a person or by an agent driving iPhone Mirroring.

It extends the [acceptance checklist and traceability table](ibridge-testing.md) (which explains the method and the automated self-tests) and the [Obsidian, iCloud and iPhone guide](obsidian.md) (which explains the behavior under test). All data is fictional. Commit hashes, local paths, account names and machine names from the original run are deliberately omitted; the run's raw evidence stays with its tester, outside this repository.

## Result at a glance

**88 rows: 85 PASS (3 of them verified on the Mac only) and 3 BLOCKED by external physical limits. 0 failed, 0 pending.**

| Section | Area | PASS | Mac-only | Blocked |
| --- | --- | ---: | ---: | ---: |
| 1 | Markdown and CSV tasks | 9 | 0 | 0 |
| 2 | Dates and priorities | 7 | 1 | 0 |
| 3 | Statuses | 7 | 0 | 0 |
| 4 | Hierarchy | 7 | 2 | 0 |
| 5 | IDs, dependencies, links, tags, Unicode, preservation | 6 | 0 | 0 |
| 6 | Recurrence | 10 | 0 | 0 |
| 7 | On completion | 4 | 0 | 0 |
| 8 | Identity preservation | 3 | 0 | 0 |
| 9 | Generated views and copied source files | 7 | 0 | 0 |
| 10 | Concurrency and stale data | 6 | 0 | 0 |
| 11 | Offline, iCloud delay, idempotence | 3 | 0 | 1 |
| 12 | Recovery | 4 | 0 | 1 |
| 13 | CSV adapter capability enforcement | 5 | 0 | 0 |
| 14 | Status reporting and notifications | 4 | 0 | 1 |
| | **Total** | **82** | **3** | **3** |

The 82 + 3 = 85 PASS rows include two rows that are honest about their evidence: 10.5 passes because the stale-copy behavior was **reproduced** (it is a documented operational limit, not something the bridge fixes) and 11.2 is a measured **observation** of iCloud delivery times rather than a pass/fail test.

The three BLOCKED rows are not framework defects. They need a physical action or a human that iPhone Mirroring cannot provide. See [Blocked rows and how to complete them](#blocked-rows-and-how-to-complete-them).

## How to use this record

1. Read [Rules for every run](#rules-for-every-run) and [Findings and operational lessons](#findings-and-operational-lessons) first. Most lost time in the original run came from those.
2. [Build the fixtures](#build-the-fictional-fixtures) once; keep them in three disposable fictional projects and one disposable vault.
3. Work through the [test matrix](#test-matrix). The rows are **not** in a required order; several need staged preconditions (a Mac commit while the phone edit waits, a lock held while two saves are staged). Group them by fixture to save effort.
4. After **each** row, write the result to disk (outside this repository) before moving on: row ID, result, scheduled-run time, and the project head before and after. An interrupted run can then be resumed by another person or agent.
5. Finish with the [restoration checklist](#restoration-checklist).

## Environment tested

| Item | Value |
| --- | --- |
| Phone | iPhone 18 Pro, iOS 27.0.1, driven through **iPhone Mirroring** (the Mac's mirroring window). Native screenshots of a mirrored phone are blocked, so evidence is Mac window captures and file contents. |
| Mac | macOS 27.0.1, one user logged in, one bridge installation |
| Obsidian | 1.14.5 on iOS |
| Tasks plugin | 8.6.0 for the later rows (upgraded from 7.21.0 with the owner's approval, official release files verified against published hashes); the earliest rows ran on 7.21.0 |
| Dataview plugin | 0.5.68 |
| Framework | The 0.2.0 source commit `2e1f7af` on `main`. Its `_tools/` and `_template/` are identical to the PR #17 head (`d384906`) and PR #19 (`b0d0602`) trees. The run started on an earlier candidate of the same pull request (`1976149`) and took over at `f9426e2`. |
| Framework checkout | Pull-only checkout (pushes disabled); the test projects were separate local repositories |
| Vault | A separate iCloud vault used only for this test, plus a second fresh vault for row 12.5 |
| Scheduler | The real macOS LaunchAgent `org.folderwise.ibridge` |

**Row revision markers.** Each observed result below carries a marker where it matters. No marker means the row was verified on the 0.2.0 code (`b0d0602`, `d384906` or `2e1f7af`). **(A)** means it ran on the first candidate `1976149` with Tasks 7.21.0, **(B)** on `f9426e2` with Tasks 8.6.0, and **(B/C)** across `f9426e2` and the later 0.2.0 code. Rows marked (A) or (B) exercise behavior that later revisions kept or extended, but they were not literally repeated on `2e1f7af`. To claim every row for a new revision, re-run the whole matrix on that one revision with Tasks 8.6.0.

Tested only on this combination. Other iOS, Obsidian or Tasks versions, Android, and any non-macOS bridge host are **not** validated. Windows is not supported.

## Rules for every run

- **Every PASS comes from the real scheduled job.** The LaunchAgent `org.folderwise.ibridge` must perform the import, rejection or export. Never run `sync` to make a result happen.
- **Diagnostics are allowed and must be labelled as such** in your notes: `status`, `doctor`, `plan`, `logs`, `notify-test`, an explicit `resolve`, reading `last-run.json` and the bridge log, and Mac-side fault injection for the recovery rows. `schedule-enable` runs a foreground sync before it registers the job, so only use it (for example to apply a new interval) when no phone edit is pending, and say so.
- **Fictional data only; one operator, one phone, one Mac.** Never use a production vault or project.
- **Never toggle the Tasks plugin off and on.** After toggling, the plugin may fail to load on the phone until Obsidian is restarted (see [findings](#findings-and-operational-lessons)). Change Tasks settings through the plugin's own settings screen and press its **Reload** banner.
- **Do not infer the phone's live Tasks settings from the Mac's `data.json`.** Editing that file on the Mac and reloading did not reliably change the values the phone used.
- **Speed settings are fine for bulk rows, defaults are required for the quiet-period rows.** The bulk of the run used a one-minute interval and a 15-second quiet period to save time. Rows 9.2 and 10.6 were run (or re-run) at the defaults: 5-minute interval, 120-second quiet period. Restore the defaults before them and at the end.
- **Verify the phone before every tick.** Mirroring drops clicks and sometimes types into the wrong line. Check the phone's text before the scheduled run, or the run may legitimately reject a stray edit.
- **Record what the Mac saw, not what the phone shows.** A checkbox on the phone proves nothing about the source note, the commit or the working tree.

For each import row, verify these on the Mac after the scheduled tick (the matrix only repeats them where a row is special):

- the project head moved by exactly one commit with subject "Update task completion from Obsidian", "Update tasks from Obsidian", "Update task fields and occurrences via Obsidian iCloud bridge" or "Update notes from Obsidian" as appropriate, and `Bridge: folderwise-ibridge` plus a `Bridge-Ops:` trailer with the expected counts, and no task text in the message;
- only the intended lines of the source note or CSV changed, the note is stamped `human` with a Change Log row, and the working tree is clean;
- the regenerated view returns to the phone;
- `status` shows `ok` and the report lists the commit under **Recent imports**;
- later ticks with no phone edit create no commit.

For each rejection row, verify instead: the phone text is saved under the bridge state's private `rejected/` folder, the view is restored from Mac data, the status report lists the file, line and reason under **Phone edits not applied**, exactly one notification was requested (`notification_sent` is true once and the same unchanged problem does not notify again), and the project head and source files are unchanged.

## Build the fictional fixtures

The matrix needs one iCloud vault, three fictional projects (a Markdown project with renames and note edits enabled, a boolean-only CSV adapter project, a rich CSV adapter project) and a handful of dashboard notes. Task IDs such as `AT-B01` map one-to-one to rows. The files below are reconstructed starting states; the dates are arbitrary, what matters is that each task starts in the state its row expects.

### Bridge and vault

Use a parent source folder outside iCloud and a separate vault under `iCloud Drive/Obsidian/`, as in [Explicit setup](obsidian.md#explicit-setup-and-reusable-vault-defaults). Use a throwaway name for the vault, for example `Folderwise-Acceptance`.

```sh
uv run _tools/icloud_bridge.py setup --source ~/fw-acceptance --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise-Acceptance" --dry-run
uv run _tools/icloud_bridge.py setup --source ~/fw-acceptance --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise-Acceptance"
uv run _tools/icloud_bridge.py configure --text-edits on --notifications errors --interval-minutes 5 --edit-settle-seconds 120
uv run _tools/icloud_bridge.py doctor
```

Then install the **Tasks** and **Dataview** community plugins on the phone through Obsidian's community-plugin browser and enable them. Open the vault on the phone and wait until the exported `Tasks.md` and the `_Folderwise Tasks/` folder arrive. The run used `new_project.py` for each project, so each has its own repository, hook and `.docs.yaml`.

To speed bulk rows you may temporarily lower the interval and the quiet period (`--interval-minutes 1 --edit-settle-seconds 15`), but restore them as the [checklist](#restoration-checklist) says.

### Project 1: `lab-notes` (Markdown, renames and note edits on)

Create it with `uv run _tools/new_project.py`, then add these keys to its `.docs.yaml` and commit:

```yaml
folderwise-ibridgesync: true
folderwise-ibridgerename: true
folderwise-ibridgeedit:
  - "docs/iphone-checks.md"
```

Create three notes with `docs_new.py` (type `plan`), paste the tasks below under a `## Tasks` heading, and commit through the project's hook.

**`docs/acceptance-020.md`**: one task per case. The fenced examples must stay inside the note exactly as shown (they prove fenced code is not exported as tasks).

````markdown
## Basic and metadata

- [ ] AT-B01 complete me on the phone
- [x] AT-B02 reopen me on the phone
- [ ] AT-B03 add due and start dates on phone
- [ ] AT-B04 add scheduled and priority on phone
- [ ] AT-B05 has existing metadata 🛫 2026-11-20 📅 2026-12-01 ⏫ #lab/tag
- [ ] AT-B06 unicode café 日本語 🎉 #lab/ünï [ext link](https://example.com/at) 🆔 atb06
- [ ] AT-B07 block id task ^atb07blk
- [ ] AT-B08 dependency target 🆔 atb08
- [ ] AT-B09 depends on target ⛔ atb08
- [ ] AT-B10 edit wording only 🔼 📅 2026-12-05 #keep

## Statuses

- [/] AT-S01 in progress task
- [-] AT-S02 cancelled task
- [ ] AT-S03 open task
- [ ] AT-S04 custom status target

## Hierarchy

- [ ] AT-H01 parent
  - [ ] AT-H01a child
    - [ ] AT-H01a1 grandchild
  - [ ] AT-H01b child
- [ ] AT-H02 tabbed parent
	- [ ] AT-H02a tab child
		- [ ] AT-H02a1 tab grandchild
1. [ ] AT-H03 numbered parent
   1. [ ] AT-H03a numbered child
- plain list parent for non-task
  - [ ] AT-H04 child of a plain item
  continuation text under the plain list
> - [ ] AT-H05 quoted task
> > - [ ] AT-H06 doubly quoted task
> [!note] callout
> - [ ] AT-H07 callout task
- [ ] AT-H08 parent A
  - [ ] AT-H08x same child title
- [ ] AT-H09 parent B
  - [ ] AT-H09x same child title
- [ ] AT-H10 first sibling
- [ ] AT-H11 second sibling

```markdown
- [ ] AT-F01 fenced example is not a task
```

> ```
> - [ ] AT-F02 quoted fenced example is not a task
> ```

## Recurrence and completion actions

- [ ] AT-R01 daily recurrence 🔁 every day 📅 2026-11-02
- [ ] AT-R02 weekly recurrence 🔁 every week 🛫 2026-10-30 📅 2026-11-03
- [ ] AT-R03 monthly recurrence 🔁 every month 📅 2026-11-04
- [ ] AT-R04 when done recurrence 🔁 every week when done 📅 2026-11-05
- [ ] AT-R05 undated recurrence 🔁 every day
- [ ] AT-D01 delete on completion 🏁 delete
- [ ] AT-D02 keep on completion 🏁 keep
- [ ] AT-D03 recurring and delete 🔁 every day 🏁 delete 📅 2026-11-07

## Concurrency and conflicts

- [ ] AT-C01 concurrent different fields 📅 2026-12-10
- [ ] AT-C02 concurrent same field 📅 2026-12-11
- [ ] AT-C03 source changes during sync
- [ ] AT-C04 offline edit task
- [ ] AT-C05 stale view task

## Reordering target

- [ ] AT-X01 reorder one
- [ ] AT-X02 reorder two
- [ ] AT-X03 reorder three
````

**`docs/duplicate-checks.md`**: true duplicate descriptions with distinct IDs (for rows 4.9 and the duplicate-rename rejections).

```markdown
- [ ] Dup parent A
  - [ ] Repeated acceptance child 🆔 dupa
- [ ] Dup parent B
  - [ ] Repeated acceptance child 🆔 dupb
- [ ] Dup untouched control
```

**`docs/dataview-checks.md`**: used with the Tasks serialization format switched to Dataview (row 2.7).

```markdown
- [ ] DV01 add dates and high priority
- [ ] DV02 highest priority
- [ ] DV03 medium priority
- [ ] DV04 low priority
- [ ] DV05 lowest priority
- [ ] DV06 remove dates  [start:: 2026-10-28]  [scheduled:: 2026-10-29]  [due:: 2026-10-31]
- [ ] DV07 remove priority  [priority:: medium]
```

**`docs/iphone-checks.md`**: the **opted-in copied note** (it matches the `folderwise-ibridgeedit` pattern above), for rows 6.9, 9.3-9.5 and 12.4. The three `acceptance-020.md`, `duplicate-checks.md` and `dataview-checks.md` notes do **not** match a pattern on purpose: row 9.7 edits a property in one of them to prove an unsupported copied-note edit pauses only its project.

```markdown
- [ ] NC01 copied parent
  - [ ] NC02 copied child to reparent
- [ ] NC03 copied second parent
- [ ] NC04 copied recurrence 🔁 every day 📅 2026-11-03
```

### Project 2: `trip-notes` (boolean-only CSV adapter)

A project whose tasks live in `data/tasks.csv` with the repository's [example adapter](examples/ibridge_csv_adapter.py) copied to `scripts/ibridge_adapter.py`, a generated block in `docs/actions.md`, and **no** `folderwise-ibridgerename` (renames off).

```csv
task_id,title,status,detail_path
AT-CSV-01,AT-CSV-01 complete me on the phone,open,docs/actions.md
AT-CSV-02,AT-CSV-02 reopen me on the phone,complete,docs/actions.md
AT-CSV-03,AT-CSV-03 add a due date on the phone,open,docs/actions.md
AT-CSV-04,AT-CSV-04 rename me on the phone,open,docs/actions.md
AT-CSV-05,AT-CSV-05 set in-progress status on the phone,open,docs/actions.md
AT-CSV-06,AT-CSV-06 complete a recurring copy,open,docs/actions.md
AT-CSV-07,AT-CSV-07 concurrent CSV edit,open,docs/actions.md
```

Register the adapter in the private bridge config (an argv array, never read from the vault), and have the adapter render the open rows into the `tasks:start`/`tasks:end` block of `docs/actions.md`:

```json
{
  "adapters": {
    "trip-notes": ["python3", "scripts/ibridge_adapter.py"]
  }
}
```

### Project 3: `rich-csv` (adapter with typed capabilities)

A second CSV project, `folderwise-ibridgerename: true`, whose adapter advertises rich capabilities per the [adapter contract](obsidian.md#authoritative-csvs-and-project-adapters): `list` returns each task with `editable` set to the fields it can store, `apply` honors `title`, `fields`, `status`, `recurrence` and `delete` requests (comparing `expected_title` and `expected_fields` first), and `validate` confirms the generated block matches the records. The run's adapter used these capabilities for every task:

```text
title due start scheduled created done cancelled priority repeat id dependsOn onCompletion block status recurrence delete
```

The self-test `ibridge_rich_adapter` in `_tools/selftest.py` contains a compact reference rich adapter to copy and adapt; the acceptance adapter was a CSV variant of it. Records:

```csv
task_id,title,status
rc01,RC01 rich field and status,
rc02,RC02 rich recurrence 🔁 every day 📅 2026-11-02,
rc03,RC03 rich delete on completion 🏁 delete,
rc04,RC04 untouched control,
```

An empty `status` means an open (space) status; `D` is the custom DONE character of row 3.6. Keep `rc04` untouched all run: it is the control that proves unrelated records are preserved.

```json
{
  "adapters": {
    "rich-csv": ["python3", "scripts/ibridge_adapter.py"]
  }
}
```

### Dashboards in the vault root

The bridge never writes or deletes unknown vault files, so dashboards are plain notes you create in the vault root (on the Mac in the iCloud vault, or on the phone). Each is a Tasks query that reads only the generated views, so a tap hits exactly one task and never a copied source note. They keep every case reachable with a few taps.

````markdown
# AT-1a

```tasks
path includes _Folderwise Tasks
description regex matches /AT-B0[1-5]/
sort by description
```
````

Create one dashboard per group by changing only the filter line. The run used these:

| Dashboard | Filter line | Used by |
| --- | --- | --- |
| `AT-1a` | `description regex matches /AT-B0[1-5]/` | 1.1-1.6, 2.1-2.4 |
| `AT-1b` | `description regex matches /AT-B(0[6-9]\|10)/` | 1.9, 2.5, 5.1-5.2, 9.2 |
| `AT-1c` | `description regex matches /AT-S0/` | section 3 |
| `AT-2b` | `description regex matches /AT-H(0[5-9]\|1[01])/` | section 4 |
| `AT-3b` | `description regex matches /AT-R05\|AT-D0/` | sections 6-7 |
| `AT-4a` | `description regex matches /AT-C0[1-5]/` | section 10 |
| `AT-4b` | `description regex matches /AT-X0/` | 4.8 |
| `AT-5csv` | `description regex matches /AT-CSV/` | 1.3, 1.4, 1.7, 3.7, section 13 |
| `AT-6-rich` | `description regex matches /RC0/` | 1.8, 6.6, 7.4, 13.4 |
| `AT-7-notes` | `description includes NC0` | 6.9, section 9 |
| `AT-8-dataview` | `description includes DV0` | 2.7 |
| `AT-9-dependency` | `description includes AT-B10` | 5.4 |
| `AT-10-conflict` | `description includes AT-C02` | 10.2 |

In a Markdown table the pipe inside a regex is escaped as `\|`; in the dashboard note itself write a plain `|`. The exported `Tasks.md` already provides the all-projects Open and Completed views, which the first rows also use.

### Tasks plugin settings used by the matrix

Change these on the phone through the Tasks settings screen, press **Reload** when it appears, and never toggle the plugin. Snapshot the original values first (`globalFilter` empty, `setCreatedDate`, `setDoneDate` and `setCancelledDate` false, emoji format, default recurrence row order).

| Setting | Value | Rows |
| --- | --- | --- |
| Automatic created, done and cancelled dates | on | 2.6, 3.4, 6.6, 6.8, 6.9 |
| Recurrence row order | next occurrence first, then completed task first | 6.1-6.8 |
| Custom status | `D`, name "Done D", type `DONE`, next status space | 3.6, 13.4 |
| Task format | Dataview, then back to emoji | 2.7 |
| Edit dialog "hide unused fields" | all fields shown (an unchecked recurrence, due or scheduled field hides that control) | all dialog rows |

## Test matrix

Legend: **PASS** = performed on the real iPhone and verified through the real scheduled job. **PASS (Mac)** = verified with a Mac-side action only. **PASS (observed)** and **PASS (reproduced)** are explained above. **BLOCKED** = could not be done, with the exact reason. "Dialog" is the Tasks plugin's edit dialog opened from a dashboard. "View" is `_Folderwise Tasks/<project>.md`. Markers (A) and (B) are explained under [Environment tested](#environment-tested).

### 1. Markdown and CSV tasks

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 1.1 | Markdown complete | Tick AT-B01 on `AT-1a` | Source line becomes `[x]`, toggle=1 commit | PASS (A) |
| 1.2 | Markdown reopen | Untick AT-B02 (and later AT-B01) | Source line becomes `[ ]`, toggle commit | PASS (A) |
| 1.3 | CSV complete | Tick AT-CSV-01, AT-CSV-05 and AT-CSV-07 on `AT-5csv` | Rows become `complete`, regenerated backlog drops them | PASS (A) |
| 1.4 | CSV reopen | Untick AT-CSV-02 | Row becomes `open`, returns to the backlog | PASS (A) |
| 1.5 | Markdown rename where enabled | In the dialog, prefix the description of AT-B02 and AT-B05 with `RN-` | Source titles renamed, rename=2, note stamped `human` | PASS (A) |
| 1.6 | Rename and toggle in one save | Rename a task and tick another in one save | One commit with toggle and rename counted together | PASS (A) |
| 1.7 | CSV rename rejected (renames off) | Type extra words into the title of AT-CSV-04 in the view | Whole save rejected: "title edits are off for this project"; CSV and head unchanged | PASS (A) |
| 1.8 | Rename by tapping a caret into the view text | Switch to source mode with the command palette, tap inside the RC01 title, verify the caret, type `TAP-` | rename=1; source link, due date and custom status preserved | PASS |
| 1.9 | Rejected rename shapes | Five separate saves in `AT-1b`, restoring the view between them: (a) rename AT-B06 (title has an external link); (b) swap the titles of AT-B07 and AT-B08; (c) rename AT-B09 to AT-B08's title; (d) start a title with `=`; (e) a title over 200 characters | Each save rejected as a unit, one notification, head unchanged, view restored. Reasons: (a) "cannot be renamed ... contains links or images"; (b) and (c) "title already used by another task; reordering or duplicating tasks is not supported"; (d) "title cannot ... start with = + - @"; (e) "title must be 1-200 characters" | PASS. The swap (b) gives the generic duplicate/reorder reason, see [findings](#findings-and-operational-lessons) |

### 2. Dates and priorities

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 2.1 | Due date | Dialog on AT-B03: due 2026-12-20 | `📅` added after the source link and imported | PASS (A) |
| 2.2 | Start date | Dialog on AT-B03: start 2026-12-01 | `🛫` imported with the due date | PASS (A) |
| 2.3 | Scheduled date | Dialog on AT-B04: scheduled 2026-12-15 | `⏳` imported | PASS (A) |
| 2.4 | Date removal | Dialog on AT-B05: clear the start date (calendar Reset, then check) | Start removed; due date and tag kept | PASS (A) |
| 2.5 | Priorities | Highest on AT-B03, High on AT-B04, Medium on AT-B05, Low on AT-B06, Lowest on AT-B07, and remove it on AT-B10 | Each emoji imported; removing it restores normal priority; block ID stays last | PASS (A) |
| 2.6 | Created, done and cancelled dates | With automatic dates on: complete, cancel and reopen Markdown tasks; complete a recurring task on the rich project | `✅`, `❌` and `➕` imported atomically; reopening clears the stale done date | PASS (B/C). Exact source and CSV snapshots compared |
| 2.7 | Dataview format | Switch Tasks to Dataview and Reload; repeat 2.1-2.5 on the `DV` tasks | `[due:: ]`, `[start:: ]`, `[scheduled:: ]`, `[priority:: ]` serialized and imported; removals retained | PASS. A first save carrying a stale line was rejected as a unit, then a clean retry imported |
| 2.8 | `plan` and `doctor` show format and statuses | Mac only | `doctor` reports the Tasks version, format, statuses and any version warning | PASS (Mac) (B) |

### 3. Statuses

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 3.1 | In progress to done | Tick AT-S01 (`[/]`) | `[/]` becomes `[x]` | PASS (A) |
| 3.2 | Cancelled to open | Tick AT-S02 (`[-]`) | `[-]` becomes `[ ]` | PASS (A) |
| 3.3 | Open to done | Tick AT-S03 | `[ ]` becomes `[x]` | PASS (A) |
| 3.4 | Cancel from the phone | Dialog on AT-B04: Status > Cancelled (Tasks 8.x; the 7.21 dialog has no status control) | `[-]` with automatic cancelled date imported | PASS (B) |
| 3.5 | Unknown status rejected | In source mode change AT-S04's status character to `!` | Rejected: unknown task status, configure its type; view restored, head unchanged | PASS |
| 3.6 | Custom DONE status | Configure custom `D`/`DONE` in Tasks; select it on RC01 in the dialog | Character `D` retained exactly, with the automatic done date | PASS |
| 3.7 | CSV adapter rejects in-progress | Set AT-CSV-05 to in progress in the dialog | Rejected: custom status edits not allowed; CSV and head unchanged | PASS (B) |

### 4. Hierarchy

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 4.1 | Child toggles at depth 2 and 3 | Tick AT-H01a and AT-H02a1 only | Only those lines change; parents and the other children do not | PASS (A) |
| 4.2 | Tab-indented, numbered and plain-list child | Tick AT-H02a1, AT-H03a and AT-H04 | Only those lines change | PASS (A) |
| 4.3 | Quoted, callout, double-quoted | Tick AT-H05, AT-H07 and AT-H06 | Only those lines change | PASS (A) |
| 4.4 | Repeated child titles | Tick AT-H08x and AT-H09x independently | Each toggles its own line | PASS (A) |
| 4.5 | Parent independent of children | Tick AT-H08, then AT-H08x | Parent toggles without touching the child | PASS (A) |
| 4.6 | Fenced examples not exported | Look for AT-F01 and AT-F02 | Absent from the exported view | PASS (Mac) |
| 4.7 | Continuation text preserved | Compare the plain-list item's continuation line after imports | Source diff shows it unchanged | PASS (Mac) |
| 4.8 | Sibling reordering rejected | In `AT-4b`'s view use "Move line up" so AT-X02 sits above AT-X01 | Rejected as reordering; the saved lines equal the exported multiset; source unchanged; view restored | PASS |
| 4.9 | Duplicate-titled rows reordered | In `duplicate-checks.md`'s view move the second repeated child above the first | Rejected as reordering; no unintended toggles | PASS. The original fixture titles were not truly identical, so the duplicate fixture above was added |

### 5. IDs, dependencies, links, tags, Unicode, preservation

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 5.1 | Unicode, emoji, tag, link, `🆔` | Change the priority of AT-B06 | Everything preserved around the new field | PASS (A) |
| 5.2 | Block ID stays last | Change the priority of AT-B07 | `^atb07blk` remains the last token | PASS (A) |
| 5.3 | Existing dependency and ID projection | Leave AT-B08 and AT-B09 alone through several imports | `⛔ atb08` and `🆔 atb08` unchanged; the view's `fwview-` prefix never reaches the source | PASS (A) |
| 5.4 | Add a dependency from the dialog | Dialog on AT-B10: "Before this" = AT-B08 | Source gains `⛔ atb08`; the regenerated view shows `⛔ fwview-atb08`; no duplicate IDs | PASS. The picker lists both the generated-view and the copied-source match |
| 5.5 | Unrelated Markdown and metadata untouched | Review every import diff | Only intended lines and the Change Log differ | PASS (A) |
| 5.6 | Corrupted `fw:` link identity | In source mode change the first character of an `fw:` identity | Rejected: source link identity changed; view restored; source unchanged | PASS. iOS also converted the opening quote to a curly quote |

### 6. Recurrence

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 6.1 | Daily | Tick AT-R01 | One completed row plus exactly one open successor, dates computed by Tasks | PASS (A) |
| 6.2 | Weekly with a start date | Tick AT-R02 | Successor with shifted start and due | PASS (A) |
| 6.3 | Monthly | Tick AT-R03 | Successor one month later | PASS (A) |
| 6.4 | When done | Tick AT-R04 | Successor one week after the completion date | PASS (A) |
| 6.5 | Undated | Tick AT-R05 | Open undated successor plus completed copy | PASS (A) |
| 6.6 | Row order | Tick a recurring task with the next-first order, then with the completed-first order and created dates on | Both serializations imported atomically with identities, rule and description validated | PASS (B/C) |
| 6.7 | Exactly one successor | Let ticks pass | No second successor, no new commit across 20+ idle ticks | PASS |
| 6.8 | Replay after a published commit and lost export state | Complete a recurring task; then on the Mac (diagnostic fault injection under the bridge lock) restore the pre-commit export state and the exact phone save | The next scheduled run keeps the published commit and exactly one open successor | PASS |
| 6.9 | Recurrence in an opted-in copied note | Tick NC04 in the copied note | Completed row plus one open successor, with the created date | PASS |
| 6.10 | CSV recurrence rejected | Add a repeat rule to a boolean CSV task | Rejected: "adapter does not allow these task fields: due, repeat" | PASS (A) |

### 7. On completion

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 7.1 | `🏁 delete` | Tick AT-D01 | Only that source line removed (delete=1) | PASS (A) |
| 7.2 | `🏁 keep` | Tick AT-D02 | Toggled done and kept | PASS (A) |
| 7.3 | Recurring and delete, twice | Tick AT-D03 twice (due moves 11-07 to 11-08) | Exactly one open successor line remains each time | PASS (A) |
| 7.4 | Delete in a rich CSV adapter | Tick RC03 | Record removed, control record unchanged | PASS |

### 8. Identity preservation

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 8.1 | Metadata appended after the link | Dialog edit on a linked task | Link and row identity kept; metadata after the link | PASS (A) |
| 8.2 | Link removed | Delete the source link of AT-C05 in the dialog | Rejected: keep the checkbox and source link | PASS (A). The message is generic, see [findings](#findings-and-operational-lessons) |
| 8.3 | Text after the link | Type text after the link of AT-C04 in the dialog | Rejected | PASS (A). The message is misleading ("reordering, duplicating or deleting"); later revisions identify text after the link |

### 9. Generated views and copied source files

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 9.1 | Edits through dashboards and the view file | Use both | Both routes import | PASS |
| 9.2 | Quiet period at the defaults over two ticks | See the [default-settings recipe](#default-settings-recipe) | Waiting on the first two ticks, one commit on the third, no intermediate text in history | PASS |
| 9.3 | Opted-in copied-note edits | `configure --text-edits on`, pattern for `docs/iphone-checks.md`; on the phone create a child NC05 and reparent NC02 under NC03 | After the quiet period one commit "Update notes from Obsidian" with stamp and log kept | PASS |
| 9.4 | Create, delete and reparent, then toggle | Create NC05, reparent NC02, toggle NC05 from the dashboard, delete NC05 from a fresh copy | Inventory refreshes after each; the new child toggles | PASS. A first deletion that also touched the protected change log was rejected safely and retried |
| 9.5 | Copied note: complete a recurring task | Same save as 6.9 | Same evidence as 6.9 | PASS |
| 9.6 | Accidental non-task edit rejected | Type into the view's heading | Rejected as a unit; view restored | PASS (A) |
| 9.7 | Property edit on a non-opted copied note pauses its project | Change `status: active` to `draft` in the Properties editor of `acceptance-020.md` | The project is **paused** with the line named; Mac source unchanged; phone text preserved; other projects keep syncing; `resolve` restores after capture | PASS |

### 10. Concurrency and stale data

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 10.1 | Different fields merge | Phone changes AT-C01's due date while a Mac commit adds a priority | Both fields present | PASS (A) |
| 10.2 | Same-field conflict | Hold the bridge lock; change AT-C02's due date on the phone; commit a different due date on the Mac; release | Notice "due also changed on the Mac"; Mac value kept; phone text saved; view restored; no silent overwrite | PASS |
| 10.3 | Source changes while phone edits wait | A Mac commit lands while phone edits are waiting | The Mac edit is retained | PASS (A). Tested on a different task than the phone's edit |
| 10.4 | CSV toggle versus Mac rename | Tick AT-CSV-07 while the Mac renames it | The toggle imports; the Mac's title stays | PASS (A) |
| 10.5 | Stale phone copy re-saves rejected text | After a rejection, edit before the restored view reaches the phone | The next tick rejects the whole save again, including unrelated valid edits | PASS (reproduced). Documented behavior |
| 10.6 | Typing across a tick at the defaults | See the [default-settings recipe](#default-settings-recipe) | No partial title committed | PASS |

### 11. Offline, iCloud delay, idempotence

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 11.1 | Offline edit, then reconnect | Edit AT-C04 in airplane mode, then reconnect | Edit arrives and imports once | BLOCKED. iPhone Mirroring cannot toggle airplane mode or Wi-Fi |
| 11.2 | iCloud delivery delays | Time each tap and the file's arrival on the Mac | Phone-to-Mac within seconds; Mac-to-phone slower | PASS (observed): phone to Mac 5 to 30 s, Mac to phone up to about 3 minutes (A) |
| 11.3 | Idempotence | Let ticks pass with no edit | No duplicate commits, heads stable | PASS (A). 20+ ticks |
| 11.4 | Transient iCloud lock | Save a task edit; a lock may occur on the next read | First lock deferred quietly, no alert, then WAITING, then the import | PASS (B). A real lock was observed after a phone save |

### 12. Recovery

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 12.1 | Missing `state.json` rebuilt | Mac: remove `state.json` from the bridge state | Next scheduled run rebuilds it identically; no commits | PASS (A) |
| 12.2 | Interrupted export | Mac fault injection: an old-bytes view, a safe journal and a stale pending key | Scheduled run replays the view, removes the journal and stale key; heads unchanged | PASS (B) |
| 12.3 | Rejected text recoverable | Open `state/rejected/` after any rejection | The exact phone text is present | PASS (A) |
| 12.4 | `resolve` of a pending edit | Make an unwanted edit to NC01; use `plan` and `resolve` | `resolve` saves the text under `rejected/` and restores the Mac version; the next scheduled run is healthy | PASS |
| 12.5 | Fresh vault versus existing vault | Open a freshly set-up vault on the phone with Tasks and Dataview present | Fresh defaults work and the upgrade path from earlier code keeps identities | BLOCKED. Existing vault passes; fresh vault: see below |

### 13. CSV adapter capability enforcement

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 13.1 | Due date rejected by name | Dialog on AT-CSV-03: due date | Rejected: "adapter does not allow these task fields: due" | PASS (A) |
| 13.2 | Recurrence and due rejected by name | Dialog on AT-CSV-06: repeat and due | Rejected: "... due, repeat" | PASS (A) |
| 13.3 | CSV integrity after rejections | Compare the CSV and head | File and head unchanged | PASS (A) |
| 13.4 | A rich adapter accepted | On `rich-csv`: recurrence plus delete (RC02, RC03), completed-first order with created date, due date plus custom `D` on RC01 | Each imported; the untouched control preserved | PASS |
| 13.5 | Boolean adapter view header | Read the exported `trip-notes` view | Header says only checkbox toggles are imported | PASS (B) |

### 14. Status reporting and notifications

| ID | Case | On the phone | Expected bridge result | Observed |
| --- | --- | --- | --- | --- |
| 14.1 | Status report lists every rejection | Read `_folderwise-sync-status.md` | File, line and reason for each | PASS (A) |
| 14.2 | One notification per issue run | Inspect `bridge.log` and `last-run.json` | One request per run with a new issue; none when unchanged | PASS (A) |
| 14.3 | Visible banner captured | Watch the Mac screen at a rejection | A visible attention banner | BLOCKED. Mirroring or capture can suppress banners; needs a human at the Mac |
| 14.4 | `notify-test` and `notifications imports` | Run `notify-test`; set `imports` mode and import | Explicit test requests a notification; an import under `imports` sets `notification_sent` with no issue | PASS. The request is logged; visibility is not claimed (see 14.3) |
| 14.5 | Recent imports table counts | Read the report after imports | Toggles, renames, fields, recurrences and deletions counted | PASS (A) |

## Blocked rows and how to complete them

These three rows were recorded and left open. None points to a framework defect. A release owner may complete them before or after tagging.

| Row | Exact reason | How to complete it |
| --- | --- | --- |
| 11.1 Offline edit then reconnect | iPhone Mirroring cannot switch airplane mode, Wi-Fi or cellular, and the owner's instruction was to record external blockers and move on | With the phone in hand: open the vault and the AT-C04 dashboard, switch on airplane mode in Control Center, edit AT-C04 (for example set a due date), confirm the Mac copy did not change over at least one scheduled tick, then switch airplane mode off. Expect delivery within the usual window, then one normal import (or a documented conflict if the Mac also changed it), no duplicate commit and no stale rejected text |
| 12.5 Fresh vault Tasks plugin load | The bridge exported a fresh vault healthily and the phone opened and trusted it, but the Tasks plugin did not load there: a Tasks query stayed raw and Settings search found no Tasks settings. The run had seeded the approved Tasks and Dataview release files directly rather than installing them through the community browser. A runtime plugin load on the phone needs an Obsidian restart or recovery, and the run was told not to toggle the plugin or ask for a restart | Set up a second empty vault with `setup` on the Mac, then on the phone install **Tasks** and **Dataview** from Obsidian's own community-plugin browser, enable them, restart Obsidian, and open `Tasks.md` in reading mode. Confirm the queries render, then run rows 1.1 and 1.3 in the fresh vault. Also confirm an existing vault still imports after the same Folderwise upgrade |
| 14.3 Visible banner | iPhone Mirroring and screen capture can make macOS keep a notification in Notification Center without a banner, and the run never changed a global privacy setting to force one. The request was proven in the run log (`notification_sent` true once per issue run) | End any capture or sharing session on the Mac, check Focus and the notification settings for **Folderwise iBridge**, then have a person watch the screen while a rejected edit (row 1.7 is quick) is processed by the scheduled job and capture the actual banner. See [the notification caveat](ibridge-testing.md#notification-caveat). An earlier owner-run test captured a real banner (see [Conflicts and recovery](obsidian.md#conflicts-and-recovery)); it was not re-captured in this run |

## Findings and operational lessons

1. **A stale phone copy re-saves rejected text.** After a rejection the Mac restores the view, but the phone may keep (and Tasks dashboards may cache) the rejected text. Edits made before the restored view arrives are saved on top of it and the Mac rejects the **whole** save again, including unrelated valid edits. Before editing again, wait until the restored view is visible on the phone: reopen the view file and the dashboards and look at the text. Dashboard caches can also re-save a recurrence ID from before an import. The rejected text is always kept under `rejected/`. (Rows 10.5 and others; also [finding 6](ibridge-testing.md#findings-from-real-runs).)
2. **The first tap in a Tasks dialog field often only blurs the keyboard.** Verify the caret and the formatting toolbar before typing. Tapping the dialog header blurs the field so the **Apply** button sits at a fixed place. One-character-at-a-time input and checking the field avoids dropped characters.
3. **The dependency picker lists two matches for a task.** "Before this" shows both the generated-view line (its description contains the source link) and the copied-source line (shown with its path in italics). Choose the highlighted generated-view match with Return. The import strips the generated `fwview-` prefix from the source.
4. **Mixed Dataview and emoji formats create duplicate `id` fields and are rejected.** A dependency added in Dataview format to a task that already carries an emoji `🆔` produced two `id` fields and was rejected as "duplicate task field: id". Keep one serialization format per fixture and switch formats only with a clean note.
5. **Whole-file quiet-period rule.** A generated view (or an opted-in note) must be byte-for-byte unchanged for `edit_settle_seconds` across **two** runs. An edit saved just after a tick is first seen as WAITING on the next tick, WAITING again if the text keeps changing, and imported only when two consecutive runs agree. With a 5-minute interval, expect an edit saved after a tick to need two further ticks. Plain checkbox and status-only toggles import without waiting.
6. **Staging multi-save cases with the bridge lock (diagnostic).** Cases that need a Mac commit and a phone save in a precise order, or two phone saves (for example swapping two titles) before a tick, can be staged by holding the bridge's lock for a few minutes so the scheduler skips. Say in your notes that you did this; release the lock when staging is done and check `status` afterwards, because a skipped tick can appear as a failed run:

   ```sh
   python3 -c "import fcntl,time; f=open('/path/to/bridge-state/lock','a'); fcntl.flock(f,fcntl.LOCK_EX); time.sleep(300)"
   ```

   Replace the path with your bridge state directory and stop the process (or let it end) to release the lock.
7. **Rejection reasons for swapped and duplicate titles are generic.** Swapped titles and duplicated titles both report "title already used by another task; reordering or duplicating tasks is not supported". Earlier revisions also gave a misleading message for text typed after the source link; later revisions identify it. The save is still rejected whole and recoverable.
8. **Do not toggle the Tasks plugin.** Disabling and re-enabling it on the phone produced "Failed to load plugin" until Obsidian was restarted. Change settings through the plugin's screen and press Reload.
9. **Tasks 7.21's dialog has no status control.** Cancelling from the phone needs Tasks 8.x (row 3.4).
10. **iPhone smart punctuation can alter text the bridge relies on.** A typed quote next to a `fw:` identity became a curly quote. Diagnostics now name a missing, malformed or changed source identity separately from text after the link; the bridge never guesses a replacement identity.
11. **Brief iCloud locks right after a phone save are normal.** The first lock must be deferred without an alert (row 11.4). The run found and fixed a case where reading a vault view file raised an alert on the first lock.
12. **Interval dominates delivery.** iCloud delivered phone edits to the Mac in seconds; the five-minute interval plus two quiet-period ticks dominated the end-to-end time.
13. **Recurring completion with `🏁 delete` keeps the next occurrence.** It counts as a field update, not a delete, in the import counts.
14. **`plan` once counted field edits as renames** in its preview text for a mixed batch while the real commit's `Bridge-Ops` counts were correct. This cosmetic issue was fixed before 0.2.0; the preview now reports `fields` separately from description renames.

## UI automation tips for iPhone Mirroring

For a person or an assistant driving the phone through the Mac:

- **Use full-screen control with iPhone Mirroring frontmost.** Background key events do not reach the phone. Typing works once the app is frontmost and has full control; opening other apps hides what you were using.
- **Key repeat drops characters.** Send keys one at a time, spaced about 0.35 seconds apart, or type short strings and check the field. Autocomplete often swallows characters: type a filter, then press Return to take the highlighted match; taps on suggestions usually do not register.
- **Edit in source mode.** In Obsidian's command palette run **Toggle Live Preview/Source mode** (the menu item did not switch reliably). Use Find to locate a task. The first body tap often only dismisses the keyboard and shifts the content a few pixels, so verify the caret.
- **Select with the keyboard.** `ctrl+a` goes to the start of a visual line; on a task line `Right` three times then `shift+Right` selects the checkbox character. Never drag: it leaves a selection popup that absorbs the next taps.
- **Scrolling needs larger amounts.** Single-digit scroll steps are often ignored; use about 20.
- **Take a screenshot after each action** where the position can change, and again before the scheduled tick. Mirroring is an unreliable input device: clicks are dropped, land on the wrong line, or arrive late.
- **Native Tasks calendar:** use **Reset** and check the field to clear a date; to apply a dialog, blur with the header then press **Apply**.

## Default-settings recipe

This is the recipe for rows 9.2 and 10.6 (quiet period at the defaults, interleaved typing across a tick). Use a view-based rename of a task that is not otherwise being touched, such as AT-B09, with renames on.

1. Restore the defaults: `configure --interval-minutes 5 --edit-settle-seconds 120`, then `schedule-enable` (with nothing pending) and note the time of the first scheduled tick **T0**.
2. Right after T0, on the phone edit the task title to a **partial** title and save, noting the time.
3. **T1** (next tick): expect WAITING, no commit. `plan` (diagnostic) shows the edit waits for the text to stay unchanged for 120 seconds across two runs.
4. After T1, type the **final** title and save.
5. **T2**: expect WAITING again because the text changed since T1. No commit.
6. **T3**: the text is unchanged across two runs: expect exactly one commit with the final title. `git log -S` for the partial text must find nothing.
7. Record the tick times, the heads at each step, and that `plan` and `status` were diagnostics.

## Restoration checklist

Do this at the end of every run and before any run that must start from defaults:

- [ ] Scheduler: `configure --interval-minutes 5 --edit-settle-seconds 120 --notifications errors`, then `schedule-enable`; `status` and `doctor` are healthy; no phone edit pending
- [ ] Text edits switch set to the value you intend (`--text-edits on` was left on for the fictional notes)
- [ ] Bridge lock released and no helper process left running
- [ ] Tasks settings on the **phone** (through the settings screen, then Reload) and the Mac `data.json`: `globalFilter` empty, `setCreatedDate`, `setDoneDate` and `setCancelledDate` false, emoji format, original recurrence row order, no custom `D` status, original edit-dialog field visibility
- [ ] The plugin itself was never toggled; Tasks and Dataview remain enabled
- [ ] Fixtures reset or archived; diagnostic files and snapshots kept outside this repository
- [ ] No production vault or project was touched
- [ ] Results table, timestamps and head hashes saved outside the repository, with the framework commit and plugin versions

## Results summary

| Total rows | PASS (phone) | PASS (Mac-only) | BLOCKED | Failed | Pending |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 88 | 82 | 3 | 3 | 0 | 0 |

PASS (phone) includes rows 10.5 (reproduced) and 11.2 (observed). Four defects confirmed during the run were fixed and merged before the final revision. Remaining notes are documented operational behavior, not blockers: a stale phone copy can re-save rejected text, and some rejection reasons are generic. No open framework bug was recorded at the end of the run.
