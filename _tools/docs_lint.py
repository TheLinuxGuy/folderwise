#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Validate doc front matter, Change Logs, tables and links between docs.

  docs_lint.py              lint every doc in the current project
  docs_lint.py FILE...      lint specific files
  docs_lint.py --staged     lint staged .md files (pre-commit); also requires
                            that edited docs got a new Change Log entry
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsextra as dx  # noqa: E402
import docslib as dl  # noqa: E402


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def staged_docs(root: Path, cfg: dict) -> list[Path]:
    out = git(root, "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z").stdout
    paths = [Path(p) for p in out.split("\0") if p.endswith(".md")]
    return [p for p in paths if not dl.is_excluded(p, cfg)]


def lint_text(text: str, cfg: dict, read_src) -> tuple[list[str], str]:
    try:
        meta, body = dl.split_front_matter(text)
    except Exception as e:  # malformed YAML
        return [f"front matter error: {e}"], ""
    return dl.validate(meta, body, cfg) + dl.table_errors(body, cfg, read_src) + dx.byline_errors(meta, body, cfg), body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--staged", action="store_true")
    args = ap.parse_args()

    root = dl.find_project_root(Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
        return 2
    cfg = dl.load_config(root)

    def read_disk(rel: str) -> str | None:
        p = root / rel
        return p.read_text() if p.is_file() else None

    def read_index(rel: str) -> str | None:  # staged version of a file
        r = git(root, "show", f":{rel}")
        return r.stdout if r.returncode == 0 else None

    read_src = read_index if args.staged else read_disk
    if args.staged:
        staged_all = git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMD", "-z").stdout.split("\0")
        # a changed CSV can make any doc's generated block stale, so lint every doc then
        files = dl.iter_docs(root, cfg) if any(p.endswith(".csv") for p in staged_all) else staged_docs(root, cfg)
    elif args.files:
        files = [(f if not f.is_absolute() else f.relative_to(root)) for f in args.files]
    else:
        files = dl.iter_docs(root, cfg)

    failures = 0
    for rel in files:
        if args.staged:
            shown = git(root, "show", f":{rel}")
            if shown.returncode != 0:  # not in the index (untracked, unstaged): not part of this commit
                continue
            text = shown.stdout
        else:
            text = (root / rel).read_text()
        errs, _ = lint_text(text, cfg, read_src)
        link_errs, link_warns = dl.link_findings(text, rel, root, cfg, read_src)
        errs += link_errs
        for w in link_warns:  # warning only: does not fail the check
            print(f"WARN {rel}: {w}", file=sys.stderr)
        try:
            doc_meta = dl.split_front_matter(text)[0]
        except Exception:
            doc_meta = None
        for w in dx.placeholder_warnings(doc_meta, text):
            print(f"WARN {rel}: {w}", file=sys.stderr)
        if args.staged and not errs:
            head = git(root, "show", f"HEAD:{rel}")
            if head.returncode == 0 and head.stdout != text and \
                    dl.changelog_block(head.stdout) == dl.changelog_block(text):
                errs.append("edited but Change Log unchanged (run docs_stamp.py)")
        for e in errs:
            print(f"{rel}: {e}")
        limit = cfg.get("max_doc_lines", dl.DEFAULT_MAX_LINES)
        if text.count("\n") > limit:  # warning only: does not fail the check
            print(f"WARN {rel}: {text.count(chr(10))} lines (> {limit}); split append-only history by period", file=sys.stderr)
        failures += bool(errs)

    if files:  # project-wide checks: README index must be current; docs nobody links to are flagged
        for e in dx.index_errors(root, cfg):
            print(e)
            failures += 1
        if not args.staged and not args.files:
            for w in dx.orphans(root, cfg, read_src):
                print(f"WARN {w}", file=sys.stderr)

    if failures:
        print(f"\n{failures} of {len(files)} doc(s) failed. Fix with: docs_stamp.py <file> --by <agent>/<model> --summary \"...\" (front matter/Change Log) or render_tables.py --by ... --summary ... (tables)", file=sys.stderr)
        return 1
    print(f"ok: {len(files)} doc(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
