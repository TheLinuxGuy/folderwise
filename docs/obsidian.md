# Use Folderwise with Obsidian, iCloud, and iPhone

The optional **folderwise-ibridge** keeps your project repositories on your Mac and exports a separate Obsidian vault into iCloud. Read your documents and complete tasks from one dashboard on iPhone. One Mac imports checkbox changes, updates authoritative records, regenerates views, stamps documents, validates them, and creates local Git commits in each project.

The bridge is deliberately simple: checking means complete; unchecking means incomplete. It does **not** interpret a task, confirm evidence, or establish that the described action happened. Task changes do not advance `last_verified`. Project adapters must implement this same boolean behavior without fabricating evidence.

## Layout and prerequisites

Use one vault for all project folders. Your source parent remains outside iCloud, for example `~/folderwise/`, with independent project repositories underneath. Create a **separate** vault in Obsidian under `iCloud Drive/Obsidian/Folderwise`. Do not move the source repositories, put Git history in the vault, or synchronize that vault with a second cloud service.

Use the same Apple account on Mac and iPhone and enable iCloud Drive. Keep the Mac vault downloaded. Obsidian's [official sync guide](https://help.obsidian.md/sync-notes) covers device setup. The bridge cannot force iCloud to deliver a change immediately or prove another device received it.

The Mac needs Git, uv, the Folderwise tools, a configured Git author, and an active login session for scheduled operation. Only committed, tracked project files are eligible for export; commit new documents on Mac before expecting them on iPhone. Never commit credentials merely to make them eligible. Existing source edits can be read, but pending phone imports wait until that project's working tree and index are clean.

## Explicit setup and reusable vault defaults

Obsidian is **off by default**. A fresh clone does not create `.obsidian/`, start a bridge job, or enable new projects for export. Choose a parent source directory outside iCloud and a separate destination under `iCloud Drive/Obsidian/`. The script initializes both as vault folders; open the iCloud vault in Obsidian on your devices afterward. Use fictional data for the first test.

Preview the complete setup, then run it (replace these fictional paths as needed):

```sh
uv run _tools/icloud_bridge.py setup --source ~/folderwise --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise" --dry-run
uv run _tools/icloud_bridge.py setup --source ~/folderwise --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Folderwise"
```

Setup creates the local parent vault alongside your project folders and a separate iCloud vault, installs missing settings, enrolls existing unconfigured projects, records the default for future projects, runs the initial sync, and registers the macOS schedule. `--no-schedule` performs setup and foreground sync without registering a job; use it on non-Mac systems and in test sandboxes. The setup notification announces the configured interval after the job is registered. `setup --dry-run` previews eligible files, estimated bytes, omissions and project enrollment without changing vaults, project flags or future-project defaults.

The framework ships reviewed defaults in `_tools/obsidian_defaults/`, not a live `.obsidian/` directory:

| Defaults | Behavior |
| --- | --- |
| `app.json` | Relative Markdown links, no automatic link renames, reading view and no duplicate inline title |
| `appearance.json` and snippet | Default theme, readable font and tabular numerals in tables |
| `core-plugins.json` | Search, graph, backlinks, outline, properties, Bases and recovery; competing sync/publish disabled |
| `graph.json` | General navigation settings without private project names or demo color groups |
| `types.json` | Shared document property types, without demo query fields |
| `community-plugins.json` and plugin settings | Tasks/Dataview IDs; automatic task dates and Dataview JavaScript disabled |

**Community-plugin binaries are not bundled or downloaded.** Install Tasks and optional Dataview through Obsidian's community-plugin browser, then enable them. Setup seeds their settings; it does not bypass Obsidian's Restricted mode. See [Obsidian's community-plugin guide](https://help.obsidian.md/community-plugins). Device-specific `workspace.json`, caches and installed plugin code are never copied from the demo.

Existing setting files are preserved in full. If you already have Tasks settings, confirm automatic dates are off; setup does not replace your preferences. `vault-init` fills missing defaults later without overwriting customization. Vaults become available when opened in Obsidian; the helper does not edit Obsidian's global vault registry.

Configuration, ownership records, baselines, temporary clones, export journal and logs stay outside iCloud. On Mac the default state directory is `~/Library/Application Support/Folderwise/ibridge/`. A private `.folderwise-obsidian.json` at the source root records whether the integration is enabled and points to that configuration. `new_project.py` reads it in each new process. Neither file is committed to the framework. Use `--config /absolute/path/config.json` before a bridge command for another private installation. Keep recovery state: deleting it removes knowledge of pending edits and owned files. Source, vault and state directories must remain separate.

`plan` previews ordinary export/cleanup; `sync` performs a foreground run. They never recreate removed Obsidian settings. New or missing defaults are installed only through explicit setup or `vault-init`.

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

## Project participation and persistent creation defaults

The positive `.docs.yaml` key is **`folderwise-ibridgesync`**. True enables participation; false or a missing key disables it. A fresh installation omits the key and creates no vault settings. Running setup opts into this integration, including eligible restricted content; the project's `sensitivity` is not an upload filter.

Setup enables existing projects with no explicit setting and preserves existing true/false choices. Each enrollment is committed through an isolated local clone and its normal hooks. Commit existing source edits first; setup will not mix them into an enrollment commit. An interrupted setup can be retried, and a failed setup does not enable the future-project default.

After successful setup, **every new `new_project.py` project writes `folderwise-ibridgesync: true`**, including from another terminal or agent process. Override that default for one project with:

```sh
uv run _tools/new_project.py --name offline-notes --description "Local-only notes" --icloud-disabled
```

This flag writes `folderwise-ibridgesync: false`, even before global setup, so a later setup respects that deliberate opt-out. Change an existing project's choice with:

```sh
uv run _tools/icloud_bridge.py disable homelab-inventory
uv run _tools/icloud_bridge.py enable homelab-inventory
```

The helpers update only that project's setting; commit it when ready. They do not change the default for future projects. Disabling removes only unchanged bridge-owned exported copies on the next sync. Pending phone edits block cleanup: re-enable, import or preserve those edits, then disable again.

### Uninstall or remove the supplied defaults

```sh
uv run _tools/icloud_bridge.py uninstall
```

Uninstall stops the owned schedule, disables the integration, removes the private creation-default profile, and deletes only unchanged settings installed by setup. Customized settings, workspace layouts, downloaded plugins, source documents, exported documents, explicit project flags and recovery state are preserved. A vault may therefore retain user-owned `.obsidian/` files. **Projects created after uninstall default to sync disabled again.** Re-running setup restores the opt-in lifecycle and preserves previous bridge configuration.

The existing framework checkout helper can do this in the same operation as removing README.md:

```sh
python3 _tools/framework_checkout.py --minimal --omit README.md --remove-obsidian --dry-run
python3 _tools/framework_checkout.py --minimal --omit README.md --remove-obsidian
```

`--remove-obsidian` uninstalls the configured integration and removes unchanged generated defaults; it does not delete reusable assets from the framework or remove user content. Normal `--minimal`, `--update` and `--omit README.md` operations leave the optional integration alone unless this flag is supplied.

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

The job launches through a private executable named **`folderwise-ibridgesync`**, so macOS Login Items identifies Folderwise rather than the shared `uv` runtime. The job label remains `org.folderwise.ibridge`. `uv` is still a dependency; its installed binary is not renamed or modified. macOS still shows its normal background-item notification and provides the normal on/off control. File-access prompts may name the runtime that actually reads the files. See [Apple's attribution rules](https://developer.apple.com/documentation/servicemanagement/updating-helper-executables-from-earlier-versions-of-macos).

### Expected macOS background-activity notice

When you enable scheduled syncing, macOS may display an **App Background Activity** notice saying that **folderwise-ibridgesync** can run in the background. This is the expected system notice for the sync job you just enabled.

![Expected macOS App Background Activity notice for folderwise-ibridgesync](assets/obsidian-background-activity-notice.png)

You can manage the helper under **System Settings → General → Login Items & Extensions**, in **Background App Activity**. Keep its switch enabled for scheduled syncing. Because each sync runs briefly, **Not running in background** between runs is normal; use `status` or `doctor` to check the last successful sync.

![The enabled folderwise-ibridgesync helper in macOS Login Items](assets/obsidian-login-items.png)

Folderwise also sends its own setup-success notification with the configured interval, described below. That confirmation is separate from the macOS background-activity notice.

For an inspectable preparation step without registering or enabling a job:

```sh
uv run _tools/icloud_bridge.py schedule-prepare
```

This writes the owned entry point under the local state directory's `bin/` and a `launchagent-preview.plist` beside the config. It works on Mac and Linux for review/testing; actual job registration still requires macOS. Preparation refuses to replace a customized entry point. `schedule-enable` prepares it automatically and upgrades existing jobs that launched `uv` directly. Uninstall removes an unchanged generated entry point and preserves one that has been customized.

The default interval is five minutes. `schedule-enable` runs a foreground sync first, registers the job, then announces: **folderwise-ibridge is now enabled. Sync job is running and scheduled every X minutes.** The first setup notification also lets you check visibility. Change the interval and reload the schedule with:

```sh
uv run _tools/icloud_bridge.py configure --interval-minutes 10
uv run _tools/icloud_bridge.py schedule-enable
uv run _tools/icloud_bridge.py notify-test
uv run _tools/icloud_bridge.py schedule-disable
```

The user must remain logged in. Background helpers may need one-time macOS file-access consent for protected folders such as Documents. For fictional testing, a source/state folder under your home directory avoids needing broad Documents-folder access; keep the separate mobile vault in iCloud. Sleep can skip interval firings; periodic runs resume after wake. The job does not overlap itself. Only one scheduled bridge installation per macOS user is supported. Re-running `schedule-enable` reloads the owned job; it refuses to replace another configuration's job. Disabling preserves vault content and local state.

Folderwise builds a small notification app locally using macOS’s built-in `osacompile` and `codesign` tools. Setup confirmations, error summaries, and `notify-test` use the same Folderwise name and logo. The icon crops transparent padding from our original artwork and includes sizes for standard and Retina displays. No additional package or developer account is required. The generated app lives beside the bridge configuration, outside iCloud; uninstall removes it when unchanged and preserves customizations. Notifications are best effort. New conflicts, failed imports and image-budget omissions produce a summary; routine success and unchanged issues stay quiet. Intentional lean exclusions do not generate alerts. Banners contain no document/task content. Focus or notification permissions can suppress them; a successful app launch does not prove a banner appeared. See [Apple's notification scripting guide](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html). macOS controls the icon on its own App Background Activity notice (the System Settings gear); Folderwise cannot replace it. Custom action buttons are outside this release. Allow notifications for **Folderwise iBridge** if macOS asks on first use.

```sh
uv run _tools/icloud_bridge.py configure --notifications off
uv run _tools/icloud_bridge.py configure --notifications errors
```

The default is `errors`; `off` also suppresses the enable announcement. `notify-test` is an explicit request to display a test regardless of that preference. Local `bridge.log` rotates at about 1 MB; launchd's stdout/stderr logs are separate files in the configuration directory. `doctor` reports pending failures, stale scheduled runs and interval mismatches. Use `launchctl print gui/$(id -u)/org.folderwise.ibridge` for OS diagnostics; the bridge does not parse its unstable output format.

### A notification appears only in Notification Center

A successful app launch or a macOS log entry saying “presenting as banner” is not proof that a banner was visible on the desktop. The bridge reports **Notification requested**, rather than claiming a banner appeared. macOS remains responsible for presentation.

Check **System Settings → Notifications → Folderwise iBridge**: enable **Allow notifications** and **Desktop**, and choose Temporary or Persistent to suit your preference. Check the active Focus and its app exceptions. **Summarize notifications** changes preview text; it is separate from the Reduce Interruptions Focus that can silence alerts.

If you use Screen Sharing, remote desktop, screen recording, or display mirroring, also check **System Settings → Notifications → when mirroring or sharing the display**. With **Notifications Off**, macOS may keep notifications in Notification Center without showing them at the top-right corner. If a computer-use or screen-reading assistant is active, end its capture session before testing; that capture can count as display sharing even when you are not presenting to another person. End the sharing session to test ordinary desktop delivery, or consciously choose **Allow Notifications** if that suits your setup. This is a global privacy preference: allowing it can show other apps’ private messages to people viewing your display. Folderwise never changes it automatically. See [Apple’s notification settings guide](https://support.apple.com/en-ie/guide/mac-help/mh40583/27/mac/27).

Repeat the setup-success notification with one command, without reinstalling or restarting the scheduled job:

```sh
uv run _tools/icloud_bridge.py notify-test --setup-message
```

Use the same `--config /absolute/path/config.json` argument as your installed bridge when its configuration is outside the default location. This command replays the setup wording using the configured interval; it does not change schedule state. Plain `notify-test` sends a generic test instead. Both explicitly request a notification even when bridge notifications are configured off, and print the macOS visibility checks. A test cannot override denied notification access, Focus, or shared-display privacy controls.

## Conflicts and recovery

Phone imports are evaluated against the last accepted baseline, not modification timestamps. Unsupported or conflicting edits freeze export so they cannot be overwritten. Read `Bridge Status.md` and local logs; preserve the edited vault file outside managed paths, resolve the corresponding source on Mac, then restore the exported file to its previous baseline or apply only the intended checkbox change. Do not erase bridge state to make a conflict disappear.

Export uses a local journal (`export.json`) so interrupted copies can finish on a later run. Replay proceeds only when each destination still matches the old or intended bytes and each source payload remains unchanged. If either side changed, it stops and preserves the files. Keep independent backups of your source repositories.

For a blocked export journal, disable scheduling first. Back up the entire private bridge-state directory and affected source/vault files. Inspect the journal's `writes`, `removes`, and proposed `state`: either restore destinations to their recorded `before` bytes and sources to the intended hashes, then rerun `sync`; or finish the intended export manually and restore the matching proposed state after review. Do not simply delete a journal after partial export: some files may already have advanced. The journal contains private paths and document baselines; never post it publicly.

Only the Mac job owns Git operations. It does not treat iCloud as a Git-aware coordinator. Avoid editing the same source record simultaneously from multiple Macs; the existing Synology one-writer rule still applies. The source check/fast-forward and vault hash checks catch common concurrent edits, but cloud delivery is asynchronous. A full end-to-end acceptance test requires your iPhone: complete a fictional Markdown and CSV-backed task, verify their local commits, reopen both from the completed view, and inspect the status report before using production data.

## Obsidian navigation

Graph edges come from explicit links. Folderwise validates relative Markdown links within each project and rejects links that leave it. A private vault dashboard can navigate across projects, but project documents must keep their normal repository-relative links. Query rows do not create persistent graph edges. Use `docs_mv.py` on Mac for moves and renames; do not rely on Obsidian's link rewriting to replace that workflow.
