#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Render CSV-backed tables inside markdown docs, then stamp the docs that changed.

A doc embeds a table with a generated block:

  <!-- table:start src=data/lots.csv cols=id,symbol where=acct=0001 sort=-date -->
  <!-- table:end -->

  render_tables.py --by codex/gpt-5.5 --summary "Add Q3 sales"   render all docs, stamp changed ones
  render_tables.py FILE... --by ... --summary ... [--verified]    only these docs
  render_tables.py --check                                        report stale blocks, exit 1 if any
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--by", help="'human' or '<agent>/<model>' (required unless --check)")
    ap.add_argument("--summary", help="Change Log summary for every doc changed")
    ap.add_argument("--verified", action="store_true", help="also set last_verified=today (only if you checked reality)")
    args = ap.parse_args()

    root = dl.find_project_root(Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
        return 2
    cfg = dl.load_config(root)

    def read_src(rel: str) -> str | None:
        p = root / rel
        return p.read_text() if p.is_file() else None

    if args.files:
        docs = [f.resolve().relative_to(root) for f in args.files]
    else:
        docs = [d for d in dl.iter_docs(root, cfg) if dl.TABLE_BLOCK_RE.search((root / d).read_text())]

    pending, failed = [], False
    for rel in docs:
        text = (root / rel).read_text()
        new, errs = dl.render_blocks(text, read_src)
        for e in errs:
            print(f"{rel}: {e}", file=sys.stderr)
        failed |= bool(errs)
        if not errs and new != text:
            pending.append((rel, new))

    if args.check:
        for rel, _ in pending:
            print(f"{rel}: generated table block(s) out of date")
        print("ok: tables current" if not (pending or failed) else "", end="\n" if not (pending or failed) else "")
        return 1 if (pending or failed) else 0
    if failed:
        return 1
    if not pending:
        print("tables already current")
        return 0
    if not args.by or not args.summary or not dl.BY_RE.match(args.by):
        print("error: tables need re-rendering; pass --by <agent>/<model> and --summary \"...\"", file=sys.stderr)
        for rel, _ in pending:
            print(f"  would change: {rel}", file=sys.stderr)
        return 2

    for rel, new in pending:
        stamped, errs, moment = dl.stamp_text(new, rel.name, cfg, args.by, args.summary, args.verified)
        (root / rel).write_text(stamped)
        for e in errs:
            print(f"{rel}: {e}", file=sys.stderr)
        print(f"rendered + stamped {rel} ({dl.format_ts(moment)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
