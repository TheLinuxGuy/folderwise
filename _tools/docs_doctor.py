#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Health check for a project's setup. Prints OK / WARN / FAIL per item and what to run to fix it.

  docs_doctor.py              current project
  docs_doctor.py --all        every project under Folderwise
  docs_doctor.py NAME ...     named projects
  docs_doctor.py --strict     exit 1 on WARN too (default: only FAIL)

Checks: tools and uv reachable, no CLAUDE.md above the project (Claude Code would load it into every project
session), git repo and pre-commit hook, rules and config in sync with the template,
.docs.yaml valid (timezone, unknown keys, sensitivity), uncommitted changes and remotes (a `restricted`
project with a remote is flagged), lint result, and docs overdue for re-verification.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_stale as ds  # noqa: E402
import docslib as dl  # noqa: E402
import sync_rules as sr  # noqa: E402

TOOLS = Path(__file__).resolve().parent
BASE_KEYS = {"schema_version", "project", "description"}


def known_config_keys() -> set[str]:
    """Every .docs.yaml key the tools read, found by scanning their source (so this never drifts)."""
    keys = set(BASE_KEYS)
    for f in TOOLS.glob("*.py"):
        keys |= set(re.findall(r'\bcfg(?:\.get\(|\[)"([a-z_][a-z_-]*)"', f.read_text()))
    return keys


def claude_md_above(root: Path) -> list[Path]:
    """CLAUDE.md files Claude Code would load from directories above the project.
    ~/.claude/CLAUDE.md is the user's personal file and does not count."""
    personal = (Path.home() / ".claude" / "CLAUDE.md").resolve()
    found = []
    for d in root.resolve().parents:
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            p = d / name
            if p.is_file() and p.resolve() != personal:
                found.append(p)
    return found


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def check_project(root: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    ok = lambda m: out.append(("OK", m))      # noqa: E731
    warn = lambda m: out.append(("WARN", m))  # noqa: E731
    fail = lambda m: out.append(("FAIL", m))  # noqa: E731

    # --- install
    if (root.parent / "_tools" / "docs_lint.py").is_file():
        ok("tools reachable at ../_tools")
    else:
        fail("tools not found at ../_tools: the project must sit next to _tools/ inside Folderwise")
    ok("uv on PATH") if shutil.which("uv") else warn("uv not on PATH: the pre-commit hook will block commits until it is installed")
    if os.environ.get("DOCS_SKIP_HOOK") == "1":
        warn("DOCS_SKIP_HOOK=1 is set in this environment: the pre-commit lint is being bypassed")
    has_git = (root / ".git").is_dir()
    if not has_git:
        fail("not a git repository (run `git init` in the project folder)")
    else:
        hook, src = root / ".git/hooks/pre-commit", TOOLS / "hooks" / "pre-commit"
        if not hook.is_file():
            fail("pre-commit hook missing: run `uv run _tools/sync_rules.py` (git does not copy hooks when cloning)")
        elif not os.access(hook, os.X_OK):
            fail("pre-commit hook is not executable: run `uv run _tools/sync_rules.py`")
        elif hook.read_text() != src.read_text():
            warn("pre-commit hook differs from the current one: run `uv run _tools/sync_rules.py`")
        else:
            ok("pre-commit hook installed and current")

    # --- instruction files above the project (Claude Code loads parent CLAUDE.md files into every project session)
    above = claude_md_above(root)
    for p in above:
        warn(f"{p} is above this project: Claude Code loads it into every project session and asks to approve its imports; "
             "delete it (projects carry their own CLAUDE.md)")
    if not above:
        ok("no CLAUDE.md above the project")

    # --- sync with the template
    drift = [d for d in sr.sync_project(root, dl.template_block(TOOLS), True) if d != "pre-commit hook"]
    ok("rules and config match the template") if not drift else warn(
        f"out of sync with the template ({', '.join(drift)}): run `uv run _tools/sync_rules.py`, then commit")

    # --- config
    cfg = None
    try:
        cfg = dl.load_config(root)
    except SystemExit as e:
        fail(f"cannot load .docs.yaml: {e}")
    if cfg is not None:
        unknown = sorted(set(cfg) - known_config_keys())
        for k in unknown:
            warn(f".docs.yaml has unknown key '{k}' (typo? the tools ignore it)")
        if cfg.get("sensitivity") not in dl.SENSITIVITIES:
            fail(f".docs.yaml sensitivity {cfg.get('sensitivity')!r} is not one of {dl.SENSITIVITIES}")
        if cfg.get("project") and cfg["project"] != root.name:
            warn(f".docs.yaml project '{cfg['project']}' does not match the folder name '{root.name}'")
        if not unknown and cfg.get("sensitivity") in dl.SENSITIVITIES:
            ok(f"config valid (timezone {cfg.get('timezone', dl.DEFAULT_TZ)}, sensitivity {cfg.get('sensitivity')})")

    # --- git state
    if has_git:
        dirty = [l for l in git(root, "status", "--porcelain").splitlines() if l.strip()]
        ok("working tree clean") if not dirty else warn(f"{len(dirty)} uncommitted file(s): commit or discard them")
        remotes = sorted({l.split()[0] for l in git(root, "remote", "-v").splitlines() if l.strip()})
        if remotes and cfg and cfg.get("sensitivity") == "restricted":
            warn(f"restricted project has remote(s) {', '.join(remotes)}: its docs can be pushed off this machine")
        else:
            ok(f"remotes: {', '.join(remotes)}" if remotes else "remotes: none (local only)")
        last = git(root, "log", "-1", "--format=%cs %s")
        ok(f"last commit: {last}") if last else warn("no commits yet")

    # --- docs
    lint = subprocess.run(["uv", "run", "--quiet", str(TOOLS / "docs_lint.py")], cwd=root, capture_output=True, text=True)
    text = lint.stdout + lint.stderr
    if lint.returncode == 0:
        n = re.search(r"ok: (\d+) doc", text)
        ok(f"lint clean ({n.group(1) if n else '?'} docs)")
    else:
        first = next((l for l in text.splitlines() if l.strip() and not l.startswith(("WARN", "\n"))), "")
        fail(f"lint failing: {first[:140]} (run `uv run ../_tools/docs_lint.py` for the full list)")
    warns = [l for l in text.splitlines() if l.startswith("WARN")]
    for label, needle in (("orphan doc(s) nothing links to", "orphan"), ("doc(s) over the size limit", "lines (>"),
                          ("unlinked mention(s) of other docs", "names another doc"), ("leftover placeholder(s)", "TODO")):
        n = sum(needle in w for w in warns)
        if n:
            warn(f"{n} {label} (see `docs_lint.py` output)")
    if cfg is not None:
        rows = ds.stale_in(root, 0)
        overdue = [r for r in rows if r[0] >= 0]
        if overdue:
            never = sum("never verified" in r[2] for r in overdue)
            warn(f"{len(overdue)} doc(s) overdue for re-verification ({never} never verified), e.g. {overdue[0][1]}: `uv run ../_tools/docs_stale.py`")
        else:
            ok("no docs overdue for re-verification")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projects", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    if args.all or args.projects:
        roots = dl.all_projects(TOOLS)
        if args.projects:
            roots = [p for p in roots if p.name in args.projects]
            missing = set(args.projects) - {p.name for p in roots}
            if missing:
                print(f"error: unknown project(s): {', '.join(sorted(missing))}", file=sys.stderr)
                return 2
    else:
        r = dl.find_project_root(Path.cwd())
        if r is None:
            print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
            return 2
        roots = [r]
    if not roots:
        print("no projects found")
        return 0

    nf = nw = 0
    for root in roots:
        print(f"== {root.name}")
        res = check_project(root)
        for level, msg in res:
            print(f"  {level:<5} {msg}")
        f, w = sum(l == "FAIL" for l, _ in res), sum(l == "WARN" for l, _ in res)
        nf, nw = nf + f, nw + w
        print(f"  -> {f} FAIL, {w} WARN\n")
    if len(roots) > 1:
        print(f"total: {nf} FAIL, {nw} WARN across {len(roots)} projects")
    return 1 if nf or (args.strict and nw) else 0


if __name__ == "__main__":
    sys.exit(main())
