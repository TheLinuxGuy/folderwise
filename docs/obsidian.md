# Use Folderwise with Obsidian, iCloud, and iPhone

The optional **folderwise-ibridge** keeps your project repositories on your Mac and exports a separate Obsidian vault into iCloud. Read your documents and complete tasks from one dashboard on iPhone. One Mac imports checkbox changes, updates authoritative records, regenerates views, stamps documents, validates them, and creates local Git commits in each project.

The bridge is deliberately simple: checking means complete; unchecking means incomplete. It does **not** interpret a task, confirm evidence, or establish that the described action happened. Task changes do not advance `last_verified`. Project adapters must implement this same boolean behavior without fabricating evidence.

## Layout and prerequisites

Use one vault for all project folders. Your source parent remains outside iCloud, for example `~/folderwise/`, with independent project repositories underneath. Create a **separate** vault in Obsidian under `iCloud Drive/Obsidian/Folderwise`. Do not move the source repositories, put Git history in the vault, or synchronize that vault with a second cloud service.

Use the same Apple account on Mac and iPhone and enable iCloud Drive. Keep the Mac vault downloaded. Obsidian's [official sync guide](https://help.obsidian.md/sync-notes) covers device setup. The bridge cannot force iCloud to deliver a change immediately or prove another device received it.

The Mac needs Git, uv, the Folderwise tools, a configured Git author, and an active login session for scheduled operation. Only committed, tracked project files are eligible for export; commit new documents on Mac before expecting them on iPhone. Never commit credentials merely to make them eligible. Existing source edits can be read, but pending phone imports wait until that project's working tree and index are clean.

## Set up and preview

These commands use fictional paths. Replace the vault path with the separate vault you created in Obsidian. Run them from the framework checkout:

```sh
uv run _tools/icloud_bridge.py setup --source ~/folderwise --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise"
uv run _tools/icloud_bridge.py plan
uv run _tools/icloud_bridge.py sync
```

`setup` writes local configuration; it does not start a background job. `plan` lists selected files, estimated bytes, omissions, and proposed cleanup without writing the vault or changing tasks. `sync` performs a foreground import/export. The first successful sync creates private `.obsidian/app.json` defaults only if absent: relative Markdown links and automatic link renaming disabled. It preserves existing Obsidian settings. Actual `.obsidian/` folders never enter the public framework repository.

Configuration, baselines, temporary transaction clones, recovery journal and logs stay outside iCloud. On Mac the default location is `~/Library/Application Support/Folderwise/ibridge/`. Use `--config /absolute/path/config.json` before the command for another private installation. Keep this directory: deleting baselines removes the bridge's knowledge of pending edits and owned files. The source and vault must not contain one another; configuration/state must be outside both.

## Central task dashboard

In Obsidian on Mac and iPhone, install and enable the community **Tasks** plugin (`obsidian-tasks-plugin`). Open the exported root `Tasks.md` in reading mode. It includes open and completed tasks across all enabled projects, grouped by project. Every result links to its source document. Undated and nested tasks are included; no tag is required. Tasks inside fenced code examples, front matter and generated blocks are excluded from generic Markdown scanning.

The bridge creates `_Folderwise Tasks/<project>.md` as a task projection. This preserves completed CSV-backed tasks for reopening even if their ordinary generated backlog hides them. The dashboard queries only this folder, avoiding duplicate results from copied source notes. [Tasks queries can update their source checkboxes](https://publish.obsidian.md/tasks/Introduction); the Mac then imports the resulting file change.

Configure Tasks for simple toggles: disable automatic done/created/cancelled dates, leave its global filter empty, use ordinary space/x statuses, and avoid recurring tasks or on-completion deletion. Those features modify more than a checkbox and are outside this bridge's contract. A plugin-added date is preserved and reported as an unsupported edit, rather than silently discarded. Dataview is optional for property tables; [Dataview TASK](https://blacksmithgu.github.io/obsidian-dataview/queries/query-types/#task) can also toggle a checkbox, provided completion metadata insertion is disabled.

Handwritten task checkboxes can also be toggled in the copied source document. Generated checkboxes must be toggled through their mapped dashboard projection. Text edits, new documents, renames, deletions, custom task statuses and capture inboxes are not imported in this release. Missing exported files are restored from Mac; phone deletions never delete a source file. Unmanaged files are left alone.

## Authoritative CSVs and project adapters

A framework cannot infer arbitrary CSV schemas. Register a project-owned adapter when checkboxes come from generated records. Without one, the status report explicitly identifies generated task sources that are not yet included in the interactive dashboard. Do not claim those tasks are synchronized until their adapter is configured and tested.

A private bridge config can contain:

```json
{
  "adapters": {
    "homelab-inventory": ["python3", "scripts/ibridge_adapter.py"]
  }
}
```

This is an excerpt, not a replacement for the complete generated config. Adapter commands are argv arrays in trusted **Mac configuration**, never executable instructions read from the iCloud vault. Relative script paths resolve inside the project. Commands receive one operation argument:

| Operation | Contract |
| --- | --- |
| `list` | Print a JSON array of `{id, title, path, checked}` objects; IDs are unique and stable, `checked` is boolean, `path` is an existing project-relative document. Include completed records. |
| `apply` | Read a JSON array of `{id, checked}` requests on stdin; update authoritative sources and regenerate every affected view. Preserve unrelated records. |
| `validate` | Exit zero only when authoritative data and regenerated views agree. No task-semantic or evidence approval gate. |

[Example CSV adapter](examples/ibridge_csv_adapter.py) demonstrates an open/complete CSV and a generated backlog that hides completed tasks. Copy it into a fictional project first, adapt its schema and renderer, and commit it with the project. Its unchecked state is explicitly `open`; map richer statuses such as blocked/cancelled deliberately. An adapter task must live in a generated block rather than also appearing as a handwritten task, to avoid two independent identities for the same record.

Adapters run in a temporary local Git clone with the project's hooks, not directly against your source working tree. The bridge applies requests, stamps changed Markdown as `human`, runs adapter validation, Folderwise lint and commit hooks, then fast-forwards the clean source repository. It never pushes. Failed validation or hooks leave source records unchanged and phone toggles pending. Local transaction work needs disk space for a project checkout; Git objects are shared with the source rather than duplicating its history. Adapters must use project-relative paths and must not write outside their working directory. Custom Git hook paths are not supported; use the project's standard `.git/hooks` directory.

Handwritten tasks use file/text identity plus duplicate occurrence. Line shifts alone do not identify a task. If identical task text occurs more than once and that source file changes concurrently, the bridge stops for review rather than guessing which duplicate moved. Changed task text or a source rename can also require review.

## Project participation

All knowledge projects participate by default, including existing projects without an explicit setting. This applies regardless of `sensitivity`: enabling the bridge exports eligible restricted content too. `_template/` and framework folders are not knowledge projects.

Create an excluded project with:

```sh
uv run _tools/new_project.py --name offline-notes --description "Local-only notes" --icloud-disabled
```

Or change participation later:

```sh
uv run _tools/icloud_bridge.py disable homelab-inventory
uv run _tools/icloud_bridge.py enable homelab-inventory
```

These helpers set `icloud_disabled: true` or `false` in the project's `.docs.yaml`; commit that project setting when ready. Disabling is not a recursive vault deletion. The next sync removes only unchanged copies owned by the bridge. Pending phone edits block cleanup: re-enable, import or preserve those edits, then disable again.

## Full, lean, and image limits

Full mode is the default and all limits are unlimited. It exports eligible tracked project content. Both modes exclude hidden/control files, Git history, agent instructions, private keys, caches, nested repositories, and symlinks. Exclusions are a practical filter, not a content classifier: review `plan` before uploading private data.

Lean mode exports Markdown and locally referenced images only. Rendered Markdown tables remain readable without exporting their CSV inputs. References must resolve inside their own project; external image URLs are not downloaded. Markdown image embeds, reference-style images, and unambiguous Obsidian image embeds are supported. Other attachments such as PDFs remain excluded in lean mode; their links may be unavailable on iPhone.

```sh
uv run _tools/icloud_bridge.py configure --mode lean
uv run _tools/icloud_bridge.py configure --max-image-bytes 5242880 --max-images-total-bytes 104857600
uv run _tools/icloud_bridge.py plan
uv run _tools/icloud_bridge.py sync
uv run _tools/icloud_bridge.py configure --unlimited-images
uv run _tools/icloud_bridge.py configure --mode full
```

Limits apply to individual images and all selected images across enabled projects. `null` means unlimited; `0` means zero bytes. Markdown/tasks are never omitted to satisfy an image limit. Selection is deterministic in project/path order: reject oversized files, include images that fit, skip one that does not fit and continue to smaller later images. Repeated references to the same path count once. Original image bytes and document references are preserved.

`Bridge Status.md` lists omitted files, sizes and reasons, including configured-limit omissions and missing/untracked referenced images. It reports selected export bytes, selected image bytes, and currently present managed payload bytes, **not** account free space or an iCloud bill. Current payload size excludes generated status/settings and unowned files, and can exceed the new selection when a conflict prevents cleanup. Obsidian plugins, unrelated vault files, iCloud retention and other account data can consume additional storage. Lowering limits removes only unchanged bridge-owned copies; modified phone files are preserved and reported. The report only changes when its meaningful content changes.

## Schedule, notifications, and controls

After a successful foreground sync, enable the per-user LaunchAgent:

```sh
uv run _tools/icloud_bridge.py schedule-enable
uv run _tools/icloud_bridge.py status
uv run _tools/icloud_bridge.py doctor
uv run _tools/icloud_bridge.py logs
```

The default interval is five minutes. `schedule-enable` runs a foreground sync first, registers the job, then announces: **folderwise-ibridge is now enabled. Sync job is running and scheduled every X minutes.** The first setup notification also lets you check visibility. Change the interval and reload the schedule with:

```sh
uv run _tools/icloud_bridge.py configure --interval-minutes 10
uv run _tools/icloud_bridge.py schedule-enable
uv run _tools/icloud_bridge.py notify-test
uv run _tools/icloud_bridge.py schedule-disable
```

The user must remain logged in. Sleep can skip interval firings; periodic runs resume after wake. The job does not overlap itself. Only one scheduled bridge installation per macOS user is supported. Re-running `schedule-enable` reloads the owned job; it refuses to replace another configuration's job. Disabling preserves vault content and local state.

Notifications use macOS's built-in script host and are best effort. New conflicts, failed imports and image-budget omissions produce a summary; routine success and unchanged issues stay quiet. Intentional lean exclusions do not generate alerts. Banners contain no document/task content. Focus or notification permissions can suppress them; a successful script invocation does not prove a banner appeared. See [Apple's notification scripting guide](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html). Branded notifications and custom action buttons are outside this release.

```sh
uv run _tools/icloud_bridge.py configure --notifications off
uv run _tools/icloud_bridge.py configure --notifications errors
```

The default is `errors`; `off` also suppresses the enable announcement. `notify-test` is an explicit request to display a test regardless of that preference. Local `bridge.log` rotates at about 1 MB; launchd's stdout/stderr logs are separate files in the configuration directory. `doctor` reports pending failures, stale scheduled runs and interval mismatches. Use `launchctl print gui/$(id -u)/org.folderwise.ibridge` for OS diagnostics; the bridge does not parse its unstable output format.

## Conflicts and recovery

Phone imports are evaluated against the last accepted baseline, not modification timestamps. Unsupported or conflicting edits freeze export so they cannot be overwritten. Read `Bridge Status.md` and local logs; preserve the edited vault file outside managed paths, resolve the corresponding source on Mac, then restore the exported file to its previous baseline or apply only the intended checkbox change. Do not erase bridge state to make a conflict disappear.

Export uses a local journal (`export.json`) so interrupted copies can finish on a later run. Replay proceeds only when each destination still matches the old or intended bytes and each source payload remains unchanged. If either side changed, it stops and preserves the files. Keep independent backups of your source repositories.

For a blocked export journal, disable scheduling first. Back up the entire private bridge-state directory and affected source/vault files. Inspect the journal's `writes`, `removes`, and proposed `state`: either restore destinations to their recorded `before` bytes and sources to the intended hashes, then rerun `sync`; or finish the intended export manually and restore the matching proposed state after review. Do not simply delete a journal after partial export: some files may already have advanced. The journal contains private paths and document baselines; never post it publicly.

Only the Mac job owns Git operations. It does not treat iCloud as a Git-aware coordinator. Avoid editing the same source record simultaneously from multiple Macs; the existing Synology one-writer rule still applies. The source check/fast-forward and vault hash checks catch common concurrent edits, but cloud delivery is asynchronous. A full end-to-end acceptance test requires your iPhone: complete a fictional Markdown and CSV-backed task, verify their local commits, reopen both from the completed view, and inspect the status report before using production data.

## Obsidian navigation

Graph edges come from explicit links. Folderwise validates relative Markdown links within each project and rejects links that leave it. A private vault dashboard can navigate across projects, but project documents must keep their normal repository-relative links. Query rows do not create persistent graph edges. Use `docs_mv.py` on Mac for moves and renames; do not rely on Obsidian's link rewriting to replace that workflow.
