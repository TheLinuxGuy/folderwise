#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Stamp a doc after editing it: updates `updated`, `updated_by`, and the Change Log.

  docs_stamp.py FILE --by codex/gpt-5.5 --summary "Add VLAN table" [--verified]
  docs_stamp.py NEW.md --init --type runbook --by claude/opus-5-5 --summary "Initial draft"
  docs_stamp.py FILE --toc ...      enable the optional generated table of contents (--no-toc removes it)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--by", required=True, help="'human' or '<agent>/<model>'")
    ap.add_argument("--summary", required=True, help="one-line description of the change")
    ap.add_argument("--verified", action="store_true", help="also set last_verified=today (only if you checked reality)")
    ap.add_argument("--init", action="store_true", help="create front matter if the file has none")
    ap.add_argument("--type", default="reference", dest="doc_type")
    ap.add_argument("--toc", action="store_true", help="enable the generated table of contents (sets toc: true)")
    ap.add_argument("--no-toc", action="store_true", help="remove the table of contents")
    args = ap.parse_args()

    if not dl.BY_RE.match(args.by):
        print("error: --by must be 'human' or '<agent>/<model>' (e.g. codex/gpt-5.5)", file=sys.stderr)
        return 2
    summary = dl.clean_summary(args.summary)
    if not summary:
        print("error: --summary is empty", file=sys.stderr)
        return 2

    if args.toc and args.no_toc:
        print("error: use only one of --toc / --no-toc", file=sys.stderr)
        return 2
    path = args.file.resolve()
    root = dl.find_project_root(path.parent)
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {path}", file=sys.stderr)
        return 2
    cfg = dl.load_config(root)
    try:
        new, errs, moment = dl.stamp_text(path.read_text(), path.name, cfg, args.by, summary,
                                          args.verified, args.init, args.doc_type,
                                          True if args.toc else False if args.no_toc else None)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    path.write_text(new)
    for e in errs:
        print(f"{path.relative_to(root)}: {e}", file=sys.stderr)
    print(f"stamped {path.relative_to(root)} ({args.by}, {dl.format_ts(moment)})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
