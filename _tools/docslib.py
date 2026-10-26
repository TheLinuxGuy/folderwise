"""Shared helpers for the docs tools. Callers must declare the `pyyaml` dependency."""
from __future__ import annotations

import csv
import datetime as dt
import fnmatch
import io
import os
import posixpath
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext
from urllib.parse import unquote
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

if TYPE_CHECKING:
    from docsource import DocumentSource

CONFIG_NAME = ".docs.yaml"
CL_START, CL_END = "<!-- changelog:start -->", "<!-- changelog:end -->"
CL_HEADING = "## Change Log"
CL_HEADER = "| When | By | Summary |\n|------|----|---------|"
MAX_LOG_ROWS = 10
DEFAULT_TZ = "America/Los_Angeles"

CORE_FIELDS = [
    "title", "doc_type", "status", "sensitivity", "owner", "created",
    "updated", "updated_by", "last_verified", "review_every", "tags",
]
OPTIONAL_FIELDS = ["toc", "summary"]
DOC_TYPES = ["overview", "reference", "runbook", "decision", "inventory", "plan", "log"]
STATUSES = ["draft", "active", "deprecated", "archived"]
DEFAULT_MAX_LINES = 400
SENSITIVITIES = ["public", "private", "restricted"]
DEFAULT_EXCLUDES = ["AGENTS.md", "CLAUDE.md", "_*", ".*", "node_modules"]

BY_RE = re.compile(r"^(human|[a-z][a-z0-9_-]*/[A-Za-z0-9._-]+)$")
INTERVAL_RE = re.compile(r"^(\d+)([dwm])$")
FM_RE = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
CL_BLOCK_RE = re.compile(re.escape(CL_START) + r"(.*?)" + re.escape(CL_END), re.S)
TOC_START, TOC_END = "<!-- toc:start -->", "<!-- toc:end -->"
TOC_BLOCK_RE = re.compile(re.escape(TOC_START) + r"(.*?)" + re.escape(TOC_END), re.S)
TOC_SECTION_RE = re.compile(r"^## Contents[ \t]*\n+" + re.escape(TOC_START) + r".*?" + re.escape(TOC_END) + r"\n*", re.S | re.M)
TOC_SKIP = {"Contents", "Change Log"}
DEFAULT_TOC_DEPTH = 2
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
ROW_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROW_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) ([A-Za-z0-9+-]{1,6})$")


# --- front matter -----------------------------------------------------------

def split_front_matter(text: str) -> tuple[dict | None, str]:
    m = FM_RE.match(text)
    if not m:
        return None, text
    meta = yaml.safe_load(m.group(1))
    if not isinstance(meta, dict):
        raise ValueError("front matter is not a YAML mapping")
    return meta, text[m.end():]


def order_meta(meta: dict) -> dict:
    ordered = {k: meta[k] for k in CORE_FIELDS + OPTIONAL_FIELDS if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    return ordered


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # keep `created`/`updated` as plain dates, not &anchors
        return True


def join_front_matter(meta: dict, body: str) -> str:
    dumped = yaml.dump(order_meta(meta), Dumper=_NoAliasDumper, sort_keys=False,
                       allow_unicode=True, default_flow_style=None, width=1000)
    return f"---\n{dumped}---\n{body}"


# --- change log -------------------------------------------------------------

def changelog_block(text: str) -> str | None:
    m = CL_BLOCK_RE.search(text)
    return m.group(1).strip() if m else None


def parse_changelog(body: str) -> list[tuple[str, str, str]] | None:
    block = changelog_block(body)
    if block is None:
        return None
    rows = []
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and ROW_TS_RE.match(cells[0]):
            rows.append((cells[0], cells[1], " | ".join(cells[2:])))
    return rows


def clean_summary(s: str) -> str:
    return " ".join(s.replace("|", "/").split())


def set_changelog(body: str, rows: list[tuple[str, str, str]]) -> str:
    lines = "\n".join(f"| {d} | {b} | {s} |" for d, b, s in rows)
    block = f"{CL_START}\n{CL_HEADER}\n{lines}\n{CL_END}"
    if CL_BLOCK_RE.search(body):
        return CL_BLOCK_RE.sub(lambda _: block, body, count=1)
    return body.rstrip("\n") + f"\n\n{CL_HEADING}\n\n{block}\n"


# --- optional table of contents (front matter `toc: true`) ---------------

def slugify(text: str) -> str:
    """GitHub-style heading anchor (also what VS Code and Forgejo use)."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("*", "")
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def heading_list(text: str) -> list[tuple[int, int, str, str]]:
    """(line index, level, title, anchor), using one fence and duplicate-heading policy."""
    seen: dict[str, int] = {}
    headings = []
    for i, line in enumerate(mask_for_links(text).splitlines()):
        m = HEADING_RE.match(line)
        if m:
            title = m.group(2).strip()
            base = slugify(title)
            n = seen.get(base, 0)
            seen[base] = n + 1
            headings.append((i, len(m.group(1)), title, base if n == 0 else f"{base}-{n}"))
    return headings


def toc_lines(body: str, depth: int = DEFAULT_TOC_DEPTH) -> list[str]:
    """Bullet lines for prose headings H2..H<depth>, excluding generated section titles."""
    return [f"{'  ' * (level - 2)}- [{title}](#{anchor})"
            for _, level, title, anchor in heading_list(body)
            if 2 <= level <= depth and title not in TOC_SKIP]


def toc_entries(body: str, depth: int) -> str:
    return "\n".join(toc_lines(body, depth)) or "No sections yet."


def toc_block(body: str, depth: int) -> str:
    return f"{TOC_START}\n{toc_entries(body, depth)}\n{TOC_END}"


def apply_toc(body: str, enabled: bool, depth: int = DEFAULT_TOC_DEPTH) -> str:
    """Insert/refresh the TOC when enabled; remove it when not."""
    if not enabled:
        return TOC_SECTION_RE.sub("", body, count=1)
    block = toc_block(body, depth)
    if TOC_BLOCK_RE.search(body):
        return TOC_BLOCK_RE.sub(lambda _: block, body, count=1)
    m = re.search(r"^## (?!Contents\b)", mask_for_links(body), re.M)
    pos = m.start() if m else len(body)
    return body[:pos] + f"## Contents\n\n{block}\n\n" + body[pos:]


# --- dates ------------------------------------------------------------------

def as_date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str) and ROW_DATE_RE.match(v):
        try:
            return dt.date.fromisoformat(v)
        except ValueError:
            return None
    return None


def parse_interval(s: str) -> dt.timedelta | None:
    m = INTERVAL_RE.match(str(s))
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return dt.timedelta(days={"d": 1, "w": 7, "m": 30}[unit] * n)


# --- project time (never the machine's local timezone) --------------------

def project_tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg.get("timezone", DEFAULT_TZ))


def now(cfg: dict) -> dt.datetime:
    fake = os.environ.get("DOCS_FAKE_NOW")  # demos/tests only: 'YYYY-MM-DDTHH:MM' in project time
    if fake:
        return dt.datetime.fromisoformat(fake).replace(tzinfo=project_tz(cfg))
    return dt.datetime.now(project_tz(cfg))


def today(cfg: dict) -> dt.date:
    return now(cfg).date()


def format_ts(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M %Z")


def check_ts(ts: str, cfg: dict) -> str | None:
    """Return an error message if a Change Log timestamp is malformed, in the future, or has the wrong zone abbreviation."""
    m = ROW_TS_RE.match(ts)
    if not m:
        return f"bad timestamp {ts!r} (want YYYY-MM-DD HH:MM TZ)"
    tz = project_tz(cfg)
    try:
        naive = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    except ValueError:
        return f"bad timestamp {ts!r}"
    candidates = [naive.replace(tzinfo=tz, fold=f) for f in (0, 1)]
    match = [c for c in candidates if c.strftime("%Z") == m.group(3)]
    if not match:
        return f"timestamp {ts!r}: zone should be {candidates[0].strftime('%Z')} for {tz.key}"
    if match[0] > now(cfg) + dt.timedelta(minutes=2):
        return f"timestamp {ts!r} is in the future"
    return None


# --- project discovery ------------------------------------------------------

def find_project_root(start: Path) -> Path | None:
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / CONFIG_NAME).is_file():
            return p
    return None


def parse_config(text: str) -> dict:
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid project YAML: {exc}") from None
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError("project config must be a YAML mapping")
    try:
        ZoneInfo(cfg.get("timezone", DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError(f"unknown timezone {cfg.get('timezone')!r} (use an IANA name like {DEFAULT_TZ})") from None
    return cfg


def load_config(root: Path) -> dict:
    try:
        return parse_config((root / CONFIG_NAME).read_text())
    except (ValueError, yaml.YAMLError) as exc:
        raise SystemExit(f"{root / CONFIG_NAME}: {exc}") from None


def is_excluded(rel: Path, cfg: dict) -> bool:
    pats = cfg.get("exclude", DEFAULT_EXCLUDES)
    return any(fnmatch.fnmatch(part, pat) for part in rel.parts for pat in pats)


def iter_docs(root: Path, cfg: dict) -> list[Path]:
    found = []
    for dirpath, dirs, files in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirs[:] = sorted(d for d in dirs if not is_excluded(rel_dir / d, cfg))
        for f in sorted(files):
            rel = rel_dir / f
            if f.endswith(".md") and not is_excluded(rel, cfg):
                found.append(rel)
    return found


def all_projects(tools_dir: Path) -> list[Path]:
    base = tools_dir.parent
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and (p / CONFIG_NAME).is_file())


# --- validation -------------------------------------------------------------

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str) and v.strip() != "",
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "date": lambda v: as_date(v) is not None,
}


def validate(meta: dict | None, body: str, cfg: dict) -> list[str]:
    if meta is None:
        return ["missing YAML front matter"]
    errs: list[str] = []
    extra = cfg.get("extra_fields") or {}
    for k in CORE_FIELDS:
        if k not in meta:
            errs.append(f"missing field: {k}")
    for k in meta:
        if k not in CORE_FIELDS and k not in OPTIONAL_FIELDS and k not in extra:
            errs.append(f"unknown field: {k} (declare it under extra_fields in {CONFIG_NAME})")

    def check_enum(key, allowed):
        if key in meta and meta[key] not in allowed:
            errs.append(f"{key}: {meta[key]!r} not in {allowed}")

    check_enum("doc_type", cfg.get("doc_types", DOC_TYPES))
    check_enum("status", STATUSES)
    check_enum("sensitivity", SENSITIVITIES)
    for k in ("title", "owner"):
        if k in meta and not _TYPE_CHECKS["string"](meta[k]):
            errs.append(f"{k}: must be a non-empty string")
    if "updated_by" in meta and not (isinstance(meta["updated_by"], str) and BY_RE.match(meta["updated_by"])):
        errs.append("updated_by: must be 'human' or '<agent>/<model>' (e.g. codex/gpt-5.5)")
    if "review_every" in meta and parse_interval(meta["review_every"]) is None:
        errs.append("review_every: must look like 30d, 12w or 6m")
    if "tags" in meta and not isinstance(meta["tags"], list):
        errs.append("tags: must be a list")
    if "toc" in meta and not isinstance(meta["toc"], bool):
        errs.append("toc: must be true or false")
    if "summary" in meta and not (isinstance(meta["summary"], str) and 0 < len(meta["summary"].strip()) <= 160 and "\n" not in meta["summary"]):
        errs.append("summary: must be one line, 1-160 characters")
    existing = TOC_BLOCK_RE.search(body)
    if meta.get("toc") is True:
        if not existing:
            errs.append("toc: true but no Contents block (run docs_stamp.py)")
        elif existing.group(1).strip() != toc_entries(body, cfg.get("toc_depth", DEFAULT_TOC_DEPTH)):
            errs.append("Contents is out of date (run docs_stamp.py)")
    elif existing:
        errs.append("Contents block present but front matter lacks 'toc: true' (set it, or run docs_stamp.py --no-toc)")

    dates = {}
    for k in ("created", "updated"):
        if k in meta:
            dates[k] = as_date(meta[k])
            if dates[k] is None:
                errs.append(f"{k}: must be an ISO date (YYYY-MM-DD)")
    if "last_verified" in meta and meta["last_verified"] is not None:
        dates["last_verified"] = as_date(meta["last_verified"])
        if dates["last_verified"] is None:
            errs.append("last_verified: must be an ISO date or null")
    if dates.get("created") and dates.get("updated") and dates["updated"] < dates["created"]:
        errs.append("updated: earlier than created")
    today_ = today(cfg)
    for k, d in dates.items():
        if d and d > today_:
            errs.append(f"{k}: is in the future")

    for k, spec in extra.items():
        if k not in meta:
            if spec.get("required"):
                errs.append(f"missing field: {k}")
            continue
        check = _TYPE_CHECKS.get(spec.get("type", "string"))
        if check is None:
            errs.append(f"{CONFIG_NAME}: unknown type for extra field {k}")
        elif not check(meta[k]):
            errs.append(f"{k}: must be {spec.get('type', 'string')}")
        elif "values" in spec and meta[k] not in spec["values"]:
            errs.append(f"{k}: {meta[k]!r} not in {spec['values']}")

    rows = parse_changelog(body)
    if rows is None:
        errs.append(f"missing Change Log block ({CL_START} ... {CL_END})")
    elif not rows:
        errs.append("Change Log has no rows")
    else:
        if len(rows) > MAX_LOG_ROWS:
            errs.append(f"Change Log has {len(rows)} rows (max {MAX_LOG_ROWS})")
        for ts, _, _ in rows:
            err = check_ts(ts, cfg)
            if err:
                errs.append(f"Change Log: {err}")
        if rows[0][0][:10] != str(meta.get("updated")) or meta.get("updated_by") != rows[0][1]:
            errs.append("newest Change Log row must match updated/updated_by (use docs_stamp.py)")
    return errs


# --- links between docs -----------------------------------------------------
# Rules: relative path from the linking file, forward slashes, with the .md extension, inside the project;
# optional #anchor must match a heading in the target. No absolute paths, file: URLs or links that leave the repo.

LINK_RE = re.compile(r'(!?)\[((?:[^\]\\]|\\.)*)\]\(\s*(<[^>]*>|[^)\s]*)(?:\s+"[^"]*")?\s*\)')
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FENCE_MARKER_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
MENTION_RE = re.compile(r"(?<![\w/.#-])((?:[\w.-]+/)*[\w.-]+\.md)(?![\w/-])")
ID_RE = re.compile(r"""<a\s+[^>]*?(?:id|name)=["']([^"']+)["']""")


def _blank(m: re.Match) -> str:
    return "\n" * m.group(0).count("\n")


def mask_for_links(text: str) -> str:
    """Mask front matter and fenced code, preserving every offset and line ending.

    A closing fence must use the opening character, be at least as long, and
    have no info string. An unclosed fence hides the remainder of the document.
    """
    fm = FM_RE.match(text)
    if fm:
        text = re.sub(r"[^\r\n]", " ", fm.group(0)) + text[fm.end():]
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = FENCE_MARKER_RE.match(line.rstrip("\r\n"))
        hidden = fence is not None
        if marker:
            token, tail = marker.groups()
            if fence:
                if token[0] == fence[0] and len(token) >= fence[1] and not tail.strip():
                    fence = None
            elif token[0] != "`" or "`" not in tail:
                fence = (token[0], len(token))
                hidden = True
        lines.append(re.sub(r"[^\r\n]", " ", line) if hidden else line)
    return "".join(lines)


def heading_anchors(text: str) -> set[str]:
    """Heading anchors and explicit prose <a id=...> anchors."""
    return {anchor for _, _, _, anchor in heading_list(text)} | set(ID_RE.findall(mask_for_links(text)))


def _exact_path(root: Path, rel: str) -> Path | None:
    """Resolve rel under root, matching case exactly (macOS is case-insensitive, Linux/Forgejo is not)."""
    cur = root
    for part in [x for x in rel.split("/") if x]:
        if not cur.is_dir() or part not in os.listdir(cur):
            return None
        cur = cur / part
    return cur


def check_target(target: str, rel: Path, own: set[str], source: DocumentSource) -> str | None:
    t = target[1:-1] if target.startswith("<") and target.endswith(">") else target
    if not t:
        return "empty link target"
    if t.startswith("#"):
        a = unquote(t[1:])
        return None if not a or a in own else f"anchor '#{a}' not found in this doc"
    if SCHEME_RE.match(t) and not re.match(r"^[A-Za-z]:[\\/]", t):
        return "file: links are not portable; use a relative path" if t.lower().startswith("file:") else None
    if t.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", t):
        return f"absolute path '{t}'; use a path relative to this file"
    path, _, frag = t.partition("#")
    path = unquote(path)
    if "\\" in path:
        return f"backslash in '{t}'; use forward slashes"
    norm = posixpath.normpath(posixpath.join(rel.parent.as_posix(), path))
    if norm == ".." or norm.startswith("../"):
        return f"'{t}' leaves the project repo; name other projects in plain text instead of linking"
    dest = source.exact_path("" if norm == "." else norm)
    if dest is None:
        return f"target not found: {path} (relative to {rel.parent.as_posix() or '.'}/; links need the .md extension and exact letter case)"
    if frag and source.is_file(norm) and dest.suffix == ".md":
        text = source.read(norm)
        if text is not None and unquote(frag) not in heading_anchors(text):
            return f"anchor '#{unquote(frag)}' not found in {norm}"
    return None


def link_findings(text: str, rel: Path, cfg: dict, source: DocumentSource) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors: invalid links. Warnings: other docs mentioned without a link."""
    masked = mask_for_links(text)
    own = heading_anchors(text)
    errs, warns = [], []
    scan = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), masked)  # link syntax shown in `code` is not a link
    for m in LINK_RE.finditer(scan):
        err = check_target(m.group(3), rel, own, source)
        if err:
            errs.append(f"line {scan.count(chr(10), 0, m.start()) + 1}: broken link [{m.group(2)[:40]}]: {err}")
    prose = re.sub(r"<!--.*?-->", _blank, LINK_RE.sub(" ", CL_BLOCK_RE.sub(_blank, masked)), flags=re.S)
    prose = re.sub(r"https?://\S+", " ", prose)  # the Change Log is history text, not a reference
    reported = set()
    for m in MENTION_RE.finditer(prose):
        tok = m.group(1)
        if tok in reported or is_excluded(Path(tok), cfg):
            continue
        for cand in (rel.parent.as_posix() + "/" + tok, tok, "docs/" + tok):
            dest = source.exact_path(posixpath.normpath(cand))
            if dest and source.is_file(posixpath.normpath(cand)) and dest != source.root / rel:
                reported.add(tok)
                suggest = posixpath.relpath(dest.relative_to(source.root).as_posix(), rel.parent.as_posix() or ".")
                warns.append(f"line {prose.count(chr(10), 0, m.start()) + 1}: '{tok}' names another doc without a link; use [Title]({suggest})")
                break
    return errs, warns


# --- shared rules + hooks ---------------------------------------------------

MANAGED_RE = re.compile(r"<!-- BEGIN MANAGED: docs-rules -->.*?<!-- END MANAGED: docs-rules -->", re.S)


def template_block(tools_dir: Path) -> str:
    text = (tools_dir.parent / "_template" / "AGENTS.md").read_text()
    m = MANAGED_RE.search(text)
    if not m:
        raise RuntimeError("_template/AGENTS.md has no managed block")
    return m.group(0)


def install_hook(project: Path, tools_dir: Path, check_only: bool = False) -> str:
    """Copy hooks/pre-commit into the project's .git/hooks. Returns 'ok', 'updated' or 'skipped'."""
    src = tools_dir / "hooks" / "pre-commit"
    dest = project / ".git" / "hooks" / "pre-commit"
    if not (project / ".git").is_dir():
        return "skipped"
    if dest.is_file() and dest.read_text() == src.read_text():
        return "ok"
    if not check_only:
        dest.write_text(src.read_text())
        dest.chmod(0o755)
    return "updated"


# --- stamping (pure text -> text) -------------------------------------------

def default_meta(name: str, body: str, cfg: dict, doc_type: str, today_: dt.date) -> dict:
    h1 = re.search(r"^#\s+(.+)$", body, re.M)
    title = h1.group(1).strip() if h1 else Path(name).stem.replace("-", " ").replace("_", " ").title()
    return {
        "title": title, "doc_type": doc_type, "status": "draft",
        "sensitivity": cfg.get("sensitivity", "private"), "owner": cfg.get("owner", "human"),
        "created": today_, "updated": today_, "updated_by": "human", "last_verified": None,
        "review_every": cfg.get("review_every_default", "90d"), "tags": [],
    }


def stamp_text(text: str, name: str, cfg: dict, by: str, summary: str, verified: bool = False,
               init: bool = False, doc_type: str = "reference",
               toc: bool | None = None) -> tuple[str, list[str], dt.datetime]:
    """Return (new_text, validation_errors, moment). Raises ValueError if there is no front matter and not init."""
    moment = now(cfg)
    today_ = moment.date()
    meta, body = split_front_matter(text)
    if meta is None:
        if not init:
            raise ValueError("no front matter; re-run with --init")
        meta, rows = default_meta(name, body, cfg, doc_type, today_), []
    else:
        rows = parse_changelog(body) or []
    if toc is True:
        meta["toc"] = True
    elif toc is False:
        meta.pop("toc", None)
    body = apply_toc(body, meta.get("toc") is True, cfg.get("toc_depth", DEFAULT_TOC_DEPTH))
    meta["updated"], meta["updated_by"] = today_, by
    if verified:
        meta["last_verified"] = today_
    import docsextra  # lazy: docsextra imports this module
    body = docsextra.apply_byline(body, meta, cfg)
    rows = ([(format_ts(moment), by, clean_summary(summary))] + rows)[:MAX_LOG_ROWS]
    new = join_front_matter(meta, set_changelog(body, rows))
    return new, validate(*split_front_matter(new), cfg), moment


# --- generated tables (CSV -> markdown) -------------------------------------

DEFAULT_INLINE_ROWS = 8
TABLE_BLOCK_RE = re.compile(r"(<!--\s*table:start\s+(?P<attrs>.*?)\s*-->)(?P<body>.*?)(<!--\s*table:end\s*-->)", re.S)
GENERATED_NOTE = "<!-- generated by render_tables.py from the source above; do not edit -->"
SEP_RE = re.compile(r"^\|[\s:|-]+\|\s*$")


def parse_attrs(s: str) -> dict:
    attrs = {}
    for tok in s.split():
        k, _, v = tok.partition("=")
        attrs[k] = v
    return attrs


def _sort_key(v: str):
    try:
        return (0, float(v), "")
    except ValueError:
        return (1, 0.0, v)


PLAIN_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
CURRENCY_CODE_RE = re.compile(r"^[A-Za-z]{3}$")


def format_money(value: str, currency: str) -> str:
    """Display a plain-decimal amount as $1,234.50 (USD) or 1,234.50 EUR. Anything else is returned unchanged."""
    raw = value.strip()
    if not PLAIN_DECIMAL_RE.match(raw) or not CURRENCY_CODE_RE.match(currency):
        return value
    with localcontext() as ctx:
        ctx.prec = len(raw) + 4
        amount = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""  # a negative that rounds to zero shows no sign
    digits = f"{abs(amount):,.2f}"
    code = currency.upper()
    return f"{sign}${digits}" if code == "USD" else f"{sign}{digits} {code}"


def _money_formatter(attrs: dict, fields: list[str], need):
    """Return cell_fn(row, col) -> display text for the opt-in money=col,col option (None when not requested)."""
    money = set(filter(None, attrs.get("money", "").split(",")))
    if not money:
        return None
    for col in sorted(money):
        need(col)
    fallback = attrs.get("currency", "")
    if fallback and not CURRENCY_CODE_RE.match(fallback):
        raise ValueError(f"currency={fallback!r} must be a 3-letter ISO code")
    cur_col = attrs.get("currency_col") or "currency"
    if cur_col not in fields and not fallback:
        raise ValueError(f"money= needs a {cur_col!r} column or an explicit currency=XXX option")

    def display(row: dict, col: str) -> str:
        if col not in money:
            return row[col]
        code = row[cur_col].strip() if cur_col in fields else ""
        return format_money(row[col], code or fallback)  # blank row currency -> fallback; invalid stays unchanged

    return display


def render_csv_table(csv_text: str, attrs: dict) -> str:
    """Render CSV text as a markdown table. attrs: cols=a,b  where=col=val,col2=val  sort=col,-col2
    Opt-in money display: money=col,col2 [currency=USD] [currency_col=name]; see README."""
    reader = csv.reader(io.StringIO(csv_text))
    try:
        fields = next(reader)
    except StopIteration:
        raise ValueError("CSV is empty (needs a header row)")
    rows = []
    for n, r in enumerate(reader, start=2):
        if not r:
            continue
        if len(r) != len(fields):
            raise ValueError(f"CSV line {n}: {len(r)} cells, header has {len(fields)}")
        rows.append(dict(zip(fields, r)))

    def need(col: str) -> str:
        if col not in fields:
            raise ValueError(f"unknown column {col!r} (have: {', '.join(fields)})")
        return col

    for cond in filter(None, attrs.get("where", "").split(",")):
        col, _, val = cond.partition("=")
        rows = [r for r in rows if r[need(col)] == val]
    for key in reversed(list(filter(None, attrs.get("sort", "").split(",")))):
        desc = key.startswith("-")
        rows.sort(key=lambda r: _sort_key(r[need(key.lstrip("-"))]), reverse=desc)
    cols = [need(c) for c in attrs["cols"].split(",")] if attrs.get("cols") else fields
    display = _money_formatter(attrs, fields, need) or (lambda row, col: row[col])

    def cell(v: str) -> str:
        return v.replace("|", "\\|").replace("\n", " ").strip()

    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(cell(display(r, c)) for c in cols) + " |" for r in rows]
    if not rows:
        out.append("")
        out.append("_No rows._")
    return "\n".join(out)


def render_blocks(text: str, read_src) -> tuple[str, list[str]]:
    """Re-render every generated block in `text`. read_src(rel_path) -> str | None. Returns (new_text, errors)."""
    errs: list[str] = []
    n_start = len(re.findall(r"<!--\s*table:start", text))
    n_end = len(re.findall(r"<!--\s*table:end", text))
    if n_start != n_end:
        errs.append(f"unbalanced table markers ({n_start} start, {n_end} end)")

    def sub(m: re.Match) -> str:
        attrs = parse_attrs(m.group("attrs"))
        src = attrs.get("src", "")
        if "table:start" in m.group("body"):
            errs.append(f"nested table block near src={src}")
            return m.group(0)
        if not src or src.startswith(("/", "..")) or ".." in Path(src).parts:
            errs.append(f"table block needs a relative src=... inside the project (got {src!r})")
            return m.group(0)
        data = read_src(src)
        if data is None:
            errs.append(f"table source not found: {src}")
            return m.group(0)
        try:
            table = render_csv_table(data, attrs)
        except ValueError as e:
            errs.append(f"{src}: {e}")
            return m.group(0)
        return f"{m.group(1)}\n{GENERATED_NOTE}\n\n{table}\n\n{m.group(4)}"

    return TABLE_BLOCK_RE.sub(sub, text), errs


def table_errors(text: str, cfg: dict, read_src) -> list[str]:
    """Lint: generated blocks must be current, and inline tables must stay small."""
    new, errs = render_blocks(text, read_src)
    if not errs and new != text:
        srcs = sorted({parse_attrs(m.group("attrs")).get("src", "?") for m in TABLE_BLOCK_RE.finditer(text)})
        errs.append(f"generated table block(s) out of date vs {', '.join(srcs)} (run render_tables.py)")
    limit = cfg.get("inline_table_max_rows", DEFAULT_INLINE_ROWS)
    stripped = TABLE_BLOCK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    stripped = CL_BLOCK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), stripped)
    lines, i = mask_for_links(stripped).splitlines(), 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("|") and i + 1 < len(lines) and SEP_RE.match(lines[i + 1].strip()):
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            rows = j - (i + 2)
            if rows > limit:
                errs.append(f"line {i + 1}: inline table has {rows} rows (max {limit}); move it to data/*.csv and embed with a table block")
            i = j
            continue
        i += 1
    return errs
