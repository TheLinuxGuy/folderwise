# Folderwise 0.2.0 real-iPhone acceptance: results and reproduction guide

This page is the public record of the real-iPhone acceptance run for the [iCloud bridge](obsidian.md) in Folderwise 0.2.0, written so a future tester or agent can rebuild the fictional fixtures and repeat the whole suite after a refactor. [Testing the iCloud bridge](ibridge-testing.md) holds the checklist and the self-test traceability table; this page holds what was actually run on a phone, case by case. Start with the [Quick Start](obsidian.md#quick-start) if you only want to try the bridge.

**Result: 88 rows = 85 PASS (3 of them Mac-only) + 3 BLOCKED, 0 failed.** See the [summary](#summary) and the [blocked rows](#blocked-rows-and-how-to-complete-them).

All data is fictional. The raw evidence (screenshots, logs, state snapshots, per-run commit hashes) stays private and is not published, so rows record outcomes rather than evidence files.

## Environment tested

| Item | Version |
| --- | --- |
| iPhone | iPhone 18 Pro, iOS 27.0.1, driven through iPhone Mirroring |
| Mac | macOS 27.0.1 (one Mac, one user, the real `org.folderwise.ibridge` LaunchAgent) |
| Obsidian (iOS) | 1.14.5 |
| Obsidian Tasks | 8.6.0 (the early bulk batches ran on 7.21.0 before an owner-approved upgrade; rows that need a status control, automatic dates or the Dataview format were run on 8.6.0) |
| Dataview | 0.5.68 installed; no row exercises Dataview's own query engine, only the Tasks plugin's Dataview *format* |
| Framework | `2e1f7af` (the 0.2.0 source commit). Earlier rows ran on earlier revisions of PRs [#17](https://github.com/TheLinuxGuy/folderwise/pull/17) and [#19](https://github.com/TheLinuxGuy/folderwise/pull/19); the tools and template of the revision used for the final rows are identical to `2e1f7af` |
| Layout | A pull-only framework checkout as the source parent, a separate scratch iCloud vault, default schedule (5 minutes), default quiet period (120 seconds) restored for the final rows |

Anything not in this table was not validated. In particular: **Android and Windows are unsupported**, and the three [BLOCKED rows](#blocked-rows-and-how-to-complete-them) (offline then reconnect, a fresh vault's Tasks plugin load on the phone, a visible notification banner) were not validated.

## Ground rules

- **Every PASS comes from the real scheduled job.** The phone edit travels over real iCloud to the Mac, and the real LaunchAgent (`org.folderwise.ibridge`) imports and commits it. A manual `sync` is never used to make a case pass.
- **Diagnostics are labelled and never produce a PASS.** Allowed: `status`, `doctor`, `plan`, `logs`, reading files and `git log`; an explicit `resolve` where the case is about `resolve`; `launchctl kickstart gui/$(id -u)/org.folderwise.ibridge` (that is the real job); `schedule-enable` after an interval change (it runs one foreground sync, so record it as diagnostic); holding the bridge lock to stage saves (see [findings](#findings-and-operational-lessons)); Mac-side fault injection for the recovery rows.
- Legend: **PASS** = done on the real iPhone and verified through the scheduled job. **PASS (Mac)** = verified with a Mac-side action only (nothing to do on the phone). **BLOCKED** = could not be done; the reason is given.
- Each case verifies the commit (`git log` subject and trailers, no task text), the source file diff, the regenerated view, the status report and an unchanged control; see the evidence list in [the checklist](ibridge-testing.md#evidence-to-keep).
- One operator, one phone, one Mac. Never use production data or a production vault, and keep the bridge's one-installation-per-macOS-user rule in mind: disable your production schedule first and restore it afterwards (see [restoration](#restoration-checklist)).

## Build the fictional fixtures

Fixture preparation may use foreground commands (`setup`, `sync`); test cases may not.

### Source parent, projects and vault

```sh
mkdir -p ~/bridge-test && cd ~/bridge-test
git clone https://github.com/TheLinuxGuy/folderwise.git source
cd source
git checkout 2e1f7af            # or the commit under test
for p in lab-notes trip-notes rich-csv; do
  uv run _tools/new_project.py --name "$p" --description "Fictional acceptance $p" \
    --sensitivity private --by human --no-prompt
done
```

The run used a [pull-only checkout](framework-checkout.md#minimal-pull-only-checkout); a plain clone works too. Use `--config ~/bridge-test/state/config.json` on every `icloud_bridge.py` command so the test bridge never touches a production configuration. The three projects:

| Project | Role | `.docs.yaml` opt-ins |
| --- | --- | --- |
| `lab-notes` | Markdown tasks, renames and copied-note edits | `folderwise-ibridgerename: true`; `folderwise-ibridgeedit: ["docs/iphone-checks.md"]` |
| `trip-notes` | CSV tasks through a boolean-only adapter | none (renames stay off) |
| `rich-csv` | CSV tasks through a rich adapter | `folderwise-ibridgerename: true` |

### A helper to create fixture documents

Fixture documents must pass project lint, so create them with `docs_new.py` and replace the skeleton body. Define this once in your shell (run from `~/bridge-test/source`); `mkdoc PROJECT PATH "Title"` reads the body from standard input:

```sh
mkdoc() {  # usage: mkdoc PROJECT DOC_PATH "Title" < body.md   (run from the framework root)
  local body; body=$(cat)
  ( cd "$1" \
    && uv run ../_tools/docs_new.py "$2" --type plan --title "$3" --about "Fictional acceptance fixtures" --by human >/dev/null \
    && BODY="$body" python3 - "$2" <<'PY'
import os, sys
path = sys.argv[1]
text = open(path).read()
start, end = text.index('## Goal'), text.index('## Change Log')
text = text[:start] + os.environ['BODY'].rstrip() + '\n\n' + text[end:]
text = text.replace('status: draft', 'status: active').replace('**Status:** draft', '**Status:** active')
open(path, 'w').write(text)
PY
    uv run ../_tools/docs_stamp.py "$2" --by human --summary "Add fixtures" >/dev/null \
    && uv run ../_tools/docs_index.py --write --by human --summary "Index fixtures" >/dev/null )
}
```

### Markdown project (`lab-notes`)

The main fixture. Every `AT-` identifier is one case; the starting state matters (for example AT-B02 starts completed and AT-S01 starts in progress).

````sh
mkdoc lab-notes docs/acceptance-020.md "Acceptance 0.2.0 Markdown fixtures" <<'EOF'
## Basic and metadata

- [ ] AT-B01 complete me on the phone
- [x] AT-B02 reopen me on the phone ✅ 2026-10-26
- [ ] AT-B03 add due and start dates on the phone
- [ ] AT-B04 add scheduled and priority on the phone
- [ ] AT-B05 has existing metadata 🛫 2026-11-20 📅 2026-12-01 ⏫ #lab/tag
- [ ] AT-B06 unicode café 日本語 🎉 #lab/ünï [ext link](https://example.com/at) 🆔 atb06
- [ ] AT-B07 block id task ^atb07blk
- [ ] AT-B08 dependency target 🆔 atb08
- [ ] AT-B09 depends on target ⛔ atb08
- [ ] AT-B10 edit wording only 📅 2026-12-05 🔼 #keep

## Statuses

- [/] AT-S01 in progress task
- [-] AT-S02 cancelled task
- [ ] AT-S03 open task to complete
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
  continuation text under the plain list item
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
EOF
````

Three smaller notes cover copied-note edits, duplicate titles and the Dataview format. `docs/iphone-checks.md` is the only note matched by `folderwise-ibridgeedit`.

```sh
mkdoc lab-notes docs/iphone-checks.md "iPhone note-edit checks" <<'EOF'
## Tasks

- [ ] NC01 copied parent
- [ ] NC03 copied second parent
  - [ ] NC02 copied child to delete
- [ ] NC04 copied recurrence 🔁 every day 📅 2026-11-02
EOF

mkdoc lab-notes docs/duplicate-checks.md "Duplicate title checks" <<'EOF'
## Tasks

- [ ] AT-DUP identical description 🆔 dupa
- [ ] AT-DUP identical description 🆔 dupb
EOF

mkdoc lab-notes docs/dataview-checks.md "Dataview format checks" <<'EOF'
## Tasks

- [ ] DV01 add dates and high priority
- [ ] DV02 highest priority
- [ ] DV03 medium priority
- [ ] DV04 low priority
- [ ] DV05 lowest priority
- [ ] DV06 remove dates [start:: 2026-10-28] [scheduled:: 2026-10-29] [due:: 2026-10-31]
- [ ] DV07 remove priority [priority:: high]
EOF

cat >> lab-notes/.docs.yaml <<'EOF'

folderwise-ibridgerename: true
folderwise-ibridgeedit:
  - "docs/iphone-checks.md"
EOF
git -C lab-notes add -A && git -C lab-notes commit -m "Add acceptance fixtures"
```

The `AT-DUP` pair is the duplicate-title fixture (identical descriptions with distinct `🆔`). The dependency fixtures are AT-B08 (target, `🆔 atb08`), AT-B09 (existing `⛔ atb08`) and AT-B10 (the task that gets a dependency added on the phone). Keep each family in one Tasks format: a Dataview-format edit on a line that carries an emoji `🆔` produces two `id` fields and is rejected (see [findings](#findings-and-operational-lessons)).

### Boolean CSV adapter project (`trip-notes`)

Start from the [example adapter](examples/ibridge_csv_adapter.py) and make it boolean-only by removing its `editable=['title']` entry, so the generated view says that only checkbox toggles are imported.

```sh
mkdir -p trip-notes/scripts trip-notes/data
cp docs/examples/ibridge_csv_adapter.py trip-notes/scripts/ibridge_adapter.py   # from a full checkout
sed -i '' "s/ editable=\['title'\],//" trip-notes/scripts/ibridge_adapter.py     # macOS sed; boolean-only
cat > trip-notes/data/tasks.csv <<'EOF'
task_id,title,status,detail_path
AT-CSV-01,AT-CSV-01 complete me on the phone,open,docs/actions.md
AT-CSV-02,AT-CSV-02 reopen me on the phone,complete,docs/actions.md
AT-CSV-03,AT-CSV-03 add a due date on the phone,open,docs/actions.md
AT-CSV-04,AT-CSV-04 rename me on the phone,open,docs/actions.md
AT-CSV-05,AT-CSV-05 set an in-progress status on the phone,open,docs/actions.md
AT-CSV-06,AT-CSV-06 add a recurrence on the phone,open,docs/actions.md
AT-CSV-07,AT-CSV-07 concurrent CSV edit,open,docs/actions.md
EOF
mkdoc trip-notes docs/actions.md "Trip actions" <<'EOF'
## Open actions

<!-- tasks:start -->
<!-- tasks:end -->
EOF
```

The adapter validates that the generated block equals what it would render, so fill the block once and stamp the note (the adapter's `apply` does this after every import):

```sh
( cd trip-notes && python3 - <<'PY'
import csv, re
from pathlib import Path
rows = list(csv.DictReader(open('data/tasks.csv')))
block = '<!-- tasks:start -->\n' + ''.join('- [ ] ' + r['title'] + '\n' for r in rows if r['status'] != 'complete') + '<!-- tasks:end -->'
p = Path('docs/actions.md')
p.write_text(re.sub(r'<!-- tasks:start -->.*?<!-- tasks:end -->', lambda _: block, p.read_text(), flags=re.S))
PY
uv run ../_tools/docs_stamp.py docs/actions.md --by human --summary "Render task block" )
git -C trip-notes add -A && git -C trip-notes commit -m "Add CSV fixtures"
```

### Rich CSV adapter project (`rich-csv`)

A rich adapter advertises field, status, recurrence and delete capabilities and implements `list`, `apply`, `render` and `validate`. This fictional one stores the whole Tasks line in `title` and reuses the bridge's own field parser (`fields.py` is a copy of `_tools/ibridge_tasks.py`). It is for acceptance runs only.

```sh
mkdir -p rich-csv/scripts rich-csv/data
cp _tools/ibridge_tasks.py rich-csv/scripts/fields.py
cat > rich-csv/scripts/ibridge_adapter.py <<'EOF'
"""Fictional rich CSV adapter for acceptance runs; never use real records."""
import csv, json, re, sys
from pathlib import Path
import fields as fmt  # a copy of _tools/ibridge_tasks.py

SOURCE, VIEW = Path('data/tasks.csv'), Path('docs/tasks.md')
CAPS = ['title', 'due', 'start', 'scheduled', 'created', 'done', 'cancelled', 'priority', 'repeat', 'id',
        'dependsOn', 'onCompletion', 'block', 'status', 'recurrence', 'delete']


def load():
    with SOURCE.open(newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r['status'] = r['status'] or ' '  # an empty CSV cell means open
    return rows


def checked(status):
    return status in ('x', 'X', 'D')  # D is a custom DONE status


def block(rows):
    lines = ''.join(f"- [{r['status']}] {r['title']}\n" for r in rows if not checked(r['status']))
    return '<!-- tasks:start -->\n' + lines + '<!-- tasks:end -->'


def render(rows):
    text, n = re.subn(r'<!-- tasks:start -->.*?<!-- tasks:end -->', lambda _: block(rows), VIEW.read_text(), flags=re.S)
    assert n == 1
    VIEW.write_text(text)


rows, op = load(), sys.argv[1]
assert len({r['task_id'] for r in rows}) == len(rows)
if op == 'list':
    print(json.dumps([dict(id=r['task_id'], title=r['title'], status=r['status'], checked=checked(r['status']),
                           path=str(VIEW), editable=CAPS) for r in rows]))
elif op == 'apply':
    for c in json.load(sys.stdin):
        r = next(r for r in rows if r['task_id'] == c['id'])
        if 'expected_title' in c:
            assert r['title'] == c['expected_title'], 'concurrent title'
        if 'expected_fields' in c:
            assert fmt.fields(r['title'])['fields'] == c['expected_fields'], 'concurrent fields'
        if 'title' in c:
            r['title'] = c['title']
        if 'status' in c:
            r['status'] = c['status']
        elif checked(r['status']) != c['checked']:
            r['status'] = 'x' if c['checked'] else ' '
        for successor in c.get('recurrence', []):  # exactly one stable-ID row per open occurrence
            if not checked(successor['status']):
                n = 1
                while any(x['task_id'] == f"{r['task_id']}-next-{n}" for x in rows):
                    n += 1
                rows.append(dict(task_id=f"{r['task_id']}-next-{n}", title=successor['title'], status=successor['status']))
        if c.get('delete'):
            rows.remove(r)
    with SOURCE.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['task_id', 'title', 'status'])
        w.writeheader()
        w.writerows(rows)
    render(rows)
elif op == 'render':
    render(rows)
elif op == 'validate':
    assert block(rows) in VIEW.read_text(), 'stale generated block'
else:
    raise ValueError(op)
EOF
printf 'task_id,title,status\nrc01,RC01 rich field and status,\nrc02,RC02 rich recurrence 🔁 every day 📅 2026-11-02,\nrc03,RC03 delete on completion 🏁 delete,\nrc04,RC04 untouched control,\n' > rich-csv/data/tasks.csv
mkdoc rich-csv docs/tasks.md "Rich CSV tasks" <<'EOF'
## Open actions

<!-- tasks:start -->
<!-- tasks:end -->
EOF
( cd rich-csv && python3 scripts/ibridge_adapter.py render \
  && uv run ../_tools/docs_stamp.py docs/tasks.md --by human --summary "Render task block" )
printf '\nfolderwise-ibridgerename: true\n' >> rich-csv/.docs.yaml
git -C rich-csv add -A && git -C rich-csv commit -m "Add rich CSV fixtures"
```

### Setup, adapters and the first export

```sh
CFG=~/bridge-test/state/config.json
VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise-Acceptance"
uv run _tools/icloud_bridge.py --config "$CFG" setup --source ~/bridge-test/source --vault "$VAULT"   # registers the schedule
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/bridge-test/state/config.json')
c = json.load(open(p))
c['adapters'] = {'trip-notes': ['python3', 'scripts/ibridge_adapter.py'],
                 'rich-csv': ['python3', 'scripts/ibridge_adapter.py']}
json.dump(c, open(p, 'w'), indent=2)
PY
uv run _tools/icloud_bridge.py --config "$CFG" sync      # fixture preparation, not a test
uv run _tools/icloud_bridge.py --config "$CFG" doctor    # expect OK and the installed Tasks version
```

Setup enrolls the three projects (their `.docs.yaml` changes are committed first, so run it only on a clean tree) and registers the default 5-minute schedule. Fenced examples (`AT-F01`, `AT-F02`) must not appear in `_Folderwise Tasks/lab-notes.md`.

### Tasks dashboards and plugin settings

On the iPhone, open the scratch vault in Obsidian, install **Tasks** (8.6.0) and optionally Dataview from the community-plugin browser (Restricted mode off), and reload. Create one dashboard note per fixture family in the vault root; the bridge leaves unknown vault files alone. Each note holds one query, restricted to the generated views so copied notes do not duplicate results:

````markdown
```tasks
path includes _Folderwise Tasks
description regex matches /AT-B/
sort by description
```
````

Use these regular expressions, one note each: `AT-B`, `AT-S`, `AT-H`, `AT-R|AT-D0`, `AT-C0`, `AT-X`, `AT-CSV`, `RC0`, `DV0`, `NC0`, `AT-DUP`. The generated root `Tasks.md` already shows every open and completed task across projects.

Baseline Tasks settings (what the vault seeds): task format `emoji`, empty global filter, automatic created/done/cancelled dates **off**, default recurrence row order. Rows below say when to change a setting. Change settings only in the phone's native Tasks settings and use the plugin's own **Reload** banner; editing the settings JSON on the Mac does not reliably update the phone's live values, and toggling the plugin off and on can leave it unable to load until Obsidian is restarted. Snapshot the original settings first (see [restoration](#restoration-checklist)).

## Test matrix

Phone actions use the Tasks edit dialog or checkbox on a dashboard unless the row says the view file. "Expected" is what the bridge must do at its scheduled run; "Result" is the observed outcome. A rejected save is always one unit: nothing is committed, the phone text is saved under the bridge state's `rejected/` folder, the view is restored from Mac data, the reason is listed in `_folderwise-sync-status.md` under **Phone edits not applied**, and one notification is requested. After every rejection, reopen the view on the phone and confirm it is restored before editing again.

### 1. Markdown and CSV tasks

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 1.1 | Markdown complete (AT-B01) | Tick it on the dashboard | Source `[x]`, one commit "Update task completion from Obsidian", `Bridge-Ops: toggle=1` | PASS |
| 1.2 | Markdown reopen (AT-B02, and AT-B01 later) | Untick in the dashboard | Source `[ ]`, done date removed | PASS |
| 1.3 | CSV complete (AT-CSV-01, -05, -07) | Tick in the CSV dashboard | Row `complete`; regenerated backlog drops it; toggle commit | PASS |
| 1.4 | CSV reopen (AT-CSV-02) | Untick in the dashboard | Row `open` again and back in the generated backlog | PASS |
| 1.5 | Markdown rename where enabled (AT-B02, AT-B05) | Edit the description in the Tasks dialog (prefix `RN-`) | One rename commit; metadata, tag and link preserved | PASS: one commit `toggle=1 rename=2` |
| 1.6 | Rename plus toggle in one save | Rename and tick in one save | One commit with both | PASS: same commit as 1.5 |
| 1.7 | CSV rename with renames off (AT-CSV-04) | Edit the title in the view file | Rejected, "title edits are off for this project" | PASS |
| 1.8 | Rename by editing view text with a tapped caret (Tasks 8.6.0) | Source mode, tap inside the title (RC01), verify the caret, type a few characters | Rename imported; source link and due/done fields preserved | PASS: `toggle=0 rename=1` |
| 1.9 | Unsafe rename shapes ([checklist step 5.4](ibridge-testing.md#5-opt-in-rename-test)) | Five separate saves in a dashboard: (a) rename AT-B06, whose title contains a link; (b) swap AT-B07 and AT-B08 titles; (c) give AT-B09 AT-B08's title; (d) title starting `=`; (e) title over 200 characters | Each rejected as a unit, head unchanged, view restored | PASS: all five rejected by the scheduled job with one notification each. Reasons: (a) "cannot be renamed ... contains links or images"; (b) and (c) the generic "title already used by another task; reordering or duplicating..." message; (d) "cannot ... start with = + - @"; (e) "title must be 1-200 characters" |

### 2. Dates and priorities

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 2.1 | Add due date (AT-B03, emoji format) | Dialog, Due | `📅` field imported after the source link | PASS |
| 2.2 | Add start date (AT-B03) | Dialog, Start | `🛫` imported | PASS |
| 2.3 | Add scheduled date (AT-B04) | Dialog, Scheduled | `⏳` imported | PASS |
| 2.4 | Remove a date (AT-B05 start) | Dialog, clear Start | `🛫` removed; due, priority and tag preserved | PASS |
| 2.5 | Priorities | Highest on B03, High on B04, change B05 High to Medium, Low on B06, Lowest on B07, remove on B10 | Each emoji appended, changed or removed; other fields and `^block-id` order kept | PASS: all five priorities and a removal |
| 2.6 | Automatic created/done/cancelled dates (Tasks 8.6.0, settings on) | Complete, cancel and reopen Markdown tasks; complete a recurring row; use the custom DONE status | `✅` on completion, `❌` on cancellation, reopening clears the stale done date, `➕` on the recurring successor | PASS: each subcase imported by a scheduled run |
| 2.7 | Dataview format (Tasks format set to Dataview; DV01-DV07) | Repeat 2.1-2.5 with `[due:: ]`, `[start:: ]`, `[scheduled:: ]`, `[priority:: ]` | All dates, priorities and removals preserved in Dataview serialization | PASS: one clean batch imported. A first save made from a stale phone copy was rejected as a unit, then a clean retry passed |
| 2.8 | Mac-side `doctor` shows Tasks version, format and status types | None | Version, format and warnings reported without changing settings | PASS (Mac): at the time `doctor` warned that installed Tasks 7.21.0 differed from the 8.6.0 fixtures |

### 3. Statuses

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 3.1 | In progress to done (AT-S01 `[/]`) | Tap the checkbox | `[x]` | PASS |
| 3.2 | Cancelled to open (AT-S02 `[-]`) | Tap the checkbox | `[ ]` | PASS |
| 3.3 | Open to done (AT-S03) | Tap the checkbox | `[x]` | PASS |
| 3.4 | Cancel from the phone (Tasks 8.6.0 dialog, AT-B04) | Dialog, Status, Cancelled | `[-]` plus the automatic `❌` date | PASS (the 7.21 dialog has no status control) |
| 3.5 | Unknown status character rejected (AT-S04 to `[!]`) | Change only the status character in source mode | Rejected ("unknown task status", configure its type); view restored; head unchanged | PASS |
| 3.6 | Custom DONE status (RC01) | Configure custom `D` (type DONE) in Tasks settings, Reload, then select it in the dialog | Imported with the exact `D` character and an automatic done date | PASS |
| 3.7 | CSV adapter status rejected (AT-CSV-05 to in progress) | Dialog, Status, In progress, on the boolean adapter's task | Rejected as a custom-status edit; CSV and head unchanged | PASS |

### 4. Hierarchy

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 4.1 | Child-only toggles at depth 2 and 3 (H01a, H02a1) | Tick the child only | Only that line changes | PASS |
| 4.2 | Tab-indented, numbered (H03a), child of a plain list item (H04) | Tick each | Only those lines change; indentation kept | PASS |
| 4.3 | Quoted (H05), double-quoted (H06), callout (H07) | Tick each | Only those lines change; `>` prefixes kept | PASS |
| 4.4 | Repeated child titles (H08x, H09x) | Tick each independently | Each toggles only itself | PASS |
| 4.5 | Parent toggle independent of children (H08) | Tick the parent | Children unchanged | PASS |
| 4.6 | Fenced examples (F01, F02) are not tasks | None | Absent from the generated view | PASS (Mac) |
| 4.7 | Continuation text under a plain list item preserved | Toggle its child | No change to the continuation line | PASS (Mac): source diff shows none |
| 4.8 | Sibling reordering (swap X01 and X02) | "Move line up" in the view file so complete rows swap | Rejected as reordering; no unintended toggles; source unchanged | PASS: exact line multiset unchanged, scheduled run rejected it |
| 4.9 | Reordering duplicate-titled rows (`AT-DUP`) | "Move line up" twice | Rejected; source unchanged | PASS. The original H08x/H09x labels were not identical, so the dedicated `AT-DUP` pair was added |

### 5. IDs, dependencies, links, tags, Unicode

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 5.1 | Unicode, emoji, `#lab/ünï`, external link and `🆔` preserved (B06) | Dialog, priority Low | Priority appended; link, Unicode, tag and id preserved; `fwview-` projection prefix stripped from the id | PASS |
| 5.2 | Block ID stays last (B07) | Dialog, priority Lowest | Priority inserted before `^atb07blk` | PASS |
| 5.3 | Existing dependency and id projection (B08, B09) | None (unchanged through four imports) | `⛔ atb08` and `🆔 atb08` unchanged in source | PASS |
| 5.4 | Add a dependency (B10, "Before this" = B08, emoji format) | Dialog, dependency picker, choose the generated-view B08 | Source B10 gains `⛔ atb08`; the view shows `⛔ fwview-atb08`; no duplicate ids | PASS. The picker lists two B08 matches (generated view first, copied source second); pick the first. An earlier mixed Dataview/emoji attempt was rejected for a duplicate `id` field, which is mixed-format fixture behavior, not a defect |
| 5.5 | Unrelated Markdown and metadata untouched | None | Every source diff shows only the intended lines | PASS |
| 5.6 | Corrupted `fw:` link identity rejected (S04) | Source mode, change one hex character of the `fw:` id | Precise rejection that the source link identity changed; view restored; source unchanged | PASS: iOS also smart-quoted the opening quote, and the rejection named the identity change |

### 6. Recurrence

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 6.1 | Daily (R01) | Tick on the dashboard | Plugin writes successor and completed row; bridge imports both in one transaction | PASS |
| 6.2 | Weekly with start date (R02) | Tick | Successor with shifted start and due | PASS |
| 6.3 | Monthly (R03) | Tick | Successor one month later | PASS |
| 6.4 | When done (R04) | Tick | Successor calculated from the completion date | PASS |
| 6.5 | Undated (R05) | Tick | Open undated successor plus completed copy | PASS |
| 6.6 | Successor-first and completed-first row orders | Tick a recurring task under each Tasks "recurrence order" setting | Either order imports; exactly one successor | PASS: successor-first, then completed-first with created dates |
| 6.7 | Exactly one successor; later runs make no commits | Wait | Heads stay put | PASS: 20+ idle ticks |
| 6.8 | Replay after a published commit and lost export state | Real phone recurrence; then Mac fault injection restores the pre-commit export state and the exact phone save while the bridge lock is held | Scheduled replay keeps the commit, creates no second successor, state equals the published snapshot | PASS |
| 6.9 | Recurrence inside a copied note (opt-in) | Tick a recurring task in `docs/iphone-checks.md` (NC04) | Completed row plus exactly one open successor with a created date | PASS |
| 6.10 | CSV recurrence rejected (boolean adapter, AT-CSV-06) | Dialog, repeat "every day" plus a due date | Rejected naming the fields: "adapter does not allow these task fields: due, repeat" | PASS |

### 7. On completion

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 7.1 | `🏁 delete` removes only that line (D01) | Tick | Line removed; `delete=1`; unrelated lines kept | PASS |
| 7.2 | `🏁 keep` retains (D02) | Tick | Task toggled and kept | PASS |
| 7.3 | Recurring plus delete (D03), twice | Tick, then tick the successor | Exactly one open successor remains each time | PASS |
| 7.4 | Delete in a CSV adapter project (RC03) | Tick | Record removed from the CSV; control row untouched | PASS |

### 8. Identity preservation

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 8.1 | Plugin appends metadata after the link; identity kept | Dialog edits on B-series tasks | Link and row identity unchanged | PASS |
| 8.2 | Link removed (C05) | Delete the link in the dialog | Rejected; view restored | PASS (generic wording at the tested revision; #19 made it precise) |
| 8.3 | Text typed after the link (C04) | Type text after the link in the dialog | Rejected; view restored | PASS (the message then said "reordering, duplicating or deleting"; #19 added a precise message for text after the link) |

### 9. Generated views and copied source files

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 9.1 | Edits through dashboards and the view file | Many | Imported or rejected as designed | PASS |
| 9.2 | Quiet period at the default 120 s over two 5-minute ticks | Partial title saved, finished after a tick (see [the recipe](#default-settings-partial-title-recipe)) | WAITING twice, then one commit with the final title only | PASS: WAITING at the first two ticks, one commit at the third, partial text in no commit |
| 9.3 | Opt-in copied-note edits (`configure --text-edits on`, pattern for `docs/iphone-checks.md`) | Create child NC05; reparent NC02 under NC03 | One commit after the quiet period; protected stamp and Change Log intact | PASS |
| 9.4 | Create, delete, reparent a child, then toggle it from the dashboard | As stated | Inventory refreshes; the new child toggles | PASS: a first deletion from a stale copy was rejected safely, then retried from a fresh copy |
| 9.5 | Recurring task in a copied note | Tick NC04 | Same as 6.9 | PASS |
| 9.6 | Accidental edit to non-task text (a heading) | Type into the view's heading | Rejected; view restored | PASS |
| 9.7 | Property edit on a copied note that is not opted in | Properties editor: `status` active to draft on `docs/acceptance-020.md` | The project is **paused** ("only checkbox on/off supported"); source unchanged; phone text preserved; `resolve` restores | PASS |

### 10. Concurrency and stale data

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 10.1 | Different fields on Mac and phone merge (C01) | Phone changes the due date while a Mac commit adds a priority | Both fields kept | PASS |
| 10.2 | Same field on both sides (C02) | Phone changes the due date while a Mac commit changes it differently | Mac value kept; notice "due also changed on the Mac"; phone text saved; view restored | PASS: staged with the bridge lock held so only C02 changed on the phone |
| 10.3 | Source changes while phone edits wait (C03) | Mac commit adds a due date during the quiet period | Mac edit kept | PASS (limited: the Mac edit was to a different task from the phone edits) |
| 10.4 | CSV toggle with a Mac rename of the same row | Phone toggles; Mac renames | Row keeps the Mac title and the toggled status | PASS |
| 10.5 | Stale phone copy after a rejection re-saves rejected text | Edit again before the restored view reaches the phone | Whole save rejected again, nothing lost or committed | PASS (reproduced; see [findings](#findings-and-operational-lessons)) |
| 10.6 | Interleaved typing across a scheduler tick with default settings | As 9.2 | As 9.2 | PASS |

### 11. Offline, iCloud delay, idempotence

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 11.1 | Offline edit, then reconnect (AT-C04) | Edit with Wi-Fi and cellular off, then reconnect | One import after reconnect, no duplicates | BLOCKED: iPhone Mirroring cannot toggle airplane mode or Wi-Fi |
| 11.2 | iCloud delivery delay observed | None | Recorded per step | PASS (observed): phone to Mac 5 to 30 s; Mac to phone up to about 3 min |
| 11.3 | Repeated ticks create no duplicate commits | Wait | Heads stable | PASS: 20+ ticks |
| 11.4 | A transient iCloud lock does not alert on first occurrence | Save a view while iCloud is syncing | Deferred quietly; no alert; import follows | PASS: one lock deferred, then WAITING, then the import |

### 12. Recovery

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 12.1 | Missing `state.json` rebuilt | None (Mac deletes it) | Identical state rebuilt; no commits | PASS |
| 12.2 | Missing `export.json` or stale pending state, interrupted export | None (Mac fault injection) | Scheduled run replays the interrupted bytes and removes the journal; heads unchanged | PASS |
| 12.3 | Rejected text recoverable from `state/rejected/` | None | Exact text present | PASS |
| 12.4 | `resolve` of a pending phone edit | Edit NC01 in the copied note | Diagnostic `plan`/list, then `resolve` saves the text and restores the Mac note; next scheduled run healthy | PASS |
| 12.5 | Fresh vault versus existing vault settings | Open a fresh vault with fresh defaults and approved plugin binaries; load Tasks | Tasks queries render; Tasks settings reachable | BLOCKED: the existing-vault path passed and the bridge's fresh-vault export was healthy, but on the phone the Tasks query stayed raw and its settings did not appear; the plugin load needs a physical restart or recovery |

### 13. CSV adapter capability enforcement

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 13.1 | Due date on a boolean adapter (AT-CSV-03) | Dialog, Due | Rejected by name: "adapter does not allow these task fields: due" | PASS |
| 13.2 | Recurrence plus due (AT-CSV-06) | Dialog | Rejected naming both fields | PASS |
| 13.3 | CSV integrity after the rejections | None | CSV and head unchanged | PASS |
| 13.4 | A rich adapter accepted on device (`rich-csv`) | Recurrence plus delete; completed-first with created dates; due date and custom status | Each imported by the adapter; untouched control preserved | PASS |
| 13.5 | A boolean adapter's view header says only toggles | None | Header: only checkbox toggles are imported | PASS |

### 14. Status reporting and notifications

| ID | Case | Phone action | Expected bridge result | Result |
| --- | --- | --- | --- | --- |
| 14.1 | The status report lists every rejection with file and reason | None | Entries under **Phone edits not applied** | PASS |
| 14.2 | One notification per run with an issue; none when unchanged | None | `notification_sent` true once per issue | PASS |
| 14.3 | A visible banner is captured | None | A human sees and captures the banner | BLOCKED: screen mirroring and screen capture can suppress banners; needs a human at the Mac |
| 14.4 | `notify-test` and the `imports` mode | None | A notification is requested | PASS: the real scheduled import set `notification_sent`; visibility is not claimed (see 14.3) |
| 14.5 | Recent imports counts toggles, renames, fields, recurrences and deletions | None | Counts match each commit's `Bridge-Ops` trailer | PASS |

## Blocked rows and how to complete them

Do not mark these PASS from indirect evidence.

- **11.1 Offline then reconnect.** Needs a person at the phone. Put it in airplane mode, tick AT-C04's checkbox in a dashboard, then confirm the Mac copy is unchanged and let at least two ticks pass with no import. Reconnect, wait for iCloud delivery, and expect one import at the next tick with one commit and no duplicate on later ticks. Variant: change the same field on the Mac meanwhile and expect the conflict behavior of row 10.2.
- **12.5 Fresh vault.** Create a new scratch vault with `setup` so Folderwise seeds its reviewed defaults, install Tasks and Dataview through Obsidian's community-plugin browser on the phone (no copied binaries), turn Restricted mode off and restart Obsidian. PASS needs a Tasks query to render as a task list (not raw code) and the Tasks settings to be reachable on the phone, followed by a normal tick and edit. The Mac export for a fresh vault was already healthy; the open question is the plugin load on the phone.
- **14.3 Visible banner.** End screen sharing, mirroring and capture sessions, check Focus and **System Settings → Notifications → Folderwise iBridge**, then trigger one real notification (for example a rejected generated-view edit, or `notify-test --setup-message`) and capture the banner on the desktop. Never change global privacy settings silently; see [the notification caveat](ibridge-testing.md#notification-caveat).

## Findings and operational lessons

Four defects found during the run were fixed before release (the boolean-adapter view header, `plan` counting field edits as renames, the first-occurrence iCloud lock alert, and imprecise source-link rejection messages). These lessons remain operational.

- **A stale phone copy can re-save rejected text.** After a rejection the Mac restores the view, but Obsidian on the phone may keep, and later re-save, the rejected text until the file is reopened, especially from a Tasks dashboard or edit dialog. The whole save is then rejected again, with any unrelated valid edit in it. Wait for the restored view to appear on the phone (reopen it) before the next edit. Dashboards can also re-save a pre-import recurrence id.
- **Dependency picker double match.** The Tasks dependency picker lists the target twice, the generated-view row first and the copied source row second. Choose the first.
- **Mixed Dataview and emoji duplicate id rejection.** With the Tasks format set to Dataview, adding `[id:: x]` to a line that already carries an emoji `🆔` (projected as `fwview-...`) gives two `id` fields, and the bridge rejects the save as a duplicate field. Keep each fixture family in one format and change the Tasks format before editing it.
- **Whole-file quiet-period rule.** A generated view's text must be unchanged for 120 seconds across two runs. The unit is the whole file, so any change anywhere in the view restarts the wait for every pending edit in it, and an accidental extra change (such as a mis-tapped "postpone" button) rides along in the same commit.
- **Bridge-lock staging for multi-save cases.** To stage a Mac commit and a phone edit before a tick, or several saves to be handled in one run, hold the bridge lock as a labelled diagnostic and release it afterwards:

  ```sh
  python3 -c "import fcntl,time; f=open('$HOME/bridge-test/state/lock','a'); fcntl.flock(f, fcntl.LOCK_EX); time.sleep(600)"
  ```

  While it is held the scheduled job does not run; kill the process to release it. Record that a case used it.
- **Generic message for swapped and duplicate titles.** Both report "title already used by another task; reordering or duplicating...". It is correct but not specific.
- **Mac-side settings JSON does not reach the live phone.** Editing the Tasks settings file on the Mac and reloading did not change the phone's runtime values. Use the native settings and the plugin's Reload banner, and restart Obsidian instead of toggling the plugin if it fails to load.
- **iCloud locks come in bursts** right after phone saves; the bridge defers them quietly and reports only the third consecutive failure.
- **Dashboard caches.** After a restore, the dashboards can show the rejected state until the note is reopened.
- **Rejection reasons are precise but the status report is the record.** Always read `_folderwise-sync-status.md`, not the notification, for the file, line and reason.

## iPhone Mirroring automation tips

For tests driven by an automation harness rather than a person at the phone:

- Use full-screen control with iPhone Mirroring frontmost. Keystrokes sent to a background app do not reach the phone.
- Space key presses about 0.35 s apart. Typing a whole string can silently drop characters, so send printable keys one at a time if it does, and verify the text before saving. Backspace works with full control, and Ctrl+a moves to the start of the visual line.
- The first tap on a field often only dismisses the keyboard and shifts the content by a few pixels. Verify the caret and the formatting toolbar before typing; tapping the dialog header blurs the field so that Apply is reachable.
- The phone's web content has no accessibility tree: work from screenshots and coordinates and re-screenshot after anything that can move content. Native screenshots of the mirrored phone are blocked; capture the window instead.
- Never drag; a drag can leave a text-selection popup that swallows later taps. Use large scroll amounts (small ones are often ignored). Use Cmd+f to find a task.
- To edit view text directly, switch with the command palette ("Toggle Live Preview/Source mode"); the menu route is unreliable. Caret placement in the dialog's description field is unreliable, and text typed there once landed inside the link title.
- For autocomplete lists such as the dependency picker, type a filter and press Return; taps pass through the list.
- Always capture and check the phone's state before the scheduled tick, and again after a rejection once the view has been restored.

## Default-settings partial-title recipe

This is the check behind rows 9.2 and 10.6.

1. Restore the defaults: `configure --interval-minutes 5 --edit-settle-seconds 120`, then `schedule-enable` (a labelled diagnostic foreground sync). Note the time of a scheduled run, T0.
2. Just after T0, in a dashboard dialog, save a **partial** new title (for example AT-B09 with a fragment typed into its description).
3. At the next tick (T1) expect no commit and `plan` to say `the phone text must stay unchanged for 120 seconds across two runs`.
4. After T1 and before T2, save the **final** title.
5. At T2 expect WAITING again and no commit (the new text has been seen once).
6. At T3 expect one commit containing the final title only. Verify with `git log -S"<fragment>"` that the partial text is in no commit.

Use only scheduled ticks for the result; `plan` and `status` are diagnostics.

## Restoration checklist

Do this when the run ends so the Mac and phone return to your normal state:

- [ ] Scheduler interval 5 minutes, `--edit-settle-seconds 120`, `--notifications errors`, schedule enabled (`configure ...`, then `schedule-enable`; confirm with `status` and `doctor`). Restore `--text-edits` to its pre-test value.
- [ ] Tasks settings on the phone and in the Mac copy returned to the originals you snapshotted: global filter empty, automatic created/done/cancelled dates off, task format emoji, default recurrence order, custom statuses removed. Use the native settings and Reload; never toggle the plugin.
- [ ] Test projects disabled or uninstalled (`disable`, or `uninstall`), the scratch vault removed from the phone, and your production schedule re-enabled with its own `--config`.
- [ ] Scratch state kept or deleted deliberately; `rejected/` holds 30 days of phone text.
- [ ] Notifications and global privacy settings (Focus, screen-sharing behavior) exactly as you found them.

## Summary

| Section | Rows | PASS | PASS (Mac) | BLOCKED |
| --- | ---: | ---: | ---: | ---: |
| 1. Markdown and CSV tasks | 9 | 9 | 0 | 0 |
| 2. Dates and priorities | 8 | 7 | 1 | 0 |
| 3. Statuses | 7 | 7 | 0 | 0 |
| 4. Hierarchy | 9 | 7 | 2 | 0 |
| 5. IDs, dependencies, links, tags, Unicode | 6 | 6 | 0 | 0 |
| 6. Recurrence | 10 | 10 | 0 | 0 |
| 7. On completion | 4 | 4 | 0 | 0 |
| 8. Identity preservation | 3 | 3 | 0 | 0 |
| 9. Generated views and copied files | 7 | 7 | 0 | 0 |
| 10. Concurrency and stale data | 6 | 6 | 0 | 0 |
| 11. Offline, iCloud delay, idempotence | 4 | 3 | 0 | 1 |
| 12. Recovery | 5 | 4 | 0 | 1 |
| 13. CSV adapter capability enforcement | 5 | 5 | 0 | 0 |
| 14. Status reporting and notifications | 5 | 4 | 0 | 1 |
| **Total** | **88** | **82** | **3** | **3** |

88 rows = 85 PASS (82 on the real phone through the scheduled job, 3 Mac-only) + 3 BLOCKED, 0 failed. The 85 PASS rows support the capability list in the [README](../README.md#-your-projects-on-iphone); the BLOCKED rows are not claimed anywhere.
