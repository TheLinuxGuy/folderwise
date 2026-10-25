<div align="center">

<h1><img src="docs/assets/folderwise-hero.png" alt="Folderwise — Human-readable knowledge. AI-assisted upkeep. Markdown and Git underneath. Wherever you need it." width="900"></h1>

[![Python 3.10 or later](docs/assets/badge-python.svg)](#getting-started)
[![Plain Markdown files](docs/assets/badge-format.svg)](docs/guide.md)
[![MIT licensed](docs/assets/badge-license.svg)](LICENSE)

[Overview](#a-place-for-what-you-know) · [Get started](#getting-started) · [See it in Obsidian](#see-it-in-obsidian) · [Documentation](docs/guide.md)

</div>

## A place for what you know

You solved it once. Keep the instructions, the evidence, and the decisions somewhere you can find them again.

**Folderwise** is a Markdown-and-Git framework for knowledge that humans read and AI agents help maintain. Create dedicated projects for your home network, household records, technical runbooks, or anything you expect to revisit.

| Organize | Maintain | Revisit |
|---|---|---|
| One topic, one folder, one Git history. | Shared rules, change stamps, and checks. | Generated indexes, review dates, and optional Obsidian views. |

## Getting started

**Requires:** Git with a configured author identity, Python 3.10+, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/TheLinuxGuy/folderwise.git ~/folderwise
cd ~/folderwise
git config core.hooksPath _tools/framework-hooks
uv run _tools/new_project.py
```

Choose a topic, describe its purpose, and set its sensitivity. Folderwise creates its Git repository, starter files, and an agent setup prompt. Give that prompt to Codex or Claude Code to shape the project, or edit the files yourself.


> [!TIP]
> You don't need to organize your whole life first. Pick one useful question—“How do I recover this service?”—and document the answer.

## From notes to a maintained knowledge folder

1. **Describe the topic.** Give an agent your context and choose a folder structure.
2. **Document what matters.** Use reference notes, inventories, runbooks, decisions, plans, and logs.
3. **Keep it useful.** Record changes, review the diff, and check which notes are due for verification.

Folderwise includes metadata and link validation, CSV-to-Markdown tables, generated indexes, and a staged-document hook. The [full guide](docs/guide.md) covers the tools and their conventions.

## See it in Obsidian

<p align="center">
  <img src="docs/assets/obsidian-local-graph.png" alt="Fictional Docker host documentation beside its related notes in Obsidian's local graph" width="800">
</p>

<sub>Obsidian demo with fictional notes. Cross-project links shown are demo-only; Folderwise currently validates links within each repository.</sub>


Obsidian adds search, backlinks, and visual navigation over your files. For Mac and iPhone, you can configure an Obsidian/iCloud workflow; syncing and Git commits remain separate. [Read the setup guide →](docs/obsidian.md)

> [!NOTE]
> Your topic folders are separate repositories, ignored by the framework's Git checkout. Folderwise does not upload them automatically or provide its own sync service. [Understand the layout](docs/framework-checkout.md).

## Keep it current

```sh
cd ~/folderwise
uv run _tools/docs_doctor.py --all
uv run _tools/docs_recent.py --all --since 7d
```

Check project health and recent updates, then review any notes whose verification is due with `docs_stale.py`. A recorded verification date reflects a check someone performed; it does not prove the contents are correct.
