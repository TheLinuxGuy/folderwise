#!/usr/bin/env python3
"""Check a Folderwise installation by using it the way the README documents.

  install_check.py --framework DIR --mode clone     DIR is a fresh `git clone` of the repository
  install_check.py --framework DIR --mode archive   DIR is an extracted release archive (no .git)

Both modes run the documented self-test, then use a fictional project in an isolated temporary
configuration: create a project, create/stamp/lint a document, commit through the installed hook, see the hook
reject an unstamped edit, and confirm the framework repository keeps ignoring independent project contents.
Nothing outside DIR (and a temporary Git configuration) is touched. Never point it at a working checkout:
it creates a project folder and stages files inside DIR.

  --expect-cold-cache   require an empty uv cache at the start (the clean-machine installation path)
  --expect-version V    archive mode: RELEASE-INFO.json must carry this version
  --expect-commit SHA   archive mode: RELEASE-INFO.json must carry this source commit
Exit code 0 = every check passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROJECT = "ci-fixture"
RESULTS: list[bool] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok and detail.strip():
        print("     " + detail.strip()[-1200:].replace("\n", "\n     "), flush=True)
    return bool(ok)


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def isolated_env(scratch: Path) -> dict[str, str]:
    """Keep the user's global Git configuration (hooksPath, templates, signing) out of the check."""
    gitconfig = scratch / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Install Check\n\temail = install-check@example.invalid\n[init]\n\tdefaultBranch = main\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DOCS_", "GIT_"))}
    env.update(GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return env


def commit_count(cwd: Path, env: dict[str, str]) -> int:
    rc, out = run(["git", "rev-list", "--count", "HEAD"], cwd, env)
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else -1


def uv_cache_state(cwd: Path, env: dict[str, str]) -> tuple[Path, bool]:
    rc, out = run(["uv", "cache", "dir"], cwd, env)
    path = Path(out.strip())
    return path, rc == 0 and (not path.exists() or not any(path.iterdir()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--framework", type=Path, required=True)
    ap.add_argument("--mode", choices=["clone", "archive"], required=True)
    ap.add_argument("--expect-cold-cache", action="store_true")
    ap.add_argument("--expect-version")
    ap.add_argument("--expect-commit")
    args = ap.parse_args()

    fw = args.framework.resolve()
    if fw == REPO:
        print("install_check: refusing to modify the repository this script lives in; use a fresh clone or extracted archive.", file=sys.stderr)
        return 2
    scratch = Path(tempfile.mkdtemp(prefix="folderwise-install-check-")).resolve()
    env = isolated_env(scratch)
    project = fw / PROJECT
    try:
        check("framework folder has _tools, _template and README.md", all((fw / n).exists() for n in ("_tools/selftest.py", "_template", "README.md")))
        check("fixture project name is unused", not project.exists())
        if args.expect_cold_cache:
            cache, cold = uv_cache_state(fw, env)
            check(f"uv cache is empty before installation ({cache})", cold)
        has_git = (fw / ".git").exists()
        if args.mode == "clone":
            check("clone has Git history", has_git and commit_count(fw, env) >= 1)
            rc, out = run(["git", "config", "core.hooksPath", "_tools/framework-hooks"], fw, env)
            check("README step: git config core.hooksPath _tools/framework-hooks", rc == 0, out)
        else:
            check("archive has no .git (no history to rely on)", not has_git)
            info_path = fw / "RELEASE-INFO.json"
            info = json.loads(info_path.read_text()) if info_path.is_file() else {}
            check("archive carries RELEASE-INFO.json with version and source commit",
                  bool(info.get("version")) and len(info.get("commit", "")) == 40, str(info))
            if args.expect_version:
                check(f"RELEASE-INFO version is {args.expect_version}", info.get("version") == args.expect_version, str(info))
            if args.expect_commit:
                check("RELEASE-INFO commit is the selected commit", info.get("commit") == args.expect_commit, str(info))

        rc, out = run(["uv", "run", "_tools/selftest.py"], fw, env)
        check("README step: uv run _tools/selftest.py passes", rc == 0 and "checks passed" in out and "FAILED" not in out, out)
        if args.expect_cold_cache:
            cache, cold = uv_cache_state(fw, env)
            check("uv resolved dependencies into the cache during installation", not cold)

        rc, out = run(["uv", "run", "_tools/new_project.py", "--name", PROJECT, "--description", "Fictional installation check",
                       "--sensitivity", "private", "--by", "human", "--no-prompt"], fw, env)
        check("new_project.py creates a project", rc == 0 and project.is_dir(), out)
        check("project is its own Git repository with the pre-commit hook", (project / ".git").is_dir() and (project / ".git/hooks/pre-commit").is_file())
        check("project starts with its first commit", commit_count(project, env) == 1)

        doc = "docs/hosts/fictional-nas.md"
        rc, out = run(["uv", "run", "../_tools/docs_new.py", doc, "--type", "inventory", "--title", "Fictional NAS inventory",
                       "--about", "Disks and shares on a fictional NAS", "--by", "human"], project, env)
        check("docs_new.py creates a document", rc == 0 and (project / doc).is_file(), out)
        with open(project / doc, "a") as fh:
            fh.write("\nFictional note: the pool has four disks.\n")
        rc, out = run(["uv", "run", "../_tools/docs_stamp.py", doc, "--by", "human", "--summary", "Add disk note"], project, env)
        check("docs_stamp.py stamps the edit", rc == 0, out)
        rc, out = run(["uv", "run", "../_tools/docs_index.py", "--write", "--by", "human", "--summary", "Refresh index"], project, env)
        check("docs_index.py refreshes the README index", rc == 0, out)
        rc, out = run(["uv", "run", "../_tools/docs_lint.py"], project, env)
        check("docs_lint.py passes", rc == 0 and "ok:" in out, out)

        run(["git", "add", "-A"], project, env)
        rc, out = run(["git", "commit", "-q", "-m", "Add fictional NAS inventory"], project, env)
        check("commit through the installed hook succeeds", rc == 0 and commit_count(project, env) == 2, out)

        with open(project / doc, "a") as fh:
            fh.write("\nUnstamped fictional edit.\n")
        run(["git", "add", "-A"], project, env)
        rc, out = run(["git", "commit", "-q", "-m", "Edit without stamping"], project, env)
        check("hook rejects an edit that was not stamped", rc != 0 and "docs_stamp.py" in out, out)
        check("the rejected commit left history unchanged", commit_count(project, env) == 2)
        run(["git", "reset", "-q", "--hard", "HEAD"], project, env)

        if args.mode == "archive":
            run(["git", "init", "-q", "-b", "main"], fw, env)  # optional README step for contributors
        rc, out = run(["git", "add", "-A"], fw, env)
        check("git add -A in the framework succeeds", rc == 0, out)
        rc, staged = run(["git", "ls-files"], fw, env)
        names = staged.split()
        check("framework index never contains the independent project", not any(n == PROJECT or n.startswith(PROJECT + "/") for n in names), staged)
        check("framework still stages its own files", "README.md" in names and "_tools/selftest.py" in names, staged)
        rc, out = run(["git", "check-ignore", "-q", "--no-index", f"{PROJECT}/docs/hosts/fictional-nas.md"], fw, env)
        check("framework .gitignore ignores the project's documents", rc == 0, out)
        rc, out = run([sys.executable, "_tools/framework_guard.py"], fw, env)
        check("framework guard accepts the staged index", rc == 0, out)
        if args.mode == "archive":
            check("RELEASE-INFO.json is ignored by the framework repository (not staged)", "RELEASE-INFO.json" not in names, staged)
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    failed = RESULTS.count(False)
    print(f"\ninstall_check ({args.mode}): {len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
