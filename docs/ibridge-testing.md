# Testing the iCloud bridge: acceptance checklist and test traceability

This page describes how the Obsidian/iPhone bridge (`folderwise-ibridge`, see [Use Folderwise with Obsidian, iCloud, and iPhone](obsidian.md)) is tested, in plain English. It is for contributors who change the bridge and for users who want to prove it works on their own Mac and iPhone before trusting it with real projects.

There are two layers:

- **Automated self-tests** run on any machine, with fake macOS services and no iCloud, in about a minute. They protect every rule the bridge enforces. Run them with `uv run _tools/selftest.py` (all) or `uv run _tools/selftest.py -k ibridge` (every bridge section).
- **A real-iPhone acceptance test** covers what software cannot fake: real iCloud delivery, the real macOS scheduler, whether a notification banner is visible, and how the Obsidian Tasks plugin behaves on a phone. It uses fictional data only and is run by a person.

The [traceability table](#traceability-table) links every manual scenario to the automated checks that cover it, and marks the parts only a real device can verify. CI fails when this page drifts from the self-tests (see [Keeping this page honest](#keeping-this-page-honest)).

## Self-test sections

| Section (`-k` name) | What it covers |
| --- | --- |
| `ibridge` | The core: export and dashboard, phone toggles for Markdown and CSV-backed tasks, idempotence, dirty-project and hook failures, lean mode, adapters, schedule and notification plumbing, journal recovery, status report. |
| `ibridge_rename` | Opt-in task renames from the phone: the setting, accepted renames, every rejected shape, Mac-side conflicts, copied-note edits, CSV adapters, iCloud conflict copies. |
| `ibridge_isolation` | One project's problem pausing only that project, the `plan` preview of phone edits, the `resolve` command, and notification modes. |
| `ibridge_setup` | Setup, enrollment, future-project defaults, uninstall and schedule lifecycle. |

## Real-iPhone acceptance checklist

### Ground rules

- **Fictional data only.** Use a throwaway source folder with two fictional projects: one with a handwritten Markdown checklist and one whose tasks come from a CSV through a project adapter (see the [example adapter](examples/ibridge_csv_adapter.py)). Never use a production vault. The bridge keeps each project in its own local Git repository and never pushes; keep it that way.
- **Never run a manual `sync` to pass a test.** The acceptance test proves the unattended path: iPhone edit, iCloud delivery, the Mac's scheduled LaunchAgent (`org.folderwise.ibridge`, five-minute default), local commit. Foreground commands are fine for inspecting state (`status`, `doctor`, `plan`, `logs`), not for making the sync happen. The one allowed shortcut is described in [the error test](#4-unsupported-edit-error-test).
- **One operator, one phone, one Mac.** Do not edit the same files on the Mac during a run, and do not start a second run until the first has finished.
- **Do not change global privacy settings** (notifications, screen-sharing behavior, Focus) to make a test pass. See [the notification caveat](#notification-caveat).
- **Use the tracked-files rule.** Only committed project files are exported. Commit fixtures on the Mac before expecting them on the phone.

### Evidence to keep

Keep these outside the repository (they contain your fictional fixtures and local paths, so they are not committed to Folderwise):

- **Timestamps** for each step: the moment you tapped on the phone, the moment the changed view appeared in the Mac's iCloud copy (its file modification time), the moment the scheduled job ran (`status` or `last-run.json` in the bridge state folder), and the commit time.
- **Screenshots** of the phone before and after each step. iPhone Mirroring blocks native screenshots, so use window captures. Take them before the scheduled run so they prove the state the phone was in.
- **Commit hashes** of the head of each project before and after each step (`git -C <project> log -3 --format='%h %ad %s' --date=iso`).
- **The status report** (`_folderwise-sync-status.md`) after every step that changes issues.
- **A manifest** (one JSON file) listing each capture: file name, capture time, the action it shows, commit hashes at that moment, a checksum, and notes such as pointer overlays or stale frames.
- **The final result table** (test, result, evidence) with the framework commit under test.

### 1. Preflight

1. The framework checkout under test is the commit you intend to ship; note its hash.
2. `uv run _tools/icloud_bridge.py doctor` reports no problems, the schedule is loaded, the interval is the expected five minutes, and `status` shows a recent successful run.
3. Notifications are set to `errors` (the default); run `uv run _tools/icloud_bridge.py notify-test --setup-message` once and confirm whether a banner appeared (see [the caveat](#notification-caveat)).
4. On the iPhone, open the iCloud vault in Obsidian with the **Tasks** plugin enabled. Open `Tasks.md` in reading mode and confirm both projects appear with Open and Completed sections.
5. Record the starting state: head commit and clean working tree of each project, the checksum of each authoritative file (the Markdown note, the CSV, the regenerated view), and a screenshot of the dashboard.
6. Prepare four tasks: an open Markdown task to complete, an open CSV-backed task to complete, an already-completed Markdown task to reopen, an already-completed CSV-backed task to reopen. Keep at least one untouched control task.
7. Wait until the iCloud copy on the Mac matches what the phone shows. A local file write on the Mac does not prove the phone has it.

### 2. Complete tasks from the dashboard

1. On the iPhone, in the `Tasks.md` dashboard, tap the checkbox of the open Markdown task, then of the open CSV-backed task. Note the exact time of each tap. Confirm on the phone that each task moved to Completed. Take a screenshot.
2. **Verify the taps before the scheduled run.** Mirroring can drop a click (see [findings](#findings-from-real-runs)); if a tap did not register, tap again and record the corrected time.
3. Record the time the changed `_Folderwise Tasks/<project>.md` files appear in the Mac's iCloud copy. This is the **iCloud delivery delay** (tap time to Mac mirror time).
4. Wait for the next scheduled run; do not run `sync`. Record the run time. The **job delay** is the run time minus the delivery time. It is bounded by the interval, so with five minutes it can be anything up to five minutes. Together they are the **end-to-end time**.
5. Verify, per project:
   - The **Mac mirror** (the iCloud copy of the view) now shows the task as completed, regenerated from the Mac.
   - The **authoritative file** changed: the Markdown note's checkbox is checked and its change log is stamped as written by a human; the CSV row now says done.
   - The **regenerated views** agree: the CSV-backed project's generated Markdown backlog no longer lists the completed row.
   - **Local commit provenance:** `git -C <project> log -1` shows the subject "Update task completion from Obsidian" (renames use "Update tasks from Obsidian") and the trailers `Bridge: folderwise-ibridge` and `Bridge-Ops: toggle=<n> rename=<m>`. No task text appears in the message.
   - **Return sync:** the regenerated files arrive back on the iPhone (open the source note and the CSV backlog on the phone and take screenshots).
   - **Unrelated files unchanged:** the control task, other files and the other project have the same checksums as in the preflight, apart from the files this step is meant to change.
   - The status report shows no issues, and the job's last-run record says `ok` with `notification_sent` false.
6. **No duplicate commits:** let at least two more scheduled runs pass with no phone edits. Both project heads must not move, and the status report must not churn.

### 3. Reopen tasks from the dashboard

Repeat step 2 for the Completed section: untick the completed Markdown task and the completed CSV-backed task on the phone, wait for delivery and the next scheduled run, and verify the same list. The CSV-backed row must return to the generated backlog (the adapter reopens a row that the normal backlog was hiding).

### 4. Unsupported-edit error test

Goal: prove that an edit the bridge does not support is contained, reported once, and recoverable. Use a project that has **renames switched off** (no `folderwise-ibridgerename`).

1. Back up the generated view and record its checksum and the project heads.
2. Edit the **title text** of a generated view (for example, change the heading of `_Folderwise Tasks/<project>.md`, or a task's words) in the vault copy.
3. Wait for the next scheduled run. If you need to capture the banner at a known moment, you may start the real job once with `launchctl kickstart gui/$(id -u)/org.folderwise.ibridge`. That is the real scheduled job, not a foreground `sync`; note in your report that you used it.
4. Verify:
   - The run reports the issue "only checkbox on/off changes are supported"; `ok` is false.
   - The status report has a **Phone edits not applied** entry naming the file and line.
   - The exact phone text is saved on the Mac in the bridge state's private `rejected/` folder, and the vault view is restored from Mac data.
   - **Exactly one notification** was requested (`notification_sent` is true for that run). Capture the banner if macOS shows it.
   - Project heads, source files and working trees are unchanged.
5. **Repeat run:** let (or start) another run while the problem still exists. It must not notify again, because the issue is unchanged.
6. **Recovery:** restore the exact bytes of the view (checksum equals the backup) or let the restored view stand, then run once more on the schedule. Expect `ok` true, no issues, and no leftover "Phone edits not applied" entry for the cleared problem.

### 5. Opt-in rename test

1. In the fictional project, add `folderwise-ibridgerename: true` to `.docs.yaml` and commit it. After the next scheduled run, the generated view should say that title edits are imported.
2. **Rename.** On the phone, edit one task's wording in the view file (see the [dialog warning](#findings-from-real-runs)); keep the checkbox and the trailing `([source](…))` link. Wait for the scheduled run. Expect a commit "Update tasks from Obsidian" with `Bridge-Ops: toggle=0 rename=1`, a source note whose line carries the new wording and is stamped `human` with the change-log row "Rename tasks via Obsidian iCloud bridge", a regenerated view with the new title, a **Recent imports** entry with the commit, a clean working tree, and no titles anywhere in the commit message. Under the default `errors` notification mode, no notification.
3. **Rename plus toggle.** In a single save, rename a task and tick it. Expect one commit with `Bridge-Ops: toggle=1 rename=1`.
4. **Rejected cases.** Make each of the following edits in turn (restore the view before the next). For each, expect that **the whole save of the view is rejected as one unit**: the phone text is saved on the Mac, the view is restored, the reason is listed in the status report, one notification is sent, and the project head does not move.
   - A due date or typed text appended **after** the source link (what the Tasks edit dialog does).
   - The source link removed from the line.
   - Two titles swapped.
   - A title changed to another task's title (a duplicate).
   - A link or image placed inside a title, and a rename of a task whose existing title already contains a link.
   - A title that starts with `=`, contains comment markers, is over 200 characters, or contains text-direction control characters.
   - A rename of a task that shares its title with another task.
5. **Mac-side race (optional on a device):** rename the same task on the Mac and on the phone before the run. Expect a reported conflict, not an overwrite.

### 6. Paused-project test

1. Leave an uncommitted file in project A. Tick a task in A's view and a task in project B's view on the phone.
2. At the next scheduled run, B's toggle must be imported and committed and B's files exported, while A is **paused**: its phone toggle stays pending, A's head is unchanged, and the status report says `Paused projects: <A>`.
3. One "needs attention" notification is sent; later runs with the same problem do not repeat it.
4. Remove the stray file. At the next run A resumes and its pending toggle is imported.

### 7. `plan` preview and `resolve`

1. With a phone edit pending (not yet picked up by a run), `uv run _tools/icloud_bridge.py plan` shows `PHONE EDIT <project>: would toggle <n> and rename <m> task(s)` for a valid edit or `PHONE EDIT REJECTED` with the reason for an unsupported one, and changes nothing (compare checksums before and after).
2. Run `uv run _tools/icloud_bridge.py resolve` to list vault files that differ from the last export. Run `resolve "<path>"` on an unwanted edit: the phone text is saved under `rejected/` and the exported version is restored. A path with no pending edit is refused. The paused project resumes on the next scheduled run.

### 8. Notification modes

1. With `errors` (default), a routine successful import is silent and an error sends one alert.
2. Switch with `uv run _tools/icloud_bridge.py configure --notifications imports`; the next run that applies phone edits sends one note with counts only (for example "Folderwise applied 2 phone change(s) in 1 project(s)") and no task or document text. If the same run needs attention, only the attention alert is sent.
3. Switch to `off`; nothing is sent, including the enable announcement. Restore your intended mode afterwards.

### Notification caveat

A successful notification request is **not** proof that a banner was visible. Screen capture, iPhone Mirroring, Screen Sharing, a computer-use assistant, or a Focus mode can make macOS keep the notification in Notification Center without showing it. The bridge reports "Notification requested", not "shown". For acceptance:

- Treat `notification_sent` and the log as proof of the request, and a screenshot of the actual banner as proof of visibility.
- If no banner appears, end the capture or sharing session, or check Focus and the app's notification permissions, then try again. See [the notification visibility guide](obsidian.md#a-notification-appears-only-in-notification-center).
- **Never silently change a global privacy setting** (for example allowing notifications while the display is shared or mirrored). Doing so can expose other apps' private messages. If you choose it for a test, do it consciously, say so in the report, and restore it.

## Findings from real runs

These came from a real fictional-data acceptance run on a Mac and iPhone. Tests must keep guarding them.

1. **The Tasks edit dialog keeps the source link but can add text after it.** When a task is edited from `Tasks.md`, the plugin preserves the `([source](…))` link but can append a due date, and any text typed in the dialog may end up after the link. A generated line must keep the link as its last part, so such an edit is rejected as a whole and the phone text is saved on the Mac. Rename from the view file with the plugin's suggestion popup dismissed, or make the change on the Mac. A rejected save is one unit: a toggle in the same save is not applied either, and the view returns to the Mac's state.
2. **Brief iCloud file locks look like errors but are not.** While iCloud is syncing a file, the bridge can hit transient operating-system errors such as `[Errno 11] Resource deadlock avoided`. They must be retried on the next run without alerting. Only the third consecutive failure is reported. A scheduled job that alerts on a one-off lock trains users to ignore alerts.
3. **iCloud delivery was fast; the job interval dominated.** In the observed runs, iCloud delivered a phone edit to the Mac within 6 to about 30 seconds, and the scheduled job added roughly one and a half to two minutes; with a five-minute interval it can add up to five. Do not fail a run for being slow inside the interval plus a generous delivery margin, and do not use a manual `sync` to hide a slow delivery.
4. **Mirroring is an unreliable input device.** Clicks were sometimes dropped (a tap that did not register) and a click once landed on the heading, so a stray character was typed into the title line. The stray text was removed before the scheduled run and no commit resulted. Always verify the phone's state (screenshot) before the five-minute run; if a bad edit does reach the run, it is rejected and the view restored.
5. **The error banner needs a human.** Window captures work; native screenshots of the mirrored phone do not, and the mirrored frame can be stale after an error test. Record these limitations in the result table rather than skipping the evidence.

## Traceability table

Each row is a scenario from the checklist. **Automated checks** are exact labels from `_tools/selftest.py` (sections `ibridge`, `ibridge_rename`, `ibridge_isolation`, `ibridge_setup`). **Manual only** means no software check can prove it; the third column says what a real device must still confirm. **Gap** means the behavior is automatable but has no self-test yet; it is a to-do, not an accepted state.

| ID | Scenario | Automated checks | Needs a real device or person |
| --- | --- | --- | --- |
| P1 | Preflight: schedule loaded, interval right, setup complete | `schedule registers isolated LaunchAgent and announces configured interval`<br>`doctor checks loaded schedule without parsing launchctl output`<br>`doctor diagnoses interval that needs schedule reload`<br>`doctor diagnoses stale scheduled runs`<br>`setup creates parent/iCloud vaults and enrolls existing projects` | Real launchd job, Login Items entry, iCloud vault opening on the phone, Tasks plugin enabled |
| P2 | Dashboard lists open and completed tasks of both projects | `bridge exports dashboard and completed tasks`<br>`generated checkbox appears once in dashboard projection` | Tasks plugin rendering of the queries on iPhone |
| T1 | Complete a Markdown task from the dashboard | `phone dashboard toggle stamps and commits authoritative Markdown` | The tap and the mirror delivery |
| T2 | Complete a CSV-backed task from the dashboard | `CSV task toggle updates authoritative row and regenerates Markdown`<br>`fictional CSV source committed with real hook` | The tap and the mirror delivery |
| T3 | Reopen a completed Markdown task | `completed dashboard task can reopen` | The tap and the mirror delivery |
| T4 | Reopen a completed CSV-backed task (row returns to the backlog) | `completed CSV row can reopen after disappearing from source view` | The tap and the mirror delivery |
| T5 | Commit provenance: `Bridge: folderwise-ibridge`, `Bridge-Ops` trailer, no task text | `phone dashboard toggle stamps and commits authoritative Markdown`<br>`rename commit has provenance, counts and no titles` | None beyond reading the real commit |
| T6 | Regenerated views written back so the phone receives the return sync | `bridge exports dashboard and completed tasks`<br>`CSV task toggle updates authoritative row and regenerates Markdown` | Real iCloud delivery of the returned files to the phone (Mac side is automated) |
| T7 | Unrelated files and other projects unchanged | `unknown phone files remain intact`<br>`bridge excludes Git and instructions` | Checksum comparison of the real files |
| T8 | Unchanged runs make no duplicate commit | `unchanged sync is idempotent`<br>`already-applied phone toggle does not create another commit`<br>`unchanged sync after a rename creates no commit`<br>`unchanged report does not churn every scheduled run` | Several real scheduled ticks |
| T9 | A checkbox toggled in a copied source note also imports | `checkbox edits inside mirrored source notes also import` | None |
| T10 | iCloud delivery delay versus job interval | Manual only | Real iCloud and real launchd timing, recorded per step |
| T11 | A dirty project or failed hook leaves the phone toggle pending, then imports once repaired | `dirty project blocks import and preserves pending phone toggle`<br>`hook rejection cannot partially change Mac records`<br>`retry after hook repair imports pending change` | None |
| U1 | Title edit with renames off is rejected, saved on the Mac, view restored | `unsupported phone edits to a generated view are saved outside iCloud and the view is restored`<br>`title edits stay off until the project opts in`<br>`new phone lines are saved and the view restored instead of imported` | The real phone edit |
| U2 | Status report entry for the rejected edit | `rejected phone edit is named in the status report` | None |
| U3 | One notification; a repeat run does not notify again | `a restored view is not reported again`<br>`an unchanged pause is not announced again` | The real notification request (see N3) |
| U4 | Recovery after restoring the view | `restored views match the Mac again`<br>`restoring the view recovers from an adapter failure`<br>`restoring the copied note recovers from the freeze` | The real restore of the bytes |
| U5 | The error banner is visible on the Mac | Manual only | Real macOS banner, screenshot, Focus and sharing state |
| U6 | A stray edit typed into the wrong line (mirroring slip) is contained | `unsupported phone edits to a generated view are saved outside iCloud and the view is restored`<br>`whitespace-only title edits are ignored` | The mirroring slip itself cannot be reproduced on demand |
| U7 | iCloud conflict copies are reported, not imported | `conflict copies are reported and not imported`<br>`the conflict-copy section disappears once the copy is gone` | Real iCloud creating the copy |
| R1 | Renames are off by default and the setting is validated | `views of projects without the setting say only toggles are imported`<br>`a non-boolean rename setting is rejected`<br>`project doctor recognizes folderwise-ibridgerename`<br>`opted-in views explain title edits` | None |
| R2 | Accepted rename: source note, human stamp, commit, view, status | `phone rename with a toggle edits the source note once`<br>`rename commit has provenance, counts and no titles`<br>`rename stamps the note as human with a rename summary`<br>`regenerated view carries the new title`<br>`status report lists the import with its commit` | The real phone edit |
| R3 | Rename plus toggle combine into one commit | `phone rename with a toggle edits the source note once`<br>`a view rename and a toggle in the copied note combine into one change` | The real phone edit |
| R4 | Due date or text appended after the source link, or a removed link, is rejected | `a due date appended by the Tasks edit dialog is rejected`<br>`removing the source link is rejected` | What the Tasks edit dialog really appends on iPhone (see R12) |
| R5 | Swapped titles, duplicate titles and renames of duplicate tasks are rejected | `swapped titles are not read as two renames`<br>`renaming to an existing title is rejected`<br>`duplicate tasks cannot be renamed` | None |
| R6 | Links in titles are rejected | `a title cannot embed links`<br>`a task whose title has links cannot be renamed from the view` | None |
| R7 | Marker, formula, over-long and direction-character titles are rejected | `a title cannot hide generated-block markers`<br>`a title cannot start a spreadsheet formula`<br>`an over-long title is rejected`<br>`invisible direction characters are rejected` | None |
| R8 | A rejected save is whole: text saved, view restored, status entry | `rejected text is saved on the Mac`<br>`restored views match the Mac again`<br>`saved phone text is forgotten after 30 days` | None |
| R9 | Mac-side changes win over a pending rename | `a rename pending during a Mac rename is a reported conflict`<br>`a pending copied-note toggle for a Mac-renamed task freezes with the project named` | None |
| R10 | Title edits in a copied source note freeze with the file and line named | `mirrored note title edits freeze with the file and line named`<br>`restoring the note recovers` | None |
| R11 | CSV adapter renames, and adapters that cannot rename | `adapter task rename updates the CSV and regenerated note`<br>`an adapter rename pending during a Mac rename is a reported conflict`<br>`an adapter that does not allow title edits is restored`<br>`an adapter that ignores the title aborts without a commit`<br>`an adapter editable field must be a list` | None |
| R12 | Tasks edit dialog behavior and its suggestion popup on iPhone | Manual only | Real Obsidian Tasks plugin on iPhone |
| R13 | A toggle keeps CRLF line endings in the source note | `a toggle keeps CRLF line endings in the source note` | None |
| Z1 | A dirty project is paused while others import and export | `a dirty project is paused and reported while other projects import`<br>`other projects still export while one is paused`<br>`the paused project keeps its pending phone edit and previous export`<br>`the status report names the paused project` | None |
| Z2 | The attention alert fires once per distinct problem | `a paused project sends the attention alert, not an import count`<br>`an unchanged pause is not announced again` | Real banner (see N3) |
| Z3 | A paused project resumes once fixed | `the paused project resumes once fixed` | None |
| Z4 | A bad edit to a copied note pauses only its project | `a bad copied-note edit pauses its project and names the file` | None |
| Z5 | Adapter or inventory failures pause only their project | `an adapter failure pauses only that project`<br>`the adapter project imports after the failure clears`<br>`an uninventoriable project is paused without losing its export`<br>`the project resumes after the inventory problem is fixed` | None |
| Q1 | `plan` previews pending and rejected phone edits and changes nothing | `plan previews a pending toggle`<br>`plan previews a rejected edit without applying it`<br>`plan changes nothing`<br>`the planned edits apply on the next sync`<br>`plan describes cleanup without removing files` | None |
| Q2 | `resolve` lists, saves and restores an unwanted edit | `resolve lists files with pending phone edits`<br>`resolve refuses a file without a pending edit`<br>`resolve saves the phone text and restores the Mac version`<br>`the project resumes after resolve`<br>`resolve reports when nothing is pending` | None |
| N1 | Notification modes: errors, imports (counts only), off | `setup accepts the imports notification mode`<br>`unknown notification modes are rejected`<br>`errors mode does not announce routine imports`<br>`imports notify with counts only` | None |
| N2 | `notify-test` and the setup replay request a notification honestly | `notification app bundles the Folderwise identity and icon`<br>`notification app launches and clears the message handoff`<br>`notification test distinguishes a request from visible delivery`<br>`one-command setup notification replay uses the configured interval`<br>`notification failure is reported by the explicit test command` | Whether a banner is actually seen (see N3) |
| N3 | A notification banner is visible on the Mac desktop | Manual only | Real macOS presentation; screen capture, mirroring and Focus can suppress it; never change global privacy settings silently |
| I1 | A transient iCloud lock such as `[Errno 11] Resource deadlock avoided` is retried quietly and only the third consecutive failure alerts | Gap | Not needed once a self-test injects the error; real iCloud rarely reproduces it on demand |
| I2 | Mirroring drops a click or types into the wrong line; the operator verifies the phone before the run | Manual only | Operator discipline; the bridge's reaction to a bad edit is covered by U1 and U6 |

## Keeping this page honest

`uv run .github/scripts/test_public_docs.py` (a required CI check) reads this page and `_tools/selftest.py` and fails when:

- this page is missing, or the traceability table is missing or has no scenarios;
- a check label cited in the table's **Automated checks** column does not exist verbatim in `_tools/selftest.py` (rename or remove a self-test and CI stays red until this page is updated);
- a `-k` section name beginning with `ibridge` in `_tools/selftest.py` is not mentioned here in backticks;
- a scenario row has neither a cited check nor an explicit **Manual only** or **Gap** marker.

Rows marked **Gap** are printed as warnings by the check; close one by adding a self-test and citing it. When you add a bridge feature, add a self-test, add a scenario row (or extend one), and update the manual checklist if a real device is needed to prove it.
