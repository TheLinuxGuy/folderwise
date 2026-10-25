#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Folderwise iCloud bridge: Mac-owned export and boolean task import.

Commands: setup, configure, plan, sync, status, enable, disable, schedule-enable,
schedule-disable, doctor, logs, notify-test. See docs/obsidian.md before setup.
"""
from __future__ import annotations

import argparse
import base64
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
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docslib as dl  # noqa: E402

TOOLS = Path(__file__).resolve().parent
LABEL = "org.folderwise.ibridge"
REPORT, DASHBOARD, TASK_DIR = "Bridge Status.md", "Tasks.md", "_Folderwise Tasks"
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".heic", ".bmp"}
SKIP = {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "_doc-template.md", "node_modules", "__pycache__", "#recycle", "credentials.json", "id_rsa", "id_ed25519"}
CHECKBOX = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+\[)([ xX])(\].*)$")
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
    settings = read_json(path)
    if not isinstance(settings, dict) or settings.get("version") != 1:
        raise ValueError("run setup first (missing or unsupported bridge config)")
    source, vault = Path(settings["source"]), Path(settings["vault"])
    if not source.is_absolute() or not vault.is_absolute():
        raise ValueError("source and vault must be absolute paths")
    if not isinstance(settings.get('adapters', {}), dict):
        raise ValueError("adapters must be an object mapping project names to commands")
    if source == vault or source in vault.parents or vault in source.parents:
        raise ValueError("source and vault must be separate, non-nested directories")
    if settings.get("mode") not in {"full", "lean"} or settings.get("notifications") not in {"off", "errors"}:
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


def projects(settings):
    source = Path(settings["source"])
    if not source.is_dir():
        raise ValueError("source directory is unavailable")
    result = []
    for p in sorted(source.iterdir()):
        if p.name.startswith(("_", ".")) or p.is_symlink() or not p.is_dir() or not (p / ".docs.yaml").is_file():
            continue
        if (p / ".docs.yaml").is_symlink():
            raise ValueError(f"symlink project config: {p.name}")
        cfg = dl.load_config(p)
        disabled = cfg.get("icloud_disabled", False)
        if type(disabled) is not bool:
            raise ValueError(f"{p.name}: icloud_disabled must be boolean")
        if not disabled:
            if Path(git(p, "rev-parse", "--show-toplevel").strip()).resolve() != p.resolve():
                raise ValueError(f"{p.name}: expected an independent Git repository")
            result.append(p)
    return result


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
    fence = None
    generated = False
    front = text.startswith("---\n")
    for line, raw in enumerate(text.splitlines()):
        if front:
            if line and raw == "---":
                front = False
            continue
        marker = re.match(r"^\s*(`{3,}|~{3,})", raw)
        if marker:
            char = marker[1][0]
            if fence and char == fence[0] and len(marker[1]) >= fence[1]:
                fence = None
            elif not fence:
                fence = (char, len(marker[1]))
            continue
        if fence:
            continue
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
        if not safe(project, task["path"]).is_file() or not isinstance(task.get("title"), str):
            raise ValueError("adapter tasks need a title and an existing source document path")
        task["id"] = "adapter:" + task["id"]
    return tasks


def inventory(settings):
    files, tasks, omissions = {}, {}, []
    total_images = 0
    for project in projects(settings):
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
        projection = [f"# {project.name} tasks", "", "Generated task view. Only checkbox toggles are imported.", ""]
        mapping = []
        for task in local_tasks:
            title = re.sub(r"[\r\n]", " ", task["title"])
            title = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)
            target = quote(project.name + "/" + task["path"], safe="/")
            mapping.append(dict(line=len(projection), id=task["id"], checked=task["checked"]))
            projection.append(f"- [{'x' if task['checked'] else ' '}] {title} ([source](../{target}))")
        files[f"{TASK_DIR}/{project.name}.md"] = ("\n".join(projection) + "\n").encode()
        tasks[project.name]["_projection"] = mapping
    files[DASHBOARD] = ("# All projects\n\n## Open tasks\n\n```tasks\npath includes " + TASK_DIR +
                        "\nnot done\ngroup by filename\n```\n\n## Completed tasks\n\n```tasks\npath includes " + TASK_DIR +
                        "\ndone\ngroup by filename\n```\n").encode()
    return files, tasks, omissions


def task_changes(base, current):
    before, after = base.splitlines(keepends=True), current.splitlines(keepends=True)
    if len(before) != len(after):
        raise ValueError("only checkbox on/off changes are supported")
    changed = {}
    for i, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        a, b = CHECKBOX.match(old.rstrip("\r\n")), CHECKBOX.match(new.rstrip("\r\n"))
        if not a or not b or a[1] != b[1] or a[3] != b[3] or old[len(old.rstrip('\r\n')):] != new[len(new.rstrip('\r\n')):]:
            raise ValueError("only checkbox on/off changes are supported")
        changed[i] = b[2] != " "
    return changed


def requests(vault, state):
    wanted = {}
    for key, entry in state.get("files", {}).items():
        p = safe(vault, key)
        if not p.is_file() or "text" not in entry:
            continue
        data = p.read_text()
        if data == entry["text"]:
            continue
        delta = task_changes(entry["text"], data)
        mapping = {t["line"]: t for t in entry.get("tasks", [])}
        project = entry.get("project")
        for line, checked in delta.items():
            if line not in mapping:
                raise ValueError(f"{key}: checkbox has no authoritative task mapping")
            task = mapping[line]
            target = wanted.setdefault(project, {})
            if task["id"] in target and target[task["id"]] != checked:
                raise ValueError(f"{key}: conflicting toggles of the same task")
            target[task["id"]] = checked
    return wanted


def import_project(settings, project, wanted, baseline, current, home):
    for key in wanted:
        if key not in current or key not in baseline:
            raise ValueError(f"{project.name}: task changed or disappeared on Mac; resolve pending toggle")
        task, old = current[key], baseline[key]
        if task.get("duplicate") and task["source_hash"] != old.get("source_hash"):
            raise ValueError(f"{project.name}: duplicate task moved during concurrent edit")
    changes = {key: value for key, value in wanted.items() if current[key]["checked"] != value}
    if not changes:
        return
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
        md, ac = {}, []
        for key, checked in changes.items():
            task = current[key]
            if key.startswith("adapter:"):
                ac.append(dict(id=key[len("adapter:"):], checked=checked))
            else:
                rel = task["path"]
                if digest(safe(clone, rel).read_text().encode()) != task["source_hash"]:
                    raise ValueError("source changed while preparing task transaction")
                lines = md.setdefault(rel, safe(clone, rel).read_text().splitlines(keepends=True))
                m = CHECKBOX.match(lines[task["line"]].rstrip("\r\n"))
                ending = "\n" if lines[task["line"]].endswith("\n") else ""
                lines[task["line"]] = m[1] + ("x" if checked else " ") + m[3] + ending
        for rel, lines in md.items():
            safe(clone, rel).write_text("".join(lines))
        if ac:
            adapter(settings, clone, "apply", ac)
        config = dl.load_config(clone)
        for rel in git(clone, "diff", "--name-only", "-z").split("\0"):
            if rel.endswith(".md"):
                p = safe(clone, rel)
                text, errors, _ = dl.stamp_text(p.read_text(), p.name, config, "human", "Toggle tasks via Obsidian iCloud bridge")
                if errors:
                    raise ValueError("; ".join(errors))
                p.write_text(text)
        if ac:
            adapter(settings, clone, "validate")
            actual = {t["id"]: t["checked"] for t in adapter(settings, clone, "list")}
            if any(actual.get("adapter:" + t["id"]) != t["checked"] for t in ac):
                raise ValueError("adapter did not apply requested checkbox states")
        run(["uv", "run", "--quiet", TOOLS / "docs_lint.py"], clone)
        git(clone, "add", "--all")
        git(clone, "commit", "--quiet", "-m", "Update task completion from Obsidian", "-m",
            f"Apply {len(changes)} user checkbox toggle(s) and regenerate authoritative views.\n\n"
            "Checkbox state is user-reported; no factual verification was performed.\n"
            "Validation: project adapter, Folderwise lint and Git hooks.\n\nBridge: folderwise-ibridge")
        if git(project, "status", "--porcelain") or git(project, "rev-parse", "HEAD").strip() != head:
            raise ValueError(f"{project.name}: Mac repository changed during import; retry after review")
        git(project, "fetch", "--quiet", "--no-tags", str(clone), "HEAD")
        git(project, "merge", "--ff-only", "--quiet", "FETCH_HEAD")
    finally:
        if clone.exists():
            shutil.rmtree(clone)


def notify(message):
    script = 'on run argv\ndisplay notification (item 1 of argv) with title "Folderwise iBridge"\nend run'
    try:
        run(["osascript", "-e", script, message])
        return True
    except (ValueError, OSError):
        return False


def report(files, omissions, issues, settings, managed_bytes):
    image_bytes = sum(content_size(data) for key, data in files.items() if Path(key).suffix.lower() in IMAGES)
    rows = ["# Bridge Status", "", f"Mode: **{settings['mode']}**. Interval: **{settings['interval_minutes']} minutes**.",
            f"Estimated managed export: **{sum(content_size(data) for data in files.values()):,} bytes**, including **{image_bytes:,} image bytes**.",
            f"Currently present managed payload: **{managed_bytes:,} bytes** (excludes status/settings and unowned files).",
            "This is a file-size estimate, not your iCloud account usage or bill.",
            f"Image limits: per file={settings['max_image_bytes']}; aggregate={settings['max_images_total_bytes']} bytes (None = unlimited).", "", "## Issues", ""]
    rows += ["- " + str(x).replace("\n", " ") for x in issues] or ["None."]
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
    vault = Path(settings['vault'])
    issues = []
    files, tasks, omissions = {}, {}, []
    try:
        if not dry:
            recover_export(home, vault)
        state = read_json(home / 'state.json', {'files': {}, 'tasks': {}})
        files, tasks, omissions = inventory(settings)
        snapshot = {key: existing_hash(safe(vault, key)) for key in state['files'].keys() | files.keys()}
        if not dry:
            pending = requests(vault, state)
            active = projects(settings)
            if pending.keys() - {p.name for p in active}:
                raise ValueError('disabled project has pending phone edits; re-enable and import before disabling')
            for project in active:
                if project.name in pending:
                    import_project(settings, project, pending[project.name], state['tasks'].get(project.name, {}), tasks[project.name], home)
            files, tasks, omissions = inventory(settings)
    except (ValueError, OSError) as exc:
        if dry:
            raise
        issues.append(str(exc))
    total = sum(content_size(data) for data in files.values())
    print(f"Mode={settings['mode']}; selected {len(files)} files / {total:,} bytes; omitted {len(omissions)} files")
    if dry:
        for key, data in files.items():
            print(f'COPY {key}: {content_size(data)} bytes')
        for key in state['files'].keys() - files.keys():
            print(f'REMOVE if unchanged: {key}')
        for item in omissions:
            print(f"SKIP {item['path']}: {item['bytes']} bytes; {item['reason']}")
        return 0
    # Failed imports freeze exports. Preflight all writes and cleanup before journaling.
    if not issues:
        next_files, writes, removes = {}, {}, {}
        try:
            for key, data in files.items():
                target = safe(vault, key)
                old = state['files'].get(key)
                before, after = existing_hash(target), content_hash(data)
                if before != snapshot.get(key):
                    raise ValueError(f'{key}: vault changed during sync; preserved for next run')
                if before is not None and before != after and (not old or before != old['hash']):
                    try:
                        task_changes(old['text'], target.read_text())
                    except (ValueError, KeyError, TypeError, UnicodeError):
                        raise ValueError(f'{key}: unexpected vault edit or unowned file; preserved') from None
                entry = {'hash': after}
                if key.lower().endswith('.md'):
                    entry['text'] = data.read_text() if isinstance(data, Path) else data.decode()
                    if key.startswith(TASK_DIR + '/'):
                        name = Path(key).stem
                        entry.update(project=name, tasks=tasks[name]['_projection'])
                    elif '/' in key:
                        name, rel = key.split('/', 1)
                        entry.update(project=name, tasks=[t for k, t in tasks[name].items() if k.startswith('md:') and t['path'] == rel])
                next_files[key] = entry
                if before != after:
                    payload = {'source': str(data)} if isinstance(data, Path) else {'data': base64.b64encode(data).decode()}
                    writes[key] = dict(before=before, after=after, **payload)
            for key, old in state['files'].items():
                if key not in files:
                    p = safe(vault, key)
                    before = existing_hash(p)
                    if before != snapshot.get(key) or before not in {None, old['hash']}:
                        raise ValueError(f'{key}: changed copy prevents cleanup; preserved')
                    removes[key] = before
            save(home / 'export.json', dict(writes=writes, removes=removes, state={'files': next_files, 'tasks': tasks}))
            recover_export(home, vault)
            app = safe(vault, '.obsidian/app.json')
            if not app.exists():
                atomic(app, b'{\"useMarkdownLinks\":true,\"newLinkFormat\":\"relative\",\"alwaysUpdateLinks\":false}\n')
        except (ValueError, OSError) as exc:
            issues.append(str(exc))
    managed_bytes = 0
    accepted = read_json(home / 'state.json', {'files': {}})
    for key in accepted['files']:
        try:
            p = safe(vault, key)
            if p.is_file():
                managed_bytes += p.stat().st_size
        except ValueError:
            pass  # already reported above; never follow a conflicting symlink to count it
    status = report(files, omissions, issues, settings, managed_bytes)
    target = safe(vault, REPORT)
    previous_report = read_json(home / 'report.json', {})
    if target.exists() and content_hash(target) not in {previous_report.get('hash'), digest(status)}:
        raise ValueError('Bridge Status.md has unowned edits; preserve/rename it before retrying')
    if not target.exists() or target.read_bytes() != status:
        atomic(target, status)
    save(home / 'report.json', {'hash': digest(status)})
    last = {'issues': issues, 'omitted_files': len(omissions), 'selected_bytes': total, 'managed_bytes': managed_bytes,
            'last_run': dl.now({'timezone': 'UTC'}).isoformat(), 'last_run_epoch': time.time(), 'ok': not issues}
    previous = read_json(home / 'last-run.json', {})
    actionable = [item for item in omissions if item['reason'] != 'excluded by lean mode']
    signature = digest(json.dumps([issues, actionable], sort_keys=True).encode())
    if settings['notifications'] == 'errors' and (issues or actionable) and previous.get('issue_signature') != signature:
        last['notification_sent'] = notify('Folderwise bridge needs attention. See Bridge Status.md in your vault.')
    last['issue_signature'] = signature
    save(home / 'last-run.json', last)
    with (home / 'bridge.log').open('a') as log:
        log.write(json.dumps(last) + '\n')
    if (home / 'bridge.log').stat().st_size > 1_000_000:
        (home / 'bridge.log').replace(home / 'bridge.previous.log')
    for issue in issues:
        print('ERROR ' + issue)
    return 1 if issues else 0

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
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv not found")
    plist = {"Label": LABEL, "ProgramArguments": [uv, "run", "--quiet", str(TOOLS / "icloud_bridge.py"), "--config", str(config_path), "sync"],
             "StartInterval": settings["interval_minutes"] * 60, "RunAtLoad": True, "WorkingDirectory": str(TOOLS.parent),
             "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "UV_CACHE_DIR": str(config_path.parent / "uv-cache")},
             "StandardOutPath": str(config_path.parent / "launchd.log"), "StandardErrorPath": str(config_path.parent / "launchd-error.log")}
    atomic(path, plistlib.dumps(plist))
    run(["launchctl", "enable", domain + "/" + LABEL])
    subprocess.run(["launchctl", "bootout", domain + "/" + LABEL], capture_output=True)
    run(["launchctl", "bootstrap", domain, path])
    message = f"folderwise-ibridge is now enabled. Sync job is running and scheduled every {settings['interval_minutes']} minutes."
    save(config_path.parent / "schedule.json", {"enabled": True, "interval_minutes": settings["interval_minutes"]})
    if settings["notifications"] != "off" and not notify(message):
        print("Notification could not be sent; check macOS notification settings. Scheduling succeeded.")
    print(message)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_HOME / "config.json")
    ap.add_argument("--source", type=Path)
    ap.add_argument("--vault", type=Path)
    ap.add_argument("--mode", choices=["full", "lean"])
    ap.add_argument("--interval-minutes", type=int)
    ap.add_argument("--max-image-bytes", type=int)
    ap.add_argument("--max-images-total-bytes", type=int)
    ap.add_argument("--unlimited-images", action="store_true")
    ap.add_argument("--notifications", choices=["off", "errors"])
    ap.add_argument("command", choices=["setup", "configure", "plan", "sync", "status", "enable", "disable", "schedule-enable", "schedule-disable", "doctor", "logs", "notify-test"])
    ap.add_argument("project", nargs="?")
    args = ap.parse_args()
    path = args.config.expanduser().absolute()
    try:
        with locked(path.parent):
            if args.command == "setup":
                if path.exists():
                    raise ValueError("config exists; use configure")
                if not args.source or not args.vault:
                    raise ValueError("setup requires --source and --vault")
                settings = dict(version=1, source=str(args.source.expanduser().resolve()), vault=str(args.vault.expanduser().resolve()),
                           mode="full", interval_minutes=5, max_image_bytes=None, max_images_total_bytes=None,
                           notifications="errors", adapters={})
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
                save(path, settings)
                print(f"Configured {settings['mode']} mode; interval {settings['interval_minutes']} minutes. Run plan, sync, then schedule-enable.")
                return 0
            if args.command in {"enable", "disable"}:
                if not args.project or args.project.startswith(("_", ".")) or "/" in args.project:
                    raise ValueError("provide a project folder name")
                project = safe(Path(settings["source"]), args.project)
                pc = dl.load_config(project)
                pc["icloud_disabled"] = args.command == "disable"
                atomic(project / ".docs.yaml", yaml.safe_dump(pc, sort_keys=False).encode())
                print(f"{args.project}: icloud_disabled={pc['icloud_disabled']}; commit this project setting when ready")
                return 0
            if args.command in {"sync", "plan"}:
                return sync(settings, path.parent, args.command == "plan")
            if args.command.startswith("schedule-"):
                if args.command == "schedule-enable" and sync(settings, path.parent):
                    raise ValueError("resolve sync errors before scheduling")
            elif args.command == "notify-test":
                if not notify("Folderwise iBridge notifications work."):
                    raise ValueError("notification delivery failed (macOS/osascript required)")
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
        if args.command.startswith("schedule-"):
            schedule(settings, path, args.command == "schedule-enable")
        return 0
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"icloud-bridge: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
