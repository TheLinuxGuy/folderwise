# Use Folderwise with Obsidian, iCloud, and iPhone

Folderwise remains ordinary Markdown and Git. Obsidian is an optional reader and editor that adds search, backlinks, local/global graphs, properties, Canvas, and Bases. It doesn't automatically run Folderwise's stamping, CSV rendering, linting, or commits.

## Start on Mac

Open your documentation parent folder as one Obsidian vault to search across topic folders. Each topic can retain its independent Git history. Avoid also opening nested topic folders as vaults. The framework's root `.gitignore` excludes `.obsidian/`; keep vault settings private or maintain an explicitly reviewed configuration separately.

Graph lines come from explicit links, not inferred topic similarity. Folderwise currently validates relative Markdown links **within each project repository** and rejects links that leave it. Existing project indexes provide useful graph connections within topics. Cross-project navigation can use a separate, private Obsidian hub outside the linted project docs, but cross-project links inside project documents need a future, tested framework extension. Don't silently disable lint to make a richer demo graph.

## Optional iCloud workflow

Obsidian documents iCloud support for Mac, iPhone and iPad. Create the vault under `iCloud Drive/Obsidian/<Vault name>` using Obsidian's iCloud option. Use the same Apple account with iCloud Drive enabled. On Mac, keep the vault downloaded so files are available offline. Follow the [official device-sync guide](https://help.obsidian.md/sync-notes) for the current steps and device-specific controls.

If your source documentation lives in another provider's folder, an iCloud vault is a different location. Folderwise does not currently mirror files or provide a two-way sync bridge. Start with a disposable copy, choose one authoritative location, and design conflict handling before moving production records. Avoid syncing the same live vault with multiple synchronization services.

## A practical mobile editing boundary

1. Create a disposable test vault in iCloud and open it on Mac and iPhone.
2. Edit one handwritten test note on iPhone; let it sync before editing elsewhere.
3. Verify the result on Mac and inspect the relevant knowledge repository's `git diff`.
4. Run Folderwise stamping, regenerate affected tables/indexes, and lint on Mac before committing in that knowledge repository.

iCloud file sync and Git history are separate. iPhone edits do not become commits automatically. Keep Git operations owned by one Mac initially, maintain an independent backup, and do not rely on cloud file synchronization as a Git-aware coordination mechanism.

Edit source CSVs rather than generated Markdown table blocks. Obsidian rename/link-update behavior does not replace `docs_mv.py`. Review tools should preserve the distinction between edit dates and verification dates.

## Future work

A selective Markdown-to-iCloud bridge, automatic Git workflow, and first-class cross-project links are potential future improvements. None is implemented by this release. Mobile access is supplied by your chosen Obsidian/iCloud workflow, not a hosted Folderwise service.
