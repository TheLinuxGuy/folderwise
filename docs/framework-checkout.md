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

## Ignore rules plus index guard

The `.gitignore` starts by ignoring every root entry, then allows only framework paths. A new folder therefore remains ignored regardless of its name. The root hooks run `framework_guard.py` against the complete staged index; forced additions of an unknown root, knowledge-project config, credentials, symlinks, or Git submodules are rejected.

The guard does not inspect the meaning of arbitrary prose for sensitive data. Review the staged diff before publishing. An explicit force-add inside an allowed public directory can still contain private text; no naming rule can prevent that by itself.
