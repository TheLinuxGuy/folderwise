#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Create a new documentation project (own git repo) from _template/.

Interactive:      new_project.py
Non-interactive: new_project.py --name homelab --description "Home network and lab" \\
                                --sensitivity private --by codex/gpt-5.5

At the end it prints a short, copy-paste prompt that makes an AI agent interview you and propose folder
structures for the new project (hide it with --no-prompt), or start the agent for you with the prompt pre-filled (--start claude|codex).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsextra as dx  # noqa: E402
import docslib as dl  # noqa: E402

TOOLS = Path(__file__).resolve().parent
BASE = TOOLS.parent
TEMPLATE = BASE / "_template"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SKIP = {"_doc-template.md"}  # copied verbatim, no placeholders to fill


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or (default or "")


def setup_prompt(name: str, description: str) -> str:
    """Single-paragraph prompt for an agent started inside the new project: read files, one batched answer
    from the human, a few targeted follow-ups, 3 structure proposals, then write minimal rules."""
    purpose = description.strip().rstrip(".")
    return (f'Set up the docs project "{name}" (purpose: {purpose}). Read AGENTS.md and .docs.yaml first; never ask what files answer. '
            "Then ask nothing yet: list a short fill-in (what it tracks, who uses it, how often it changes, recurring agent tasks, "
            "what agents must never do without my OK, sensitive data, material to import) for me to answer once, free-form, partial is fine. "
            "Then restate your understanding, flag assumptions, and ask at most 5 follow-ups (8 if essential), one at a time, each with a "
            "recommended default and only on gaps that change the structure. Then propose 3 genuinely different folder structures with "
            "trade-offs, recommend one, and wait for my choice. After I choose: write short, non-obvious project rules in AGENTS.md "
            "(never the managed block), set .docs.yaml extra_fields if useful, create the folders and starter docs with "
            "../_tools/docs_new.py, run ../_tools/docs_lint.py, show me the diff, and commit once I agree.")


def render(text: str, values: dict[str, str]) -> str:
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v).replace("{{" + k + "_YAML}}", json.dumps(v))
    return text


def run(cwd: Path, *cmd: str) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--description")
    ap.add_argument("--sensitivity", choices=dl.SENSITIVITIES)
    ap.add_argument("--timezone", default=dl.DEFAULT_TZ, help="IANA timezone for all timestamps in this project")
    ap.add_argument("--by", default="human", help="'human' or '<agent>/<model>' recorded as the creator")
    ap.add_argument("--icloud-disabled", action="store_true", help="exclude this project from the optional iCloud bridge")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--no-prompt", action="store_true", help="do not print the agent setup prompt")
    ap.add_argument("--start", choices=["claude", "codex"], help="after creating, start this agent in the project with the setup prompt pre-filled (interactive terminal only)")
    args = ap.parse_args()

    interactive = sys.stdin.isatty()
    name = args.name or (ask("Project folder name (lowercase-kebab)") if interactive else "")
    if not NAME_RE.match(name):
        print("error: --name must be lowercase letters, digits and hyphens", file=sys.stderr)
        return 2
    dest = BASE / name
    if dest.exists():
        print(f"error: {dest} already exists", file=sys.stderr)
        return 2
    description = args.description or (ask("One-line purpose of this project") if interactive else "")
    if not description:
        print("error: --description is required", file=sys.stderr)
        return 2
    sensitivity = args.sensitivity or (
        ask(f"Sensitivity of this repo ({'/'.join(dl.SENSITIVITIES)})", "private") if interactive else "private")
    if sensitivity not in dl.SENSITIVITIES:
        print(f"error: sensitivity must be one of {dl.SENSITIVITIES}", file=sys.stderr)
        return 2
    if not dl.BY_RE.match(args.by):
        print("error: --by must be 'human' or '<agent>/<model>'", file=sys.stderr)
        return 2

    try:
        ZoneInfo(args.timezone)  # validate only
    except (ZoneInfoNotFoundError, ValueError):
        print(f"error: unknown timezone {args.timezone!r}", file=sys.stderr)
        return 2
    moment = dl.now({"timezone": args.timezone})

    values = {
        "PROJECT": name, "PROJECT_TITLE": name.replace("-", " ").title(),
        "DESCRIPTION": description, "SENSITIVITY": sensitivity,
        "DATE": moment.date().isoformat(), "TIMESTAMP": dl.format_ts(moment),
        "TIMEZONE": args.timezone, "BY": args.by,
    }
    profile_path = BASE / ".folderwise-obsidian.json"
    try:
        if profile_path.is_symlink():
            raise ValueError("Obsidian profile must not be a symlink")
        profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
        if not isinstance(profile, dict) or type(profile.get('enabled', False)) is not bool:
            raise ValueError("invalid Obsidian profile")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    bridge_enabled = profile.get("enabled", False) is True and not args.icloud_disabled
    for src in sorted(TEMPLATE.rglob("*")):
        rel = src.relative_to(TEMPLATE)
        out = dest / rel
        if src.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(src.read_text() if rel.name in SKIP else render(src.read_text(), values))

    # stamp the README so it gets its byline, index and first Change Log row from the shared tools
    if bridge_enabled or args.icloud_disabled:
        config_path = dest / ".docs.yaml"
        config_path.write_text(config_path.read_text() + f"\nfolderwise-ibridgesync: {str(bridge_enabled).lower()}\n")
    new_cfg, readme = dl.load_config(dest), dest / "README.md"
    meta, body = dl.split_front_matter(readme.read_text())
    stamped, _, _ = dl.stamp_text(dl.join_front_matter(meta, dx.apply_index(body, dest, new_cfg)),
                                  "README.md", new_cfg, args.by, "Project scaffolded")
    readme.write_text(stamped)

    run(dest, "git", "init", "-q", "-b", "main")
    dl.install_hook(dest, TOOLS)
    if not args.no_commit:
        run(dest, "git", "add", "-A")
        run(dest, "git", "commit", "-q", "-m", "Scaffold project from template",
            "-m", f"Agent: {args.by.split('/')[0]}" + (f"\nModel: {args.by.split('/')[1]}" if "/" in args.by else ""))
    print(f"created {dest}")
    prompt = setup_prompt(name, description)
    if args.no_prompt and not args.start:
        print("Next: edit AGENTS.md (project-specific rules) and .docs.yaml (extra_fields).")
    elif not args.no_prompt:
        print("\nNext: start an agent in the project, then paste the prompt below.")
        print(f"  cd {dest} && claude    (or: codex)\n")
        print("--- paste ---")
        print(prompt)
        print("--- end ---")
        print('\n(Or edit AGENTS.md "Project-specific rules" and .docs.yaml extra_fields by hand.)')
    if args.start:
        if not (sys.stdin.isatty() or os.environ.get("DOCS_START_FORCE") == "1"):
            print(f"\n--start needs an interactive terminal; not starting {args.start}. Run: cd {dest} && {args.start}")
        elif shutil.which(args.start) is None:
            print(f"\n--start: '{args.start}' is not on PATH; install it or paste the prompt into another agent.")
        else:
            print(f"\nStarting {args.start} in {dest} with the setup prompt ...", flush=True)
            subprocess.run([args.start, prompt], cwd=dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
