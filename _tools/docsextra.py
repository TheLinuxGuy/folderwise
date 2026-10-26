"""Human-readability helpers: byline, README index, orphan check, skeletons, recent changes.

Imported lazily by docslib.stamp_text and by docs_lint / docs_index / docs_new / docs_recent.
Callers must declare the `pyyaml` and `tzdata` dependencies.
"""
from __future__ import annotations

import datetime as dt
import posixpath
import re
from pathlib import Path

import docslib as dl
from docsource import DocumentSource

BYLINE_START, BYLINE_END = "<!-- byline:start -->", "<!-- byline:end -->"
BYLINE_RE = re.compile(r"\n*" + re.escape(BYLINE_START) + r"(.*?)" + re.escape(BYLINE_END) + r"\n*", re.S)
H1_RE = re.compile(r"^# .+$", re.M)
INDEX_START, INDEX_END = "<!-- index:start -->", "<!-- index:end -->"
INDEX_RE = re.compile(re.escape(INDEX_START) + r"(.*?)" + re.escape(INDEX_END), re.S)
CONTENTS_RE = re.compile(r"^## Contents[ \t]*\n(.*?)(?=^## |\Z)", re.S | re.M)
PLACEHOLDER = "TODO: fill in"
SKELETON_DIRS = ("_skeletons",)  # project override, checked before the shared _tools/skeletons


# --- byline: a visible one-line status under the H1 (front matter is hidden in the VS Code preview) ---

def byline_line(meta: dict, cfg: dict) -> str:
    """Status and last update only; verification, review dates and sensitivity stay in the front matter."""
    return (f"> **Status:** {meta.get('status', '?')} · "
            f"**Updated:** {dl.as_date(meta.get('updated'))} by {meta.get('updated_by')}")


def byline_block(meta: dict, cfg: dict) -> str:
    return f"{BYLINE_START}\n{byline_line(meta, cfg)}\n{BYLINE_END}"


def apply_byline(body: str, meta: dict, cfg: dict) -> str:
    """Insert/refresh the byline right under the first H1 (or remove it when `byline` is off)."""
    if not cfg.get("byline", False):
        return BYLINE_RE.sub("\n\n", body, count=1)
    block = byline_block(meta, cfg)
    if BYLINE_RE.search(body):
        return BYLINE_RE.sub(lambda _: f"\n\n{block}\n\n", body, count=1)
    m = H1_RE.search(body)
    if m:
        return body[:m.end()] + f"\n\n{block}\n\n" + body[m.end():].lstrip("\n")
    return f"{block}\n\n" + body.lstrip("\n")


def byline_errors(meta: dict | None, body: str, cfg: dict) -> list[str]:
    if meta is None:
        return []
    found = BYLINE_RE.search(body)
    if not cfg.get("byline", False):
        return ["byline block present but `byline` is off in .docs.yaml"] if found else []
    if not found:
        return ["byline missing (run docs_stamp.py)"]
    if found.group(1).strip() != byline_line(meta, cfg):
        return ["byline is out of date vs front matter (run docs_stamp.py)"]
    return []


def placeholder_warnings(meta: dict | None, text: str) -> list[str]:
    if meta and meta.get("status") != "draft" and PLACEHOLDER in text:
        return [f"contains unfilled placeholder {PLACEHOLDER} but status is {meta.get('status')}; fill it in or keep status: draft"]
    return []


# --- catalogue + README index ----------------------------------------------

def catalogue(root: Path, cfg: dict, readme_name: str = "README.md", source: DocumentSource | None = None) -> list[dict]:
    source = source if source is not None else DocumentSource(root)
    rows = []
    for rel in source.docs(cfg):
        if rel.as_posix() == readme_name:
            continue
        try:
            meta, _ = dl.split_front_matter(source.read(rel.as_posix()))
        except Exception:
            continue
        if meta:
            rows.append(dict(rel=rel, meta=meta))
    rows.sort(key=lambda r: (r["rel"].parent.as_posix(), r["rel"].name))
    return rows


def index_entries(root: Path, cfg: dict, source: DocumentSource | None = None) -> str:
    rows = catalogue(root, cfg, source=source)
    if not rows:
        return "No docs yet."
    out, last_dir = [], None
    for r in rows:
        d = r["rel"].parent.as_posix()
        if d != last_dir:
            out.append(f"- **{d + '/' if d != '.' else './'}**")
            last_dir = d
        m = r["meta"]
        blurb = f" - {m['summary']}" if m.get("summary") else ""
        out.append(f"  - [{m.get('title', r['rel'].stem)}]({r['rel'].as_posix()}){blurb} ({m.get('doc_type')}, {m.get('status')})")
    return "\n".join(out)


def index_block(root: Path, cfg: dict) -> str:
    return f"{INDEX_START}\n{index_entries(root, cfg)}\n{INDEX_END}"


def apply_index(readme_body: str, root: Path, cfg: dict) -> str:
    """Refresh the index block, adopting an existing `## Contents` section or creating one."""
    block = index_block(root, cfg)
    if INDEX_RE.search(readme_body):
        return INDEX_RE.sub(lambda _: block, readme_body, count=1)
    m = CONTENTS_RE.search(readme_body)
    if m:
        return readme_body[:m.start(1)] + f"\n{block}\n\n" + readme_body[m.end(1):]
    h = re.search(r"^## ", readme_body, re.M)
    pos = h.start() if h else len(readme_body)
    return readme_body[:pos] + f"## Contents\n\n{block}\n\n" + readme_body[pos:]


def refresh_readme_index(root: Path, cfg: dict, by: str, summary: str, stamp: bool = True) -> bool:
    """Rebuild the README index block if the README has one. Stamps README unless stamp=False."""
    import sys
    path = root / "README.md"
    if not path.is_file():
        return False
    try:
        meta, body = dl.split_front_matter(path.read_text())
    except Exception:
        return False
    if meta is None or not INDEX_RE.search(body):
        return False
    new_body = apply_index(body, root, cfg)
    if new_body == body:
        return False
    text = dl.join_front_matter(meta, new_body)
    if stamp:
        text, errs, _ = dl.stamp_text(text, "README.md", cfg, by, summary)
        for e in errs:
            print(f"WARN README.md: {e}", file=sys.stderr)
    path.write_text(text)
    return True


def index_errors(root: Path, cfg: dict, readme: str = "README.md", source: DocumentSource | None = None) -> list[str]:
    source = source if source is not None else DocumentSource(root)
    if not source.is_file(readme):
        return []
    try:
        _, body = dl.split_front_matter(source.read(readme))
    except Exception:
        return []
    m = INDEX_RE.search(body)
    if m and m.group(1).strip() != index_entries(root, cfg, source):
        return [f"{readme}: index block is out of date (run docs_index.py --write --by ... --summary ...)"]
    return []


# --- orphan docs ------------------------------------------------------------

def orphans(root: Path, cfg: dict, read) -> list[str]:
    docs = dl.iter_docs(root, cfg)
    names = {d.as_posix() for d in docs}
    inbound: dict[str, set[str]] = {n: set() for n in names}
    for rel in docs:
        text = read(rel.as_posix())
        if text is None:
            continue
        scan = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), dl.mask_for_links(text))
        for m in dl.LINK_RE.finditer(scan):
            t = m.group(3)[1:-1] if m.group(3).startswith("<") else m.group(3)
            if not t or t.startswith("#") or dl.SCHEME_RE.match(t) or t.startswith("/"):
                continue
            norm = posixpath.normpath(posixpath.join(rel.parent.as_posix(), dl.unquote(t.partition("#")[0])))
            if norm in names and norm != rel.as_posix():
                inbound[norm].add(rel.as_posix())
    return [f"{n}: no other doc links here (orphan); add it to the README index or a related doc"
            for n in sorted(names) if n != "README.md" and not inbound[n]]


# --- skeletons --------------------------------------------------------------

def skeleton_for(doc_type: str, root: Path, tools_dir: Path) -> str | None:
    for base in [root / d for d in SKELETON_DIRS] + [tools_dir / "skeletons"]:
        p = base / f"{doc_type}.md"
        if p.is_file():
            return p.read_text()
    return None


# --- recent changes across docs ---------------------------------------------

def row_moment(ts: str, cfg: dict) -> dt.datetime | None:
    m = dl.ROW_TS_RE.match(ts)
    if not m:
        return None
    tz = dl.project_tz(cfg)
    naive = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    for fold in (0, 1):
        cand = naive.replace(tzinfo=tz, fold=fold)
        if cand.strftime("%Z") == m.group(3):
            return cand
    return naive.replace(tzinfo=tz)


def recent_changes(root: Path, cfg: dict, since: dt.datetime) -> list[tuple[dt.datetime, str, str, str, str]]:
    out = []
    for rel in dl.iter_docs(root, cfg):
        try:
            _, body = dl.split_front_matter((root / rel).read_text())
        except Exception:
            continue
        for ts, by, summary in dl.parse_changelog(body) or []:
            moment = row_moment(ts, cfg)
            if moment and moment >= since:
                out.append((moment, ts, by, f"{root.name}/{rel.as_posix()}", summary))
    return out
