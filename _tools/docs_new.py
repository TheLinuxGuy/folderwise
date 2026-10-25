#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Create a new doc from a skeleton for its type, with front matter, byline and Change Log.

  docs_new.py docs/hosts/nas.md --type inventory --title "NAS inventory" \\
      --about "Disks, volumes and shares on the NAS" --by codex/gpt-5.5

Types: overview, reference, runbook, decision, inventory, plan, log. Skeletons live in
_tools/skeletons/<type>.md; a project can override one with _skeletons/<type>.md.
New docs start as `status: draft`. Placeholders look like TODO: fill in; lint warns if an
active doc still has them. The README index is refreshed automatically; after changing a doc's status, title or summary run docs_index.py --write ...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsextra as dx  # noqa: E402
import docslib as dl  # noqa: E402

TOOLS = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--type", required=True, dest="doc_type", choices=dl.DOC_TYPES)
    ap.add_argument("--title")
    ap.add_argument("--about", help="one-line summary (front matter `summary`, shown in the README index)")
    ap.add_argument("--by", required=True, help="'human' or '<agent>/<model>'")
    ap.add_argument("--summary", default="Initial draft", help="Change Log summary")
    ap.add_argument("--toc", action="store_true", help="enable the optional table of contents")
    args = ap.parse_args()

    if not dl.BY_RE.match(args.by):
        print("error: --by must be 'human' or '<agent>/<model>' (e.g. codex/gpt-5.5)", file=sys.stderr)
        return 2
    path = args.path.resolve()
    root = dl.find_project_root(path.parent if path.parent.exists() else Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {path}", file=sys.stderr)
        return 2
    cfg = dl.load_config(root)
    if path.suffix != ".md":
        print("error: path must end in .md", file=sys.stderr)
        return 2
    if path.exists():
        print(f"error: {path.relative_to(root)} already exists; edit it and use docs_stamp.py", file=sys.stderr)
        return 1
    if args.doc_type not in cfg.get("doc_types", dl.DOC_TYPES):
        print(f"error: doc type {args.doc_type!r} is not enabled in {dl.CONFIG_NAME}", file=sys.stderr)
        return 2
    skeleton = dx.skeleton_for(args.doc_type, root, TOOLS)
    if skeleton is None:
        print(f"error: no skeleton for type {args.doc_type!r}", file=sys.stderr)
        return 2

    title = args.title or path.stem.replace("-", " ").replace("_", " ").title()
    body = skeleton.replace("{{TITLE}}", title)
    meta = dl.default_meta(path.name, body, cfg, args.doc_type, dl.today(cfg))
    meta["title"] = title
    if args.about:
        meta["summary"] = " ".join(args.about.split())
    path.parent.mkdir(parents=True, exist_ok=True)
    new, errs, moment = dl.stamp_text(dl.join_front_matter(meta, body), path.name, cfg, args.by,
                                      dl.clean_summary(args.summary), toc=True if args.toc else None)
    path.write_text(new)
    rel = path.relative_to(root)
    for e in errs:
        print(f"{rel}: {e}", file=sys.stderr)
    print(f"created {rel} ({args.doc_type}, draft; {args.by}, {dl.format_ts(moment)})")
    if dx.refresh_readme_index(root, cfg, args.by, f"Add {rel.as_posix()} to index"):
        print("README index refreshed")
    print("Next: replace every 'TODO: fill in', set status: active and re-stamp, then `docs_index.py --write --by ... --summary ...` (the index shows status and summary).")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
