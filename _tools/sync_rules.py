#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Sync shared rules and hooks from the template into project repos.

For each project: refresh the managed block in AGENTS.md, ensure CLAUDE.md
imports AGENTS.md, install the pre-commit hook, and sync shared config files (.markdownlint.json,
_doc-template.md overwritten; .vscode/*.json and .claude/settings.json merged, keeping project-only keys;
missing .gitignore lines appended). Does NOT commit.

  sync_rules.py              all projects
  sync_rules.py homelab      one project
  sync_rules.py --check      report drift only (exit 1 if any)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402

TOOLS = Path(__file__).resolve().parent


COPIED = [".markdownlint.json", "_doc-template.md"]          # overwritten from the template
MERGED_JSON = [".vscode/settings.json", ".vscode/extensions.json", ".claude/settings.json"]  # template keys win; project extras are kept
APPEND_LINES = [".gitignore"]                                  # template lines missing from the project file are appended


def merge_json(template, project):
    """Template values override; keys only the project has are kept; lists are unioned."""
    if isinstance(template, dict) and isinstance(project, dict):
        out = dict(project)
        for k, v in template.items():
            out[k] = merge_json(v, project[k]) if k in project else v
        return out
    if isinstance(template, list) and isinstance(project, list):
        return template + [x for x in project if x not in template]
    return template


def sync_files(p: Path, check: bool) -> list[str]:
    changes = []
    tpl = TOOLS.parent / "_template"
    for rel in COPIED:
        src, dest = tpl / rel, p / rel
        if src.is_file() and (not dest.is_file() or dest.read_text() != src.read_text()):
            changes.append(rel)
            if not check:
                dest.write_text(src.read_text())
    for rel in MERGED_JSON:
        src, dest = tpl / rel, p / rel
        if not src.is_file():
            continue
        want = json.loads(src.read_text())
        try:
            have = json.loads(dest.read_text()) if dest.is_file() else None
        except ValueError:
            have = None
        merged = want if have is None else merge_json(want, have)
        if merged != have:
            changes.append(rel)
            if not check:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(merged, indent=2) + "\n")
    for rel in APPEND_LINES:
        src, dest = tpl / rel, p / rel
        if not src.is_file():
            continue
        want = [l for l in src.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
        have_text = dest.read_text() if dest.is_file() else ""
        have = {l.strip() for l in have_text.splitlines()}
        missing = [l for l in want if l.strip() not in have]
        if missing:
            changes.append(rel)
            if not check:
                dest.write_text(have_text.rstrip("\n") + ("\n" if have_text else "") + "\n".join(missing) + "\n")
    return changes


def sync_project(p: Path, block: str, check: bool) -> list[str]:
    changes = sync_files(p, check)
    agents = p / "AGENTS.md"
    if not agents.is_file():
        changes.append("AGENTS.md missing")
    else:
        text = agents.read_text()
        new = dl.MANAGED_RE.sub(lambda _: block, text, count=1) if dl.MANAGED_RE.search(text) \
            else text.rstrip("\n") + "\n\n" + block + "\n"
        if new != text:
            changes.append("AGENTS.md managed block")
            if not check:
                agents.write_text(new)
    claude = p / "CLAUDE.md"
    if not claude.is_file() or "@AGENTS.md" not in claude.read_text():
        changes.append("CLAUDE.md import")
        if not check:
            claude.write_text("@AGENTS.md\n")
    if dl.install_hook(p, TOOLS, check_only=check) == "updated":
        changes.append("pre-commit hook")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projects", nargs="*")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    projects = dl.all_projects(TOOLS)
    if args.projects:
        projects = [p for p in projects if p.name in args.projects]
        missing = set(args.projects) - {p.name for p in projects}
        if missing:
            print(f"error: unknown project(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    block = dl.template_block(TOOLS)
    drift = False
    for p in projects:
        changes = sync_project(p, block, args.check)
        drift |= bool(changes)
        verb = "drift" if args.check else "updated"
        print(f"{p.name}: {verb}: {', '.join(changes)}" if changes else f"{p.name}: in sync")
    if not projects:
        print("no projects found")
    if drift and not args.check:
        print("\nReview and commit the changes inside each project repo.")
    return 1 if (drift and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
