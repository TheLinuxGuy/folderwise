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

## Minimal pull-only checkout

Use this opt-in mode when the framework lives at the root of your knowledge folder and each topic below it is an independent repository. It requires Git 2.25+ and Python 3.10+. Start with a normal clone into a **new directory**, then configure it locally:

```sh
git clone https://github.com/TheLinuxGuy/folderwise.git ~/folderwise
cd ~/folderwise
python3 _tools/framework_checkout.py --minimal --dry-run
python3 _tools/framework_checkout.py --minimal
uv run _tools/selftest.py
```

For an existing clone, run the last four commands from its root instead. The preview performs the same safety checks but makes no changes. Do not clone over existing knowledge files; see the nonempty-folder migration below.

The setup uses Git's persistent non-cone sparse checkout with this allowlist:

```text
/_*/
/.gitignore
/.gitattributes
/AGENTS.md
/README.md
/LICENSE
/uv.toml
```

Only tracked **top-level** directories whose names begin with `_` are materialized, including future underscore-prefixed directories. Their entire contents remain available, including `_template/docs/` and the tool self-tests. Root `.gitignore` protects independent topic repositories, `.gitattributes` preserves line-ending rules, `AGENTS.md` holds framework instructions, and `uv.toml` supplies portable defaults. Git's own `.git` metadata remains. README.md and LICENSE stay present by default. Public `docs/` (including images), `.github/`, `CONTRIBUTING.md`, and development-only root settings disappear from disk without staging deletions. Read the public guides on GitHub or in your separate development clone.

The script requires a clean tracked working tree (except unstaged deletions of the optional root README/LICENSE when configuring minimal mode) and no unfinished merge/rebase/cherry-pick/revert. It refuses excluded framework directories containing untracked or ignored files: move those files elsewhere, then retry. It never runs `git clean` or `git reset`, never deletes local knowledge projects, and does not move their contents. A Git failure stops the script and may leave already-applied local settings in place; review its output before retrying.

Minimal setup also applies the pull-only safeguards listed above, including the blocked origin push URL and framework hooks. These settings apply to this clone; they do not change the public repository. Use a separate full development clone for contributions. The script requires an `origin` remote; `--update` also requires an attached branch with an upstream.

### Optional README and license files

`README.md` and `LICENSE` are included by default. To omit either or both without recording a repository deletion:

```sh
python3 _tools/framework_checkout.py --minimal --omit README.md LICENSE
```

You can also simply delete either file locally, then run `python3 _tools/framework_checkout.py --update` (or `--minimal`). The script recognizes only **unstaged deletions of these two exact root files**, remembers the preference in local `folderwise.omittedRootFiles` configuration, and updates the sparse rules. `--dry-run` previews this choice without saving it. Modified files, staged deletions, and changes to required framework files still stop setup; they are never silently discarded.

Once recorded, both ordinary `git pull --ff-only` and the updater keep the chosen files absent, even when upstream changes them. A bare `git pull` cannot record a new manual deletion: run the updater once after deleting a file, or use `--omit` before pulling. All repository objects are still fetched; omission controls files on disk. Your preference remains local and is not committed upstream.

To restore previously omitted files and resume updating them:

```sh
python3 _tools/framework_checkout.py --minimal --include README.md LICENSE
```

Only README.md and LICENSE are optional; required Git rules, agent instructions and tool configuration cannot be omitted this way. `--full` also restores optional files and clears the saved omission preference while keeping pull-only safeguards.

### Updating a minimal checkout

After setup, normal Git updates preserve the sparse rules:

```sh
git pull --ff-only
uv run _tools/selftest.py
```

Or enforce the minimal configuration before pulling and reapply it afterward:

```sh
python3 _tools/framework_checkout.py --update --dry-run
python3 _tools/framework_checkout.py --update
uv run _tools/selftest.py
```

An existing personal update script can call `python3 _tools/framework_checkout.py --update` from the framework root instead of calling `git pull` directly. No extra root script or non-underscore directory is installed. Neither update method updates independent project repositories or applies managed template changes. Preview those separately with `uv run _tools/sync_rules.py --check`.

Sparse checkout controls working-tree contents, not downloads: Git still fetches repository history, and pull summaries can mention excluded files. Local files left in excluded directories are preserved and reported rather than deleted automatically. The promise concerns tracked framework directories; pre-existing knowledge folders remain untouched.

### Restoring the full checkout

```sh
python3 _tools/framework_checkout.py --full --dry-run
python3 _tools/framework_checkout.py --full
```

This restores tracked documentation and CI files. Pull-only safeguards remain enabled; use your development clone to publish. Release archives have no Git metadata and cannot use this script until they are set up as a real clone. Default full clones and release archive contents are unchanged.

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

5. Preview, then copy. `rsync` without `--delete` only writes files that exist in the new release; `--checksum` compares content, so only files that really differ are replaced (modification times in archives are the release commit's time and say nothing about content); `--backup-dir` keeps the previous version of every overwritten file outside your install. Your project folders are not in the release, so they are not touched:

```bash
rsync -a --checksum --dry-run --itemize-changes --backup --backup-dir="$HOME/folderwise-backup-before-1.3.0" ~/folderwise-upgrade/ ~/folderwise/
```

```bash
rsync -a --checksum --itemize-changes --backup --backup-dir="$HOME/folderwise-backup-before-1.3.0" ~/folderwise-upgrade/ ~/folderwise/
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
