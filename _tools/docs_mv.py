#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Move or rename a doc/folder, or rename a heading, and keep every link valid.

  docs_mv.py mv SRC DST --by codex/gpt-5.5 [--dry-run]
      Moves a file or folder (git mv when tracked), rewrites links to it in every .md file
      (keeping #anchors), recomputes relative links inside the moved docs, updates
      `table:start src=` paths, stamps touched docs, then lints.
  docs_mv.py heading FILE "Old heading" "New heading" --by codex/gpt-5.5 [--nth N] [--dry-run]
      Renames a heading and rewrites #anchor links to it across the project.

Plain-text mentions and references in scripts or CSVs cannot be rewritten safely; they are listed
so you can fix them by hand.
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402
import docsextra as dx  # noqa: E402

TOOLS = Path(__file__).resolve().parent
PROTECTED = {"AGENTS.md", "CLAUDE.md", dl.CONFIG_NAME}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


class Fail(Exception):
    pass


# ---------- scanning helpers ----------

def blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def mask(text: str) -> str:
    """Same-length copy with front matter, code, generated blocks and comments blanked (offsets stay valid)."""
    text = dl.mask_for_links(text)
    for rx in (dl.TABLE_BLOCK_RE, CODE_SPAN_RE, COMMENT_RE):
        text = rx.sub(blank, text)
    return text


def walk_files(root: Path):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            yield Path(dirpath, f).relative_to(root).as_posix()


def parse_target(t: str, rel_dir: str):
    """(normalized project path, path text as written, fragment or None), or None for non-file links."""
    if not t or t.startswith("#") or dl.SCHEME_RE.match(t) or t.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", t):
        return None
    path, sep, frag = t.partition("#")
    norm = posixpath.normpath(posixpath.join(rel_dir, unquote(path)))
    if norm == ".." or norm.startswith("../"):
        return None
    return norm, path, (frag if sep else None)


def rewrite_links(text: str, rewriter) -> tuple[str, int]:
    masked, edits = mask(text), []
    for m in dl.LINK_RE.finditer(masked):
        raw = m.group(3)
        wrapped = raw.startswith("<") and raw.endswith(">")
        t = raw[1:-1] if wrapped else raw
        new = rewriter(t)
        if new is not None and new != t:
            edits.append((m.start(3), m.end(3), f"<{new}>" if wrapped else new))
            if m.group(2) == t:  # link text was the old path itself: keep it in sync
                edits.append((m.start(2), m.end(2), new))
    for s, e, r in sorted(edits, reverse=True):
        text = text[:s] + r + text[e:]
    return text, len(edits)


# ---------- shared apply step ----------

class Plan:
    def __init__(self, root: Path, cfg: dict):
        self.root, self.cfg = root, cfg
        self.moves: list[tuple[str, str]] = []          # (old rel, new rel) for every file that moves
        self.new_text: dict[str, str] = {}              # old rel -> rewritten text (only changed files)
        self.counts: dict[str, int] = {}                # old rel -> links rewritten
        self.summaries: dict[str, str] = {}             # old rel -> stamp summary
        self.notes: list[str] = []
        self.new_rel = {}                               # old rel -> new rel
        self.refresh_index = False                      # mv only: README index lists paths
        self.index_summary = ""

    def lintable(self, rel: str) -> bool:
        return rel.endswith(".md") and not dl.is_excluded(Path(rel), self.cfg)


def readme_index_enabled(root: Path) -> bool:
    p = root / "README.md"
    if not p.is_file():
        return False
    try:
        meta, body = dl.split_front_matter(p.read_text())
    except Exception:
        return False
    return meta is not None and dx.INDEX_RE.search(body) is not None


def refresh_readme_index(plan: Plan, by: str, already_stamped: bool) -> bool:
    """Rebuild the README index block (it lists doc paths). Stamps README unless this run already did."""
    return dx.refresh_readme_index(plan.root, plan.cfg, by, plan.index_summary, stamp=not already_stamped)


def finish(plan: Plan, by: str, dry: bool, do_move) -> int:
    root, cfg = plan.root, plan.cfg
    touched = sorted(set(plan.new_text) | {o for o, n in plan.moves if o.endswith(".md")})
    for old in touched:
        new = plan.new_rel.get(old, old)
        extra = f", {plan.counts[old]} link(s) rewritten" if plan.counts.get(old) else ""
        print(f"  {'moved ' if new != old else 'edited'} {old}" + (f" -> {new}" if new != old else "") + extra
              + ("  [stamp]" if plan.lintable(new) else ""))
    for n in plan.notes:
        print(n)
    index_on = plan.refresh_index and readme_index_enabled(root)
    if index_on:
        print("  README.md index block will be refreshed")
    if dry:
        print("dry run: nothing changed")
        return 0

    do_move()
    stamped, problems, stamped_paths = 0, [], set()
    for old in touched:
        new = plan.new_rel.get(old, old)
        path = root / new
        text = plan.new_text.get(old, path.read_text() if path.is_file() else "")
        if plan.lintable(new):
            try:
                text, errs, _ = dl.stamp_text(text, path.name, cfg, by, plan.summaries[old])
                stamped += 1
                stamped_paths.add(new)
                problems += [f"{new}: {e}" for e in errs]
            except ValueError:
                problems.append(f"{new}: no front matter, not stamped")
        path.write_text(text)
    if index_on and refresh_readme_index(plan, by, "README.md" in stamped_paths):
        stamped += "README.md" not in stamped_paths
        print("refreshed README index")
    print(f"stamped {stamped} doc(s)")
    for p in problems:
        print(f"WARN {p}", file=sys.stderr)
    rc = subprocess.run(["uv", "run", "--quiet", str(TOOLS / "docs_lint.py")], cwd=root).returncode
    print("lint: " + ("ok" if rc == 0 else "FAILED (see above)") + "; commit the move, link rewrites and stamps together")
    return rc


# ---------- mv ----------

def mapper(src: str, dst: str):
    def m(p: str) -> str:
        if p == src:
            return dst
        return dst + p[len(src):] if p.startswith(src + "/") else p
    return m


def plan_mv(root: Path, cfg: dict, src: str, dst: str, by: str) -> tuple[Plan, callable]:
    s, d = root / src, root / dst
    if Path(src).name in PROTECTED or ".git" in Path(src).parts:
        raise Fail(f"{src} cannot be moved with this tool")
    if not s.exists():
        raise Fail(f"source not found: {src}")
    if d.exists() and not (s.is_file() and d.is_file() and os.path.samefile(s, d) and src != dst):
        raise Fail(f"destination exists: {dst} (give the full new path, not a folder to move into)")
    if dst == src or dst.startswith(src + "/"):
        raise Fail("destination is the same as, or inside, the source")
    if ".." in Path(dst).parts or ".git" in Path(dst).parts:
        raise Fail("destination must be inside the project")
    mp = mapper(src, dst)
    plan = Plan(root, cfg)
    plan.refresh_index, plan.index_summary = True, f"Update index after moving {src} to {dst}"
    files = list(walk_files(root))
    plan.moves = [(f, mp(f)) for f in files if mp(f) != f]
    plan.new_rel = dict(plan.moves)

    for rel in (f for f in files if f.endswith(".md")):
        text = (root / rel).read_text()
        new_rel = mp(rel)
        odir, ndir = posixpath.dirname(rel), posixpath.dirname(new_rel)

        def rw(t, odir=odir, ndir=ndir):
            p = parse_target(t, odir)
            if not p or dl._exact_path(root, p[0]) is None:  # not a file link, or already broken: leave alone
                return None
            norm, path, frag = p
            new_norm = mp(norm)
            if new_norm == norm and ndir == odir:
                return None
            new_path = posixpath.relpath(new_norm, ndir or ".")
            if path.endswith("/") and not new_path.endswith("/"):
                new_path += "/"
            if posixpath.normpath(unquote(path)) == posixpath.normpath(new_path):
                return None
            if " " in new_path:
                new_path = quote(new_path, safe="/._-~")
            return new_path + ("#" + frag if frag is not None else "")

        new_text, n = rewrite_links(text, rw)

        def fix_src(m: re.Match) -> str:  # `table:start src=...` paths are project-relative
            a = dl.parse_attrs(m.group("attrs")).get("src")
            if a and mp(posixpath.normpath(a)) != posixpath.normpath(a):
                return m.group(0).replace(f"src={a}", f"src={mp(posixpath.normpath(a))}", 1)
            return m.group(0)

        fixed = dl.TABLE_BLOCK_RE.sub(fix_src, new_text)
        if fixed != new_text:
            n += 1
            new_text = fixed
        if new_text != text:
            plan.new_text[rel], plan.counts[rel] = new_text, n
            plan.summaries[rel] = f"Update links after moving {src} to {dst}"
        if new_rel != rel:
            plan.summaries[rel] = f"Moved from {rel}"

        # notes: links inside generated blocks cannot be hand-edited; plain-text mentions are not rewritten
        for blk in dl.TABLE_BLOCK_RE.finditer(text):
            for lm in dl.LINK_RE.finditer(blk.group(0)):
                p = parse_target(lm.group(3).strip("<>"), odir)
                if p and mp(p[0]) != p[0]:
                    plan.notes.append(f"NOTE {rel}: generated table block links to {p[0]}; fix the source CSV/script, then re-render")
        prose = re.sub(r"<!--.*?-->", blank, dl.LINK_RE.sub(" ", dl.CL_BLOCK_RE.sub(blank, dl.mask_for_links(text))), flags=re.S)
        for mm in dl.MENTION_RE.finditer(prose):
            for cand in (odir + "/" + mm.group(1), mm.group(1), "docs/" + mm.group(1)):
                hit = dl._exact_path(root, posixpath.normpath(cand))
                if hit and mp(hit.relative_to(root).as_posix()) != hit.relative_to(root).as_posix():
                    plan.notes.append(f"NOTE {rel}:{prose.count(chr(10), 0, mm.start()) + 1}: plain-text mention '{mm.group(1)}' not rewritten; update by hand")
                    break

    # other references to the old path (scripts, CSVs, code spans) that we did not rewrite
    shown = 0
    for rel in files:
        p = root / rel
        if p.stat().st_size > 2_000_000:
            continue
        try:
            text = dl.CL_BLOCK_RE.sub(blank, plan.new_text.get(rel) or p.read_text())  # Change Log is history
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if src in line and shown < 15:
                plan.notes.append(f"NOTE {rel}:{i}: still mentions '{src}'; update by hand if needed")
                shown += 1

    def do_move():
        d.parent.mkdir(parents=True, exist_ok=True)
        if (root / ".git").exists() and subprocess.run(["git", "mv", src, dst], cwd=root, capture_output=True).returncode == 0:
            return
        shutil.move(str(s), str(d))

    print(f"move {src} -> {dst}  ({len(plan.moves)} file(s))")
    return plan, do_move


# ---------- heading ----------

def plan_heading(root: Path, cfg: dict, file: str, old: str, new: str, nth: int) -> tuple[Plan, callable]:
    path = root / file
    if not path.is_file() or not file.endswith(".md"):
        raise Fail(f"not a markdown file: {file}")
    text = path.read_text()
    old_list = dl.heading_list(text)
    hits = [h for h in old_list if h[2] == old]
    if not hits:
        raise Fail(f"heading '{old}' not found in {file}")
    if len(hits) > 1 and nth == 0:
        raise Fail(f"{len(hits)} headings are named '{old}'; pass --nth 1..{len(hits)}")
    idx, level, _, _ = hits[(nth or 1) - 1]
    lines = text.split("\n")
    lines[idx] = f"{'#' * level} {new}"
    new_text = "\n".join(lines)
    new_list = dl.heading_list(new_text)
    amap = {o[3]: n[3] for o, n in zip(old_list, new_list) if o[3] != n[3]}
    if not amap:
        raise Fail("the new heading produces the same anchor; nothing to rewrite (edit the heading by hand)")

    plan = Plan(root, cfg)
    plan.new_text[file], plan.counts[file] = new_text, 0
    plan.summaries[file] = f"Rename heading '{old}' to '{new}'"
    for rel in (f for f in walk_files(root) if f.endswith(".md")):
        base = new_text if rel == file else (root / rel).read_text()
        odir = posixpath.dirname(rel)

        def rw(t, rel=rel, odir=odir):
            if t.startswith("#"):
                if rel != file:
                    return None
                path_txt, frag = "", t[1:]
            else:
                p = parse_target(t, odir)
                if not p or p[0] != file or p[2] is None:
                    return None
                path_txt, frag = p[1], p[2]
            fixed = amap.get(unquote(frag))
            return None if fixed is None else f"{path_txt}#{fixed}"

        out, n = rewrite_links(base, rw)
        if rel == file:
            plan.new_text[rel], plan.counts[rel] = out, n
        elif out != base:
            plan.new_text[rel], plan.counts[rel] = out, n
            plan.summaries[rel] = f"Update anchor links after renaming a heading in {file}"

    old_anchors = ", ".join(f"#{k}->#{v}" for k, v in amap.items())
    print(f"rename heading in {file}: '{old}' -> '{new}'  ({old_anchors})")
    return plan, lambda: None


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("mv", "heading"):
        sp = sub.add_parser(name)
        sp.add_argument("--by", required=True, help="'human' or '<agent>/<model>'")
        sp.add_argument("--dry-run", action="store_true")
        if name == "mv":
            sp.add_argument("src")
            sp.add_argument("dst")
        else:
            sp.add_argument("file")
            sp.add_argument("old")
            sp.add_argument("new")
            sp.add_argument("--nth", type=int, default=0, help="which heading when several share the name (1-based)")
    args = ap.parse_args()
    if not dl.BY_RE.match(args.by):
        print("error: --by must be 'human' or '<agent>/<model>'", file=sys.stderr)
        return 2
    root = dl.find_project_root(Path.cwd())
    if root is None:
        print(f"error: no {dl.CONFIG_NAME} found above {Path.cwd()}", file=sys.stderr)
        return 2
    cfg = dl.load_config(root)

    def rel(arg: str) -> str:
        try:
            return Path(os.path.abspath(arg)).relative_to(root).as_posix()
        except ValueError:
            raise Fail(f"{arg} is outside the project {root}")

    try:
        if args.cmd == "mv":
            plan, do_move = plan_mv(root, cfg, rel(args.src).rstrip("/"), rel(args.dst).rstrip("/"), args.by)
        else:
            plan, do_move = plan_heading(root, cfg, rel(args.file), args.old, args.new, args.nth)
    except Fail as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return finish(plan, args.by, args.dry_run, do_move)


if __name__ == "__main__":
    sys.exit(main())
