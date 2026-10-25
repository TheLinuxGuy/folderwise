#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Catalogue of docs, and the generated index in README.md.

  docs_index.py                         print one line per doc (path, type, status, dates, summary).
                                        Agents: run this instead of opening files to see what exists.
  docs_index.py --all                   same for every project
  docs_index.py --write --by X --summary "..."
                                        refresh the index between <!-- index:start --> and <!-- index:end -->
                                        in README.md (adopts an existing `## Contents` section, or creates one)
                                        and stamp the README
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsextra as dx  # noqa: E402
import docslib as dl  # noqa: E402


def print_catalogue(root: Path) -> None:
    cfg = dl.load_config(root)
    rows = dx.catalogue(root, cfg)
    print(f"# {root.name}: {len(rows)} doc(s)")
    for r in rows:
        m = r["meta"]
        ver = dl.as_date(m.get("last_verified")) or "never"
        line = (f"{r['rel'].as_posix()}  [{m.get('doc_type')}/{m.get('status')}]  {m.get('title')}  "
                f"upd {dl.as_date(m.get('updated'))} ver {ver}")
        print(line + (f"  :: {m['summary']}" if m.get("summary") else ""))


def write_index(root: Path, by: str, summary: str) -> int:
    cfg = dl.load_config(root)
    path = root / "README.md"
    if not path.is_file():
        print("error: no README.md in this project", file=sys.stderr)
        return 2
    meta, body = dl.split_front_matter(path.read_text())
    if meta is None:
        print("error: README.md has no front matter (run docs_stamp.py --init)", file=sys.stderr)
        return 2
    new_body = dx.apply_index(body, root, cfg)
    if new_body == body:
        print("index already up to date")
        return 0
    new, errs, moment = dl.stamp_text(dl.join_front_matter(meta, new_body), "README.md", cfg, by, summary)
    path.write_text(new)
    for e in errs:
        print(f"README.md: {e}", file=sys.stderr)
    print(f"index written; stamped README.md ({by}, {dl.format_ts(moment)})")
    return 1 if errs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--by")
    ap.add_argument("--summary", default="Refresh docs index")
    args = ap.parse_args()

    if args.all and args.write:
        print("error: --write works on one project at a time", file=sys.stderr)
        return 2
    if args.all:
        for root in dl.all_projects(Path(__file__).resolve().parent):
            print_catalogue(root)
        return 0
    root = dl.find_project_root(Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
        return 2
    if args.write:
        if not args.by or not dl.BY_RE.match(args.by):
            print("error: --write needs --by 'human' or '<agent>/<model>'", file=sys.stderr)
            return 2
        return write_index(root, args.by, dl.clean_summary(args.summary))
    print_catalogue(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
