#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""List docs overdue for re-verification (last_verified, or created if never verified, + review_every).

  docs_stale.py                 current project
  docs_stale.py --all           every project under Folderwise
  docs_stale.py --within 14     also include docs falling due in the next 14 days
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402


def stale_in(root: Path, within: int) -> list[tuple[int, str, str]]:
    cfg = dl.load_config(root)
    today = dl.today(cfg)  # project timezone, not the machine's
    out = []
    for rel in dl.iter_docs(root, cfg):
        try:
            meta, _ = dl.split_front_matter((root / rel).read_text())
        except Exception:
            continue
        if not meta or meta.get("status") in ("deprecated", "archived"):
            continue
        interval = dl.parse_interval(meta.get("review_every", ""))
        base = dl.as_date(meta.get("last_verified")) or dl.as_date(meta.get("created"))
        if not interval or not base:
            continue
        days_over = (today - (base + interval)).days
        if days_over >= -within:
            kind = "never verified" if not meta.get("last_verified") else f"verified {base}"
            out.append((days_over, f"{root.name}/{rel}", kind))
    return sorted(out, reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--within", type=int, default=0, metavar="DAYS")
    ap.add_argument("--fail", action="store_true", help="exit 1 if anything is overdue")
    args = ap.parse_args()

    if args.all:
        roots = dl.all_projects(Path(__file__).resolve().parent)
    else:
        r = dl.find_project_root(Path.cwd())
        if r is None:
            print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
            return 2
        roots = [r]

    rows = [row for r in roots for row in stale_in(r, args.within)]
    for days_over, path, kind in rows:
        state = f"{days_over}d overdue" if days_over >= 0 else f"due in {-days_over}d"
        print(f"{state:>14}  {path}  ({kind})")
    if not rows:
        print("nothing overdue")
    return 1 if (rows and args.fail and any(r[0] >= 0 for r in rows)) else 0


if __name__ == "__main__":
    sys.exit(main())
