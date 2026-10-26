#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Validate doc front matter, Change Logs, tables and links between docs.

  docs_lint.py              lint every doc in the current project
  docs_lint.py FILE...      lint specific files
  docs_lint.py --staged     lint the complete staged doc graph (pre-commit); also requires
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
from docsource import DocumentSource  # noqa: E402


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


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

    if args.staged:
        found = git(Path.cwd(), "rev-parse", "--show-toplevel")
        root = Path(found.stdout.strip()) if found.returncode == 0 else None
    else:
        root = dl.find_project_root(Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
        return 2
    try:
        source = DocumentSource(root, staged=args.staged)
        config_text = source.read(dl.CONFIG_NAME)
        if config_text is None:
            raise ValueError(f"{dl.CONFIG_NAME} is missing from the document source")
        cfg = dl.parse_config(config_text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.files and not args.staged:
        files = [(f if not f.is_absolute() else f.relative_to(root)) for f in args.files]
    else:
        # Check the complete staged graph, including incoming links to deleted or renamed docs.
        files = source.docs(cfg)

    failures = 0
    for rel in files:
        text = source.read(rel.as_posix())
        errs, _ = lint_text(text, cfg, source.read)
        link_errs, link_warns = dl.link_findings(text, rel, cfg, source)
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
        for e in dx.index_errors(root, cfg, source=source):
            print(e)
            failures += 1
        if not args.staged and not args.files:
            for w in dx.orphans(root, cfg, source.read):
                print(f"WARN {w}", file=sys.stderr)

    if failures:
        print(f"\n{failures} of {len(files)} doc(s) failed. Fix with: docs_stamp.py <file> --by <agent>/<model> --summary \"...\" (front matter/Change Log) or render_tables.py --by ... --summary ... (tables)", file=sys.stderr)
        return 1
    print(f"ok: {len(files)} doc(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
