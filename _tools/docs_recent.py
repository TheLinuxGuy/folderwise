#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""What changed lately? Merge every doc's Change Log into one newest-first list (no git needed).

  docs_recent.py                 last 7 days, current project
  docs_recent.py --since 30d     d/w/m intervals, like review_every
  docs_recent.py --all           every project under Folderwise
  docs_recent.py --by codex      only rows whose author contains 'codex'
  docs_recent.py --limit 20

Each doc keeps only its last 10 Change Log rows, so very old activity may be missing; use `git log` for that.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsextra as dx  # noqa: E402
import docslib as dl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="7d", metavar="INTERVAL")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--by", default="", help="substring filter on the author")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    interval = dl.parse_interval(args.since)
    if interval is None:
        print("error: --since must look like 7d, 2w or 1m", file=sys.stderr)
        return 2
    if args.all:
        roots = dl.all_projects(Path(__file__).resolve().parent)
    else:
        r = dl.find_project_root(Path.cwd())
        if r is None:
            print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
            return 2
        roots = [r]

    rows = []
    for root in roots:
        cfg = dl.load_config(root)
        rows += dx.recent_changes(root, cfg, dl.now(cfg) - interval)
    rows = sorted((r for r in rows if args.by in r[2]), key=lambda r: r[0], reverse=True)
    total, docs = len(rows), len({r[3] for r in rows})
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print(f"no changes in the last {args.since}")
        return 0
    for _, ts, by, path, summary in rows:
        print(f"{ts}  {by:<18} {path}  {summary}")
    print(f"\n{total} change(s) across {docs} doc(s) in the last {args.since}" + (f" (showing {len(rows)})" if len(rows) < total else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
