# Keep framework updates separate from your knowledge

## Layout

```text
folderwise/                 # Framework Git checkout
  .gitignore                # Explicit public root allowlist
  AGENTS.md
  README.md
  uv.toml
  _tools/
  _template/
  docs/                     # Public framework guides
  finances/                 # Ignored here; independent private repository
  sysadmin/                 # Ignored here; independent private repository
  any-new-topic/            # Ignored here automatically
```

Only the framework is published. `docs/` is reserved for public framework guides; don't create a knowledge project inside it, `_tools/`, or `_template/`.

## Two checkouts

Use a development clone for framework changes and publishing. A second clone can live at your everyday documentation root and pull releases beside existing independent knowledge repositories. The directory can have any name; tools resolve the parent of `_tools/`, not a hard-coded folder name.

For the everyday clone, configure local Git settings:

```sh
git config core.hooksPath _tools/framework-hooks
git config pull.ff only
git config submodule.recurse false
git config fetch.recurseSubmodules false
git config folderwise.pullOnly true
git config push.default nothing
git config remote.origin.pushurl no-push://folderwise-pull-only
```

The push URL intentionally cannot be used. The pre-push hook also refuses pushes from a checkout marked pull-only. These are local safeguards; they aren't inherited by fresh clones and can be changed by their owner. They do not control Synology, iCloud, or another file synchronization service.

## Adding the framework to a nonempty documentation folder

Do not clone directly over existing files or run a destructive reset/clean. First back up the framework files, confirm existing topic repositories are independent, and compare any existing root files with the incoming release. Initialize/fetch the framework repository and reconcile only the named public paths. A migration should verify hashes of knowledge files before and after, and test that an arbitrary new topic folder is ignored.

## Updating

From the framework checkout, review `git status --short`, then run `git pull --ff-only`. Framework updates do not push or pull any knowledge project. Run `uv run _tools/selftest.py` after updating. Local changes to tracked framework files can block a pull; contribute them from the development clone instead of discarding them blindly.

If managed templates changed, preview `uv run _tools/sync_rules.py --check`. Applying template changes modifies independent project files and should be a separate, reviewed step.

## Install from a release archive

Each [GitHub release](https://github.com/TheLinuxGuy/folderwise/releases) offers `folderwise-VERSION.zip` and `folderwise-VERSION.tar.gz` with a `SHA256SUMS` file. Archives contain only the tracked framework files (tools, project template, guides, license, and the root files that keep your projects out of the framework Git index) plus `RELEASE-INFO.json`, which records the version and source commit. They contain no `.git` folder, so there is no history to pull from. Replace `1.2.3` below with the version you downloaded.

Verify the download, then extract it as `~/folderwise` (the folder must not exist yet):

```bash
shasum -a 256 -c SHA256SUMS --ignore-missing
```

```bash
mkdir ~/folderwise && tar -xzf folderwise-1.2.3.tar.gz -C ~/folderwise --strip-components=1
```

For the zip, `unzip -q folderwise-1.2.3.zip && mv folderwise-1.2.3 ~/folderwise` does the same. Then check the install and create a project:

```bash
cd ~/folderwise && uv run _tools/selftest.py
```

```bash
cd ~/folderwise && uv run _tools/new_project.py
```

You do not need Git history to use the tools: `new_project.py` creates each project as its own Git repository (Git must have an author identity configured). Only if you want the framework guard for your own edits, run `git init` in the extracted folder and `git config core.hooksPath _tools/framework-hooks`; the `.gitignore` allowlist keeps projects and `RELEASE-INFO.json` out of that repository.

## Clone installs and archive installs

| | Clone (recommended) | Release archive |
|---|---|---|
| Get it | `git clone` | download from a GitHub release, verify `SHA256SUMS`, extract |
| History | full | none (no `.git` folder); `RELEASE-INFO.json` names the version and source commit |
| Upgrade | `git pull --ff-only` | extract the new release beside the old one and copy framework files with backups (below) |
| Detect local edits | `git status` | compare against a fresh extraction with `diff -r` |
| Framework hooks | `git config core.hooksPath _tools/framework-hooks` | only after `git init` yourself; optional |

Both are tested the same way before a release is offered: a clean machine with an empty uv cache runs the documented self-test, creates a fictional project, creates/stamps/lints a document, commits through the installed hook, sees the hook reject an unstamped edit, and confirms the framework repository ignores the project.

## Upgrading an archive install

The goal is to replace framework files only. Your knowledge projects are sibling folders with their own Git repositories; nothing here reads or writes them, and none of these steps uses a reset, a clean, or `--delete`.

1. Download the new release and verify it (`shasum -a 256 -c SHA256SUMS --ignore-missing`). Read its compatibility and upgrade notes.
2. Extract it to a **separate** folder, not over your install:

```bash
mkdir ~/folderwise-upgrade && tar -xzf folderwise-1.3.0.tar.gz -C ~/folderwise-upgrade --strip-components=1
```

3. Run the new release's own self-test before it touches anything:

```bash
uv run ~/folderwise-upgrade/_tools/selftest.py
```

4. Review what differs. Local edits to framework files show up here; keep them by contributing or re-applying them afterwards. Files that only exist in the old install (removed upstream) are listed too and are never deleted for you:

```bash
diff -rq ~/folderwise/_tools ~/folderwise-upgrade/_tools
```

5. Preview, then copy. `rsync` without `--delete` only writes files that exist in the new release, and `--backup-dir` keeps the previous version of every overwritten file outside your install. Your project folders are not in the release, so they are not touched:

```bash
rsync -a --dry-run --itemize-changes --backup --backup-dir="$HOME/folderwise-backup-before-1.3.0" ~/folderwise-upgrade/ ~/folderwise/
```

```bash
rsync -a --itemize-changes --backup --backup-dir="$HOME/folderwise-backup-before-1.3.0" ~/folderwise-upgrade/ ~/folderwise/
```

6. Verify the upgraded install, then preview (do not apply) template changes for your projects; applying them is a separate, reviewed step that modifies each project repository:

```bash
cd ~/folderwise && uv run _tools/selftest.py
```

```bash
cd ~/folderwise && uv run _tools/sync_rules.py --check
```

If something looks wrong, restore files from the backup folder; nothing was deleted. Once you are satisfied, remove `~/folderwise-upgrade` and the backup folder yourself. If your install is also a Git checkout, upgrade it with Git instead.

## Ignore rules plus index guard

The `.gitignore` starts by ignoring every root entry, then allows only framework paths. A new folder therefore remains ignored regardless of its name. The root hooks run `framework_guard.py` against the complete staged index; forced additions of an unknown root, knowledge-project config, credentials, symlinks, or Git submodules are rejected.

The guard does not inspect the meaning of arbitrary prose for sensitive data. Review the staged diff before publishing. An explicit force-add inside an allowed public directory can still contain private text; no naming rule can prevent that by itself.
