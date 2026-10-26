#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Folderwise iCloud bridge: Mac-owned export and boolean task import.

Commands: setup, configure, plan, sync, resolve, status, enable, disable, schedule-enable,
schedule-disable, schedule-prepare, doctor, logs, notify-test, vault-init, uninstall. See docs/obsidian.md before setup.
"""
from __future__ import annotations

import argparse
import base64
import errno
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402

TOOLS = Path(__file__).resolve().parent
LABEL = "org.folderwise.ibridge"
LAUNCHER_NAME = "folderwise-ibridgesync"
LAUNCHER_BODY = b'#!/bin/sh\n# Folderwise iCloud bridge launch entry point.\nexec "$@"\n'
LEGACY_REPORT = "Bridge Status.md"
REPORT, DASHBOARD, TASK_DIR = "_folderwise-sync-status.md", "Tasks.md", "_Folderwise Tasks"
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".heic", ".bmp"}
SKIP = {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "_doc-template.md", "node_modules", "__pycache__", "#recycle", "credentials.json", "id_rsa", "id_ed25519"}
CHECKBOX = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+\[)([ xX])(\].*)$")
SOURCE_TAIL = " ([source]("
MAX_TITLE = 200
KEEP_DAYS, KEEP_ENTRIES = 30, 10
# iCloud can briefly lock a file it is syncing; these are retried, not reported.
TRANSIENT = {errno.EDEADLK, errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT}
DEFAULT_HOME = Path.home() / ("Library/Application Support/Folderwise/ibridge" if sys.platform == "darwin" else ".local/state/folderwise-ibridge")


def run(argv, cwd=None, data=None):
    try:
        result = subprocess.run(list(map(str, argv)), cwd=cwd, input=data, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise ValueError(f"{Path(str(argv[0])).name} timed out; pending changes are preserved") from None
    if result.returncode:
        raise ValueError(f"{Path(str(argv[0])).name} failed: {(result.stderr or result.stdout).strip()[-1200:]}")
    return result.stdout


def git(root, *args):
    return run(["git", "-C", root, *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ibridge-', delete=False) as stream:
            temporary = Path(stream.name)
            if isinstance(data, Path):
                with data.open('rb') as source:
                    shutil.copyfileobj(source, stream, 1024 * 1024)
            else:
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save(path, obj):
    atomic(path, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode())


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def safe(root, rel):
    """Reject links at every component, even links pointing inside the root."""
    parts = PurePosixPath(rel).parts
    if not parts or PurePosixPath(rel).is_absolute() or any(p in {"..", ".git"} for p in parts):
        raise ValueError(f"unsafe path: {rel!r}")
    p = root
    for part in parts:
        p = p / part
        if p.is_symlink():
            raise ValueError(f"symlink not supported: {rel!r}")
    return p


def config_load(path):
    return validate_settings(read_json(path), path)


def validate_settings(settings, path):
    if not isinstance(settings, dict) or settings.get("version") != 1:
        raise ValueError("run setup first (missing or unsupported bridge config)")
    if type(settings.get("enabled", True)) is not bool:
        raise ValueError("enabled must be boolean")
    source, vault = Path(settings["source"]), Path(settings["vault"])
    if not source.is_absolute() or not vault.is_absolute():
        raise ValueError("source and vault must be absolute paths")
    if not isinstance(settings.get('adapters', {}), dict):
        raise ValueError("adapters must be an object mapping project names to commands")
    if source == vault or source in vault.parents or vault in source.parents:
        raise ValueError("source and vault must be separate, non-nested directories")
    if settings.get("mode") not in {"full", "lean"} or settings.get("notifications") not in {"off", "errors", "imports"}:
        raise ValueError("invalid mode or notification setting")
    for name in ("interval_minutes", "max_image_bytes", "max_images_total_bytes"):
        n = settings[name]
        if n is not None and (type(n) is not int or n < (1 if name == "interval_minutes" else 0)):
            raise ValueError(f"{name}: use a positive interval/nonnegative byte limit; null means unlimited")
    if settings["interval_minutes"] is None:
        raise ValueError("interval_minutes cannot be null")
    state = path.parent.resolve()
    if state == vault or vault in state.parents or state == source or source in state.parents:
        raise ValueError("bridge config/state must be outside source and vault")
    return settings


@contextmanager
def locked(home):
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (home / "lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another bridge operation is running") from None
        yield


def projects(settings, include_disabled=False, failed=None):
    """One validated configuration snapshot per project; discovery failures stay local."""
    source = Path(settings["source"])
    if not source.is_dir():
        raise ValueError("source directory is unavailable")
    result = {}
    for p in sorted(source.iterdir()):
        if p.name.startswith(("_", ".")) or p.is_symlink() or not p.is_dir():
            continue
        config = p / ".docs.yaml"
        if not config.is_file() and not config.is_symlink():
            continue
        try:
            if config.is_symlink():
                raise ValueError(f"symlink project config: {p.name}")
            cfg = dl.parse_config((p / ".docs.yaml").read_text())
            enabled = cfg.get("folderwise-ibridgesync", False)
            if type(enabled) is not bool:
                raise ValueError("folderwise-ibridgesync must be boolean")
            if type(cfg.get("folderwise-ibridgerename", False)) is not bool:
                raise ValueError("folderwise-ibridgerename must be boolean")
            if enabled or include_disabled:
                if Path(git(p, "rev-parse", "--show-toplevel").strip()).resolve() != p.resolve():
                    raise ValueError("expected an independent Git repository")
                result[p] = cfg
        except (ValueError, OSError, yaml.YAMLError) as exc:
            if failed is None:
                raise ValueError(f"{p.name}: {exc}") from None
            failed[p.name] = f"{p.name}: {exc}"
    return result


def owner(key):
    """The project a vault path belongs to, or None for bridge-wide files such as the dashboard."""
    parts = PurePosixPath(key).parts
    if parts[0] == TASK_DIR:
        return Path(key).stem if len(parts) == 2 else None
    return parts[0] if len(parts) > 1 else None


def tracked(project):
    files = []
    for entry in filter(None, git(project, "ls-files", "--stage", "-z").split("\0")):
        meta, rel = entry.split("\t", 1)
        mode, _, stage = meta.split()
        parts = PurePosixPath(rel).parts
        if mode not in {"100644", "100755"} or stage != "0":
            continue
        if any(part.startswith(".") or part in SKIP for part in parts) or rel.endswith((".pem", ".key", ".p12", ".pfx", ".pyc")):
            continue
        if safe(project, rel).is_file():
            files.append(rel)
    return sorted(files)


def markdown_tasks(text, path):
    """List tasks outside front matter, fenced examples and generated blocks."""
    tasks, counts = [], {}
    generated = False
    for line, raw in enumerate(dl.mask_for_links(text).splitlines()):
        if re.search(r"<!--\s*[^>]*:start\b", raw):
            generated = True
        if generated:
            if re.search(r"<!--\s*[^>]*:end\b", raw):
                generated = False
            continue
        m = CHECKBOX.match(raw)
        if m:
            identity = m[1] + " " + m[3]
            ordinal = counts.get(identity, 0)
            counts[identity] = ordinal + 1
            key = "md:" + digest((path + "\0" + identity + "\0" + str(ordinal)).encode())
            tasks.append(dict(id=key, checked=m[2] != " ", path=path, line=line,
                              title=m[3][1:].strip(), identity=identity))
    for task in tasks:
        task["duplicate"] = counts[task["identity"]] > 1
        task["source_hash"] = digest(text.encode())
    return tasks


def view_title(title):
    """The title as the generated view shows it: one line, links and images reduced to their text."""
    title = re.sub(r"[\r\n]", " ", title)
    return re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)


def adapter(settings, project, operation, changes=None):
    command = settings.get("adapters", {}).get(project.name)
    if not command:
        return []
    if not isinstance(command, list) or not command or not all(isinstance(s, str) for s in command):
        raise ValueError(f"{project.name}: adapter must be an argv list")
    output = run([*command, operation], project, json.dumps(changes) if changes is not None else None)
    if operation != "list":
        return []
    tasks = json.loads(output)
    if not isinstance(tasks, list):
        raise ValueError("adapter list must return a JSON array")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("adapter tasks must be JSON objects")
        if not isinstance(task.get("id"), str) or not task["id"] or task["id"] in ids or type(task.get("checked")) is not bool:
            raise ValueError("adapter tasks need unique string id and boolean checked")
        ids.add(task["id"])
        if not isinstance(task.get("path"), str) or not safe(project, task["path"]).is_file() or not isinstance(task.get("title"), str):
            raise ValueError("adapter tasks need a title and an existing source document path")
        editable = task.get("editable", [])
        if not isinstance(editable, list) or not all(isinstance(s, str) for s in editable):
            raise ValueError("adapter task editable must be a list of field names")
        task["id"] = "adapter:" + task["id"]
    return tasks


def inventory(settings, selected_projects=None, failed=None):
    files, tasks, omissions = {}, {}, []
    total_images = 0
    for project, cfg in (projects(settings, failed=failed) if selected_projects is None else selected_projects).items():
        mark = (set(files), len(omissions), total_images)
        try:
            names = tracked(project)
            refs, local_tasks = set(), []
            for rel in names:
                if Path(rel).suffix.lower() != ".md":
                    continue
                text = safe(project, rel).read_text()
                local_tasks.extend(markdown_tasks(text, rel))
                blocks = re.findall(r'<!--\s*([\w-]+):start\b[^>]*-->(.*?)<!--\s*\1:end\s*-->', text, re.S)
                if project.name not in settings.get("adapters", {}) and any(CHECKBOX.match(line) for _, block in blocks for line in block.splitlines()):
                    omissions.append(dict(path=project.name + '/' + rel, bytes=0, reason='generated task source requires an adapter (document is still exported)'))
                definitions = {label.casefold(): angle or plain for label, angle, plain in re.findall(r'^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|([^\s]+))', text, re.M)}
                links = [angle or plain for angle, plain in re.findall(r'!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)', text)]
                links += [definitions.get(label.casefold(), "") for label in re.findall(r'!\[[^\]]*\]\[([^\]]+)\]', text)]
                wiki = re.findall(r'!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', text)
                links += wiki
                for link in links:
                    url = urlsplit(link)
                    if not link or url.scheme or url.netloc:
                        continue
                    target = os.path.normpath(str(PurePosixPath(rel).parent / unquote(url.path)))
                    safe(project, target)
                    if link in wiki and target not in names:
                        matches = [name for name in names if name == unquote(url.path) or name.endswith('/' + unquote(url.path))]
                        if len(matches) != 1:
                            raise ValueError(f"{project.name}/{rel}: missing or ambiguous image embed {link!r}")
                        target = matches[0]
                    if target not in names and Path(target).suffix.lower() in IMAGES:
                        omissions.append(dict(path=project.name + '/' + target, bytes=0, reason='referenced image is missing or not tracked'))
                    refs.add(target)
            local_tasks.extend(adapter(settings, project, "list"))
            tasks[project.name] = {t["id"]: t for t in local_tasks}
            for rel in names:
                p = safe(project, rel)
                suffix, size = p.suffix.lower(), p.stat().st_size
                image, reason = suffix in IMAGES, None
                if settings["mode"] == "lean" and suffix != ".md" and not (image and rel in refs):
                    reason = "excluded by lean mode"
                elif image and settings["max_image_bytes"] is not None and size > settings["max_image_bytes"]:
                    reason = "exceeds per-image limit"
                elif image and settings["max_images_total_bytes"] is not None and total_images + size > settings["max_images_total_bytes"]:
                    reason = "exceeds aggregate image limit"
                key = project.name + "/" + rel
                if reason:
                    omissions.append(dict(path=key, bytes=size, reason=reason))
                    continue
                if image:
                    total_images += size
                files[key] = p
            can_rename = cfg.get("folderwise-ibridgerename", False)
            note = ("Generated task view. Checkbox toggles and title edits are imported; keep each line's trailing (source) link."
                    if can_rename else "Generated task view. Only checkbox toggles are imported.")
            projection = [f"# {project.name} tasks", "", note, ""]
            mapping = []
            for task in local_tasks:
                target = quote(project.name + "/" + task["path"], safe="/")
                mapping.append(dict(line=len(projection), id=task["id"], checked=task["checked"]))
                projection.append(f"- [{'x' if task['checked'] else ' '}] {view_title(task['title'])}{SOURCE_TAIL}../{target}))")
            files[f"{TASK_DIR}/{project.name}.md"] = ("\n".join(projection) + "\n").encode()
            tasks[project.name]["_projection"] = mapping
        except (ValueError, OSError, yaml.YAMLError) as exc:
            if failed is None:
                raise
            # One project's problem pauses that project only; it keeps its previous export.
            for key in set(files) - mark[0]:
                del files[key]
            del omissions[mark[1]:]
            total_images = mark[2]
            tasks.pop(project.name, None)
            failed[project.name] = str(exc)
    files[DASHBOARD] = ("# All projects\n\n## Open tasks\n\n```tasks\npath includes " + TASK_DIR +
                        "\nnot done\ngroup by filename\n```\n\n## Completed tasks\n\n```tasks\npath includes " + TASK_DIR +
                        "\ndone\ngroup by filename\n```\n").encode()
    return files, tasks, omissions


class Rejected(ValueError):
    """A phone edit the Mac will not apply. A generated view can be restored once its text is saved."""


def task_changes(base, current):
    before, after = base.splitlines(keepends=True), current.splitlines(keepends=True)
    if len(before) != len(after):
        raise Rejected("only checkbox on/off changes are supported (the number of lines changed)")
    changed = {}
    for i, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        a, b = CHECKBOX.match(old.rstrip("\r\n")), CHECKBOX.match(new.rstrip("\r\n"))
        if not a or not b or a[1] != b[1] or a[3] != b[3] or old[len(old.rstrip('\r\n')):] != new[len(new.rstrip('\r\n')):]:
            raise Rejected(f"line {i + 1}: only checkbox on/off changes are supported")
        changed[i] = dict(checked=b[2] != " ", title=None)
    return changed


def clean_title(title):
    """Normalize and validate a phone-typed title; return the text that may be written to the source."""
    text = unicodedata.normalize("NFC", title).strip()
    if not text or len(text) > MAX_TITLE:
        raise Rejected(f"a title must be 1-{MAX_TITLE} characters")
    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in text):
        raise Rejected("a title cannot contain control, direction or line-break characters")
    if "<!--" in text or "-->" in text or SOURCE_TAIL in text or text[0] in "=+-@" or re.match(r"\[[ xX]\]", text):
        raise Rejected("a title cannot contain comment markers, a source link or a checkbox, or start with = + - @")
    if view_title(text) != text:
        raise Rejected("a title cannot contain links or images; edit it on the Mac")
    return text


def split_view(line):
    """Split a generated view line into (head, mark, title, tail, line ending), or None."""
    body = line.rstrip("\r\n")
    m = CHECKBOX.match(body)
    if not m or not m[3].startswith("] "):
        return None
    rest = m[3][2:]
    cut = rest.rfind(SOURCE_TAIL)
    if cut < 0 or not rest.endswith("))"):
        return None
    return m[1], m[2], rest[:cut], rest[cut:], line[len(body):]


def view_changes(base, current, renames):
    """Toggles and, when allowed, title edits in a generated view; anything else is rejected."""
    before, after = base.splitlines(keepends=True), current.splitlines(keepends=True)
    if len(before) != len(after):
        raise Rejected("only checkbox on/off changes are supported (the number of lines changed)")
    known = [parts[2] for parts in map(split_view, before) if parts]
    changed, fresh = {}, []
    for i, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        a, b = split_view(old), split_view(new)
        if not a or not b or a[0] != b[0] or a[3] != b[3] or a[4] != b[4]:
            raise Rejected(f"line {i + 1}: " + ("keep the checkbox and the trailing source link" if renames
                                                else "only checkbox on/off changes are supported"))
        title = None
        if a[2] != b[2]:
            if not renames:
                raise Rejected(f"line {i + 1}: only checkbox on/off changes are supported (title edits are off for this project)")
            try:
                title = clean_title(b[2])
            except Rejected as exc:
                raise Rejected(f"line {i + 1}: {exc}") from None
            if title == a[2]:
                title = None
            elif title in known or title in fresh:
                raise Rejected(f"line {i + 1}: that title is already used by another task; "
                               "reordering or duplicating tasks is not supported")
            else:
                fresh.append(title)
        checked = None if a[1] == b[1] else b[1] != " "
        if checked is not None or title is not None:
            changed[i] = dict(checked=checked, title=title)
    return changed


def merge_edits(target, staged):
    """Merge one file's task edits into the project's; two files may not disagree about a task."""
    merged = {key: dict(value) for key, value in target.items()}
    for key, change in staged.items():
        prior = merged.get(key)
        if prior:
            for field in ("checked", "title"):
                if prior[field] is not None and change[field] is not None and prior[field] != change[field]:
                    raise Rejected("conflicting edits of the same task")
            change = {field: prior[field] if change[field] is None else change[field] for field in prior}
        merged[key] = change
    return merged


def requests(vault, state, renames=frozenset(), failures=None):
    """Collect phone edits: (wanted per project, files each project's edits came from,
    vault hashes accepted as valid, generated views rejected with the reason).
    A bad edit to a copied note is recorded in `failures` for its project when a dict is given."""
    wanted, sources, accepted, rejected = {}, {}, {}, {}
    for key, entry in state.get("files", {}).items():
        project = entry.get("project")
        view = key.startswith(TASK_DIR + "/")
        try:
            p = safe(vault, key)
            if not p.is_file() or "text" not in entry:
                continue
            data = p.read_text()
            if data == entry["text"]:
                continue
            delta = view_changes(entry["text"], data, project in renames) if view else task_changes(entry["text"], data)
            mapping = {t["line"]: t for t in entry.get("tasks", [])}
            staged = {}
            for line, change in delta.items():
                if line not in mapping:
                    raise Rejected("checkbox has no authoritative task mapping")
                staged[mapping[line]["id"]] = change
            wanted[project] = merge_edits(wanted.get(project, {}), staged)
            accepted_hash = content_hash(p)
        except Rejected as exc:
            if view:
                rejected[key] = str(exc)
            elif failures is None or project is None:
                raise ValueError(f"{key}: {exc}") from None
            else:
                failures.setdefault(project, f"{key}: {exc}")
            continue
        except (ValueError, OSError) as exc:
            if failures is None or project is None:
                raise
            failures.setdefault(project, f"{key}: {exc}")
            continue
        sources.setdefault(project, set()).add(key)
        accepted[key] = accepted_hash
    return wanted, sources, accepted, rejected


def rewrite_task(line, checked, title):
    """Change one task line's checkbox and/or title, keeping its bullet, spacing and line ending."""
    body = line.rstrip("\r\n")
    m = CHECKBOX.match(body)
    rest = m[3][1:]
    if title is not None:
        rest = rest[:len(rest) - len(rest.lstrip())] + title + rest[len(rest.rstrip()):]
    mark = m[2] if checked is None else ("x" if checked else " ")
    return m[1] + mark + "]" + rest + line[len(body):]


def plan_import(name, wanted, baseline, current):
    """What a project's pending phone edits would change: (toggles, renames), or Rejected."""
    toggles, renames = {}, {}
    for key, want in wanted.items():
        if key not in current or key not in baseline:
            raise Rejected(f"{name}: task changed or disappeared on Mac; resolve pending edit")
        task, old = current[key], baseline[key]
        if task.get("duplicate") and task["source_hash"] != old.get("source_hash"):
            raise Rejected(f"{name}: duplicate task moved during concurrent edit")
        if want["checked"] is not None and task["checked"] != want["checked"]:
            toggles[key] = want["checked"]
        title = want["title"]
        if title is not None and title != task["title"]:
            reason = None
            if task["title"] != old["title"]:
                reason = "its title also changed on the Mac"
            elif task.get("duplicate"):
                reason = "other tasks share its title"
            elif not task["title"] or view_title(task["title"]) != task["title"]:
                reason = "its title is empty or contains links or images"
            elif key.startswith("adapter:") and "title" not in task.get("editable", []):
                reason = "its adapter does not allow title edits"
            if reason:
                raise Rejected(f"{name}: a task cannot be renamed from the phone ({reason}); edit it on the Mac")
            renames[key] = title
    return toggles, renames


@contextmanager
def project_transaction(project, home):
    """Prepare and publish one validated local commit without touching the live index."""
    if git(project, "status", "--porcelain"):
        raise ValueError(f"{project.name}: uncommitted Mac changes; commit them before importing")
    head = git(project, "rev-parse", "HEAD").strip()
    work = home / "work"
    work.mkdir(exist_ok=True)
    tools_link = work / "_tools"
    if not tools_link.exists():
        tools_link.symlink_to(TOOLS, target_is_directory=True)
    clone = work / project.name
    if clone.exists():
        shutil.rmtree(clone)
    try:
        run(["git", "clone", "--quiet", "--shared", project, clone])
        hooks = Path(git(project, "rev-parse", "--git-path", "hooks").strip())
        if not hooks.is_absolute():
            hooks = project / hooks
        if hooks.is_dir():
            shutil.copytree(hooks, clone / ".git/hooks", dirs_exist_ok=True)
        if not (clone / ".git/hooks/pre-commit").is_file():
            dl.install_hook(clone, TOOLS)
        for key in ("user.name", "user.email"):
            r = subprocess.run(["git", "-C", project, "config", "--get", key], capture_output=True, text=True)
            if r.returncode == 0:
                git(clone, "config", key, r.stdout.strip())
        yield clone
        if git(project, "status", "--porcelain") or git(project, "rev-parse", "HEAD").strip() != head:
            raise ValueError(f"{project.name}: Mac repository changed during transaction; retry after review")
        git(project, "fetch", "--quiet", "--no-tags", str(clone), "HEAD")
        git(project, "merge", "--ff-only", "--quiet", "FETCH_HEAD")
    finally:
        if clone.exists():
            shutil.rmtree(clone)


def import_project(settings, project, wanted, baseline, current, home):
    toggles, renames = plan_import(project.name, wanted, baseline, current)
    if not toggles and not renames:
        return None
    with project_transaction(project, home) as clone:
        md, ac, originals = {}, [], {}
        for key in sorted(toggles.keys() | renames.keys()):
            task = current[key]
            checked, title = toggles.get(key), renames.get(key)
            if key.startswith("adapter:"):
                item = dict(id=key[len("adapter:"):], checked=task["checked"] if checked is None else checked)
                if title is not None:
                    item.update(title=title, expected_title=task["title"])
                ac.append(item)
            else:
                rel = task["path"]
                if digest(safe(clone, rel).read_text().encode()) != task["source_hash"]:
                    raise ValueError("source changed while preparing task transaction")
                original = originals.setdefault(rel, safe(clone, rel).read_bytes().decode())
                lines = md.setdefault(rel, original.splitlines(keepends=True))
                lines[task["line"]] = rewrite_task(lines[task["line"]], checked, title)
        for rel, lines in md.items():
            renamed = {key: renames[key] for key in renames if current[key].get("path") == rel and not key.startswith("adapter:")}
            before = markdown_tasks(originals[rel], rel)
            after = markdown_tasks("".join(lines), rel)
            ids = {t["id"] for t in before}
            # A rename must replace exactly the renamed tasks and nothing else in the note.
            if (len(after) != len(before) or ids - {t["id"] for t in after} != set(renamed)
                    or sorted(t["title"] for t in after if t["id"] not in ids) != sorted(renamed.values())):
                raise ValueError(f"{project.name}/{rel}: rename would change more than the requested tasks")
            safe(clone, rel).write_bytes("".join(lines).encode())
        if ac:
            adapter(settings, clone, "apply", ac)
        config = dl.parse_config((clone / dl.CONFIG_NAME).read_text())
        summary = ("Toggle and rename tasks" if toggles and renames else "Rename tasks" if renames else "Toggle tasks") + " via Obsidian iCloud bridge"
        for rel in git(clone, "diff", "--name-only", "-z").split("\0"):
            if rel.endswith(".md"):
                p = safe(clone, rel)
                raw = p.read_bytes().decode()
                text, errors, _ = dl.stamp_text(raw.replace("\r\n", "\n"), p.name, config, "human", summary)
                if errors:
                    raise ValueError("; ".join(errors))
                p.write_bytes((text.replace("\n", "\r\n") if "\r\n" in raw else text).encode())
        if ac:
            adapter(settings, clone, "validate")
            actual = {t["id"]: t for t in adapter(settings, clone, "list")}
            for item in ac:
                got = actual.get("adapter:" + item["id"])
                if got is None or got["checked"] != item["checked"]:
                    raise ValueError("adapter did not apply requested checkbox states")
                if "title" in item and unicodedata.normalize("NFC", got["title"]).strip() != item["title"]:
                    raise ValueError("adapter did not apply the requested title")
        run(["uv", "run", "--quiet", TOOLS / "docs_lint.py"], clone)
        git(clone, "add", "--all")
        if renames:
            subject = "Update tasks from Obsidian"
            body = (f"Apply {len(toggles)} user checkbox toggle(s) and {len(renames)} user title edit(s) and regenerate authoritative views.\n\n"
                    "Checkbox state and task titles are user-typed; no factual verification was performed.\n")
        else:
            subject = "Update task completion from Obsidian"
            body = (f"Apply {len(toggles)} user checkbox toggle(s) and regenerate authoritative views.\n\n"
                    "Checkbox state is user-reported; no factual verification was performed.\n")
        git(clone, "commit", "--quiet", "-m", subject, "-m",
            body + f"Validation: project adapter, Folderwise lint and Git hooks.\n\nBridge: folderwise-ibridge\n"
            f"Bridge-Ops: toggle={len(toggles)} rename={len(renames)}")
    return dict(commit=git(project, "rev-parse", "--short", "HEAD").strip(), toggled=len(toggles), renamed=len(renames))


def stash_phone_text(home, key, path):
    """Keep the exact rejected phone bytes outside iCloud before the generated view is restored."""
    root = home / "rejected"
    root.mkdir(exist_ok=True, mode=0o700)
    folder = root / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    folder.mkdir(exist_ok=True, mode=0o700)
    data = path.read_bytes()
    target = folder / key.replace("/", "__")
    while target.exists():
        target = target.with_name(target.name + "+")
    atomic(target, data)
    target.chmod(0o600)
    if target.read_bytes() != data:
        raise ValueError(f"{key}: could not save the phone text; nothing was overwritten")


def prune_private(home, ledger):
    """Forget saved phone text and ledger entries older than KEEP_DAYS."""
    cutoff = time.time() - KEEP_DAYS * 86400
    root = home / "rejected"
    for folder in root.iterdir() if root.is_dir() else []:
        if folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
    for kind in ledger:
        ledger[kind] = [e for e in ledger[kind] if e["epoch"] >= cutoff]


def ledger_add(ledger, kind, **entry):
    entry.update(at=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), epoch=time.time())
    ledger[kind] = (ledger[kind] + [entry])[-KEEP_ENTRIES:]


def conflict_copies(vault, keys):
    """Unmanaged siblings iCloud may have created beside managed files (for example 'note 2.md')."""
    folders = {}
    for key in keys:
        folders.setdefault(safe(vault, key).parent, []).append(safe(vault, key))
    found = set()
    for folder, managed in folders.items():
        if not folder.is_dir():
            continue
        names = {p.name for p in folder.iterdir()}
        for p in managed:
            pattern = re.compile(re.escape(p.stem) + r" \d+" + re.escape(p.suffix))
            for name in names - {p.name}:
                rel = (folder / name).relative_to(vault).as_posix()
                if rel not in keys and (pattern.fullmatch(name) or (name.startswith(p.stem) and "conflicted copy" in name)):
                    found.add(rel)
    return sorted(found)


def resolve(settings, home, key=None):
    """List vault files that differ from the last export, or save one's phone text and put the Mac version back."""
    vault = Path(settings['vault'])
    state = read_json(home / 'state.json', {'files': {}})
    pending = [name for name, entry in sorted(state['files'].items())
               if 'text' in entry and safe(vault, name).is_file() and safe(vault, name).read_text() != entry['text']]
    if key is None:
        for name in pending:
            print('PENDING ' + name)
        print(f"{len(pending)} pending phone edit(s); run resolve with one path to save its phone text and restore the Mac version."
              if pending else 'No pending phone edits.')
        return 0
    if key not in pending:
        raise ValueError(f"{key}: no pending phone edit; run resolve without a path to list them")
    stash_phone_text(home, key, safe(vault, key))
    atomic(safe(vault, key), state['files'][key]['text'].encode())
    print(f"Saved the phone text under {home / 'rejected'} and restored {key} to the last exported version; the next sync continues.")
    return 0


def deferrable(home, exc):
    """True, and recorded, for a brief iCloud file lock; the third consecutive failure is reported."""
    if not (isinstance(exc, OSError) and exc.errno in TRANSIENT):
        return False
    last = read_json(home / "last-run.json", {})
    if last.get("deferred", 0) >= 2:
        return False
    last["deferred"] = last.get("deferred", 0) + 1
    save(home / "last-run.json", last)
    return True


NOTIFIER_NAME = 'Folderwise iBridge.app'
NOTIFIER_INFO = {'CFBundleIdentifier': 'org.folderwise.ibridge.notifications',
                 'CFBundleDisplayName': 'Folderwise iBridge', 'CFBundleName': 'Folderwise iBridge',
                 'CFBundleIconFile': 'Folderwise.icns', 'CFBundleVersion': '2', 'LSUIElement': True}
NOTIFIER_SCRIPT = '''on run
try
    set messagePath to (POSIX path of (path to me)) & "../notification-message.txt"
    set notificationText to read POSIX file messagePath as «class utf8»
    display notification notificationText with title "Folderwise iBridge"
end try
end run
'''


def notifier_files(app):
    """Fingerprint the generated bundle so updates/uninstall preserve user edits."""
    files = {}
    for item in sorted(app.rglob('*')):
        if item.is_symlink():
            raise ValueError('notification app contains a symlink')
        if item.is_file():
            files[item.relative_to(app).as_posix()] = digest(item.read_bytes())
    return files


def prepare_notifier(home):
    """Compile Apple's script app locally; no download, launch or banner."""
    app = safe(home, NOTIFIER_NAME)
    manifest = safe(home, 'notifier.json')
    previous = read_json(manifest, {})
    icon = TOOLS / 'ibridge_assets/folderwise.icns'
    version = digest(NOTIFIER_SCRIPT.encode() + icon.read_bytes() + plistlib.dumps(NOTIFIER_INFO))
    if app.exists():
        if not previous.get('files') or notifier_files(app) != previous['files']:
            raise ValueError('notification app has custom content; preserve it before rebuilding')
        if previous.get('version') == version:
            return app
    with tempfile.TemporaryDirectory(dir=home, prefix='.notifier-') as temp:
        script = Path(temp) / 'notify.applescript'
        script.write_text(NOTIFIER_SCRIPT)
        built = Path(temp) / NOTIFIER_NAME
        run(['osacompile', '-o', built, script])
        info = built / 'Contents/Info.plist'
        metadata = plistlib.loads(info.read_bytes())
        metadata.pop('CFBundleIconName', None)
        metadata.update(NOTIFIER_INFO)
        # osacompile ships an asset catalog that otherwise overrides IconFile.
        (built / 'Contents/Resources/Assets.car').unlink(missing_ok=True)
        atomic(info, plistlib.dumps(metadata))
        shutil.copyfile(icon, built / 'Contents/Resources/Folderwise.icns')
        shutil.copyfile(icon, built / 'Contents/Resources/applet.icns')
        run(['codesign', '--force', '--sign', '-', built])
        files = notifier_files(built)
        if app.exists():
            shutil.rmtree(app)
        built.replace(app)
        save(manifest, {'version': version, 'files': files})
    return app


def notify(message, home):
    try:
        app = prepare_notifier(home)
        # Script apps do not receive open's command-line arguments. Hand off
        # UTF-8 data outside the signed bundle; never compile message text.
        message_file = safe(home, 'notification-message.txt')
        atomic(message_file, message.encode('utf-8'))
        try:
            run(['open', '-W', '-n', '-g', app])
        finally:
            message_file.unlink(missing_ok=True)
        return True
    except (ValueError, OSError):
        return False


def remove_notifier(home):
    app = safe(home, NOTIFIER_NAME)
    manifest = safe(home, 'notifier.json')
    if app.exists():
        if notifier_files(app) != read_json(manifest, {}).get('files'):
            print('Preserved customized notification app: ' + str(app))
            return
        shutil.rmtree(app)
    manifest.unlink(missing_ok=True)


def cell(value):
    return str(value).replace("|", "&#124;").replace("\n", " ")


def report(files, omissions, issues, settings, managed_bytes, ledger=None, copies=(), paused=()):
    image_bytes = sum(content_size(data) for key, data in files.items() if Path(key).suffix.lower() in IMAGES)
    rows = ["# Folderwise sync status", "", f"Mode: **{settings['mode']}**. Interval: **{settings['interval_minutes']} minutes**.",
            f"Estimated managed export: **{sum(content_size(data) for data in files.values()):,} bytes**, including **{image_bytes:,} image bytes**.",
            f"Currently present managed payload: **{managed_bytes:,} bytes** (excludes status/settings and unowned files).",
            "This is a file-size estimate, not your iCloud account usage or bill.",
            f"Image limits: per file={settings['max_image_bytes']}; aggregate={settings['max_images_total_bytes']} bytes (None = unlimited).", "", "## Issues", ""]
    rows += ["- " + str(x).replace("\n", " ") for x in issues] or ["None."]
    if paused:
        rows += ["", "Paused projects: " + ", ".join(cell(p) for p in paused) + ". Their imports and exports wait until the issue is fixed; other projects keep syncing."]
    ledger = ledger or {}
    if ledger.get("rejected"):
        rows += ["", "## Phone edits not applied", "",
                 "The text was saved on the Mac outside iCloud and the generated view was restored.", "",
                 "| When | File | Reason |", "| --- | --- | --- |"]
        rows += [f"| {e['at']} | {cell(e['file'])} | {cell(e['reason'])} |" for e in ledger["rejected"]]
    if ledger.get("imports"):
        rows += ["", "## Recent imports", "", "| When | Project | Commit | Toggled | Renamed |", "| --- | --- | --- | ---: | ---: |"]
        rows += [f"| {e['at']} | {cell(e['project'])} | {e['commit']} | {e['toggled']} | {e['renamed']} |" for e in ledger["imports"]]
    if copies:
        rows += ["", "## iCloud conflict copies", "", "These files were not imported. Compare each with its original and delete the one you do not want.", ""]
        rows += [f"- {cell(c)}" for c in copies]
    rows += ["", "## Omitted files", "", "| Path | Bytes | Reason |", "| --- | ---: | --- |"]
    rows += [f"| {x['path'].replace('|', '&#124;')} | {x['bytes']} | {x['reason']} |" for x in omissions]
    return ("\n".join(rows) + "\n").encode()


def content_size(data):
    return data.stat().st_size if isinstance(data, Path) else len(data)


def content_hash(data):
    if not isinstance(data, Path):
        return digest(data)
    h = hashlib.sha256()
    with data.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def existing_hash(path):
    if path.is_dir():
        raise ValueError(f"expected a file: {path.name}")
    return content_hash(path) if path.exists() else None


def recover_export(home, vault):
    """Replay an interrupted export only while every destination is old or new.

    The journal stores source locators, not duplicate large attachment payloads.
    A concurrent phone edit blocks replay and stays intact for manual recovery.
    """
    path = home / 'export.json'
    journal = read_json(path)
    if not journal:
        return
    for key, entry in journal['writes'].items():
        actual = existing_hash(safe(vault, key))
        if actual not in {entry['before'], entry['after']}:
            raise ValueError(f"{key}: changed during interrupted export; preserve it and see recovery instructions")
        if 'source' in entry and content_hash(Path(entry['source'])) != entry['after']:
            raise ValueError(f"{key}: source changed during interrupted export; see recovery instructions")
    for key, before in journal['removes'].items():
        if existing_hash(safe(vault, key)) not in {None, before}:
            raise ValueError(f"{key}: changed during interrupted cleanup; preserved")
    for key, entry in journal['writes'].items():
        p = safe(vault, key)
        if existing_hash(p) != entry['after']:
            data = Path(entry['source']) if 'source' in entry else base64.b64decode(entry['data'])
            if existing_hash(p) != entry['before']:
                raise ValueError(f"{key}: destination changed during export; retry after review")
            atomic(p, data)
    for key, before in journal['removes'].items():
        p = safe(vault, key)
        if existing_hash(p) not in {None, before}:
            raise ValueError(f"{key}: destination changed during cleanup; preserved")
        p.unlink(missing_ok=True)
    save(home / 'state.json', journal['state'])
    path.unlink()


def sync(settings, home, dry=False):
    if not settings.get("enabled", True):
        raise ValueError("bridge is uninstalled or setup incomplete; run setup to enable it")
    vault = Path(settings['vault'])
    issues, notices, held, run_imports, preview = [], [], {}, [], []
    files, tasks, omissions = {}, {}, []
    ledger = read_json(home / 'ledger.json', {'imports': [], 'rejected': []})
    accepted, restored = {}, set()

    def reject(key, reason):
        """Save the phone's text, then let the export restore the generated view."""
        stash_phone_text(home, key, safe(vault, key))
        restored.add(key)
        accepted.pop(key, None)
        notices.append(f'{key}: {reason}')
        ledger_add(ledger, 'rejected', file=key, reason=reason)

    try:
        if not dry:
            recover_export(home, vault)
            prune_private(home, ledger)
        state = read_json(home / 'state.json', {'files': {}, 'tasks': {}})
        active = projects(settings, failed=None if dry else held)
        files, tasks, omissions = inventory(settings, selected_projects=active, failed=None if dry else held)
        snapshot = {}
        for key in state['files'].keys() | files.keys():
            try:
                snapshot[key] = existing_hash(safe(vault, key))
            except (ValueError, OSError) as exc:
                name = owner(key)
                if name is None:
                    raise
                held[name] = f"{key}: {exc}"
        renames = {p.name for p, cfg in active.items() if cfg.get("folderwise-ibridgerename", False)}
        pending, sources, accepted, rejected = requests(vault, state, renames, held)
        if dry:
            for key, reason in rejected.items():
                preview.append(f'PHONE EDIT REJECTED {key}: {reason}; the text would be saved and the view restored')
            for name, reason in held.items():
                preview.append(f'PHONE EDIT BLOCKED {name}: {reason}')
            for name, wanted in sorted(pending.items()):
                try:
                    toggles, renames = plan_import(name, wanted, state['tasks'].get(name, {}), tasks.get(name, {}))
                except Rejected as exc:
                    preview.append(f'PHONE EDIT REJECTED {name}: {exc}; the text would be saved and the view restored')
                else:
                    if toggles or renames:
                        preview.append(f'PHONE EDIT {name}: would toggle {len(toggles)} and rename {len(renames)} task(s)')
        else:
            if pending.keys() - {p.name for p in active} - held.keys():
                raise ValueError('disabled project has pending phone edits; re-enable and import before disabling')
            for project in active:
                if project.name not in pending or project.name in held:
                    continue
                try:
                    done = import_project(settings, project, pending[project.name], state['tasks'].get(project.name, {}), tasks[project.name], home)
                except Rejected as exc:
                    origin = sources.get(project.name, set())
                    if origin and all(k.startswith(TASK_DIR + '/') for k in origin):
                        for key in sorted(origin):
                            reject(key, str(exc))
                    else:
                        held[project.name] = str(exc)
                    continue
                except (ValueError, OSError) as exc:
                    held[project.name] = str(exc)
                    continue
                if done:
                    run_imports.append(done)
                    ledger_add(ledger, 'imports', project=project.name, **done)
            for key, reason in rejected.items():
                if owner(key) not in held:
                    reject(key, reason)
            files, tasks, omissions = inventory(settings, selected_projects=active, failed=held)
    except (ValueError, OSError) as exc:
        if dry:
            raise
        if deferrable(home, exc):
            print(f'Deferred: iCloud is busy with a file ({exc}); retrying on the next run.')
            return 0
        issues.append(str(exc))
    total = sum(content_size(data) for data in files.values())
    print(f"Mode={settings['mode']}; selected {len(files)} files / {total:,} bytes; omitted {len(omissions)} files")
    if dry:
        for key, data in files.items():
            print(f'COPY {key}: {content_size(data)} bytes')
        for key in state['files'].keys() - files.keys():
            if owner(key) not in held:
                print(f'REMOVE if unchanged: {key}')
        for item in omissions:
            print(f"SKIP {item['path']}: {item['bytes']} bytes; {item['reason']}")
        for line in preview:
            print(line)
        return 0
    # A bridge-wide problem freezes every export. A problem in one project pauses only that project:
    # it keeps its previous records and vault files while the others sync.
    if not issues:
        next_files, writes, removes = {}, {}, {}
        try:
            for key, data in files.items():
                name = owner(key)
                if name in held:
                    continue
                try:
                    target = safe(vault, key)
                    old = state['files'].get(key)
                    before, after = existing_hash(target), content_hash(data)
                    if before != snapshot.get(key):
                        raise ValueError(f'{key}: vault changed during sync; preserved for next run')
                    if (before is not None and before != after and (not old or before != old['hash'])
                            and before != accepted.get(key) and key not in restored):
                        try:
                            task_changes(old['text'], target.read_text())
                        except (ValueError, KeyError, TypeError, UnicodeError):
                            raise ValueError(f'{key}: unexpected vault edit or unowned file; preserved') from None
                    entry = {'hash': after}
                    if key.lower().endswith('.md'):
                        entry['text'] = data.read_text() if isinstance(data, Path) else data.decode()
                        if key.startswith(TASK_DIR + '/'):
                            entry.update(project=name, tasks=tasks[name]['_projection'])
                        elif '/' in key:
                            entry.update(project=name, tasks=[t for k, t in tasks[name].items() if k.startswith('md:') and t['path'] == key.split('/', 1)[1]])
                    next_files[key] = entry
                    if before != after:
                        payload = {'source': str(data)} if isinstance(data, Path) else {'data': base64.b64encode(data).decode()}
                        writes[key] = dict(before=before, after=after, **payload)
                except ValueError as exc:
                    if name is None:
                        raise
                    held[name] = str(exc)
            for key, old in state['files'].items():
                name = owner(key)
                if key in files or name in held:
                    continue
                try:
                    p = safe(vault, key)
                    before = existing_hash(p)
                    if before != snapshot.get(key) or before not in {None, old['hash']}:
                        raise ValueError(f'{key}: changed copy prevents cleanup; preserved')
                    removes[key] = before
                except ValueError as exc:
                    if name is None:
                        raise
                    held[name] = str(exc)
            for key in [k for k in list(next_files) + list(removes) if owner(k) in held]:
                next_files.pop(key, None)
                writes.pop(key, None)
                removes.pop(key, None)
            for key, old in state['files'].items():
                if owner(key) in held:
                    next_files[key] = old
            kept = {name: state['tasks'][name] for name in held if name in state['tasks']}
            save(home / 'export.json', dict(writes=writes, removes=removes, state={'files': next_files, 'tasks': {**tasks, **kept}, 'schema': 2}))
            recover_export(home, vault)
        except (ValueError, OSError) as exc:
            if deferrable(home, exc):
                print(f'Deferred: iCloud is busy with a file ({exc}); retrying on the next run.')
                return 0
            issues.append(str(exc))
    managed_bytes = 0
    accepted_state = read_json(home / 'state.json', {'files': {}})
    for key in accepted_state['files']:
        try:
            p = safe(vault, key)
            if p.is_file():
                managed_bytes += p.stat().st_size
        except ValueError:
            pass  # already reported above; never follow a conflicting symlink to count it
    previous_report = read_json(home / 'report.json', {})
    legacy = safe(vault, LEGACY_REPORT)
    legacy_before = existing_hash(legacy)
    legacy_owned = (legacy_before is not None and previous_report.get('path', LEGACY_REPORT) == LEGACY_REPORT
                    and legacy_before == previous_report.get('hash'))
    if legacy_before is not None and not legacy_owned:
        issues.append(f'{LEGACY_REPORT}: legacy report has unowned edits; preserved. Move it outside the vault after review.')
    copies = conflict_copies(vault, set(accepted_state['files']) | set(files)) if not issues else []
    issues.extend(held.values())
    status = report(files, omissions, issues, settings, managed_bytes, ledger, copies, sorted(held))
    target = safe(vault, REPORT)
    if target.exists() and content_hash(target) not in {previous_report.get('hash'), digest(status)}:
        raise ValueError(f'{REPORT} has unowned edits; preserve/rename it before retrying')
    if not target.exists() or target.read_bytes() != status:
        atomic(target, status)
    if legacy_owned:
        if existing_hash(legacy) != legacy_before:
            raise ValueError(f'{LEGACY_REPORT}: changed during migration; preserved')
        legacy.unlink()
    save(home / 'report.json', {'path': REPORT, 'hash': digest(status)})
    last = {'issues': issues, 'notices': notices, 'omitted_files': len(omissions), 'selected_bytes': total, 'managed_bytes': managed_bytes,
            'last_run': dl.now({'timezone': 'UTC'}).isoformat(), 'last_run_epoch': time.time(), 'ok': not issues}
    previous = read_json(home / 'last-run.json', {})
    actionable = [item for item in omissions if item['reason'] != 'excluded by lean mode']
    signature = digest(json.dumps([issues, notices, actionable], sort_keys=True).encode())
    mode = settings['notifications']
    if mode != 'off' and (issues or actionable or notices) and previous.get('issue_signature') != signature:
        last['notification_sent'] = notify('Folderwise bridge needs attention. See _folderwise-sync-status.md in your vault.', home)
    elif mode == 'imports' and run_imports:
        changes = sum(item['toggled'] + item['renamed'] for item in run_imports)
        last['notification_sent'] = notify(f'Folderwise applied {changes} phone change(s) in {len(run_imports)} project(s). '
                                           'See _folderwise-sync-status.md in your vault.', home)
    last['issue_signature'] = signature
    save(home / 'ledger.json', ledger)
    save(home / 'last-run.json', last)
    with (home / 'bridge.log').open('a') as log:
        log.write(json.dumps(last) + '\n')
    if (home / 'bridge.log').stat().st_size > 1_000_000:
        (home / 'bridge.log').replace(home / 'bridge.previous.log')
    for notice in notices:
        print('NOTICE ' + notice)
    for issue in issues:
        print('ERROR ' + issue)
    return 1 if issues else 0


def prepare_schedule(settings, config_path):
    """Prepare an owned named entry point and plist preview, without OS registration."""
    launcher = safe(config_path.parent, 'bin/' + LAUNCHER_NAME)
    if launcher.exists() and launcher.read_bytes() != LAUNCHER_BODY:
        raise ValueError('launch entry point has custom content; preserve or restore it before scheduling')
    if not launcher.exists():
        atomic(launcher, LAUNCHER_BODY)
    launcher.chmod(0o700)
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv not found")
    plist = {"Label": LABEL, "ProgramArguments": [str(launcher), uv, "run", "--quiet", str(TOOLS / "icloud_bridge.py"), "--config", str(config_path), "sync"],
             "StartInterval": settings["interval_minutes"] * 60, "RunAtLoad": True, "WorkingDirectory": str(TOOLS.parent),
             "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "UV_CACHE_DIR": str(config_path.parent / "uv-cache")},
             "StandardOutPath": str(config_path.parent / "launchd.log"), "StandardErrorPath": str(config_path.parent / "launchd-error.log")}
    preview = config_path.parent / 'launchagent-preview.plist'
    atomic(preview, plistlib.dumps(plist))
    return plist


def remove_launcher(home):
    launcher = safe(home, 'bin/' + LAUNCHER_NAME)
    if launcher.exists():
        if launcher.read_bytes() == LAUNCHER_BODY:
            launcher.unlink()
        else:
            print('Preserved customized launch entry point: ' + str(launcher))


NOTIFICATION_VISIBILITY = (
    'Notification requested; macOS controls whether a banner is visible. '
    'If it only appears in Notification Center, check System Settings > Notifications > Folderwise iBridge '
    '(Allow notifications and Desktop), Focus, and Notifications > when mirroring or sharing the display. '
    'The bridge does not change these settings; allowing shared-display notifications can expose other apps’ messages.'
)


def setup_notification(settings):
    return f"folderwise-ibridge is now enabled. Sync job is running and scheduled every {settings['interval_minutes']} minutes."


def schedule(settings, config_path, enable):
    if sys.platform != "darwin":
        raise ValueError("scheduling requires macOS; use sync manually on other systems")
    agent_dir = Path(settings.get("launchagents_dir", str(Path.home() / "Library/LaunchAgents")))
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / (LABEL + ".plist")
    domain = f"gui/{os.getuid()}"
    if path.exists():
        previous = plistlib.loads(path.read_bytes())
        if str(config_path) not in previous.get("ProgramArguments", []):
            raise ValueError("another bridge installation owns this scheduled job")
    if not enable:
        run(["launchctl", "disable", domain + "/" + LABEL])
        subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], capture_output=True)
        path.unlink(missing_ok=True)
        save(config_path.parent / "schedule.json", {"enabled": False})
        print("Scheduled bridge disabled; vault and local state preserved.")
        return
    plist = prepare_schedule(settings, config_path)
    atomic(path, plistlib.dumps(plist))
    run(["launchctl", "enable", domain + "/" + LABEL])
    subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], capture_output=True)
    run(["launchctl", "bootstrap", domain, path])
    message = setup_notification(settings)
    save(config_path.parent / "schedule.json", {"enabled": True, "interval_minutes": settings["interval_minutes"]})
    if settings["notifications"] != "off":
        if not notify(message, config_path.parent):
            print("Notification could not be requested. Scheduling succeeded; use notify-test to retry.")
        else:
            print(NOTIFICATION_VISIBILITY)
    print(message)


def seed_vaults(settings, home):
    """Create reviewed defaults only where a setting file does not already exist."""
    defaults = TOOLS / 'obsidian_defaults'
    if not defaults.is_dir():
        raise ValueError('Obsidian defaults are missing from this framework installation')
    manifest = read_json(home / 'vault-defaults.json', {})
    for root in (Path(settings['source']), Path(settings['vault'])):
        owned = manifest.setdefault(str(root), {})
        for asset in sorted(defaults.rglob('*')):
            if not asset.is_file() or asset.is_symlink():
                continue
            rel = '.obsidian/' + asset.relative_to(defaults).as_posix()
            target = safe(root, rel)
            if target.exists():
                if rel not in owned:
                    print(f'Preserved existing setting: {root.name}/{rel}')
                continue
            atomic(target, asset)
            owned[rel] = content_hash(asset)
            # Retain ownership even if setup is interrupted between setting files.
            save(home / 'vault-defaults.json', manifest)


def enroll_project(project, home):
    """Enroll through the same validated transaction used for task imports."""
    with project_transaction(project, home) as clone:
        target = clone / ".docs.yaml"
        target.write_text(target.read_text() + "\nfolderwise-ibridgesync: true\n")
        dl.parse_config(target.read_text())
        git(clone, "add", "--", ".docs.yaml")
        git(clone, "commit", "--quiet", "-m", "Enable project participation in the Obsidian iCloud bridge", "-m",
            "Record the user-selected bridge setup. Task imports remain subject to project validation and hooks.\n\nBridge: folderwise-ibridge")


def setup_bridge(settings, path, dry=False):
    source = Path(settings['source'])
    roots = projects(settings, include_disabled=True)
    enrollment = []
    for project in roots:
        cfg = roots[project]
        # Missing means not configured yet; an explicit false remains an opt-out.
        if 'folderwise-ibridgesync' not in cfg:
            if git(project, 'status', '--porcelain'):
                raise ValueError(f'{project.name}: commit local changes before setup enrolls this project')
            git(project, 'ls-files', '--error-unmatch', '.docs.yaml')
            enrollment.append(project)
    marker = safe(source, '.folderwise-obsidian.json')
    previous = read_json(marker, {})
    if previous and previous.get('bridge_config') != str(path):
        raise ValueError('another bridge configuration owns the local Obsidian setup')
    print(f"Initialize parent vault: {source}; iCloud vault: {settings['vault']}")
    print('New projects will default to folderwise-ibridgesync: true; --icloud-disabled opts out.')
    print('Enroll unconfigured projects: ' + (', '.join(p.name for p in enrollment) or 'none'))
    print('Preserve explicit project opt-outs and existing Obsidian settings. Install Tasks/Dataview through Obsidian.')
    if dry:
        eligible = {p: cfg for p, cfg in roots.items() if p in enrollment or cfg.get('folderwise-ibridgesync', False)}
        files, _, omissions = inventory(settings, selected_projects=eligible)
        print(f"Preview export: {len(files)} files / {sum(content_size(data) for data in files.values()):,} bytes; {len(omissions)} omissions")
        for key, data in files.items():
            print(f"COPY {key}: {content_size(data)} bytes")
        for item in omissions:
            print(f"SKIP {item['path']}: {item['reason']}")
        return 0
    # An incomplete setup does not change defaults for future projects or enable sync.
    save(path, dict(settings, enabled=False))
    save(marker, {'version': 1, 'enabled': False, 'bridge_config': str(path)})
    seed_vaults(settings, path.parent)
    for project in enrollment:
        enroll_project(project, path.parent)
    settings['enabled'] = True
    save(path, settings)
    result = sync(settings, path.parent)
    if result:
        settings['enabled'] = False
        save(path, settings)
        return result
    save(marker, {'version': 1, 'enabled': True, 'bridge_config': str(path)})
    print('Obsidian defaults installed. Community-plugin code and device workspace layouts were not copied.')
    return 0


def uninstall_bridge(settings, path):
    """Disable integration and remove only unchanged, setup-owned setting files."""
    home = path.parent
    if read_json(home / 'schedule.json', {}).get('enabled'):
        schedule(settings, path, False)
    settings['enabled'] = False
    save(path, settings)
    remove_launcher(home)
    remove_notifier(home)
    marker = safe(Path(settings['source']), '.folderwise-obsidian.json')
    profile = read_json(marker, {})
    if profile.get('bridge_config') == str(path):
        marker.unlink()
    manifest = read_json(home / 'vault-defaults.json', {})
    allowed = {settings['source'], settings['vault']}
    retained = {}
    for folder, entries in manifest.items():
        if folder not in allowed:
            raise ValueError('defaults manifest names an unrelated vault; inspect it before uninstalling')
        root = Path(folder)
        for rel, expected in entries.items():
            if not rel.startswith('.obsidian/'):
                raise ValueError('defaults manifest contains an unmanaged path')
            p = safe(root, rel)
            if not p.exists():
                continue
            if p.is_file() and content_hash(p) == expected:
                p.unlink()
                print(f'Removed setup default: {root.name}/{rel}')
                for parent in p.parents:
                    if parent == root:
                        break
                    try:
                        parent.rmdir()
                    except OSError:
                        break
            else:
                retained.setdefault(folder, {})[rel] = expected
                print(f'Preserved customized setting: {root.name}/{rel}')
    save(home / 'vault-defaults.json', retained)
    print('Bridge uninstalled. New projects default to sync disabled. Documents, project flags, plugins and recovery state were preserved.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_HOME / "config.json")
    ap.add_argument("--dry-run", action="store_true", help="preview setup without changing vaults, projects or defaults")
    ap.add_argument("--setup-message", action="store_true", help="notify-test: replay the setup-success text with the configured interval")
    ap.add_argument("--no-schedule", action="store_true", help="initialize and sync without registering a macOS job")
    ap.add_argument("--source", type=Path)
    ap.add_argument("--vault", type=Path)
    ap.add_argument("--mode", choices=["full", "lean"])
    ap.add_argument("--interval-minutes", type=int)
    ap.add_argument("--max-image-bytes", type=int)
    ap.add_argument("--max-images-total-bytes", type=int)
    ap.add_argument("--unlimited-images", action="store_true")
    ap.add_argument("--notifications", choices=["off", "errors", "imports"])
    ap.add_argument("command", choices=["setup", "configure", "plan", "sync", "status", "enable", "disable", "schedule-enable", "schedule-disable", "doctor", "logs", "notify-test", "vault-init", "uninstall", "schedule-prepare", "resolve"])
    ap.add_argument("project", nargs="?", help="enable/disable: project folder; resolve: vault-relative path of a file with a pending phone edit")
    args = ap.parse_args()
    if args.setup_message and args.command != "notify-test":
        ap.error("--setup-message requires notify-test")
    path = args.config.expanduser().absolute()
    try:
        with locked(path.parent):
            if args.command == "setup":
                if path.exists() and config_load(path).get('enabled', True):
                    raise ValueError("config exists; use configure or vault-init")
                if not args.source or not args.vault:
                    raise ValueError("setup requires --source and --vault")
                settings = dict(version=1, source=str(args.source.expanduser().resolve()), vault=str(args.vault.expanduser().resolve()),
                           mode="full", interval_minutes=5, max_image_bytes=None, max_images_total_bytes=None,
                           notifications="errors", adapters={}, enabled=False)
                if path.exists():
                    previous = config_load(path)
                    if (previous['source'], previous['vault']) != (settings['source'], settings['vault']):
                        raise ValueError('reinstall must use the original source and vault; use a new config for another installation')
                    settings = previous
            else:
                settings = config_load(path)
            if args.command in {"setup", "configure"}:
                for key in ("mode", "interval_minutes", "max_image_bytes", "max_images_total_bytes", "notifications"):
                    value = getattr(args, key)
                    if value is not None:
                        settings[key] = value
                if args.unlimited_images:
                    settings["max_image_bytes"] = settings["max_images_total_bytes"] = None
                candidate = path.with_name("config-candidate.json")
                try:
                    save(candidate, settings)
                    config_load(candidate)
                finally:
                    candidate.unlink(missing_ok=True)
                if args.command == 'setup':
                    result = setup_bridge(settings, path, args.dry_run)
                    if result or args.dry_run or args.no_schedule:
                        return result
                else:
                    save(path, settings)
                    print(f"Configured {settings['mode']} mode; interval {settings['interval_minutes']} minutes. Reload scheduling if the interval changed.")
                    return 0
            if args.command == 'vault-init':
                seed_vaults(settings, path.parent)
                return 0
            if args.command == 'uninstall':
                uninstall_bridge(settings, path)
                return 0
            if args.command in {"enable", "disable"}:
                if not args.project or args.project.startswith(("_", ".")) or "/" in args.project:
                    raise ValueError("provide a project folder name")
                project = safe(Path(settings["source"]), args.project)
                pc = dl.load_config(project)
                pc["folderwise-ibridgesync"] = args.command == "enable"
                atomic(project / ".docs.yaml", yaml.safe_dump(pc, sort_keys=False).encode())
                print(f"{args.project}: folderwise-ibridgesync={pc['folderwise-ibridgesync']}; commit this project setting when ready")
                return 0
            if args.command == "resolve":
                return resolve(settings, path.parent, args.project)
            if args.command in {"sync", "plan"}:
                return sync(settings, path.parent, args.command == "plan")
            if args.command == 'schedule-prepare':
                prepare_schedule(settings, path)
                print('Prepared named launcher and preview at ' + str(path.parent / 'launchagent-preview.plist'))
                return 0
            if args.command.startswith("schedule-") or args.command == "setup":
                if args.command == "schedule-enable" and sync(settings, path.parent):
                    raise ValueError("resolve sync errors before scheduling")
            elif args.command == "notify-test":
                message = setup_notification(settings) if args.setup_message else "Folderwise iBridge notifications work."
                if not notify(message, path.parent):
                    raise ValueError("notification request failed (macOS notification app required)")
                print(message)
                print(NOTIFICATION_VISIBILITY)
            elif args.command == "doctor":
                files, _, omissions = inventory(settings)
                for key in files:
                    safe(Path(settings["vault"]), key)
                if not shutil.which('uv'):
                    raise ValueError('uv missing; install uv before scheduling')
                print(f"OK {len(files)} export files; {len(omissions)} policy omissions; notifications={settings['notifications']}")
                last = read_json(path.parent / "last-run.json", {})
                scheduled = read_json(path.parent / "schedule.json", {})
                print(json.dumps({'last_run': last, 'schedule': scheduled}, indent=2))
                if scheduled.get('enabled'):
                    if scheduled['interval_minutes'] != settings['interval_minutes']:
                        raise ValueError('interval changed; rerun schedule-enable to update launchd')
                    if time.time() - last.get('last_run_epoch', 0) > settings['interval_minutes'] * 180:
                        raise ValueError('scheduled sync is stale; inspect logs and launchd-error.log')
                    result = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], capture_output=True)
                    if result.returncode:
                        raise ValueError('scheduled job is not loaded; rerun schedule-enable')
                if (path.parent / 'export.json').exists() or last.get("issues"):
                    return 1
            elif args.command == "logs":
                log = path.parent / "bridge.log"
                print(log.read_text()[-12000:] if log.exists() else "No runs yet.")
            else:
                print(json.dumps({"config": settings, "last_run": read_json(path.parent / "last-run.json", {}),
                                  "schedule": read_json(path.parent / "schedule.json", {}), "schedule_plist": str(Path(settings.get("launchagents_dir", str(Path.home() / "Library/LaunchAgents"))) / (LABEL + ".plist"))}, indent=2))
        if args.command.startswith("schedule-") or args.command == "setup":
            schedule(settings, path, args.command != "schedule-disable")
        return 0
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"icloud-bridge: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
