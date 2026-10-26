#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Self-test for the docs tools. Run it after any change to _tools/ or _template/, and before sync_rules.py.

It copies _tools/ and _template/ into a temp folder, creates a project there with new_project.py and
drives the real CLIs and the real git pre-commit hook. Nothing in your folders is touched.

  selftest.py              run everything (about 15 seconds)
  selftest.py -k links     only sections whose name contains 'links'
  selftest.py --keep       keep the temp folder and print its path
Exit code 0 = all passed, 1 = something failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC_TOOLS = Path(__file__).resolve().parent
SRC_TEMPLATE = SRC_TOOLS.parent / "_template"
RESULTS: list[tuple[bool, str, str]] = []
CTX: dict = {}

GIT_ENV = {"GIT_AUTHOR_NAME": "selftest", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "selftest", "GIT_COMMITTER_EMAIL": "t@t"}


def sh(cmd, cwd=None, env=None) -> tuple[int, str]:
    e = dict(os.environ, **GIT_ENV)
    e.pop("DOCS_FAKE_NOW", None)
    e.pop("DOCS_SKIP_HOOK", None)
    e.update(env or {})
    r = subprocess.run(cmd, cwd=cwd or CTX["proj"], env=e, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def tool(name, *args, cwd=None, env=None):
    return sh(["uv", "run", "--quiet", str(CTX["tools"] / name), *map(str, args)], cwd, env)


def git(*args, env=None):
    return sh(["git", *args], env=env)


def check(label: str, cond: bool, detail: str = ""):
    RESULTS.append((bool(cond), label, "" if cond else detail.strip()[-600:]))
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond else f"\n       {detail.strip()[-300:]}"), flush=True)


def load_docslib():
    """Import docslib from the isolated temp copy of the tools (not the source tree)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("docslib_under_test", CTX["tools"] / "docslib.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(rel: str) -> str:
    return (CTX["proj"] / rel).read_text()


def write(rel: str, text: str):
    p = CTX["proj"] / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def edit(rel: str, old: str, new: str):
    t = read(rel)
    assert old in t, f"{rel}: {old!r} not found"
    write(rel, t.replace(old, new, 1))


def commit(msg="test", env=None):
    git("add", "-A")
    return git("commit", "-q", "-m", msg, "-m", "Agent: selftest\nModel: x", env=env)


# ---------------------------------------------------------------- sections

def s_create():
    rc, out = sh(["uv", "run", "--quiet", str(CTX["tools"] / "new_project.py"), "--name", "proj",
                  "--description", "Self-test project", "--sensitivity", "private", "--by", "claude/selftest"], cwd=CTX["root"])
    check("new_project exits 0", rc == 0, out)
    m = re.search(r"--- paste ---\n(.*?)\n--- end ---", out, re.S)
    prompt = m.group(1) if m else ""
    check("new_project prints a paste-ready agent setup prompt", bool(prompt) and f"cd {CTX['proj']} && claude" in out, out)
    check("setup prompt names the project and its purpose", 'docs project "proj"' in prompt and "purpose: Self-test project" in prompt, prompt)
    check("setup prompt: read files first, one batched answer, capped follow-ups, 3 structures, wait for a choice, commit gate", all(x in prompt for x in (
        "never ask what files answer", "ask nothing yet", "at most 5 follow-ups (8 if essential)", "recommended default",
        "3 genuinely different folder structures", "wait for my choice", "never the managed block", "show me the diff", "commit once I agree")), prompt)
    check("setup prompt stays brief and on one line (easy to paste)", len(prompt.split()) <= 160 and "\n" not in prompt, f"{len(prompt.split())} words")
    rc2, out2 = sh(["uv", "run", "--quiet", str(CTX["tools"] / "new_project.py"), "--name", "proj-np", "--description", "x",
                    "--sensitivity", "private", "--by", "human", "--no-prompt"], cwd=CTX["root"])
    check("--no-prompt hides the prompt", rc2 == 0 and "--- paste ---" not in out2 and "Next: edit AGENTS.md" in out2, out2)
    shutil.rmtree(CTX["root"] / "proj-np", ignore_errors=True)
    # --start: launch the agent in the new project with the prompt as its first argument (fake agent binary)
    fake = CTX["root"] / "fakebin"
    fake.mkdir()
    (fake / "claude").write_text('#!/bin/sh\nprintf "%s\\n%s\\n" "$(pwd -P)" "$1" > "$(dirname "$0")/started.txt"\n')
    (fake / "claude").chmod(0o755)
    start = ["uv", "run", "--quiet", str(CTX["tools"] / "new_project.py"), "--name", "proj-start", "--description", "Start test",
             "--sensitivity", "private", "--by", "human", "--start", "claude"]
    path_env = {"PATH": f"{fake}:{os.environ['PATH']}"}
    rc3, out3 = sh(start, cwd=CTX["root"], env=path_env)
    check("--start without an interactive terminal does not launch the agent", rc3 == 0 and not (fake / "started.txt").exists()
          and "needs an interactive terminal" in out3, out3)
    shutil.rmtree(CTX["root"] / "proj-start", ignore_errors=True)
    rc4, out4 = sh(start, cwd=CTX["root"], env={**path_env, "DOCS_START_FORCE": "1"})
    started = (fake / "started.txt").read_text().splitlines() if (fake / "started.txt").exists() else []
    check("--start launches the agent inside the new project with the setup prompt as its first argument",
          rc4 == 0 and len(started) == 2 and started[0] == str((CTX["root"] / "proj-start").resolve())
          and started[1].startswith('Set up the docs project "proj-start"'), out4 + str(started))
    shutil.rmtree(CTX["root"] / "proj-start", ignore_errors=True)
    shutil.rmtree(fake, ignore_errors=True)
    proj = CTX["proj"]
    for f in ("AGENTS.md", "CLAUDE.md", ".docs.yaml", "README.md", "_doc-template.md", ".markdownlint.json",
              ".vscode/settings.json", ".vscode/extensions.json", "data/.gitkeep", "docs/.gitkeep"):
        check(f"project has {f}", (proj / f).exists())
    check("CLAUDE.md imports AGENTS.md", "@AGENTS.md" in read("CLAUDE.md"))
    try:
        cs = json.loads(read(".claude/settings.json"))
    except Exception as e:  # missing or invalid
        cs = {}
        check(".claude/settings.json is valid JSON", False, repr(e))
    check("project ships .claude/settings.json with acceptEdits and no auto memory",
          cs.get("permissions", {}).get("defaultMode") == "acceptEdits" and cs.get("autoMemoryEnabled") is False, str(cs))
    check("project settings default to model sonnet and effortLevel low",
          cs.get("model") == "sonnet" and cs.get("effortLevel") == "low", str(cs))
    check(".gitignore keeps .claude/settings.local.json out of git and escapes #recycle", ".claude/settings.local.json" in read(".gitignore") and "\\#recycle/" in read(".gitignore"))
    check("pre-commit hook installed", os.access(proj / ".git/hooks/pre-commit", os.X_OK))
    rc, out = git("log", "--format=%B")
    check("scaffold commit has Agent trailer", rc == 0 and "Agent: claude" in out, out)
    check("README starts with front matter, byline and index", read("README.md").startswith("---\n") and "byline:start" in read("README.md"))
    rc, out = tool("docs_lint.py")
    check("fresh project lints clean", rc == 0, out)


def s_new_doc_and_index():
    rc, out = tool("docs_new.py", "docs/hosts/nas.md", "--type", "inventory", "--title", "NAS inventory",
                   "--about", "Disks and shares", "--by", "codex/selftest")
    check("docs_new creates a doc", rc == 0 and (CTX["proj"] / "docs/hosts/nas.md").exists(), out)
    check("docs_new refreshes the README index", "docs/hosts/nas.md" in read("README.md") and "README index refreshed" in out, out)
    rc, out = tool("docs_lint.py")
    check("lint clean after docs_new (index in sync, no orphan warning)", rc == 0 and "orphan" not in out, out)
    rc, out = commit("add nas")
    check("commit with valid docs passes the hook", rc == 0, out)
    rc, out = tool("docs_new.py", "docs/hosts/nas.md", "--type", "inventory", "--by", "codex/selftest")
    check("docs_new refuses to overwrite", rc != 0, out)


def s_stamp_and_hook():
    edit("docs/hosts/nas.md", "## Change Log", "Extra line.\n\n## Change Log")
    rc, out = commit("unstamped edit")
    check("hook blocks an edited doc with no new Change Log row", rc != 0 and "Change Log unchanged" in out, out)
    git("reset", "-q")
    rc, out = tool("docs_stamp.py", "docs/hosts/nas.md", "--by", "codex/selftest", "--summary", "Add extra line")
    check("docs_stamp exits 0", rc == 0, out)
    t = read("docs/hosts/nas.md")
    check("stamp wrote Change Log row and updated_by", "Add extra line" in t and "updated_by: codex/selftest" in t)
    rc, out = commit("stamped edit")
    check("commit passes once stamped", rc == 0, out)
    rc, out = tool("docs_stamp.py", "docs/hosts/nas.md", "--by", "bad by", "--summary", "x")
    check("stamp rejects a malformed --by", rc != 0, out)
    rc, out = tool("docs_stamp.py", "docs/hosts/nas.md", "--by", "codex/selftest", "--summary", "verify", "--verified")
    check("--verified sets last_verified", rc == 0 and re.search(r"last_verified: \d{4}-\d{2}-\d{2}", read("docs/hosts/nas.md")), out)
    commit("verified")


def s_hook_fail_closed():
    tools, off = CTX["tools"], CTX["root"] / "_tools_off"
    tools.rename(off)
    try:
        rc, out = git("commit", "--allow-empty", "-q", "-m", "x")
        check("hook blocks when the tools folder is missing", rc != 0 and "BLOCKED" in out, out)
        rc, out = git("commit", "--allow-empty", "-q", "-m", "x", env={"DOCS_SKIP_HOOK": "1"})
        check("DOCS_SKIP_HOOK=1 bypasses the hook", rc == 0 and "skipped" in out, out)
    finally:
        off.rename(tools)
    rc, out = git("commit", "--allow-empty", "-q", "-m", "x")
    check("hook passes again once tools are back", rc == 0, out)


def s_lint_rules():
    write("docs/bad.md", "# Bad\n\ntext\n")
    tool("docs_stamp.py", "docs/bad.md", "--init", "--type", "reference", "--by", "codex/selftest", "--summary", "base")
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")  # so only the doc under test can fail lint
    base = read("docs/bad.md")
    rc, out = tool("docs_lint.py", "docs/bad.md")
    check("baseline doc lints clean before mutations", rc == 0, out)
    cases = [
        ("bad status", lambda t: t.replace("status: draft", "status: weird", 1), "status:"),
        ("bad updated_by", lambda t: t.replace("updated_by: codex/selftest", "updated_by: bob", 1), "updated_by"),
        ("unknown field", lambda t: t.replace("\n---\n", "\nbogus: 1\n---\n", 1), "unknown field"),
        ("bad toc value", lambda t: t.replace("\n---\n", "\ntoc: maybe\n---\n", 1), "toc: must be true or false"),
        ("wrong zone abbreviation", lambda t: re.sub(r"\b(PDT|PST)\b", "JST", t, count=1), "zone should be"),
        ("future date", lambda t: re.sub(r"^updated: .*$", "updated: 2099-01-01", t, count=1, flags=re.M), "in the future"),
        ("stale byline", lambda t: t.replace("**Status:** draft", "**Status:** active", 1), "byline is out of date"),
        ("missing front matter", lambda t: re.sub(r"\A---\n.*?\n---\n", "", t, flags=re.S), "front matter"),
    ]
    for label, fn, expect in cases:
        write("docs/bad.md", fn(base))
        rc, out = tool("docs_lint.py", "docs/bad.md")
        check(f"lint rejects: {label}", rc == 1 and expect in out, out)
    write("docs/bad.md", base)
    edit(".docs.yaml", "extra_fields: {}", "extra_fields:\n  host: {type: string, required: true}")
    rc, out = tool("docs_lint.py", "docs/bad.md")
    check("lint enforces a required extra field from .docs.yaml", rc == 1 and "missing field: host" in out, out)
    edit(".docs.yaml", "extra_fields:\n  host: {type: string, required: true}", "extra_fields: {}")
    edit(".docs.yaml", "schema_version: 1", "schema_version: 1\nmax_doc_lines: 5")
    rc, out = tool("docs_lint.py", "docs/bad.md")
    check("size limit only warns (exit 0)", rc == 0 and "WARN docs/bad.md" in out, out)
    edit(".docs.yaml", "max_doc_lines: 5\n", "")
    (CTX["proj"] / "docs/bad.md").unlink()
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")


def s_timezone():
    for fake, zone in (("2026-07-04T12:00", "PDT"), ("2026-01-04T09:30", "PST")):
        p = CTX["proj"] / "docs/tz.md"
        p.write_text("# Tz\n")
        rc, out = tool("docs_stamp.py", "docs/tz.md", "--init", "--by", "human", "--summary", "tz",
                       env={"DOCS_FAKE_NOW": fake, "TZ": "Asia/Tokyo"})
        want = fake.replace("T", " ") + " " + zone
        check(f"project timezone beats machine timezone ({want})", rc == 0 and want in read("docs/tz.md"), out + read("docs/tz.md"))
        p.unlink()


def s_links():
    write("docs/guide.md", "# Guide\n\n## Setup\n\ntext, see [other](other.md).\n\n## Usage\n\ntext\n")
    tool("docs_stamp.py", "docs/guide.md", "--init", "--by", "human", "--summary", "g")
    body = ("# Other\n\nGood: [setup](guide.md#setup), [guide](guide.md). Code `[x](nope.md)` is ignored.\n\n"
            "```md\n[y](nope2.md)\n```\n\nBad: [gone](missing.md), [anchor](guide.md#nope), [abs](/Users/x/guide.md), "
            "[case](Guide.md), [escape](../../x.md).\n\nPlain mention of guide.md should warn.\n")
    write("docs/other.md", body)
    tool("docs_stamp.py", "docs/other.md", "--init", "--by", "human", "--summary", "o")
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")
    rc, out = tool("docs_lint.py")
    check("lint fails on broken links", rc == 1, out)
    for needle, label in (("missing.md", "missing file"), ("#nope", "missing anchor"), ("absolute path", "absolute path"),
                          ("Guide.md", "wrong letter case"), ("leaves the project", "link outside the repo")):
        check(f"links: reports {label}", needle in out, out)
    check("links: code span and fence are ignored", "nope.md" not in out and "nope2.md" not in out, out)
    check("links: plain mention only warns", "WARN docs/other.md" in out and "names another doc without a link" in out, out)
    t = read("docs/other.md")
    for bad in ("[gone](missing.md), ", "[anchor](guide.md#nope), ", "[abs](/Users/x/guide.md), ", "[case](Guide.md), ", "[escape](../../x.md)."):
        t = t.replace(bad, "")
    write("docs/other.md", t)
    tool("docs_stamp.py", "docs/other.md", "--by", "human", "--summary", "fix links")
    rc, out = tool("docs_lint.py")
    check("lint passes once links are valid (warnings allowed)", rc == 0, out)


def s_staged_source():
    """The real pre-commit hook must validate the commit, regardless of disk-only edits."""
    project = CTX['root'] / 'staged-boundary'
    tool('new_project.py', '--name', project.name, '--description', 'Staged boundary test', '--no-prompt', cwd=CTX['root'])

    def local(name, *args):
        return tool(name, *args, cwd=project)

    def repo(*args):
        return sh(['git', *args], cwd=project)

    def stamp(rel):
        return local('docs_stamp.py', rel, '--by', 'human', '--summary', 'Boundary regression')

    def commit_staged():
        return repo('commit', '--allow-empty', '-qm', 'Exercise the staged hook')

    def restore():
        repo('restore', '--source=HEAD', '--staged', '--worktree', '.')

    local('docs_new.py', 'docs/target.md', '--type', 'reference', '--title', 'Target', '--by', 'human')
    local('docs_new.py', 'docs/source.md', '--type', 'reference', '--title', 'Source', '--by', 'human')
    source, target = project / 'docs/source.md', project / 'docs/target.md'
    source.write_text(source.read_text().replace('## Change Log', '[Target](target.md#target)\n\n## Change Log'))
    stamp('docs/source.md')
    repo('add', '-A')
    rc, out = commit_staged()
    check('staged source fixture commits through the real hook', rc == 0, out)

    source.write_text(source.read_text().replace('target.md#target', 'untracked.md'))
    (project / 'docs/untracked.md').write_text('# Disk-only target\n')
    stamp('docs/source.md'); repo('add', 'docs/source.md')
    rc, out = commit_staged()
    check('staged hook rejects a disk-only link target', rc != 0 and 'target not found: untracked.md' in out, out)
    restore(); (project / 'docs/untracked.md').unlink()

    repo('rm', '--cached', 'docs/target.md')
    rc, out = commit_staged()
    check('staged deletion checks incoming links even when the file remains on disk', rc != 0 and 'target not found: target.md' in out, out)
    restore()

    source.write_text(source.read_text().replace('target.md#target', 'Target.md'))
    stamp('docs/source.md'); repo('add', 'docs/source.md')
    rc, out = commit_staged()
    check('staged target lookup preserves exact letter case', rc != 0 and 'target not found: Target.md' in out, out)
    restore()

    source.write_text(source.read_text().replace('target.md#target', 'target.md#disk-only'))
    stamp('docs/source.md'); repo('add', 'docs/source.md')
    target.write_text(target.read_text() + '\n## Disk only\n')
    rc, out = commit_staged()
    check('staged anchor validation ignores unstaged target headings', rc != 0 and "anchor '#disk-only' not found" in out, out)
    restore()

    target.write_text(target.read_text().replace('# Target', '# Renamed', 1))
    stamp('docs/target.md'); repo('add', 'docs/target.md')
    rc, out = commit_staged()
    check('staged heading changes validate unchanged incoming links', rc != 0 and "anchor '#target' not found" in out, out)
    restore()

    readme = project / 'README.md'
    readme.write_text(readme.read_text().replace('  - [Source]', '  - [Wrong title]', 1))
    stamp('README.md'); repo('add', 'README.md')
    readme.write_text(repo('show', 'HEAD:README.md')[1])
    rc, out = commit_staged()
    check('staged README index cannot be hidden by a corrected working copy', rc != 0 and 'index block is out of date' in out, out)
    restore()

    cfg = project / '.docs.yaml'
    good_config = cfg.read_text()
    for bad, needle in [('timezone: Invalid/Zone\n', 'unknown timezone'), ('- not a mapping\n', 'YAML mapping'), ('bad: [\n', 'invalid project YAML')]:
        cfg.write_text(bad); repo('add', '.docs.yaml'); cfg.write_text(good_config)
        rc, out = commit_staged()
        check('staged config rejects ' + needle, rc != 0 and needle in out and 'Traceback' not in out, out)
        restore()

    source.write_text(source.read_text() + '\nA valid staged edit.\n')
    stamp('docs/source.md'); repo('add', 'docs/source.md')
    target.unlink(); readme.unlink(); cfg.unlink()
    rc, out = commit_staged()
    check('staged hook uses indexed documents, README and config despite conflicting disk edits', rc == 0, out)
    restore()

    # A merge conflict and a missing staged config fail closed with useful diagnostics.
    blob = repo('rev-parse', 'HEAD:docs/target.md')[1].strip()
    repo('update-index', '--force-remove', 'docs/target.md')
    env = dict(os.environ, **GIT_ENV)
    subprocess.run(['git', 'update-index', '--index-info'], cwd=project, env=env,
                   input=f'100644 {blob} 1\tdocs/target.md\n100644 {blob} 2\tdocs/target.md\n', text=True, check=True)
    rc, out = local('docs_lint.py', '--staged')
    check('staged merge conflicts fail closed without a traceback', rc == 1 and 'unresolved merge entry' in out, out)
    restore()
    repo('rm', '--cached', '.docs.yaml')
    rc, out = commit_staged()
    check('staged hook rejects an unstaged-only project config', rc != 0 and '.docs.yaml is missing' in out, out)
    restore()


def s_markdown_fences():
    """Exercise the shared scanner through stamping, lint, heading/move rewrites and bridge imports."""
    root = CTX['root'] / 'fences-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    project = source / 'fences'

    def local(name, *args):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=project if project.exists() else source)

    def bridge(*args):
        return local('icloud_bridge.py', '--config', home / 'config.json', *args)

    def commit_all():
        sh(['git', 'add', '-A'], cwd=project)
        return sh(['git', 'commit', '-qm', 'Fence regression fixture'], cwd=project)

    local('new_project.py', '--name', 'fences', '--description', 'Fence regression', '--no-prompt')
    local('docs_new.py', 'docs/fenced.md', '--type', 'reference', '--title', 'Fenced', '--by', 'human')
    note = project / 'docs/fenced.md'
    example = ('````md\n```\n## Example heading\n[Missing](missing.md)\n- [ ] Example task\n'
               '~~~\n```` trailing text\n- [ ] Still example\n`````\n\n'
               '~~~~md\n~~~\n## Tilde example\n[Missing](also-missing.md)\n- [ ] Tilde task\n~~~~\n')
    body = (example + '\n## Real heading\n\n[Real](#real-heading)\n- [ ] Real task\n\n'
            '## Repeated\n\n## Repeated\n\n[Second](#repeated-1)\n\n'
            '```unclosed\n## Hidden tail\n[Missing](tail.md)\n- [ ] Hidden task\n')
    original = note.read_text()
    front = original.split('\n---\n', 1)[0] + '\n---\n'
    note.write_text(front + '# Fenced\n\nCafé offset test.\n\n' + body + '\n' + original[original.index('## Change Log'):])
    # Keep the changelog outside an unclosed fence; use a separate doc for the unclosed case.
    note.write_text(note.read_text().replace('```unclosed\n## Hidden tail\n[Missing](tail.md)\n- [ ] Hidden task\n', ''))
    rc, out = local('docs_stamp.py', 'docs/fenced.md', '--toc', '--by', 'human', '--summary', 'Add fenced examples')
    text = note.read_text()
    check('TOC ignores short, mismatched and non-closing fences', rc == 0 and example in text
          and '- [Real heading](#real-heading)' in text
          and '- [Example heading]' not in text and '- [Tilde example]' not in text and '- [Repeated](#repeated-1)' in text, out)
    rc, out = local('docs_lint.py', 'docs/fenced.md')
    check('link lint shares the TOC fence policy', rc == 0 and 'target not found' not in out, out)
    rc, out = local('docs_mv.py', 'heading', 'docs/fenced.md', 'Real heading', 'Renamed heading', '--by', 'human')
    check('heading rename keeps offsets and fenced bytes intact', rc == 0 and example in note.read_text()
          and '[Real](#renamed-heading)' in note.read_text(), out)
    local('docs_new.py', 'docs/ref.md', '--type', 'reference', '--title', 'Reference', '--by', 'human')
    ref = project / 'docs/ref.md'
    ref.write_text(ref.read_text().replace('## Change Log', '[Link](fenced.md#renamed-heading)\n\n````md\n```\n[Example](fenced.md)\n````\n\n## Change Log'))
    local('docs_stamp.py', 'docs/ref.md', '--by', 'human', '--summary', 'Link the example')
    rc, out = local('docs_mv.py', 'mv', 'docs/fenced.md', 'docs/moved.md', '--by', 'human')
    note = project / 'docs/moved.md'
    check('file moves rewrite prose links without touching nested code examples', rc == 0
          and '[Link](moved.md#renamed-heading)' in ref.read_text() and '[Example](fenced.md)' in ref.read_text(), out)
    local('docs_new.py', 'docs/unclosed.md', '--type', 'reference', '--title', 'Unclosed', '--by', 'human')
    unclosed = project / 'docs/unclosed.md'
    unclosed.write_text(unclosed.read_text() + '\n```unclosed\n## Hidden tail\n[Missing](tail.md)\n- [ ] Hidden task\n')
    local('docs_stamp.py', 'docs/unclosed.md', '--toc', '--by', 'human', '--summary', 'Unclosed example')
    rc, out = local('docs_lint.py')
    check('an unclosed code fence masks the rest of the document', rc == 0 and '- [Hidden tail]' not in unclosed.read_text(), out)
    note.write_bytes(note.read_text().replace('\n', '\r\n').encode())
    rc, out = commit_all()
    check('nested-fence documents commit through the real hook', rc == 0, out)
    rc, out = bridge('setup', '--source', source, '--vault', vault, '--notifications', 'off', '--no-schedule')
    view = vault / '_Folderwise Tasks/fences.md'
    text = view.read_text() if view.exists() else ''
    check('bridge task discovery uses the same nested and unclosed fence policy', rc == 0 and 'Real task' in text
          and all(s not in text for s in ('Example task', 'Still example', 'Tilde task', 'Hidden task')), out)
    view.write_text(text.replace('- [ ] Real task', '- [x] Real task'))
    rc, out = bridge('sync')
    check('bridge applies the real task at its CRLF source line without changing fenced examples', rc == 0
          and b'- [x] Real task\r\n' in note.read_bytes() and example in note.read_text(), out)


def s_toc():
    rc, out = tool("docs_stamp.py", "docs/guide.md", "--toc", "--by", "human", "--summary", "toc")
    t = read("docs/guide.md")
    check("--toc inserts Contents with anchors", rc == 0 and "toc: true" in t and "- [Setup](#setup)" in t and "- [Usage](#usage)" in t, out + t)
    edit("docs/guide.md", "## Usage", "## Extra\n\ntext\n\n## Usage")
    rc, out = tool("docs_lint.py", "docs/guide.md")
    check("lint flags a stale Contents list", rc == 1 and "Contents is out of date" in out, out)
    tool("docs_stamp.py", "docs/guide.md", "--by", "human", "--summary", "refresh toc")
    check("re-stamp regenerates it", "- [Extra](#extra)" in read("docs/guide.md"))
    rc, out = tool("docs_stamp.py", "docs/guide.md", "--no-toc", "--by", "human", "--summary", "no toc")
    check("--no-toc removes it", rc == 0 and "toc:" not in read("docs/guide.md") and "## Contents" not in read("docs/guide.md"), out)
    rc, out = tool("docs_lint.py")
    check("lint clean after TOC round trip", rc == 0, out)
    commit("toc round trip")


def s_mv():
    write("docs/uses.md", "# Uses\n\nSee [setup](guide.md#setup) and [guide](guide.md).\n")
    tool("docs_stamp.py", "docs/uses.md", "--init", "--by", "human", "--summary", "u")
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")
    commit("uses")
    rc, out = tool("docs_mv.py", "mv", "docs/guide.md", "docs/howto/guide.md", "--by", "codex/selftest")
    check("docs_mv mv exits 0 and lint passes", rc == 0 and "lint: ok" in out, out)
    uses = read("docs/uses.md")
    check("mv rewrote links and kept the anchor", "(howto/guide.md#setup)" in uses and "(howto/guide.md)" in uses, uses)
    check("mv recomputed relative links inside the moved doc", "(../other.md)" in read("docs/howto/guide.md"), read("docs/howto/guide.md"))
    check("mv refreshed the README index", "docs/howto/guide.md" in read("README.md"), read("README.md"))
    check("mv stamped the moved doc", "Moved from docs/guide.md" in read("docs/howto/guide.md"))
    rc, out = git("status", "--short")
    check("git sees a rename", re.search(r"^R", out, re.M) is not None, out)
    commit("moved")
    rc, out = tool("docs_mv.py", "heading", "docs/howto/guide.md", "Setup", "Install", "--by", "codex/selftest")
    check("docs_mv heading exits 0", rc == 0 and "lint: ok" in out, out)
    check("heading rename rewrote #anchor links", "(howto/guide.md#install)" in read("docs/uses.md"), read("docs/uses.md"))
    rc, out = tool("docs_mv.py", "mv", "docs/uses.md", "docs/hosts/nas.md", "--by", "human")
    check("mv refuses an existing destination", rc != 0 and "exists" in out, out)
    rc, out = tool("docs_mv.py", "mv", "AGENTS.md", "x.md", "--by", "human")
    check("mv refuses protected files", rc != 0, out)
    rc, out = tool("docs_mv.py", "mv", "docs/howto", "docs/guides", "--by", "codex/selftest")
    check("mv moves a whole folder and lints clean", rc == 0 and "lint: ok" in out and "(guides/guide.md#install)" in read("docs/uses.md"), out)
    commit("folder moved")


def s_tables():
    write("data/hosts.csv", "name,ip\nnas,10.0.0.5\nrouter,10.0.0.1\n")
    write("docs/tbl.md", "# Hosts\n\n<!-- table:start src=data/hosts.csv -->\n<!-- table:end -->\n")
    tool("docs_stamp.py", "docs/tbl.md", "--init", "--by", "human", "--summary", "t")
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")
    rc, out = tool("docs_lint.py", "docs/tbl.md")
    check("lint flags an unrendered table block", rc == 1 and "out of date" in out, out)
    rc, out = tool("render_tables.py", "--by", "codex/selftest", "--summary", "render")
    check("render_tables renders and stamps", rc == 0 and "| nas | 10.0.0.5 |" in read("docs/tbl.md"), out)
    rc, out = tool("docs_lint.py")
    check("lint clean after render", rc == 0, out)
    write("data/hosts.csv", "name,ip\nnas,10.0.0.5\nrouter,10.0.0.1\nap,10.0.0.9\n")
    rc, out = tool("docs_lint.py", "docs/tbl.md")
    check("lint flags a block stale vs its CSV", rc == 1, out)
    tool("render_tables.py", "--by", "codex/selftest", "--summary", "render again")
    big = "\n".join(f"| r{i} | {i} |" for i in range(12))
    write("docs/big.md", "# Big\n\n| a | b |\n|---|---|\n" + big + "\n")
    tool("docs_stamp.py", "docs/big.md", "--init", "--by", "human", "--summary", "b")
    rc, out = tool("docs_lint.py", "docs/big.md")
    check("lint rejects a large inline table", rc == 1 and "inline table" in out, out)
    (CTX["proj"] / "docs/big.md").unlink()
    commit("tables")
    s_tables_money()


def s_tables_money():
    """Opt-in currency display (money=, currency=, currency_col=); legacy directives stay byte-identical."""
    lib = load_docslib()
    render = lib.render_csv_table
    ledger = (
        "id,account,amount,currency,rate,qty,opened,pct\n"
        "A1,1234567890,21000,USD,4.25,10.5,2026-01-02,5%\n"
        "A2,0001,1234567.5,EUR,0.0425,3,2026-02-03,7%\n"
        "A3,0002,,USD,1.5,2,2026-03-04,\n"
        "A4,0003,unknown,GBP,1.5,2,2026-03-04,\n"
        "A5,0004,-1234.567,usd,1.5,2,2026-03-04,\n"
        "A6,0005,50,,1.5,2,2026-03-04,\n"
        "A7,0006,50,N/A,1.5,2,2026-03-04,\n"
        "A8,0007,1000.005,JPY,1.5,2,2026-03-04,\n"
        "A9,0008,-0.001,USD,1.5,2,2026-03-04,\n"
        "A10,0009,$5,USD,1.5,2,2026-03-04,\n"
    )
    legacy = {"src": "x", "cols": "id,amount,rate", "sort": "-amount", "where": "currency=USD"}
    plain = render(ledger, legacy)
    check("money: legacy directive shows raw values", "| A1 | 21000 | 4.25 |" in plain and "$" not in plain.replace("$5", ""), plain)
    legacy_all = render(ledger, {"cols": "id,amount,rate", "where": "id=A1"}) + "\n" + render(ledger, {"cols": "id,amount,rate", "where": "id=A6"})
    check("money: legacy output is byte-identical to the pre-money format",
          render(ledger, {"cols": "id,amount,rate", "where": "id=A1"}) == "| id | amount | rate |\n|---|---|---|\n| A1 | 21000 | 4.25 |",
          legacy_all)
    check("money: unknown directive keys are still ignored without money=",
          render(ledger, {**legacy, "currency": "EUR", "currency_col": "nope"}) == plain)
    check("money: empty money= is not an opt-in", render(ledger, {**legacy, "money": ""}) == plain)

    out = render(ledger, {"money": "amount", "sort": "id"})
    row = {ln.split(" | ")[0].lstrip("| "): ln for ln in out.splitlines() if ln.startswith("| A")}
    check("money: USD shows $21,000.00", "| $21,000.00 |" in row["A1"], row["A1"])
    check("money: non-USD uses separators, 2 places and ISO code", "| 1,234,567.50 EUR |" in row["A2"], row["A2"])
    check("money: blank and unknown amounts stay unchanged", "| 0002 |  | USD |" in row["A3"] and "| unknown | GBP |" in row["A4"], row["A3"] + row["A4"])
    check("money: negatives and lowercase codes", "| -$1,234.57 |" in row["A5"], row["A5"])
    check("money: blank/invalid row currency without fallback stays raw", "| 50 |  |" in row["A6"] and "| 50 | N/A |" in row["A7"], row["A6"] + row["A7"])
    check("money: explicit rounding is half-up", "| 1,000.01 JPY |" in row["A8"], row["A8"])
    check("money: tiny negative rounds to $0.00 without a sign", "| $0.00 |" in row["A9"], row["A9"])
    check("money: non-plain decimals ($5) are untouched", "| $5 | USD |" in row["A10"], row["A10"])
    check("money: rates, quantities, dates, ids, accounts, percentages untouched",
          all(x in row["A2"] for x in ("| 0.0425 |", "| 3 |", "| 2026-02-03 |", "| 7% |", "| 0001 |", "| A2 |")), row["A2"])

    out = render(ledger, {"money": "amount", "currency": "USD", "sort": "id"})
    check("money: currency= falls back for blank row currency only",
          "| $50.00 |" in out and "| 50 | N/A |" in out and "1,234,567.50 EUR" in out, out)
    nocur = "id,balance,rate\nB1,2500,3.5\nB2,,3.5\nB3,n/a,3.5\n"
    out = render(nocur, {"money": "balance", "currency": "usd"})
    check("money: table without currency column uses explicit currency=",
          "| B1 | $2,500.00 | 3.5 |" in out and "| B2 |  | 3.5 |" in out and "| B3 | n/a | 3.5 |" in out, out)
    for label, a in (("a table without a currency column needs currency=", {"money": "balance"}),
                     ("an unknown money column is an error", {"money": "nope", "currency": "USD"}),
                     ("a malformed currency= is an error", {"money": "balance", "currency": "dollars"})):
        try:
            render(nocur, a)
            check(f"money: {label}", False, "no error raised")
        except ValueError as e:
            check(f"money: {label}", True, str(e))
    alt = "id,amt,ccy\nC1,10,CAD\n"
    check("money: currency_col= picks another currency column", "| C1 | 10.00 CAD | CAD |" in render(alt, {"money": "amt", "currency_col": "ccy"}))
    pipe = render("id,amount,currency,note\nP1,5,EUR,a|b\n", {"money": "amount"})
    check("money: escaping and source order preserved", "| P1 | 5.00 EUR | EUR | a\\|b |" in pipe, pipe)
    check("money: output is stable across renders", render(ledger, {"money": "amount"}) == render(ledger, {"money": "amount"}))

    write("data/ledger.csv", "id,amount,currency\nL1,21000,USD\nL2,3500.5,CHF\n")
    write("docs/money.md", "# Money\n\n<!-- table:start src=data/ledger.csv money=amount -->\n<!-- table:end -->\n"
                          "\n<!-- table:start src=data/ledger.csv cols=id,amount -->\n<!-- table:end -->\n")
    tool("docs_stamp.py", "docs/money.md", "--init", "--by", "human", "--summary", "m")
    tool("docs_index.py", "--write", "--by", "human", "--summary", "index")
    rc, out = tool("render_tables.py", "--by", "codex/selftest", "--summary", "money")
    text = read("docs/money.md")
    check("money: render_tables renders opted-in and legacy blocks side by side",
          rc == 0 and "| L1 | $21,000.00 | USD |" in text and "| L2 | 3,500.50 CHF | CHF |" in text and "| L1 | 21000 |" in text, out + text)
    rc, out = tool("docs_lint.py")
    check("money: lint clean after render", rc == 0, out)
    write("docs/bad.md", "# Bad\n\n<!-- table:start src=data/hosts.csv money=ip -->\n<!-- table:end -->\n")
    rc, out = tool("render_tables.py", "docs/bad.md", "--by", "codex/selftest", "--summary", "bad")
    check("money: render_tables reports a misconfigured directive", rc == 1 and "currency" in out, out)
    (CTX["proj"] / "docs/bad.md").unlink()
    commit("money tables")


def s_stale_index_recent():
    rc, out = tool("docs_stale.py", env={"DOCS_FAKE_NOW": "2027-12-01T10:00"})
    check("docs_stale lists overdue docs", rc == 0 and "overdue" in out and "nas.md" in out, out)
    edit("docs/hosts/nas.md", "status: draft", "status: archived")
    tool("docs_stamp.py", "docs/hosts/nas.md", "--by", "human", "--summary", "archive")
    rc, out = tool("docs_stale.py", env={"DOCS_FAKE_NOW": "2027-12-01T10:00"})
    check("archived docs are skipped by staleness", "nas.md" not in out, out)
    rc, out = tool("docs_index.py")
    check("docs_index lists docs", rc == 0 and "docs/hosts/nas.md" in out, out)
    rc, out = tool("docs_recent.py", "--since", "30d")
    check("docs_recent lists recent changes with who", rc == 0 and "selftest" in out and "nas.md" in out, out)
    rc, out = tool("docs_lint.py")
    check("index goes stale when a doc's status changes, and lint says how to fix it",
          rc == 1 and "docs_index.py --write" in out, out)
    tool("docs_index.py", "--write", "--by", "human", "--summary", "refresh index")
    rc, out = tool("docs_lint.py")
    check("lint clean after docs_index --write", rc == 0, out)
    commit("stale/index")


def s_sync():
    proj = CTX["proj"]
    rc, out = tool("sync_rules.py", "--check", cwd=CTX["root"])
    check("sync_rules --check: fresh project is in sync", rc == 0, out)
    edit("AGENTS.md", "Documentation rules", "Documentation rulez")
    (proj / ".markdownlint.json").unlink()
    s = json.loads(read(".vscode/settings.json"))
    s.pop("markdown.preview.frontMatter", None)
    s["editor.rulers"] = [100]
    write(".vscode/settings.json", json.dumps(s))
    rc, out = tool("sync_rules.py", "--check", cwd=CTX["root"])
    check("--check reports rules, config and settings drift", rc == 1 and "AGENTS.md managed block" in out and ".markdownlint.json" in out
          and ".vscode/settings.json" in out, out)
    rc, out = tool("sync_rules.py", cwd=CTX["root"])
    check("sync_rules applies the template", rc == 0, out)
    s = json.loads(read(".vscode/settings.json"))
    check("settings merge restores template keys and keeps project-only keys",
          s.get("markdown.preview.frontMatter") == "hide" and s.get("editor.rulers") == [100], str(s))
    check("copied config restored", (proj / ".markdownlint.json").is_file())
    cs = json.loads(read(".claude/settings.json"))
    cs["permissions"]["allow"].append("Bash(echo *)")
    cs["permissions"]["ask"].remove("Bash(git push *)")
    write(".claude/settings.json", json.dumps(cs))
    write(".gitignore", "node_modules/\n")
    rc, out = tool("sync_rules.py", "--check", cwd=CTX["root"])
    check("--check reports .claude/settings.json and .gitignore drift", rc == 1 and ".claude/settings.json" in out and ".gitignore" in out, out)
    tool("sync_rules.py", cwd=CTX["root"])
    cs = json.loads(read(".claude/settings.json"))
    check("claude settings merge restores template rules and keeps project-only allow rules",
          "Bash(echo *)" in cs["permissions"]["allow"] and "Bash(git push *)" in cs["permissions"]["ask"], str(cs))
    check(".gitignore keeps project lines and gains template lines", "node_modules/" in read(".gitignore") and ".claude/settings.local.json" in read(".gitignore"), read(".gitignore"))
    rc, out = tool("sync_rules.py", "--check", cwd=CTX["root"])
    check("--check is clean after sync", rc == 0, out)
    (proj / ".git/hooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")
    rc, out = tool("sync_rules.py", "--check", cwd=CTX["root"])
    check("--check notices a modified hook", rc == 1 and "pre-commit hook" in out, out)
    tool("sync_rules.py", cwd=CTX["root"])


def s_doctor():
    proj = CTX["proj"]
    rc, out = tool("docs_doctor.py")
    check("doctor: a healthy project has no FAIL", rc == 0 and "0 FAIL" in out, out)
    check("doctor: reports hook, template sync and lint", all(x in out for x in ("pre-commit hook installed", "rules and config match the template", "lint clean")), out)
    check("doctor: clean when no CLAUDE.md sits above the project", "no CLAUDE.md above the project" in out, out)
    for rel in ("CLAUDE.md", ".claude/CLAUDE.md"):
        write(f"../{rel}", "@AGENTS.md\n")  # lands in the temp root, above the project
        rc, out = tool("docs_doctor.py")
        check(f"doctor: warns about {rel} above the project (exit 0)", rc == 0 and "is above this project" in out and rel in out, out)
        rc, out = tool("docs_doctor.py", "--strict")
        check(f"doctor --strict fails on {rel} above the project", rc == 1, out)
        (CTX["root"] / rel).unlink()
    (CTX["root"] / ".claude").rmdir()
    hook = proj / ".git/hooks/pre-commit"
    hook.unlink()
    rc, out = tool("docs_doctor.py")
    check("doctor: a missing hook is a FAIL (exit 1)", rc == 1 and "pre-commit hook missing" in out, out)
    tool("sync_rules.py", cwd=CTX["root"])
    check("sync_rules reinstalls the hook", hook.is_file())
    edit(".docs.yaml", "schema_version: 1", "schema_version: 1\nmax_doc_line: 5")
    rc, out = tool("docs_doctor.py")
    check("doctor: an unknown .docs.yaml key warns (exit 0)", rc == 0 and "unknown key 'max_doc_line'" in out, out)
    rc, out = tool("docs_doctor.py", "--strict")
    check("doctor --strict turns warnings into exit 1", rc == 1, out)
    edit(".docs.yaml", "max_doc_line: 5\n", "")
    edit(".docs.yaml", "sensitivity: private", "sensitivity: restricted")
    git("remote", "add", "origin", "/tmp/nowhere.git")
    rc, out = tool("docs_doctor.py")
    check("doctor: a restricted project with a remote warns", "restricted project has remote(s) origin" in out, out)
    git("remote", "remove", "origin")
    edit(".docs.yaml", "sensitivity: restricted", "sensitivity: private")
    rc, out = tool("docs_doctor.py", env={"DOCS_FAKE_NOW": "2028-06-01T10:00"})
    check("doctor: flags docs overdue for re-verification", "overdue for re-verification" in out, out)
    write("docs/nofm.md", "# No front matter\n")
    rc, out = tool("docs_doctor.py")
    check("doctor: failing lint is a FAIL", rc == 1 and "lint failing" in out, out)
    (proj / "docs/nofm.md").unlink()
    rc, out = tool("docs_doctor.py", "--all", cwd=CTX["root"])
    check("doctor --all covers every project", "== proj" in out, out)
    rc, out = tool("docs_doctor.py", "nosuch", cwd=CTX["root"])
    check("doctor rejects an unknown project name", rc == 2, out)


def s_layout():
    """Guards for the real Folderwise folder: nothing above the projects may feed Claude Code extra instructions."""
    root = SRC_TOOLS.parent
    for rel in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
        check(f"no {rel} at the Folderwise root (Claude Code would load it into every project)", not (root / rel).exists())
    check("root AGENTS.md exists (read natively by Codex and by Claude Code when working at the root)", (root / "AGENTS.md").is_file())
    try:
        ts = json.loads((SRC_TEMPLATE / ".claude/settings.json").read_text())
    except Exception as e:
        ts = {}
        check("template .claude/settings.json is valid JSON", False, repr(e))
    mode = ts.get("permissions", {}).get("defaultMode")
    check("template does not set defaultMode to auto/bypassPermissions (Claude Code ignores those in project settings)",
          mode not in ("auto", "bypassPermissions") and mode is not None, str(mode))
    check("template does not lock effort via the CLAUDE_CODE_EFFORT_LEVEL env var (it would override /effort)",
          "CLAUDE_CODE_EFFORT_LEVEL" not in ts.get("env", {}))
    check("template has no deny rules (owner chose not to block git or rm commands)", not ts.get("permissions", {}).get("deny"))
    tpl = (SRC_TEMPLATE / "CLAUDE.md")
    check("template CLAUDE.md imports AGENTS.md (keeps parent AGENTS.md out of project sessions)", tpl.is_file() and "@AGENTS.md" in tpl.read_text())


def s_cli_errors():
    """Documented failure modes: bad arguments and wrong locations are refused with exit 2/1 and a clear message."""
    root_cwd = CTX["root"]  # contains no .docs.yaml, so there is no project here
    cases = [
        ("docs_new rejects a malformed --by", ("docs_new.py", "docs/x.md", "--type", "reference", "--by", "bob"), None, 2, "--by must be"),
        ("docs_new rejects a non-markdown path", ("docs_new.py", "docs/x.txt", "--type", "reference", "--by", "human"), None, 2, "must end in .md"),
        ("docs_new refuses to overwrite an existing doc", ("docs_new.py", "README.md", "--type", "reference", "--by", "human"), None, 1, "already exists"),
        ("docs_new outside a project is refused", ("docs_new.py", "docs/x.md", "--type", "reference", "--by", "human"), root_cwd, 2, "no .docs.yaml"),
        ("docs_stamp rejects a malformed --by", ("docs_stamp.py", "README.md", "--by", "bob", "--summary", "s"), None, 2, "--by must be"),
        ("docs_stamp rejects an empty --summary", ("docs_stamp.py", "README.md", "--by", "human", "--summary", " "), None, 2, "--summary is empty"),
        ("docs_stamp rejects --toc with --no-toc", ("docs_stamp.py", "README.md", "--by", "human", "--summary", "s", "--toc", "--no-toc"), None, 2, "only one of"),
        ("docs_stamp outside a project is refused", ("docs_stamp.py", "x.md", "--by", "human", "--summary", "s"), root_cwd, 2, "no .docs.yaml"),
        ("docs_index --write needs --by", ("docs_index.py", "--write"), None, 2, "--write needs --by"),
        ("docs_index --all cannot be combined with --write", ("docs_index.py", "--all", "--write", "--by", "human"), None, 2, "one project at a time"),
        ("docs_index outside a project is refused", ("docs_index.py",), root_cwd, 2, "no .docs.yaml"),
        ("docs_recent rejects a malformed --since", ("docs_recent.py", "--since", "soon"), None, 2, "--since must look like"),
        ("docs_recent outside a project is refused", ("docs_recent.py",), root_cwd, 2, "no .docs.yaml"),
        ("docs_stale outside a project is refused", ("docs_stale.py",), root_cwd, 2, "no .docs.yaml"),
        ("render_tables outside a project is refused", ("render_tables.py", "--check"), root_cwd, 2, "no .docs.yaml"),
        ("new_project rejects an invalid name", ("new_project.py", "--name", "Bad_Name", "--description", "x", "--by", "human"), root_cwd, 2, "--name must be"),
        ("new_project refuses an existing folder", ("new_project.py", "--name", "proj", "--description", "x", "--by", "human"), root_cwd, 2, "already exists"),
        ("new_project requires a description", ("new_project.py", "--name", "no-description", "--by", "human"), root_cwd, 2, "--description is required"),
        ("new_project rejects a malformed --by", ("new_project.py", "--name", "bad-by", "--description", "x", "--by", "bob"), root_cwd, 2, "--by must be"),
        ("new_project rejects an unknown timezone", ("new_project.py", "--name", "bad-tz", "--description", "x", "--by", "human", "--timezone", "Mars/Olympus"), root_cwd, 2, "unknown timezone"),
    ]
    for label, args, cwd, want_rc, want_text in cases:
        rc, out = tool(*args, cwd=cwd)
        check(label, rc == want_rc and want_text in out, f"rc={rc} {out}")
    check("refused new_project calls leave no folder behind",
          not any((CTX["root"] / n).exists() for n in ("Bad_Name", "no-description", "bad-sens", "bad-by", "bad-tz")))
    rc, out = tool("docs_recent.py", "--since", "30d", "--by", "no-such-author")
    check("docs_recent --by filters to matching authors only", rc == 0 and "no changes in the last 30d" in out, out)
    rc, out = tool("docs_recent.py", "--since", "30d", "--limit", "1")
    check("docs_recent --limit caps the listed rows", rc == 0 and "(showing 1)" in out and sum("proj/" in line for line in out.splitlines()) == 1, out)
    rc, out = tool("docs_stale.py", "--fail", env={"DOCS_FAKE_NOW": "2099-01-01T10:00"})
    check("docs_stale --fail exits 1 when something is overdue", rc == 1 and "overdue" in out, out)
    rc, out = tool("docs_stale.py", "--within", "30", env={"DOCS_FAKE_NOW": "2027-12-01T10:00"})
    check("docs_stale --within still lists overdue docs", rc == 0 and out.strip(), out)


def s_failure_paths():
    """Refusals and diagnostics of mv, render_tables, sync_rules and the doctor, on a scratch project."""
    root = CTX["root"]
    rc, out = sh(["uv", "run", "--quiet", str(CTX["tools"] / "new_project.py"), "--name", "fail-proj", "--description", "Failure paths",
                  "--sensitivity", "private", "--by", "human", "--no-prompt"], cwd=root)
    check("scratch project for failure paths is created", rc == 0, out)
    fp = root / "fail-proj"
    for name in ("a", "b"):
        tool("docs_new.py", f"docs/{name}.md", "--type", "reference", "--by", "human", cwd=fp)

    def mv(*args, cwd=fp):
        return tool("docs_mv.py", *args, cwd=cwd)

    rc, out = mv("mv", "docs/a.md", "docs/c.md", "--by", "bob")
    check("docs_mv rejects a malformed --by", rc == 2 and "--by must be" in out, out)
    rc, out = mv("mv", "docs/a.md", "docs/c.md", "--by", "human", cwd=root)
    check("docs_mv outside a project is refused", rc == 2 and "no .docs.yaml" in out, out)
    rc, out = mv("mv", "docs/a.md", "../elsewhere.md", "--by", "human")
    check("docs_mv refuses a destination outside the project", rc == 1 and "outside the project" in out, out)
    rc, out = mv("mv", "docs/missing.md", "docs/c.md", "--by", "human")
    check("docs_mv refuses a missing source", rc == 1 and "error:" in out, out)
    rc, out = mv("mv", "docs/a.md", "docs/b.md", "--by", "human")
    check("docs_mv refuses to overwrite an existing doc", rc == 1 and "error:" in out, out)
    rc, out = mv("heading", "docs/a.md", "No such heading", "Anything", "--by", "human")
    check("docs_mv heading refuses a heading that does not exist", rc == 1 and "error:" in out, out)

    (fp / "data").mkdir(exist_ok=True)
    (fp / "data" / "t.csv").write_text("id,name\n1,alpha\n")
    (fp / "docs" / "t.md").write_text("# T\n\n<!-- table:start src=data/t.csv -->\n<!-- table:end -->\n")
    tool("docs_stamp.py", "docs/t.md", "--init", "--by", "human", "--summary", "t", cwd=fp)
    rc, out = tool("render_tables.py", "--check", cwd=fp)
    check("render_tables --check reports an out-of-date table", rc == 1 and "out of date" in out, out)
    rc, out = tool("render_tables.py", cwd=fp)
    check("render_tables without --by/--summary lists what it would change and refuses", rc == 2 and "would change" in out, out)
    rc, out = tool("render_tables.py", "--by", "human", "--summary", "render", cwd=fp)
    check("render_tables renders and stamps when given --by and --summary", rc == 0 and "rendered + stamped" in out, out)
    rc, out = tool("render_tables.py", cwd=fp)
    check("render_tables reports tables already current", rc == 0 and "already current" in out, out)

    rc, out = tool("sync_rules.py", "no-such-project", cwd=root)
    check("sync_rules rejects an unknown project name", rc == 2 and "unknown project" in out, out)
    (fp / "CLAUDE.md").write_text("no import here\n")
    rc, out = tool("sync_rules.py", "--check", "fail-proj", cwd=root)
    check("sync_rules --check reports drift without changing anything", rc == 1 and "CLAUDE.md import" in out and (fp / "CLAUDE.md").read_text() == "no import here\n", out)
    rc, out = tool("sync_rules.py", "fail-proj", cwd=root)
    check("sync_rules repairs the drift", rc == 0 and "@AGENTS.md" in (fp / "CLAUDE.md").read_text(), out)

    hook = fp / ".git" / "hooks" / "pre-commit"
    original = hook.read_text()
    hook.write_text(original + "# local edit\n")
    rc, out = tool("docs_doctor.py", cwd=fp)
    check("doctor warns when the hook differs from the current one", "differs from the current one" in out, out)
    hook.chmod(0o644)
    rc, out = tool("docs_doctor.py", cwd=fp)
    check("doctor fails when the hook is not executable", rc == 1 and "not executable" in out, out)
    hook.write_text(original)
    hook.chmod(0o755)
    rc, out = tool("docs_doctor.py", cwd=fp, env={"DOCS_SKIP_HOOK": "1"})
    check("doctor warns when DOCS_SKIP_HOOK=1 is set", "DOCS_SKIP_HOOK=1" in out, out)
    shutil.copytree(fp, root / "nogit-proj", ignore=shutil.ignore_patterns(".git"))
    rc, out = tool("docs_doctor.py", cwd=root / "nogit-proj")
    check("doctor fails for a project that is not a git repository", rc == 1 and "not a git repository" in out, out)
    shutil.rmtree(root / "nogit-proj", ignore_errors=True)
    shutil.rmtree(fp, ignore_errors=True)


def s_uv_cache():
    """The public config is portable; local cache overrides work from either level."""
    root = SRC_TOOLS.parent
    text = (root / "uv.toml").read_text()
    check("root uv.toml does not hard-code a cache path", not re.search(r'^cache-dir\s*=', text, re.M), text)
    want = CTX["root"] / ".cache" / "uv-portability-probe"
    env = dict(os.environ, UV_CACHE_DIR=str(want))
    for cwd in (root, root / "_tools"):
        r = subprocess.run(["uv", "cache", "dir"], cwd=cwd, env=env, capture_output=True, text=True)
        got = Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None
        check(f"UV_CACHE_DIR override works from {cwd.relative_to(root)}/", got == want.resolve(), r.stdout + r.stderr)
    want.mkdir(parents=True, exist_ok=True)
    probe = want / ".selftest-write-check"
    probe.write_text("ok")
    probe.unlink()
    check("local uv cache override is writable", True)


def s_framework_index():
    """Simulate normal adds and forced mistakes beside independent knowledge repos."""
    root = CTX["root"]
    for name in (".gitignore", "AGENTS.md", "uv.toml"):
        shutil.copy2(SRC_TOOLS.parent / name, root / name)
    (root / "README.md").write_text("# Fictional framework fixture\n")
    sh(["git", "init", "-q", "-b", "main"], cwd=root)
    private = root / "a-new-personal-topic"
    private.mkdir()
    (private / "secret.md").write_text("fictional private sentinel")
    sh(["git", "init", "-q", "-b", "main"], cwd=private)
    for name in ("a-new-personal-topic/secret.md", "proj/README.md", ".obsidian/graph.json", ".cache/anything"):
        rc, out = sh(["git", "check-ignore", "--no-index", name], cwd=root)
        check(f"framework ignores {name}", rc == 0, out)
    rc, out = sh(["git", "add", "-A"], cwd=root)
    check("framework git add -A succeeds without adding knowledge repos", rc == 0, out)
    guard = [sys.executable, str(root / "_tools/framework_guard.py")]
    rc, out = sh(guard, cwd=root)
    check("framework guard accepts the public staged index", rc == 0, out)
    loose = root / "private-loose-topic"
    loose.mkdir()
    (loose / "secret.md").write_text("fictional private sentinel")
    rc, out = sh(["git", "add", "-f", "private-loose-topic/secret.md"], cwd=root)
    check("test fixture can force-stage a loose private file", rc == 0, out)
    rc, out = sh(guard, cwd=root)
    check("framework guard rejects a forced private-topic addition", rc == 1 and "not an approved" in out, out)
    sh(["git", "update-index", "--force-remove", "private-loose-topic/secret.md"], cwd=root)
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_under_test", root / "_tools/framework_guard.py")
    guard_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_module)
    check("framework guard rejects a nested repository even in an allowed root", bool(guard_module.validate_entry("160000", "docs/nested")))
    check("framework guard rejects a symlink even in an allowed root", bool(guard_module.validate_entry("120000", "docs/link.md")))
    check("framework guard rejects project configs in framework guides", bool(guard_module.validate_entry("100644", "docs/.docs.yaml")))
    check("framework guard allows the project template config", guard_module.validate_entry("100644", "_template/.docs.yaml") is None)
    sh(["git", "config", "folderwise.pullOnly", "true"], cwd=root)
    rc, out = sh(["sh", str(root / "_tools/framework-hooks/pre-push")], cwd=root)
    check("framework pre-push hook blocks the pull-only checkout", rc == 1 and "pull-only" in out, out)


def s_ci_allowlist():
    """The .gitignore allowlist and framework_guard.py agree on the exact CI/configuration files, and deny the rest."""
    import importlib.util
    src_root = SRC_TOOLS.parent
    spec = importlib.util.spec_from_file_location("guard_ci_under_test", src_root / "_tools/framework_guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    allowed = sorted(guard.CI_FILES | {f for f in guard.FILES if f not in {".gitignore", ".gitattributes"}})
    sandbox = CTX["root"] / "ci-allowlist-sandbox"
    (sandbox / "_tools").mkdir(parents=True)
    shutil.copy2(src_root / ".gitignore", sandbox / ".gitignore")
    shutil.copy2(src_root / "_tools/framework_guard.py", sandbox / "_tools/framework_guard.py")
    sh(["git", "init", "-q", "-b", "main"], cwd=sandbox)
    guard_cmd = [sys.executable, str(sandbox / "_tools/framework_guard.py")]

    declared = {m.group(1) for m in re.finditer(r"^!/(\.github/\S*[^/\s])$", (src_root / ".gitignore").read_text(), re.M)}
    check(".gitignore re-includes exactly the CI files the guard allows", declared == set(guard.CI_FILES),
          f"only in .gitignore: {sorted(declared - guard.CI_FILES)}; only in guard: {sorted(guard.CI_FILES - declared)}")
    if (src_root / ".github").is_dir():  # release archives ship only the tools, not the development-only CI files
        check("every allowed CI/config path exists in the repository", all((src_root / f).is_file() for f in allowed),
              str([f for f in allowed if not (src_root / f).is_file()]))
    else:
        check("release archive: development-only CI files are absent by design (existence check skipped)", not (src_root / ".coveragerc").exists())

    for rel in allowed:
        (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / rel).write_text("fictional placeholder\n")
    sh(["git", "add", "-A"], cwd=sandbox)
    rc, tracked = sh(["git", "ls-files"], cwd=sandbox)
    check("git add -A stages every exact CI/config file", all(f in tracked.split() for f in allowed),
          str([f for f in allowed if f not in tracked.split()]))
    rc, out = sh(guard_cmd, cwd=sandbox)
    check("framework guard accepts the exact CI/config files", rc == 0, out)

    rogue = [".github/workflows/rogue.yml", ".github/scripts/rogue.py", ".github/secrets.env", ".github/ISSUE_TEMPLATE/bug.md",
             ".github/workflows/__pycache__/ci.cpython-312.pyc", ".codecov-token", ".coverage", "coverage.xml", ".ci-coverage/coverage.xml",
             "htmlcov/index.html", ".ruff_cache/CACHEDIR.TAG", "private-topic/notes.md", "codecov.yaml",
             "_tools/.coverage", "_tools/.coverage.host.1234.abcd", "_tools/coverage.xml", "docs/htmlcov/index.html", "_tools/.ruff_cache/x"]
    for rel in rogue:
        (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / rel).write_text("fictional private sentinel\n")
    sh(["git", "add", "-A"], cwd=sandbox)
    rc, tracked = sh(["git", "ls-files"], cwd=sandbox)
    leaked = [f for f in rogue if f in tracked.split()]
    check("git add -A does not stage rogue .github files, tokens, coverage data or caches", not leaked, str(leaked))
    for rel in rogue:
        sh(["git", "add", "-f", rel], cwd=sandbox)
        rc, out = sh(guard_cmd, cwd=sandbox)
        check(f"framework guard rejects forced {rel}", rc == 1 and repr(rel) in out, out)
        sh(["git", "rm", "-q", "--cached", rel], cwd=sandbox)
    check("framework guard rejects a symlink in place of an allowed CI file", bool(guard.validate_entry("120000", ".github/workflows/ci.yml")))
    check("framework guard allows executable CI helper scripts", guard.validate_entry("100755", ".github/scripts/ci_coverage.py") is None)
    check("framework guard rejects a .github file that is not on the exact list", bool(guard.validate_entry("100644", ".github/workflows/other.yml")))
    shutil.rmtree(sandbox, ignore_errors=True)


def s_framework_checkout():
    """Exercise the real setup/update CLI with local upstream and private repositories."""
    base = CTX["root"] / "checkout-fixtures"
    base.mkdir()
    upstream = base / "upstream"
    upstream.mkdir()
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def run(root, *args):
        return sh(list(args), cwd=root, env=env)

    def g(root, *args):
        rc, out = run(root, "git", *args)
        if rc:
            raise RuntimeError(out)
        return out.strip()

    def put(root, rel, text="fictional fixture\n"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    g(upstream, "init", "-q", "-b", "main")
    for name in (".gitignore", ".gitattributes", "AGENTS.md", "uv.toml"):
        shutil.copy2(SRC_TOOLS.parent / name, upstream / name)
    put(upstream, "_tools/framework_checkout.py", (SRC_TOOLS / "framework_checkout.py").read_text())
    for rel in ("README.md", "LICENSE", "CONTRIBUTING.md", "docs/guide.md", "docs/assets/image.png", ".github/workflows/ci.yml", "ruff.toml", "_template/starter.md"):
        put(upstream, rel)
    g(upstream, "add", "-f", ".")
    g(upstream, "commit", "-qm", "fictional upstream")
    private = base / "private"
    g(base, "clone", "-q", str(upstream), str(private))
    topic = private / "my-topic"
    topic.mkdir()
    g(topic, "init", "-q", "-b", "main")
    put(topic, "notes.md", "private sentinel\n")
    g(topic, "add", ".")
    g(topic, "commit", "-qm", "private sentinel")
    topic_head = g(topic, "rev-parse", "HEAD")
    cli = str(private / "_tools/framework_checkout.py")

    def invoke(*args):
        return run(private, sys.executable, cli, *args)

    config = g(private, "config", "--local", "--list")
    rc, out = invoke("--minimal", "--dry-run")
    check("minimal preview changes neither files nor Git config", rc == 0 and (private / "docs/guide.md").is_file()
          and config == g(private, "config", "--local", "--list"), out)
    put(private, "AGENTS.md", "edited rules\n")
    for args in (("--minimal",), ("--update",), ("--full",)):
        rc, out = invoke(*args)
        check(f"checkout {args[0]} refuses tracked edits", rc == 1 and "local changes" in out, out)
    g(private, "add", "AGENTS.md")
    rc, out = invoke("--minimal")
    check("minimal refuses staged edits", rc == 1 and "local changes" in out, out)
    g(private, "restore", "--staged", "--worktree", "AGENTS.md")
    put(private, "docs/local.md", "keep this local file\n")
    rc, out = invoke("--minimal")
    check("minimal refuses untracked files in excluded framework folders", rc == 1 and "nothing was deleted" in out
          and (private / "docs/local.md").read_text() == "keep this local file\n", out)
    (private / "docs/local.md").unlink()
    put(private, "docs/.env", "fictional ignored sentinel\n")
    rc, out = invoke("--minimal")
    check("minimal also preserves ignored files in excluded folders", rc == 1 and "nothing was deleted" in out, out)
    (private / "docs/.env").unlink()
    (private / ".git/MERGE_HEAD").write_text(g(private, "rev-parse", "HEAD") + "\n")
    rc, out = invoke("--minimal")
    check("minimal refuses an unfinished merge", rc == 1 and "current Git operation" in out, out)
    (private / ".git/MERGE_HEAD").unlink()
    rc, out = invoke("--minimal")
    check("minimal setup succeeds", rc == 0, out)
    check("minimal removes public directories and development root files", all(not (private / p).exists()
          for p in ("docs", ".github", "CONTRIBUTING.md", "ruff.toml")))
    check("minimal keeps runtime folders and required root files", all((private / p).exists()
          for p in ("_tools", "_template", ".gitignore", ".gitattributes", "AGENTS.md", "README.md", "LICENSE", "uv.toml")))
    check("minimal checkout has a clean tracked status", g(private, "status", "--porcelain", "--untracked-files=no") == "")
    check("minimal configures pull-only hooks and push safeguards", g(private, "config", "folderwise.pullOnly") == "true"
          and g(private, "config", "remote.origin.pushurl") == "no-push://folderwise-pull-only"
          and g(private, "config", "core.hooksPath") == "_tools/framework-hooks"
          and g(private, "config", "pull.ff") == "only")
    rc, out = invoke("--minimal")
    check("minimal setup is repeatable", rc == 0, out)

    for rel in ("docs/new-guide.md", ".github/new-policy.md", "website/index.html", "_future/nested/file.md"):
        put(upstream, rel)
    g(upstream, "add", "-f", ".")
    g(upstream, "commit", "-qm", "new framework paths")
    rc, out = run(private, "git", "pull", "--ff-only")
    check("direct git pull keeps excluded directories absent and includes future underscore folders", rc == 0
          and all(not (private / p).exists() for p in ("docs", ".github", "website"))
          and (private / "_future/nested/file.md").is_file(), out)
    put(upstream, "_future/update.md")
    g(upstream, "add", "-f", ".")
    g(upstream, "commit", "-qm", "next update")
    rc, out = invoke("--update", "--dry-run")
    check("update preview does not fetch or advance HEAD", rc == 0
          and not (private / "_future/update.md").exists(), out)
    rc, out = invoke("--update")
    check("update CLI pulls with the minimal layout", rc == 0 and (private / "_future/update.md").is_file()
          and all(not (private / p).exists() for p in ("docs", ".github", "website")), out)
    # Optional root-file omissions are local sparse preferences, never staged deletions.
    (private / "README.md").unlink()
    before = g(private, "config", "--local", "--list")
    rc, out = invoke("--update", "--dry-run")
    check("deletion preview reports the omission without changing config or status", rc == 0
          and "README.md" in out and before == g(private, "config", "--local", "--list")
          and g(private, "status", "--porcelain", "--untracked-files=no") == "D README.md", out)
    rc, out = invoke("--update")
    check("updater remembers a manually deleted README and leaves a clean index", rc == 0
          and not (private / "README.md").exists() and (private / "LICENSE").is_file()
          and g(private, "config", "folderwise.omittedRootFiles") == "README.md"
          and g(private, "status", "--porcelain", "--untracked-files=no") == "", out)
    for name in ("README.md", "LICENSE"):
        put(upstream, name, "updated optional file\n")
    g(upstream, "add", "-f", ".")
    g(upstream, "commit", "-qm", "update optional root files")
    rc, out = run(private, "git", "pull", "--ff-only")
    check("direct pulls keep omitted README absent even when upstream changes it", rc == 0
          and not (private / "README.md").exists() and (private / "LICENSE").read_text() == "updated optional file\n", out)
    (private / "LICENSE").unlink()
    rc, out = invoke("--minimal")
    check("minimal setup remembers deleted LICENSE alongside previous README choice", rc == 0
          and not (private / "LICENSE").exists() and not (private / "README.md").exists()
          and g(private, "config", "folderwise.omittedRootFiles") == "LICENSE README.md", out)
    rc, out = invoke("--minimal")
    check("repeated setup preserves optional-file omissions", rc == 0
          and not (private / "LICENSE").exists() and not (private / "README.md").exists(), out)
    rc, out = invoke("--minimal", "--include", "README.md", "LICENSE")
    check("include restores optional files at the current upstream version", rc == 0
          and all((private / name).read_text() == "updated optional file\n" for name in ("README.md", "LICENSE"))
          and g(private, "config", "folderwise.omittedRootFiles") == "", out)
    (private / "README.md").unlink()
    rc, out = invoke("--minimal", "--include", "README.md")
    check("include can also undo a fresh manual deletion", rc == 0
          and (private / "README.md").read_text() == "updated optional file\n"
          and g(private, "status", "--porcelain", "--untracked-files=no") == "", out)
    (private / "LICENSE").unlink()
    g(private, "add", "-u")
    rc, out = invoke("--minimal")
    check("optional-file staged deletions remain protected", rc == 1 and "local changes" in out, out)
    g(private, "restore", "--staged", "--worktree", "LICENSE")
    put(private, "README.md", "edited README\n")
    rc, out = invoke("--minimal", "--omit", "README.md")
    check("omit refuses optional-file edits instead of discarding them", rc == 1 and "local changes" in out, out)
    g(private, "restore", "README.md")
    rc, out = invoke("--minimal", "--omit", "README.md", "LICENSE")
    check("explicit omit supports both optional root files", rc == 0
          and all(not (private / name).exists() for name in ("README.md", "LICENSE")), out)
    for name in ("README.md", "LICENSE"):
        put(upstream, name, "newer optional file\n")
    g(upstream, "add", "-f", ".")
    g(upstream, "commit", "-qm", "next optional root files")
    rc, out = invoke("--update")
    check("updater keeps both omitted root files absent through upstream edits", rc == 0
          and all(not (private / name).exists() for name in ("README.md", "LICENSE")), out)
    for args in (("--minimal", "--omit", "AGENTS.md"),
                 ("--full", "--omit", "README.md"),
                 ("--minimal", "--omit", "README.md", "--include", "README.md")):
        rc, out = invoke(*args)
        check(f"optional-file CLI rejects invalid request {args}", rc == 2, out)
    g(private, "config", "folderwise.omittedRootFiles", "AGENTS.md")
    rc, out = invoke("--minimal")
    check("invalid stored omissions cannot hide required framework files", rc == 1 and "Invalid" in out, out)
    g(private, "config", "folderwise.omittedRootFiles", "LICENSE README.md")
    check("setup and both update methods preserve independent repository contents and history",
          (topic / "notes.md").read_text() == "private sentinel\n" and g(topic, "rev-parse", "HEAD") == topic_head
          and g(topic, "status", "--porcelain") == "")
    rc, out = invoke("--full", "--dry-run")
    check("full preview leaves the minimal layout in place", rc == 0 and not (private / "docs").exists(), out)
    rc, out = invoke("--full")
    check("full checkout can be restored without enabling pushes", rc == 0 and (private / "docs/guide.md").is_file()
          and g(private, "config", "folderwise.pullOnly") == "true"
          and g(private, "config", "folderwise.omittedRootFiles") == ""
          and all((private / name).is_file() for name in ("README.md", "LICENSE")), out)

    # Failure paths: archive/parent repository, missing origin, detached updater, invalid CLI.
    archive = base / "archive"
    put(archive, "_tools/framework_checkout.py", (SRC_TOOLS / "framework_checkout.py").read_text())
    rc, out = run(archive, sys.executable, str(archive / "_tools/framework_checkout.py"), "--minimal")
    check("checkout CLI refuses an archive or parent repository", rc == 1, out)
    g(private, "remote", "remove", "origin")
    rc, out = invoke("--minimal")
    check("minimal requires an origin remote", rc == 1, out)
    g(private, "remote", "add", "origin", str(upstream))
    g(private, "checkout", "--detach", "-q")
    rc, out = invoke("--update")
    check("update refuses detached HEAD", rc == 1, out)
    rc, out = invoke()
    check("checkout CLI requires an explicit mode", rc == 2, out)
    shutil.rmtree(base)


def s_ibridge():
    """Drive a fictional two-project vault through the real CLI, adapters and hooks."""
    root = CTX['root'] / 'bridge-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf = home / 'config.json'
    sandbox_env = {}

    def invoke(*args, env=None):
        return tool('icloud_bridge.py', '--config', conf, *args, env={**sandbox_env, **(env or {})})

    def local(name, *args, cwd=None):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=cwd or source)

    for name, extra in [('alpha', []), ('beta', []), ('disabled', ['--icloud-disabled'])]:
        rc, out = local('new_project.py', '--name', name, '--description', 'Fictional bridge test', '--no-prompt', *extra)
        check('bridge creates ' + name, rc == 0, out)
    alpha = source / 'alpha'
    rc,out=local('docs_doctor.py',cwd=alpha)
    check('project doctor recognizes folderwise-ibridgesync as a framework setting',rc==0 and 'unknown key' not in out,out)
    rc, out = local('docs_new.py', 'docs/checklist.md', '--type', 'plan', '--title', 'Checklist', '--by', 'human', cwd=alpha)
    note = alpha / 'docs/checklist.md'
    note.write_text(note.read_text().replace('## Change Log', '- [ ] First task\n  - [ ] Nested task\n- [x] Completed task\n- [ ] Duplicate\n- [ ] Duplicate\n\n```md\n- [ ] Example only\n```\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add tasks', cwd=alpha)
    sh(['git', 'add', '-A'], cwd=alpha)
    sh(['git', 'commit', '-qm', 'Add test tasks'], cwd=alpha)
    rc, out = invoke('setup', '--source', source, '--vault', vault, '--notifications', 'off', '--no-schedule')
    check('bridge setup defaults full/unlimited/five minutes', rc == 0 and json.loads(conf.read_text())['mode'] == 'full'
          and json.loads(conf.read_text())['max_image_bytes'] is None and json.loads(conf.read_text())['interval_minutes'] == 5, out)
    rc, out = invoke('setup', '--source', source, '--vault', vault)
    check('bridge refuses accidental re-setup', rc == 1 and 'exists' in out, out)
    rc, out = invoke('plan')
    check('bridge plan lists both opted-in projects and preserves the initialized vault', rc == 0 and 'alpha/docs/checklist.md' in out
          and 'beta/README.md' in out and 'disabled/' not in out and vault.exists(), out)
    rc, out = invoke('sync')
    view = vault / '_Folderwise Tasks/alpha.md'
    check('bridge exports dashboard and completed tasks', rc == 0 and '## Completed tasks' in (vault / 'Tasks.md').read_text()
          and '- [x] Completed task' in view.read_text() and 'Example only' not in view.read_text(), out)
    check('bridge excludes Git and instructions', not (vault / 'alpha/.git').exists() and not (vault / 'alpha/AGENTS.md').exists())
    report_path=vault/'_folderwise-sync-status.md'
    legacy=vault/'Bridge Status.md'
    legacy_data=report_path.read_bytes().replace(b'# Folderwise sync status',b'# Bridge Status',1)
    report_path.unlink();legacy.write_bytes(legacy_data)
    legacy_manifest={'hash':hashlib.sha256(legacy_data).hexdigest()}
    (home/'report.json').write_text(json.dumps(legacy_manifest))
    rc,out=invoke('plan')
    check('status migration dry run preserves the legacy report and ownership',rc==0 and legacy.exists() and not report_path.exists()
          and json.loads((home/'report.json').read_text())==legacy_manifest,out)
    report_path.write_text('User-owned destination\n')
    rc,out=invoke('sync')
    check('status migration refuses an unowned destination without removing the old report',rc==1 and legacy.read_bytes()==legacy_data
          and report_path.read_text()=='User-owned destination\n',out)
    report_path.write_bytes(legacy_data)
    rc,out=invoke('sync')
    check('status migration recognizes an unchanged copy at the new name',rc==0 and report_path.exists() and not legacy.exists()
          and json.loads((home/'report.json').read_text())['path']=='_folderwise-sync-status.md',out)
    stamp=report_path.stat().st_mtime_ns
    rc,out=invoke('sync')
    check('migrated status report is idempotent',rc==0 and report_path.stat().st_mtime_ns==stamp,out)
    report_path.unlink();legacy.write_bytes(legacy_data)
    (home/'report.json').write_text(json.dumps(legacy_manifest))
    rc,out=invoke('sync')
    check('status report migrates when no destination exists',rc==0 and report_path.exists() and not legacy.exists(),out)
    report_path.write_bytes(legacy_data)
    (home/'report.json').write_text(json.dumps(legacy_manifest))
    rc,out=invoke('sync')
    check('status migration recognizes an unchanged manually renamed report',rc==0
          and json.loads((home/'report.json').read_text())['path']=='_folderwise-sync-status.md',out)
    report_path.unlink();legacy.write_bytes(legacy_data+b'User notes\n')
    (home/'report.json').write_text(json.dumps(legacy_manifest))
    rc,out=invoke('sync')
    check('edited legacy report is preserved and explained in the new report',rc==1 and legacy.read_bytes()==legacy_data+b'User notes\n'
          and 'legacy report has unowned edits' in report_path.read_text(),out)
    legacy.unlink();invoke('sync')
    legacy.write_bytes(report_path.read_bytes())
    rc,out=invoke('sync')
    check('unowned legacy report is preserved even when its bytes match the current report',rc==1 and legacy.exists()
          and 'legacy report has unowned edits' in report_path.read_text(),out)
    legacy.unlink();invoke('sync')
    view.write_text(view.read_text().replace('- [ ] First task', '- [x] First task'))
    rc, out = invoke('sync')
    _, log = sh(['git', 'log', '-1', '--format=%B'], cwd=alpha)
    check('phone dashboard toggle stamps and commits authoritative Markdown', rc == 0 and '- [x] First task' in note.read_text()
          and 'updated_by: human' in note.read_text() and 'Bridge: folderwise-ibridge' in log, out)
    head = sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1]
    rc, out = invoke('sync')
    check('unchanged sync is idempotent', rc == 0 and sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1] == head, out)
    view.write_text(view.read_text().replace('- [x] First task', '- [ ] First task'))
    rc, out = invoke('sync')
    check('completed dashboard task can reopen', rc == 0 and '- [ ] First task' in note.read_text(), out)
    mirror = vault / 'alpha/docs/checklist.md'
    mirror.write_text(mirror.read_text().replace('- [ ] Nested task', '- [x] Nested task'))
    rc, out = invoke('sync')
    check('checkbox edits inside mirrored source notes also import', rc == 0 and '- [x] Nested task' in note.read_text(), out)
    # Dirty source/index and failed hooks must leave both source and phone pending.
    view.write_text(view.read_text().replace('- [ ] First task', '- [x] First task'))
    (alpha / 'scratch.txt').write_text('uncommitted\n')
    rc, out = invoke('sync')
    check('dirty project blocks import and preserves pending phone toggle', rc == 1 and 'uncommitted' in out
          and '- [ ] First task' in note.read_text() and '- [x] First task' in view.read_text(), out)
    (alpha / 'scratch.txt').unlink()
    hook = alpha / '.git/hooks/pre-commit'
    original_hook = hook.read_text()
    hook.write_text('#!/bin/sh\necho intentional hook rejection >&2\nexit 1\n')
    rc, out = invoke('sync')
    check('hook rejection cannot partially change Mac records', rc == 1 and 'intentional hook rejection' in out
          and '- [ ] First task' in note.read_text(), out)
    hook.write_text(original_hook)
    rc, out = invoke('sync')
    check('retry after hook repair imports pending change', rc == 0 and '- [x] First task' in note.read_text(), out)
    view.write_text(view.read_text().replace('First task', 'Phone prose edit'))
    rc, out = invoke('sync')
    saved_edits = [p.read_text() for p in (home / 'rejected').rglob('*') if p.is_file()]
    check('unsupported phone edits to a generated view are saved outside iCloud and the view is restored', rc == 0 and 'NOTICE' in out
          and 'Phone prose edit' not in view.read_text() and '- [x] First task' in view.read_text()
          and any('Phone prose edit' in text for text in saved_edits)
          and not any(p.stat().st_mode & 0o077 for p in (home / 'rejected').rglob('*')), out)
    status_text = (vault / '_folderwise-sync-status.md').read_text()
    check('rejected phone edit is named in the status report', '## Phone edits not applied' in status_text and '_Folderwise Tasks/alpha.md' in status_text
          and 'line 5' in status_text and 'only checkbox on/off changes are supported' in status_text, status_text)
    rc, out = invoke('sync')
    check('a restored view is not reported again', rc == 0 and 'NOTICE' not in out, out)
    # Adapter lives in project, uses a CSV, and hides completed rows in normal Markdown.
    (alpha / 'data/tasks.csv').write_text('id,title,done\nitem-1,CSV action,false\n')
    script = alpha / 'scripts/adapter.py'
    script.parent.mkdir(exist_ok=True)
    script.write_text('''import csv,json,sys
from pathlib import Path
p=Path('data/tasks.csv')
rows=list(csv.DictReader(p.open()))
op=sys.argv[1]
if op=='list':
 print(json.dumps([dict(id=r['id'],title=r['title'],checked=r['done']=='true',path='docs/checklist.md') for r in rows]))
elif op=='apply':
 changes={c['id']:c['checked'] for c in json.load(sys.stdin)}
 for r in rows:
  if r['id'] in changes: r['done']='true' if changes[r['id']] else 'false'
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['id','title','done']);w.writeheader();w.writerows(rows)
 note=Path('docs/checklist.md');text=note.read_text();start=text.index('<!-- tasks:start -->');end=text.index('<!-- tasks:end -->')
 block='<!-- tasks:start -->\\n'+''.join('- [ ] '+r['title']+'\\n' for r in rows if r['done']=='false')
 note.write_text(text[:start]+block+text[end:])
elif op=='validate':
 assert all(r['done'] in ('true','false') for r in rows)
''')
    note.write_text(note.read_text().replace('## Change Log', '<!-- tasks:start -->\n- [ ] CSV action\n<!-- tasks:end -->\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add generated tasks', cwd=alpha)
    sh(['git', 'add', '-A'], cwd=alpha)
    rc, out = sh(['git', 'commit', '-qm', 'Add CSV adapter'], cwd=alpha)
    check('fictional CSV source committed with real hook', rc == 0, out)
    cfg = json.loads(conf.read_text());cfg['adapters']={'alpha':[sys.executable,'scripts/adapter.py']};conf.write_text(json.dumps(cfg))
    invoke('sync')
    check('generated checkbox appears once in dashboard projection', view.read_text().count('CSV action') == 1)
    view.write_text(view.read_text().replace('- [ ] CSV action', '- [x] CSV action'))
    rc, out = invoke('sync')
    check('CSV task toggle updates authoritative row and regenerates Markdown', rc == 0 and 'item-1,CSV action,true' in (alpha / 'data/tasks.csv').read_text()
          and '- [ ] CSV action' not in note.read_text() and '- [x] CSV action' in view.read_text(), out)
    view.write_text(view.read_text().replace('- [x] CSV action', '- [ ] CSV action'))
    rc, out = invoke('sync')
    check('completed CSV row can reopen after disappearing from source view', rc == 0 and 'item-1,CSV action,false' in (alpha / 'data/tasks.csv').read_text()
          and '- [ ] CSV action' in note.read_text(), out)
    # Full/lean mode, image caps and reporting.
    images = alpha / 'docs/assets';images.mkdir()
    for name, size in [('a.png',3),('b.png',8),('c.png',2),('unused.png',1)]:
        (images / name).write_bytes(b'x'*size)
    (alpha / 'large.pdf').write_bytes(b'pdf'*100)
    note.write_text(note.read_text().replace('## Change Log', '![A](assets/a.png)\n![B](assets/b.png)\n![C](assets/c.png)\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add images', cwd=alpha)
    sh(['git', 'add', '-A'], cwd=alpha);sh(['git','commit','-qm','Add attachments'],cwd=alpha)
    rc,out=invoke('sync')
    check('full mode exports other tracked content',rc==0 and (vault/'alpha/large.pdf').exists(),out)
    invoke('configure','--mode','lean','--max-image-bytes','5','--max-images-total-bytes','4')
    rc,out=invoke('sync')
    status=(vault/'_folderwise-sync-status.md').read_text()
    check('lean mode honors both limits and cleans unchanged owned copies',rc==0 and (vault/'alpha/docs/assets/a.png').exists()
          and not (vault/'alpha/large.pdf').exists() and not (vault/'alpha/docs/assets/unused.png').exists()
          and 'exceeds per-image limit' in status and 'exceeds aggregate image limit' in status,out)
    stamp=(vault/'_folderwise-sync-status.md').stat().st_mtime_ns
    invoke('sync')
    check('unchanged report does not churn every scheduled run',(vault/'_folderwise-sync-status.md').stat().st_mtime_ns==stamp)
    invoke('configure','--unlimited-images')
    rc,out=invoke('sync')
    check('unlimited image setting restores all referenced images',rc==0 and (vault/'alpha/docs/assets/b.png').exists()
          and (vault/'alpha/docs/assets/c.png').exists(),out)
    (vault/'alpha/docs/assets/b.png').write_bytes(b'phone image edit')
    invoke('configure','--max-image-bytes','1')
    rc,out=invoke('sync')
    check('shrinking cap preserves changed mobile image',rc==1 and (vault/'alpha/docs/assets/b.png').read_bytes()==b'phone image edit',out)
    (vault/'alpha/docs/assets/b.png').write_bytes((images/'b.png').read_bytes())
    invoke('configure','--unlimited-images');invoke('sync')
    rc,out=invoke('disable','beta');invoke('sync')
    check('disable helper excludes a project and removes its unchanged files',rc==0 and not (vault/'beta/README.md').exists(),out)
    rc,out=invoke('enable','beta');invoke('sync')
    check('enable helper restores project inclusion',rc==0 and (vault/'beta/README.md').exists(),out)
    for command in ['status','doctor','logs']:
        rc,out=invoke(command);check('bridge '+command+' diagnostics',rc==0,out)
    rc,out=invoke('configure','--interval-minutes','0')
    check('bridge rejects zero interval without corrupting config',rc==1 and json.loads(conf.read_text())['interval_minutes']==5,out)
    # Directory escape via an image reference fails before an external file can upload.
    original=note.read_text();note.write_text(original.replace('## Change Log','![Escape](../../../outside.png)\n\n## Change Log'))
    rc,out=invoke('plan')
    check('bridge rejects image path escapes',rc==1 and 'unsafe path' in out,out)
    note.write_text(original)
    (vault/'alpha/docs/assets/a.png').unlink();(vault/'alpha/docs/assets/a.png').symlink_to(root/'outside')
    rc,out=invoke('sync')
    check('bridge refuses symlink destinations',rc==1 and 'symlink' in out,out)
    (vault/'alpha/docs/assets/a.png').unlink();invoke('sync')
    # Prepare and execute the real named entry point without any OS registration.
    import plistlib
    rc,out=invoke('schedule-prepare')
    preview=plistlib.loads((home/'launchagent-preview.plist').read_bytes())
    launcher=Path(preview['ProgramArguments'][0])
    check('schedule preparation creates the Folderwise-named executable',rc==0 and launcher.name=='folderwise-ibridgesync'
          and os.access(launcher,os.X_OK) and str(conf) in preview['ProgramArguments'],out)
    before=json.loads((home/'last-run.json').read_text())['last_run_epoch']
    rc,out=sh(preview['ProgramArguments'],cwd=source)
    check('prepared launch command runs a real foreground sync',rc==0 and json.loads((home/'last-run.json').read_text())['last_run_epoch']>before,out)
    literal='a spaced value; $(this-must-remain-data)'
    rc,out=sh([str(launcher),sys.executable,'-c','import sys; print(sys.argv[1])',literal],cwd=source)
    check('named launcher preserves literal arguments without shell interpretation',rc==0 and out.strip()==literal,out)
    owned=launcher.read_bytes();launcher.write_text('#!/bin/sh\n# user customization\n')
    rc,out=invoke('schedule-prepare')
    check('schedule preparation preserves an altered entry point',rc==1 and 'custom content' in out
          and launcher.read_text()=='#!/bin/sh\n# user customization\n',out)
    launcher.write_bytes(owned)
    no_runtime=root/'no-runtime';no_runtime.mkdir()
    rc,out=sh([sys.executable,str(CTX['tools']/'icloud_bridge.py'),'--config',str(conf),'schedule-prepare'],cwd=source,env={'PATH':str(no_runtime)})
    check('schedule preparation diagnoses a missing runtime',rc==1 and 'uv not found' in out,out)

    # Fake OS executables exercise notification/scheduling CLI without touching launchd.
    fake=root/'fakebin';fake.mkdir()
    for executable in ['open','codesign','launchctl']:
        f=fake/executable
        f.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(root/'os-calls')+'"\nexit 0\n');f.chmod(0o755)
    opener=fake/'open'
    opener.write_text(opener.read_text().replace('exit 0', 'cat "'+str(home/'notification-message.txt')+'" > "'+str(root/'notification-body')+'"\ncat "'+str(home/'notification-message.txt')+'" >> "'+str(root/'os-calls')+'"\nexit 0'))
    compiler=fake/'osacompile'
    compiler.write_text('#!'+sys.executable+'\nimport pathlib,plistlib,sys\np=pathlib.Path(sys.argv[2])/"Contents"\n(p/"Resources").mkdir(parents=True)\n(p/"Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"applet","CFBundleIconName":"applet"}))\n(p/"Resources/Assets.car").write_bytes(b"compiler icon catalog")\n(p/"Resources/main.scpt").write_bytes(pathlib.Path(sys.argv[3]).read_bytes())\n')
    compiler.chmod(0o755)
    env={'PATH':str(fake)+os.pathsep+os.environ['PATH']}
    sandbox_env = env
    rc,out=invoke('notify-test',env=env)
    app=home/'Folderwise iBridge.app'
    metadata=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    icon=app/'Contents/Resources/Folderwise.icns'
    check('notification app bundles the Folderwise identity and icon',rc==0
          and metadata['CFBundleIdentifier']=='org.folderwise.ibridge.notifications'
          and metadata['CFBundleIconFile']=='Folderwise.icns' and metadata['LSUIElement'] and 'CFBundleIconName' not in metadata
          and icon.read_bytes()==(CTX['tools']/'ibridge_assets/folderwise.icns').read_bytes()
          and (app/'Contents/Resources/applet.icns').read_bytes()==icon.read_bytes()
          and not (app/'Contents/Resources/Assets.car').exists(),out)
    check('notification app launches and clears the message handoff', '-W -n -g '+str(app) in (root/'os-calls').read_text() and not (home/'notification-message.txt').exists(),out)
    check('notification text is handed off as UTF-8 data', (root/'notification-body').read_text()=='Folderwise iBridge notifications work.',out)
    check('notification test distinguishes a request from visible delivery',rc==0 and 'Notification requested; macOS controls' in out
          and 'when mirroring or sharing the display' in out and 'can expose other apps' in out,out)
    invoke('configure','--interval-minutes','9')
    rc,out=invoke('notify-test','--setup-message',env=env)
    check('one-command setup notification replay uses the configured interval',rc==0
          and (root/'notification-body').read_text()=='folderwise-ibridge is now enabled. Sync job is running and scheduled every 9 minutes.',out)
    invoke('configure','--interval-minutes','5')
    rc,out=invoke('status','--setup-message',env=env)
    check('setup notification replay flag rejects unrelated commands',rc==2 and '--setup-message requires notify-test' in out,out)
    compiled=icon.stat().st_mtime_ns
    rc,out=invoke('notify-test',env=env)
    check('unchanged notification app is reused',rc==0 and icon.stat().st_mtime_ns==compiled,out)
    manifest=home/'notifier.json'
    saved=json.loads(manifest.read_text());saved['version']='previous release';manifest.write_text(json.dumps(saved))
    signer=fake/'codesign';signer_body=signer.read_text();signer.write_text('#!/bin/sh\nexit 1\n')
    rc,out=invoke('notify-test',env=env)
    check('failed notification app update preserves the installed bundle',rc==1 and icon.stat().st_mtime_ns==compiled,out)
    signer.write_text(signer_body)
    rc,out=invoke('notify-test',env=env)
    check('notification app updates when bundled inputs change',rc==0 and json.loads(manifest.read_text())['version']!='previous release',out)
    original=icon.read_bytes();icon.write_bytes(b'user customization')
    rc,out=invoke('notify-test',env=env)
    check('customized notification app is preserved and delivery fails safely',rc==1 and icon.read_bytes()==b'user customization',out)
    rc,out=invoke('uninstall',env=env)
    check('uninstall preserves customized notification app',rc==0 and app.exists(),out)
    icon.write_bytes(original)
    # Restore installed state after the preservation check.
    invoke('setup','--source',str(source),'--vault',str(vault),'--no-schedule',env=env)
    if sys.platform=='darwin':
        cfg=json.loads(conf.read_text());cfg['launchagents_dir']=str(root/'LaunchAgents');cfg['notifications']='errors';conf.write_text(json.dumps(cfg))
        rc,out=invoke('schedule-enable',env=env)
        plist=plistlib.loads((root/'LaunchAgents/org.folderwise.ibridge.plist').read_bytes())
        calls=(root/'os-calls').read_text()
        check('schedule registers isolated LaunchAgent and announces configured interval',rc==0 and Path(plist['ProgramArguments'][0]).name=='folderwise-ibridgesync' and plist['StartInterval']==300
              and 'bootstrap' in calls and 'scheduled every 5 minutes' in calls,out)
        rc,out=invoke('schedule-disable',env=env)
        check('schedule disable removes only the owned job definition',rc==0 and not (root/'LaunchAgents/org.folderwise.ibridge.plist').exists(),out)
    else:
        rc,out=invoke('schedule-enable',env=env)
        check('non-Mac scheduling fails with a clear diagnostic',rc==1 and 'requires macOS' in out,out)

    # A file obstructing a new asset directory leaves a recoverable partial export.
    new_assets=alpha/'docs/new';new_assets.mkdir()
    (new_assets/'snapshot.png').write_bytes(b'new image')
    note.write_text(note.read_text().replace('## Change Log','![New](new/snapshot.png)\n\n## Change Log'))
    local('docs_stamp.py','docs/checklist.md','--by','human','--summary','Add recovery image',cwd=alpha)
    sh(['git','add','-A'],cwd=alpha);sh(['git','commit','-qm','Add recovery asset'],cwd=alpha)
    obstruction=vault/'alpha/docs/new';obstruction.write_text('obstructed directory')
    rc,out=invoke('sync')
    check('failed export retains a replay journal',rc==1 and (home/'export.json').exists(),out)
    (new_assets/'snapshot.png').write_bytes(b'changed source during recovery')
    rc,out=invoke('sync')
    check('recovery refuses changed source payloads',rc==1 and 'source changed during interrupted export' in out,out)
    (new_assets/'snapshot.png').write_bytes(b'new image')
    mirror.write_text(mirror.read_text().replace('First task','Phone edit during recovery'))
    rc,out=invoke('sync')
    check('recovery preserves phone edits made after a partial export',rc==1 and 'Phone edit during recovery' in mirror.read_text(),out)
    mirror.write_text(note.read_text());obstruction.unlink()
    rc,out=invoke('sync')
    check('retry finishes partial export and advances baseline once',rc==0 and not (home/'export.json').exists()
          and (vault/'alpha/docs/new/snapshot.png').read_bytes()==b'new image',out)
    # Identical task text stays separate, but a concurrent source edit makes it ambiguous.
    view.write_text(view.read_text().replace('- [ ] Duplicate','- [x] Duplicate',1))
    note.write_text(note.read_text().replace('## Change Log','Concurrent prose.\n\n## Change Log'))
    local('docs_stamp.py','docs/checklist.md','--by','human','--summary','Concurrent prose',cwd=alpha)
    sh(['git','add','-A'],cwd=alpha);sh(['git','commit','-qm','Concurrent prose'],cwd=alpha)
    rc,out=invoke('sync')
    check('duplicate task cannot be misidentified after a concurrent Mac edit',rc==0 and 'duplicate task moved' in out and '- [ ] Duplicate' in view.read_text(),out)
    view.write_text(view.read_text().replace('- [x] Duplicate','- [ ] Duplicate',1));invoke('sync')
    view.write_text(view.read_text().replace('- [x] First task','- [ ] First task'))
    invoke('disable','alpha')
    rc,out=invoke('sync')
    check('disabling never discards a pending phone toggle',rc==1 and 'pending phone edits' in out and view.exists(),out)
    invoke('enable','alpha')
    sh(['git','add','.docs.yaml'],cwd=alpha);sh(['git','commit','-qm','Restore bridge setting'],cwd=alpha)
    invoke('sync')
    # Adapter contract failures and generated-source warnings are explicit.
    cfg=json.loads(conf.read_text());original_cfg=dict(cfg)
    cfg['adapters']={'alpha':[sys.executable,'-c','print("{}")']};conf.write_text(json.dumps(cfg))
    rc,out=invoke('sync')
    check('malformed adapter response fails visibly without replacing the vault',rc==1 and 'JSON array' in out,out)
    cfg['adapters']={};conf.write_text(json.dumps(cfg));invoke('sync')
    check('unmapped generated tasks are explicitly reported','requires an adapter' in (vault/'_folderwise-sync-status.md').read_text())
    conf.write_text(json.dumps(original_cfg));invoke('sync')
    # Attachment references, image ordering and unknown files remain predictable.
    original=note.read_text()
    note.write_text(original.replace('## Change Log','![Ref][asset]\n\n[asset]: assets/a.png\n\n![[a.png]]\n![Missing](assets/not-tracked.png)\n![Remote](https://example.invalid/a.png)\n\n## Change Log'))
    rc,out=invoke('plan')
    check('lean resolves reference and wiki embeds and reports missing images',rc==0 and 'missing or not tracked' in out,out)
    note.write_text(original)
    unknown=vault/'alpha/new-phone-note.md';unknown.write_text('A capture is outside this PR.\n')
    invoke('sync');check('unknown phone files remain intact',unknown.read_text()=='A capture is outside this PR.\n')
    cfg=json.loads(conf.read_text());backup=dict(cfg)
    for changes,reason in [({'version':2},'unsupported bridge config'),({'vault':cfg['source']},'separate'),
                           ({'mode':'bad'},'invalid mode'),({'interval_minutes':None},'cannot be null'),
                           ({'source':'relative'},'absolute paths'),({'enabled':'false'},'enabled must be boolean'),({'adapters':[]},'adapters must')]:
        conf.write_text(json.dumps(dict(backup,**changes)))
        rc,out=invoke('status');check('invalid bridge config: '+reason,rc==1 and reason in out,out)
    conf.write_text(json.dumps(backup))
    rc,out=invoke('disable','../alpha');check('project helper rejects path traversal',rc==1 and 'folder name' in out,out)
    # Lock contention prevents a second sync from racing the first.
    import fcntl
    with (home/'lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rc,out=invoke('sync');check('overlapping bridge processes do not race',rc==1 and 'another bridge' in out,out)
    if sys.platform=='darwin':
        cfg=json.loads(conf.read_text());cfg['launchagents_dir']=str(root/'LaunchAgents');cfg['notifications']='errors';conf.write_text(json.dumps(cfg))
        rc,out=invoke('schedule-enable',env=env)
        rc,out=invoke('doctor',env=env);check('doctor checks loaded schedule without parsing launchctl output',rc==0,out)
        invoke('configure','--interval-minutes','10')
        rc,out=invoke('doctor',env=env);check('doctor diagnoses interval that needs schedule reload',rc==1 and 'interval changed' in out,out)
        invoke('configure','--interval-minutes','5')
        saved=json.loads((home/'last-run.json').read_text());saved['last_run_epoch']=0;(home/'last-run.json').write_text(json.dumps(saved))
        rc,out=invoke('doctor',env=env);check('doctor diagnoses stale scheduled runs',rc==1 and 'stale' in out,out)
        invoke('schedule-disable',env=env)
    # Explicit notification failure is diagnostic and never mutates task records.
    (fake/'open').write_text('#!/bin/sh\nexit 1\n')
    rc,out=invoke('notify-test',env=env)
    check('notification failure is reported by the explicit test command',rc==1 and 'request failed' in out,out)
    if sys.platform=='darwin':
        rc,out=invoke('schedule-enable',env=env)
        check('failed setup notification does not claim delivery or undo scheduling',rc==0
              and 'could not be requested' in out and 'Notification requested;' not in out
              and json.loads((home/'schedule.json').read_text())['enabled'],out)
        invoke('schedule-disable',env=env)
    (home/'bridge.log').write_text('old log\n'*150000)
    invoke('sync')
    check('local bridge log rotates instead of growing forever',(home/'bridge.previous.log').exists())

    # Exercise portable CLI failure paths as well as macOS-only scheduling.
    backup=json.loads(conf.read_text())
    for response,reason in [('[]','ok'),('[1]','JSON objects'),
                            ('[{"id":"x","checked":"yes"}]','boolean checked'),
                            ('[{"id":"x","checked":false,"path":"missing.md","title":"x"}]','existing source')]:
        if reason=='ok':
            continue
        cfg=dict(backup);cfg['adapters']={'alpha':[sys.executable,'-c','print('+repr(response)+')']};conf.write_text(json.dumps(cfg))
        rc,out=invoke('plan');check('adapter contract rejects '+reason,rc==1 and reason in out,out)
    cfg=dict(backup);cfg['adapters']={'alpha':'not an argv array'};conf.write_text(json.dumps(cfg))
    rc,out=invoke('plan');check('adapter command must be an argument array',rc==1 and 'argv list' in out,out)
    cfg=dict(backup);cfg['source']=str(root/'missing-source');conf.write_text(json.dumps(cfg))
    rc,out=invoke('plan');check('missing source directory is diagnostic',rc==1 and 'unavailable' in out,out)
    cfg=dict(backup);cfg['source']=str(home);conf.write_text(json.dumps(cfg))
    rc,out=invoke('status');check('source cannot contain private bridge state',rc==1 and 'outside source' in out,out)
    conf.write_text(json.dumps(backup))
    pc=alpha/'.docs.yaml';original=pc.read_text()
    pc.write_text(original.replace('folderwise-ibridgesync: true','folderwise-ibridgesync: "true"'))
    rc,out=invoke('plan');check('project opt-out rejects ambiguous string booleans',rc==1 and 'must be boolean' in out,out)
    pc.write_text(original);pc.rename(alpha/'saved-config');pc.symlink_to(alpha/'saved-config')
    rc,out=invoke('plan');check('project config cannot be a symlink',rc==1 and 'symlink project config' in out,out)
    pc.unlink();(alpha/'saved-config').rename(pc)
    sh(['git','init','-q'],cwd=source)
    child=source/'not-independent';child.mkdir();(child/'.docs.yaml').write_text(original)
    rc,out=invoke('plan');check('project discovery requires an independent repository',rc==1 and 'independent Git' in out,out)
    shutil.rmtree(child)
    # An extra phone line and a generated-source toggle are unsupported edits.
    saved=view.read_text();view.write_text(saved+'New phone line\n')
    rc,out=invoke('sync');check('new phone lines are saved and the view restored instead of imported',rc==0 and 'number of lines changed' in out and 'New phone line' not in view.read_text(),out)
    view.write_text(saved)
    saved=mirror.read_text();mirror.write_text(saved.replace('- [ ] CSV action','- [x] CSV action'))
    rc,out=invoke('sync');check('generated raw checkboxes require dashboard mappings',rc==1 and 'no authoritative task mapping' in out,out)
    mirror.write_text(saved);invoke('sync')
    # Removing or renaming the source task while a phone edit is pending is a conflict.
    saved=view.read_text()
    view.write_text(saved.replace('- [ ] First task','- [x] First task'))
    note.write_text(note.read_text().replace('First task','Renamed source task'))
    local('docs_stamp.py','docs/checklist.md','--by','human','--summary','Rename a source task',cwd=alpha)
    sh(['git','add','-A'],cwd=alpha);sh(['git','commit','-qm','Rename task'],cwd=alpha)
    rc,out=invoke('sync');check('pending phone edits cannot target a disappeared task',rc==0 and 'changed or disappeared' in out and 'Renamed source task' in view.read_text(),out)
    view.write_text(saved);invoke('sync')
    # Source already reflecting the requested state is an idempotent acknowledgement.
    saved=view.read_text();view.write_text(saved.replace('- [ ] Renamed source task','- [x] Renamed source task'))
    note.write_text(note.read_text().replace('- [ ] Renamed source task','- [x] Renamed source task'))
    local('docs_stamp.py','docs/checklist.md','--by','human','--summary','Complete locally',cwd=alpha)
    sh(['git','add','-A'],cwd=alpha);sh(['git','commit','-qm','Complete locally'],cwd=alpha)
    head=sh(['git','rev-parse','HEAD'],cwd=alpha)[1]
    rc,out=invoke('sync');check('already-applied phone toggle does not create another commit',rc==0 and sh(['git','rev-parse','HEAD'],cwd=alpha)[1]==head,out)
    hook.unlink()
    view.write_text(view.read_text().replace('- [x] Renamed source task','- [ ] Renamed source task'))
    rc,out=invoke('sync');check('isolated transaction installs the framework hook if absent',rc==0 and '- [ ] Renamed source task' in note.read_text(),out)
    hook.write_text(original_hook);hook.chmod(0o755)
    # New source content cannot overwrite an unrelated vault file at the same path.
    extra=alpha/'payload.bin';extra.write_bytes(b'owned source payload')
    link=alpha/'docs/symlink.png';link.symlink_to(images/'a.png')
    sh(['git','add','-A'],cwd=alpha);sh(['git','commit','-qm','Add payload and excluded link'],cwd=alpha)
    invoke('configure','--mode','full')
    collision=vault/'alpha/payload.bin';collision.write_bytes(b'unrelated vault payload')
    rc,out=invoke('sync');check('new source file cannot overwrite an unowned vault collision',rc==1 and collision.read_bytes()==b'unrelated vault payload',out)
    collision.unlink();invoke('sync')
    check('Git symlinks are excluded from export',not (vault/'alpha/docs/symlink.png').exists())
    invoke('configure','--mode','lean')
    rc,out=invoke('plan');check('plan describes cleanup without removing files',rc==0 and 'REMOVE if unchanged: alpha/payload.bin' in out and collision.exists(),out)
    invoke('sync')
    saved=(vault/'_folderwise-sync-status.md').read_text();(vault/'_folderwise-sync-status.md').write_text('User-owned status edits\n')
    rc,out=invoke('sync');check('status report cannot overwrite user edits',rc==1 and 'unowned edits' in out and (vault/'_folderwise-sync-status.md').read_text()=='User-owned status edits\n',out)
    (vault/'_folderwise-sync-status.md').write_text(saved)
    # Obstructed destination type and incomplete setup get specific diagnostics.
    mirror.unlink();mirror.mkdir()
    rc,out=invoke('sync');check('a directory cannot masquerade as an exported file',rc==1 and 'expected a file' in out,out)
    mirror.rmdir();invoke('sync')
    rc,out=tool('icloud_bridge.py','--config',root/'empty-state/config.json','setup')
    check('setup requires explicit source and vault',rc==1 and 'requires --source and --vault' in out,out)
    rc,out=invoke('uninstall')
    check('uninstall cleans fully owned empty configuration folders',rc==0 and not (vault/'.obsidian').exists() and not (source/'.obsidian').exists() and not launcher.exists() and not app.exists() and not (home/'notifier.json').exists(),out)
    launcher.write_text('#!/bin/sh\n# user-owned customization\n')
    rc,out=invoke('uninstall')
    check('uninstall preserves a customized launch entry point',rc==0 and launcher.read_text()=='#!/bin/sh\n# user-owned customization\n',out)


def s_ibridge_rename():
    """Phone title edits: opt-in renames for Markdown and adapter tasks, rejection paths, CRLF and conflict copies."""
    root = CTX['root'] / 'rename-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf = home / 'config.json'

    def invoke(*args):
        return tool('icloud_bridge.py', '--config', conf, *args)

    def local(name, *args, cwd=None):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=cwd or source)

    def commit(project, message):
        sh(['git', 'add', '-A'], cwd=project)
        return sh(['git', 'commit', '-qm', message], cwd=project)

    def adapter_script(editable, honor_title):
        return ("import csv,json,sys\nfrom pathlib import Path\np=Path('data/tasks.csv')\nrows=list(csv.DictReader(p.open()))\nop=sys.argv[1]\n"
                "if op=='list':\n print(json.dumps([dict(id=r['id'],title=r['title'],checked=r['done']=='true',path='docs/checklist.md'"
                + (",editable=['title']" if editable else "") + ") for r in rows]))\n"
                "elif op=='apply':\n for c in json.load(sys.stdin):\n  for r in rows:\n   if r['id']==c['id']:\n    r['done']='true' if c['checked'] else 'false'\n"
                + ("    if 'title' in c:\n     assert r['title']==c['expected_title']\n     r['title']=c['title']\n" if honor_title else "")
                + " with p.open('w',newline='') as f:\n  w=csv.DictWriter(f,fieldnames=['id','title','done']);w.writeheader();w.writerows(rows)\n"
                " note=Path('docs/checklist.md');text=note.read_text();start=text.index('<!-- tasks:start -->');end=text.index('<!-- tasks:end -->')\n"
                " note.write_text(text[:start]+'<!-- tasks:start -->\\n'+''.join('- [ ] '+r['title']+'\\n' for r in rows if r['done']=='false')+text[end:])\n")

    for name in ('alpha', 'beta', 'gamma', 'delta'):
        rc, out = local('new_project.py', '--name', name, '--description', 'Fictional rename test', '--no-prompt')
        check('rename sandbox creates ' + name, rc == 0, out)
    alpha = source / 'alpha'
    rc, out = local('docs_new.py', 'docs/checklist.md', '--type', 'plan', '--title', 'Checklist', '--by', 'human', cwd=alpha)
    note = alpha / 'docs/checklist.md'
    note.write_text(note.read_text().replace('## Change Log', '- [ ] Alpha one\n- [ ] Beta two\n- [ ] Gamma three\n- [ ] See [the docs](https://example.com/x) now\n'
                                                              '- [ ] Twin\n- [ ] Twin\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add tasks', cwd=alpha)
    commit(alpha, 'Add test tasks')
    for name, editable, honor in (('beta', True, True), ('gamma', False, True), ('delta', True, False)):
        project = source / name
        (project / 'data').mkdir(exist_ok=True)
        (project / 'data/tasks.csv').write_text('id,title,done\nrow-1,CSV one,false\n')
        (project / 'scripts').mkdir(exist_ok=True)
        (project / 'scripts/adapter.py').write_text(adapter_script(editable, honor))
        local('docs_new.py', 'docs/checklist.md', '--type', 'plan', '--title', 'Checklist', '--by', 'human', cwd=project)
        doc = project / 'docs/checklist.md'
        doc.write_text(doc.read_text().replace('## Change Log', '<!-- tasks:start -->\n- [ ] CSV one\n<!-- tasks:end -->\n\n## Change Log'))
        local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add generated tasks', cwd=project)
        commit(project, 'Add CSV adapter')
    rc, out = invoke('setup', '--source', source, '--vault', vault, '--notifications', 'off', '--no-schedule')
    cfg = json.loads(conf.read_text())
    cfg['adapters'] = {n: [sys.executable, 'scripts/adapter.py'] for n in ('beta', 'gamma', 'delta')}
    conf.write_text(json.dumps(cfg))
    # Renames are opt-in: the default keeps today's checkbox-only behavior.
    view = vault / '_Folderwise Tasks/alpha.md'
    invoke('sync')
    check('rename sandbox exports a schema-2 state', json.loads((home / 'state.json').read_text()).get('schema') == 2)
    check('views of projects without the setting say only toggles are imported', 'Only checkbox toggles are imported' in view.read_text())
    view.write_text(view.read_text().replace('- [ ] Alpha one', '- [ ] Alpha renamed'))
    head = sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1]
    rc, out = invoke('sync')
    check('title edits stay off until the project opts in', rc == 0 and 'title edits are off' in out and '- [ ] Alpha one' in view.read_text()
          and 'Alpha renamed' not in note.read_text() and sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1] == head, out)
    for name in ('alpha', 'beta', 'gamma', 'delta'):
        config = source / name / '.docs.yaml'
        config.write_text(config.read_text() + '\nfolderwise-ibridgerename: ' + ('"yes"' if name == 'delta' else 'true') + '\n')
    rc, out = invoke('sync')
    check('a non-boolean rename setting is rejected', rc == 1 and 'folderwise-ibridgerename must be boolean' in out, out)
    delta_config = source / 'delta/.docs.yaml'
    delta_config.write_text(delta_config.read_text().replace('"yes"', 'true'))
    for name in ('alpha', 'beta', 'gamma', 'delta'):
        commit(source / name, 'Allow phone title edits')
    rc, out = local('docs_doctor.py', cwd=alpha)
    check('project doctor recognizes folderwise-ibridgerename', 'unknown key' not in out, out)
    rc, out = invoke('sync')
    check('opted-in views explain title edits', rc == 0 and 'title edits are imported' in view.read_text(), out)
    # Markdown rename, rename plus toggle, then idempotence.
    view.write_text(view.read_text().replace('- [ ] Alpha one', '- [x] Alpha renamed'))
    rc, out = invoke('sync')
    _, log = sh(['git', 'log', '-1', '--format=%s%n%B'], cwd=alpha)
    check('phone rename with a toggle edits the source note once', rc == 0 and '- [x] Alpha renamed ' not in note.read_text() and '- [x] Alpha renamed\n' in note.read_text()
          and 'Alpha one' not in note.read_text(), out)
    check('rename commit has provenance, counts and no titles', 'Update tasks from Obsidian' in log and 'Bridge: folderwise-ibridge' in log
          and 'Bridge-Ops: toggle=1 rename=1' in log and 'Alpha renamed' not in log and 'user-typed' in log, log)
    check('rename stamps the note as human with a rename summary', 'updated_by: human' in note.read_text() and 'Toggle and rename tasks via Obsidian iCloud bridge' in note.read_text())
    check('regenerated view carries the new title', '- [x] Alpha renamed (' in view.read_text())
    status = (vault / '_folderwise-sync-status.md').read_text()
    check('status report lists the import with its commit', '## Recent imports' in status and '| alpha |' in status and sh(['git', 'rev-parse', '--short', 'HEAD'], cwd=alpha)[1].strip() in status, status)
    head = sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1]
    rc, out = invoke('sync')
    check('unchanged sync after a rename creates no commit', rc == 0 and sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1] == head, out)
    view.write_text(view.read_text().replace('- [x] Alpha renamed', '- [ ] Alpha renamed'))
    invoke('sync')
    # Rejections never reach the source: swap, duplicate, markup, links, lossy title, length and a Mac-side rename.
    def rejected(label, edit, expected, project=alpha, path=view):
        before = sh(['git', 'rev-parse', 'HEAD'], cwd=project)[1]
        path.write_text(edit(path.read_text()))
        rc, out = invoke('sync')
        check(label, rc == 0 and expected in out and sh(['git', 'rev-parse', 'HEAD'], cwd=project)[1] == before
              and 'NOTICE' in out, out)
    def swap(text):
        return text.replace('Beta two', 'TMP').replace('Gamma three', 'Beta two').replace('TMP', 'Gamma three')
    rejected('swapped titles are not read as two renames', swap, 'already used by another task')
    rejected('renaming to an existing title is rejected', lambda s: s.replace('Beta two', 'Gamma three'), 'already used')
    rejected('a title cannot hide generated-block markers', lambda s: s.replace('Beta two', 'Beta <!-- x:start -->'), 'comment markers')
    rejected('a title cannot start a spreadsheet formula', lambda s: s.replace('Beta two', '=SUM(A1)'), 'start with')
    rejected('a title cannot embed links', lambda s: s.replace('Beta two', 'Beta [x](http://example.com)'), 'links or images')
    rejected('an over-long title is rejected', lambda s: s.replace('Beta two', 'B' * 201), 'characters')
    rejected('invisible direction characters are rejected', lambda s: s.replace('Beta two', 'Beta \u202etwo'), 'direction')
    rejected('removing the source link is rejected', lambda s: s.replace('Beta two ([source](../alpha/docs/checklist.md))', 'Beta two'), 'trailing source link')
    rejected('a due date appended by the Tasks edit dialog is rejected', lambda s: s.replace('Beta two ([source](../alpha/docs/checklist.md))', 'Beta two ([source](../alpha/docs/checklist.md)) \U0001F4C5 2026-10-25'), 'trailing source link')
    rejected('a task whose title has links cannot be renamed from the view', lambda s: s.replace('See the docs now', 'See the docs soon'), 'links or images')
    rejected('duplicate tasks cannot be renamed', lambda s: s.replace('- [ ] Twin', '- [ ] Twin renamed', 1), 'share its title')
    check('rejected text is saved on the Mac', sum(1 for p in (home / 'rejected').rglob('*') if p.is_file()) >= 10)
    check('restored views match the Mac again', 'Beta two' in view.read_text() and 'TMP' not in view.read_text())
    # A rename pending while the Mac renames the same task is a conflict.
    view.write_text(view.read_text().replace('Beta two', 'Beta phone'))
    note.write_text(note.read_text().replace('Beta two', 'Beta mac'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Rename on Mac', cwd=alpha)
    commit(alpha, 'Rename on Mac')
    rc, out = invoke('sync')
    check('a rename pending during a Mac rename is a reported conflict', rc == 0 and 'changed or disappeared on Mac' in out and 'Beta mac' in view.read_text()
          and 'Beta phone' not in note.read_text(), out)
    # Renames inside mirrored notes are still toggle-only, with a named error.
    mirror = vault / 'alpha/docs/checklist.md'
    saved = mirror.read_text()
    mirror.write_text(saved.replace('Gamma three', 'Gamma edited'))
    rc, out = invoke('sync')
    check('mirrored note title edits freeze with the file and line named', rc == 1 and 'alpha/docs/checklist.md: line' in out and 'only checkbox' in out, out)
    mirror.write_text(saved)
    rc, out = invoke('sync')
    check('restoring the note recovers', rc == 0, out)
    head = sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1]
    view.write_text(view.read_text().replace('Gamma three (', 'Gamma three  ('))
    rc, out = invoke('sync')
    check('whitespace-only title edits are ignored', rc == 0 and 'NOTICE' not in out and sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1] == head, out)
    saved = mirror.read_text()
    view.write_text(view.read_text().replace('Gamma three', 'Gamma renamed'))
    mirror.write_text(saved.replace('- [ ] Gamma three', '- [x] Gamma three'))
    rc, out = invoke('sync')
    check('a view rename and a toggle in the copied note combine into one change', rc == 0 and '- [x] Gamma renamed' in note.read_text(), out)
    # A copied-note toggle for a task renamed on the Mac cannot be restored away, so it freezes with a clear error.
    note.write_text(note.read_text().replace('Alpha renamed', 'Alpha mac'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Rename again on Mac', cwd=alpha)
    commit(alpha, 'Rename again on Mac')
    saved = mirror.read_text()
    mirror.write_text(saved.replace('- [ ] Alpha renamed', '- [x] Alpha renamed'))
    rc, out = invoke('sync')
    check('a pending copied-note toggle for a Mac-renamed task freezes with the project named', rc == 1 and 'alpha: task changed or disappeared on Mac' in out, out)
    mirror.write_text(saved)
    rc, out = invoke('sync')
    check('restoring the copied note recovers from the freeze', rc == 0, out)
    old_stash = home / 'rejected/19700101T000000Z'
    old_stash.mkdir(parents=True)
    (old_stash / 'old-edit').write_text('very old phone text')
    os.utime(old_stash, (1, 1))
    invoke('sync')
    check('saved phone text is forgotten after 30 days', not old_stash.exists())
    # Adapter-backed renames.
    beta_view = vault / '_Folderwise Tasks/beta.md'
    beta_view.write_text(beta_view.read_text().replace('CSV one', 'CSV renamed'))
    rc, out = invoke('sync')
    _, log = sh(['git', 'log', '-1', '--format=%B'], cwd=source / 'beta')
    check('adapter task rename updates the CSV and regenerated note', rc == 0 and 'row-1,CSV renamed,false' in (source / 'beta/data/tasks.csv').read_text()
          and 'CSV renamed' in (source / 'beta/docs/checklist.md').read_text() and 'Bridge-Ops: toggle=0 rename=1' in log, out)
    beta_view.write_text(beta_view.read_text().replace('CSV renamed', 'CSV phone'))
    csv_file = source / 'beta/data/tasks.csv'
    csv_file.write_text(csv_file.read_text().replace('CSV renamed', 'CSV mac'))
    commit(source / 'beta', 'Rename CSV row on Mac')
    rc, out = invoke('sync')
    check('an adapter rename pending during a Mac rename is a reported conflict', rc == 0 and 'its title also changed on the Mac' in out
          and 'CSV mac' in beta_view.read_text(), out)
    gamma_view = vault / '_Folderwise Tasks/gamma.md'
    gamma_view.write_text(gamma_view.read_text().replace('CSV one', 'CSV nope'))
    rc, out = invoke('sync')
    check('an adapter that does not allow title edits is restored', rc == 0 and 'does not allow title edits' in out and 'CSV nope' not in gamma_view.read_text()
          and 'CSV one' in (source / 'gamma/data/tasks.csv').read_text(), out)
    delta_view = vault / '_Folderwise Tasks/delta.md'
    delta_head = sh(['git', 'rev-parse', 'HEAD'], cwd=source / 'delta')[1]
    saved = delta_view.read_text()
    delta_view.write_text(saved.replace('CSV one', 'CSV ignored'))
    rc, out = invoke('sync')
    check('an adapter that ignores the title aborts without a commit', rc == 1 and 'did not apply the requested title' in out
          and sh(['git', 'rev-parse', 'HEAD'], cwd=source / 'delta')[1] == delta_head and 'row-1,CSV one,false' in (source / 'delta/data/tasks.csv').read_text(), out)
    delta_view.write_text(saved)
    rc, out = invoke('sync')
    check('restoring the view recovers from an adapter failure', rc == 0, out)
    # CRLF sources keep their line endings through a toggle.
    rc, out = local('docs_new.py', 'docs/windows.md', '--type', 'plan', '--title', 'Windows', '--by', 'human', cwd=alpha)
    windows = alpha / 'docs/windows.md'
    windows.write_bytes(windows.read_text().replace('## Change Log', '- [ ] Windows task\n\n## Change Log').replace('\n', '\r\n').encode())
    commit(alpha, 'Add CRLF note')
    invoke('sync')
    view.write_text(view.read_text().replace('- [ ] Windows task', '- [x] Windows task'))
    rc, out = invoke('sync')
    raw = windows.read_bytes()
    check('a toggle keeps CRLF line endings in the source note', rc == 0 and b'- [x] Windows task\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b''), out)
    # iCloud conflict copies are reported, never imported.
    copy = vault / 'alpha/docs/checklist 2.md'
    copy.write_text('- [x] Alpha renamed\n')
    rc, out = invoke('sync')
    status = (vault / '_folderwise-sync-status.md').read_text()
    check('conflict copies are reported and not imported', rc == 0 and '## iCloud conflict copies' in status and 'alpha/docs/checklist 2.md' in status
          and copy.read_text() == '- [x] Alpha renamed\n', status)
    copy.unlink()
    invoke('sync')
    check('the conflict-copy section disappears once the copy is gone', '## iCloud conflict copies' not in (vault / '_folderwise-sync-status.md').read_text())
    script = source / 'gamma/scripts/adapter.py'
    script.write_text(script.read_text().replace("path='docs/checklist.md')", "path='docs/checklist.md',editable='title')"))
    commit(source / 'gamma', 'Break the editable field')
    rc, out = invoke('sync')
    check('an adapter editable field must be a list', rc == 1 and 'editable must be a list' in out, out)


def s_ibridge_isolation():
    """One project's problem pauses only that project; plan previews phone edits; resolve; counts-only notifications."""
    root = CTX['root'] / 'isolation-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf = home / 'config.json'
    fake = root / 'fakebin'
    fake.mkdir()
    for executable in ('open', 'codesign', 'launchctl'):
        (fake / executable).write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(root / 'os-calls') + '"\nexit 0\n')
        (fake / executable).chmod(0o755)
    (fake / 'open').write_text((fake / 'open').read_text().replace('exit 0', 'cat "' + str(home / 'notification-message.txt') + '" >> "' + str(root / 'notification-bodies') + '"\necho >> "' + str(root / 'notification-bodies') + '"\nexit 0'))
    (fake / 'osacompile').write_text('#!' + sys.executable + '\nimport pathlib,plistlib,sys\np=pathlib.Path(sys.argv[2])/"Contents"\n(p/"Resources").mkdir(parents=True)\n(p/"Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"applet","CFBundleIconName":"applet"}))\n(p/"Resources/Assets.car").write_bytes(b"x")\n(p/"Resources/main.scpt").write_bytes(pathlib.Path(sys.argv[3]).read_bytes())\n')
    (fake / 'osacompile').chmod(0o755)

    def invoke(*args, extra=None):
        return tool('icloud_bridge.py', '--config', conf, *args, env={'PATH': str(fake) + os.pathsep + os.environ['PATH'], **(extra or {})})

    def local(name, *args, cwd=None):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=cwd or source)

    def commit(project, message):
        sh(['git', 'add', '-A'], cwd=project)
        return sh(['git', 'commit', '-qm', message], cwd=project)

    def head(project):
        return sh(['git', 'rev-parse', 'HEAD'], cwd=project)[1]

    def bodies():
        path = root / 'notification-bodies'
        return path.read_text() if path.exists() else ''

    for name in ('alpha', 'beta', 'gamma', 'delta'):
        rc, out = local('new_project.py', '--name', name, '--description', 'Fictional isolation test', '--no-prompt')
        check('isolation sandbox creates ' + name, rc == 0, out)
        local('docs_new.py', 'docs/checklist.md', '--type', 'plan', '--title', 'Checklist', '--by', 'human', cwd=source / name)
    alpha, beta, gamma, delta = (source / n for n in ('alpha', 'beta', 'gamma', 'delta'))
    for project, marker in ((alpha, 'A1'), (beta, 'B1'), (delta, 'D1')):
        doc = project / 'docs/checklist.md'
        doc.write_text(doc.read_text().replace('## Change Log', f'- [ ] {marker} task\n\n## Change Log'))
        local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add task', cwd=project)
        commit(project, 'Add task')
    (gamma / 'data').mkdir(exist_ok=True)
    (gamma / 'data/tasks.csv').write_text('id,title,done\nrow-1,G1 task,false\n')
    (gamma / 'scripts').mkdir(exist_ok=True)
    (gamma / 'scripts/adapter.py').write_text(
        "import csv,json,os,sys\nfrom pathlib import Path\np=Path('data/tasks.csv')\nrows=list(csv.DictReader(p.open()))\nop=sys.argv[1]\n"
        "if op=='list':\n print(json.dumps([dict(id=r['id'],title=r['title'],checked=r['done']=='true',path='docs/checklist.md') for r in rows]))\n"
        "elif op=='apply':\n changes={c['id']:c['checked'] for c in json.load(sys.stdin)}\n for r in rows:\n  if r['id'] in changes: r['done']='true' if changes[r['id']] else 'false'\n"
        " with p.open('w',newline='') as f:\n  w=csv.DictWriter(f,fieldnames=['id','title','done']);w.writeheader();w.writerows(rows)\n"
        " note=Path('docs/checklist.md');text=note.read_text();s=text.index('<!-- tasks:start -->');e=text.index('<!-- tasks:end -->')\n"
        " note.write_text(text[:s]+'<!-- tasks:start -->\\n'+''.join('- [ ] '+r['title']+'\\n' for r in rows if r['done']=='false')+text[e:])\n"
        "elif op=='validate' and os.environ.get('IBRIDGE_FAIL_VALIDATE'):\n print('validation refused',file=sys.stderr);sys.exit(1)\n")
    doc = gamma / 'docs/checklist.md'
    doc.write_text(doc.read_text().replace('## Change Log', '<!-- tasks:start -->\n- [ ] G1 task\n<!-- tasks:end -->\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add generated task', cwd=gamma)
    commit(gamma, 'Add adapter')
    rc, out = invoke('setup', '--source', source, '--vault', vault, '--notifications', 'imports', '--no-schedule')
    cfg = json.loads(conf.read_text())
    cfg['adapters'] = {'gamma': [sys.executable, 'scripts/adapter.py']}
    conf.write_text(json.dumps(cfg))
    check('setup accepts the imports notification mode', rc == 0 and json.loads(conf.read_text())['notifications'] == 'imports', out)
    rc, out = tool('icloud_bridge.py', '--config', conf, 'configure', '--notifications', 'sometimes')
    check('unknown notification modes are rejected', rc == 2, out)
    views = {n: vault / f'_Folderwise Tasks/{n}.md' for n in ('alpha', 'beta', 'gamma', 'delta')}
    notes = {n: source / n / 'docs/checklist.md' for n in views}
    invoke('sync')

    # A dirty project is paused while its neighbours keep importing and exporting.
    local('docs_new.py', 'docs/late.md', '--type', 'plan', '--title', 'Late', '--by', 'human', cwd=alpha)
    local('docs_new.py', 'docs/beta-late.md', '--type', 'plan', '--title', 'Beta late', '--by', 'human', cwd=beta)
    commit(alpha, 'Add late doc')
    commit(beta, 'Add beta late doc')
    (alpha / 'scratch.txt').write_text('uncommitted\n')
    views['alpha'].write_text(views['alpha'].read_text().replace('- [ ] A1 task', '- [x] A1 task'))
    views['beta'].write_text(views['beta'].read_text().replace('- [ ] B1 task', '- [x] B1 task'))
    alpha_head, beta_head = head(alpha), head(beta)
    rc, out = invoke('sync')
    status = (vault / '_folderwise-sync-status.md').read_text()
    check('a dirty project is paused and reported while other projects import', rc == 1 and head(beta) != beta_head and '- [x] B1 task' in notes['beta'].read_text()
          and head(alpha) == alpha_head and '- [ ] A1 task' in notes['alpha'].read_text() and 'uncommitted' in out, out)
    check('other projects still export while one is paused', (vault / 'beta/docs/beta-late.md').exists() and not (vault / 'alpha/docs/late.md').exists())
    check('the paused project keeps its pending phone edit and previous export', '- [x] A1 task' in views['alpha'].read_text())
    check('the status report names the paused project', 'Paused projects: alpha.' in status and 'keep syncing' in status, status)
    check('a paused project sends the attention alert, not an import count', 'needs attention' in bodies() and 'phone change' not in bodies(), bodies())
    count_before = bodies().count('needs attention')
    rc, out = invoke('sync')
    check('an unchanged pause is not announced again', rc == 1 and bodies().count('needs attention') == count_before, bodies())
    (alpha / 'scratch.txt').unlink()
    rc, out = invoke('sync')
    check('the paused project resumes once fixed', rc == 0 and '- [x] A1 task' in notes['alpha'].read_text() and (vault / 'alpha/docs/late.md').exists()
          and 'Paused projects' not in (vault / '_folderwise-sync-status.md').read_text(), out)
    check('imports notify with counts only', 'Folderwise applied 1 phone change(s) in 1 project(s).' in bodies() and 'A1' not in bodies(), bodies())

    # An unsupported edit to a copied note pauses only that project.
    mirror = vault / 'beta/docs/checklist.md'
    saved = mirror.read_text()
    mirror.write_text(saved.replace('B1 task', 'B1 edited'))
    views['alpha'].write_text(views['alpha'].read_text().replace('- [x] A1 task', '- [ ] A1 task'))
    rc, out = invoke('sync')
    check('a bad copied-note edit pauses its project and names the file', rc == 1 and 'beta/docs/checklist.md: line' in out and '- [ ] A1 task' in notes['alpha'].read_text()
          and 'Paused projects: beta.' in (vault / '_folderwise-sync-status.md').read_text(), out)
    rc, out = invoke('resolve')
    check('resolve lists files with pending phone edits', rc == 0 and 'PENDING beta/docs/checklist.md' in out, out)
    rc, out = invoke('resolve', 'alpha/docs/checklist.md')
    check('resolve refuses a file without a pending edit', rc == 1 and 'no pending phone edit' in out, out)
    rc, out = invoke('resolve', 'beta/docs/checklist.md')
    stash = [p.read_text() for p in (home / 'rejected').rglob('*') if p.is_file()]
    check('resolve saves the phone text and restores the Mac version', rc == 0 and mirror.read_text() == saved and any('B1 edited' in text for text in stash), out)
    rc, out = invoke('sync')
    check('the project resumes after resolve', rc == 0 and 'Paused projects' not in (vault / '_folderwise-sync-status.md').read_text(), out)
    rc, out = invoke('resolve')
    check('resolve reports when nothing is pending', rc == 0 and 'No pending phone edits.' in out, out)

    # An adapter validation failure pauses only that project; the same edit imports once it recovers.
    views['alpha'].write_text(views['alpha'].read_text().replace('- [ ] A1 task', '- [x] A1 task'))
    views['gamma'].write_text(views['gamma'].read_text().replace('- [ ] G1 task', '- [x] G1 task'))
    gamma_head = head(gamma)
    rc, out = invoke('sync', extra={'IBRIDGE_FAIL_VALIDATE': '1'})
    check('an adapter failure pauses only that project', rc == 1 and 'validation refused' in out and head(gamma) == gamma_head
          and '- [x] A1 task' in notes['alpha'].read_text() and 'row-1,G1 task,false' in (gamma / 'data/tasks.csv').read_text(), out)
    rc, out = invoke('sync')
    check('the adapter project imports after the failure clears', rc == 0 and 'row-1,G1 task,true' in (gamma / 'data/tasks.csv').read_text(), out)

    # A project that cannot be inventoried keeps its previous export instead of being removed.
    before = sorted(p.relative_to(vault).as_posix() for p in (vault / 'delta').rglob('*') if p.is_file())
    broken = delta / 'docs/broken.md'
    local('docs_new.py', 'docs/broken.md', '--type', 'plan', '--title', 'Broken', '--by', 'human', cwd=delta)
    broken.write_text(broken.read_text().replace('## Change Log', '![escape](../../outside.png)\n\n## Change Log'))
    local('docs_stamp.py', 'docs/broken.md', '--by', 'human', '--summary', 'Add escaping link', cwd=delta)
    commit(delta, 'Add an escaping link')
    views['beta'].write_text(views['beta'].read_text().replace('- [ ] B1 task', '- [x] B1 task'))
    rc, out = invoke('sync')
    after = sorted(p.relative_to(vault).as_posix() for p in (vault / 'delta').rglob('*') if p.is_file())
    check('an uninventoriable project is paused without losing its export', rc == 1 and 'unsafe path' in out and after == before
          and views['delta'].exists() and '- [x] B1 task' in notes['beta'].read_text(), out)
    broken.unlink()
    commit(delta, 'Remove the escaping link')
    rc, out = invoke('sync')
    check('the project resumes after the inventory problem is fixed', rc == 0 and (vault / 'delta/docs/checklist.md').exists(), out)

    # Discovery/config failures stay project-local, including disabled projects.
    original_config = (alpha / '.docs.yaml').read_text()
    alpha_export = (vault / 'alpha/docs/checklist.md').read_bytes()
    for index, invalid in enumerate(('timezone: Invalid/Zone\n', 'folderwise-ibridgesync: maybe\n', '- invalid mapping\n', 'bad: [\n')):
        (alpha / '.docs.yaml').write_text(invalid)
        late = beta / f'docs/config-isolation-{index}.md'
        local('docs_new.py', late.relative_to(beta), '--type', 'plan', '--title', 'Healthy export', '--by', 'human', cwd=beta)
        commit(beta, 'Healthy project advances during invalid config')
        before_run = json.loads((home / 'last-run.json').read_text())['last_run_epoch']
        rc, out = invoke('sync')
        status = (vault / '_folderwise-sync-status.md').read_text()
        check('config isolation preserves healthy exports: ' + invalid.split(':')[0].strip(), rc == 1
              and (vault / 'beta' / late.relative_to(beta)).is_file()
              and (vault / 'alpha/docs/checklist.md').read_bytes() == alpha_export
              and 'Paused projects: alpha.' in status and 'Traceback' not in out
              and json.loads((home / 'last-run.json').read_text())['last_run_epoch'] > before_run, out)
    (alpha / '.docs.yaml').write_text(original_config)
    rc, out = invoke('sync')
    check('a project resumes after repairing its config', rc == 0 and 'Paused projects' not in (vault / '_folderwise-sync-status.md').read_text(), out)
    cfg_path = alpha / '.docs.yaml'
    outside_config = root / 'linked-config.yaml'; outside_config.write_text(original_config)
    cfg_path.unlink(); cfg_path.symlink_to(outside_config)
    rc, out = invoke('sync')
    check('a symlink project config pauses only its project', rc == 1 and 'Paused projects: alpha.' in (vault / '_folderwise-sync-status.md').read_text(), out)
    outside_config.unlink()
    rc, out = invoke('sync')
    check('a dangling config symlink preserves the previous project export', rc == 1
          and (vault / 'alpha/docs/checklist.md').read_bytes() == alpha_export
          and 'symlink project config' in out, out)
    cfg_path.unlink(); cfg_path.write_text(original_config)
    invoke('sync')

    # A hook that changes the live repository cannot publish its disposable clone.
    hook = alpha / '.git/hooks/pre-commit'
    original_hook = hook.read_bytes()
    saved_hook = root / 'original-pre-commit'; saved_hook.write_bytes(original_hook); saved_hook.chmod(0o755)
    scratch = alpha / 'concurrent.txt'
    hook.write_text('#!' + sys.executable + '\nimport subprocess\nfrom pathlib import Path\n'
                    + f'subprocess.run([{str(saved_hook)!r}], check=True)\nPath({str(scratch)!r}).write_text("Concurrent Mac edit")\n')
    wanted = views['alpha'].read_text().replace('- [x] A1 task', '- [ ] A1 task')
    views['alpha'].write_text(wanted)
    before_head = head(alpha)
    rc, out = invoke('sync')
    check('shared transaction refuses a concurrent live edit and removes its clone', rc == 1 and 'changed during transaction' in out
          and head(alpha) == before_head and views['alpha'].read_text() == wanted and not (home / 'work/alpha').exists(), out)
    hook.write_bytes(original_hook); scratch.unlink()
    rc, out = invoke('sync')
    check('shared transaction retries the preserved edit after the race clears', rc == 0 and '- [ ] A1 task' in notes['alpha'].read_text(), out)
    # Restore the state expected by the following plan scenario.
    views['alpha'].write_text(views['alpha'].read_text().replace('- [ ] A1 task', '- [x] A1 task'))
    invoke('sync')

    # plan previews pending phone edits without changing anything.
    views['alpha'].write_text(views['alpha'].read_text().replace('- [x] A1 task', '- [ ] A1 task'))
    views['beta'].write_text(views['beta'].read_text().replace('B1 task', 'B1 renamed'))
    heads, vault_text = {n: head(source / n) for n in views}, views['alpha'].read_text()
    rc, out = invoke('plan')
    check('plan previews a pending toggle', rc == 0 and 'PHONE EDIT alpha: would toggle 1 and rename 0 task(s)' in out, out)
    check('plan previews a rejected edit without applying it', 'PHONE EDIT REJECTED _Folderwise Tasks/beta.md: line' in out and 'title edits are off' in out, out)
    check('plan changes nothing', {n: head(source / n) for n in views} == heads and views['alpha'].read_text() == vault_text
          and 'B1 renamed' in views['beta'].read_text() and not (home / 'export.json').exists(), out)
    rc, out = invoke('sync')
    check('the planned edits apply on the next sync', '- [ ] A1 task' in notes['alpha'].read_text() and 'B1 renamed' not in views['beta'].read_text(), out)

    # Bridge-wide files must not create a fictitious paused project called None.
    dashboard = vault / 'Tasks.md'
    original_dashboard = dashboard.read_bytes()
    dashboard.write_text(dashboard.read_text() + '\nUnowned phone prose\n')
    rc, out = invoke('sync')
    check('bridge-wide phone edits are preserved and reported without a project-name crash', rc == 1
          and 'Tasks.md:' in out and 'Traceback' not in out and 'Unowned phone prose' in dashboard.read_text(), out)
    dashboard.write_bytes(original_dashboard)
    invoke('sync')

    # The default notification mode stays quiet about imports.
    invoke('configure', '--notifications', 'errors')
    count = bodies().count('phone change')
    views['alpha'].write_text(views['alpha'].read_text().replace('- [ ] A1 task', '- [x] A1 task'))
    rc, out = invoke('sync')
    check('errors mode does not announce routine imports', rc == 0 and bodies().count('phone change') == count, bodies())


def s_ibridge_notes():
    """Opt-in phone text edits to copied notes: gates, quiet period, merge safety, protected regions and recovery."""
    root = CTX['root'] / 'notes-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf = home / 'config.json'

    def invoke(*args):
        return tool('icloud_bridge.py', '--config', conf, *args)

    def local(name, *args, cwd=None):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=cwd or source)

    def commit(project, message):
        sh(['git', 'add', '-A'], cwd=project)
        return sh(['git', 'commit', '-qm', message], cwd=project)

    def head():
        return sh(['git', 'rev-parse', 'HEAD'], cwd=alpha)[1]

    for name in ('alpha', 'beta'):
        rc, out = local('new_project.py', '--name', name, '--description', 'Fictional note edit test', '--no-prompt')
        check('notes sandbox creates ' + name, rc == 0, out)
    alpha = source / 'alpha'
    for rel in ('docs/notes.md', 'docs/other.md'):
        local('docs_new.py', rel, '--type', 'plan', '--title', Path(rel).stem.title(), '--by', 'human', cwd=alpha)
    note = alpha / 'docs/notes.md'
    lines = ''.join(f'Reference line {i}.\n' for i in range(1, 101))
    note.write_text(note.read_text().replace('## Change Log', 'Original paragraph.\n\n- [ ] A handwritten task\n\n' + lines + '\n## Change Log'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Add body', cwd=alpha)
    pc = alpha / '.docs.yaml'
    pc.write_text(pc.read_text() + '\nfolderwise-ibridgeedit:\n  - "docs/notes*.md"\n  - "journal/**/*.md"\n  - "archive/**"\n')
    for rel in ('journal/2026/entry.md', 'archive/old.md'):
        local('docs_new.py', rel, '--type', 'plan', '--title', 'Deep', '--by', 'human', cwd=alpha)
    commit(alpha, 'Add note and edit patterns')
    rc, out = invoke('setup', '--source', source, '--vault', vault, '--notifications', 'off', '--no-schedule')
    mirror, other, view = vault / 'alpha/docs/notes.md', vault / 'alpha/docs/other.md', vault / '_Folderwise Tasks/alpha.md'
    check('notes sandbox exports the note', rc == 0 and mirror.read_text() == note.read_text(), out)
    base = mirror.read_text()

    def pause_and_resolve(label, text, expected, path=mirror, key='alpha/docs/notes.md', runs=1):
        before = head()
        path.write_text(text)
        for _ in range(runs):
            rc, out = invoke('sync')
        check(label, rc == 1 and expected in out and head() == before and path.read_text() == text
              and 'Paused projects: alpha.' in (vault / '_folderwise-sync-status.md').read_text(), out)
        rc, out = invoke('resolve', key)
        rc2, out2 = invoke('sync')
        check(label + ' (recovers with resolve)', rc == 0 and rc2 == 0 and path.read_text() == base if path == mirror else rc2 == 0, out + out2)

    # Off by default: configuration is validated and a text edit behaves as before.
    pause_and_resolve('phone text edits are refused until the bridge switch is on', base.replace('Original paragraph.', 'Edited paragraph.'), 'only checkbox on/off changes are supported')
    rc, out = invoke('configure', '--text-edits', 'maybe')
    check('the text edit switch accepts only on or off', rc == 2, out)
    rc, out = invoke('configure', '--edit-settle-seconds', '-5')
    check('the quiet period cannot be negative', rc == 1 and 'edit_settle_seconds' in out, out)
    original_config = pc.read_text()
    pc.write_text(original_config.replace('folderwise-ibridgeedit:\n  - "docs/notes*.md"\n  - "journal/**/*.md"\n  - "archive/**"', 'folderwise-ibridgeedit: "docs/*.md"'))
    rc, out = invoke('plan')
    check('edit patterns must be a list of project-relative paths', rc == 1 and 'folderwise-ibridgeedit must be a list' in out, out)
    pc.write_text(original_config.replace('"docs/notes*.md"', '"../outside.md"'))
    rc, out = invoke('plan')
    check('edit patterns cannot leave the project', rc == 1 and 'folderwise-ibridgeedit must be a list' in out, out)
    pc.write_text(original_config)
    rc, out = tool('icloud_bridge.py', '--config', conf, 'doctor')
    rc, out = sh(['uv', 'run', '--quiet', str(source / '_tools/docs_doctor.py')], cwd=alpha)
    check('project doctor recognizes folderwise-ibridgeedit', 'unknown key' not in out, out)
    cfg = json.loads(conf.read_text())
    conf.write_text(json.dumps(dict(cfg, text_edits='yes')))
    rc, out = invoke('plan')
    check('the text edit switch must be a real boolean', rc == 1 and 'text_edits must be boolean' in out, out)
    conf.write_text(json.dumps(cfg))
    invoke('configure', '--text-edits', 'on', '--edit-settle-seconds', '3600')

    # A phone edit waits for a quiet period, then applies as one human-stamped commit.
    phone_text = base.replace('Original paragraph.', 'Original paragraph.\n\nPhone added this paragraph.')
    mirror.write_text(phone_text)
    rc, out = invoke('plan')
    check('plan says the phone note is waiting for the quiet period', rc == 0 and 'PHONE EDIT WAITING alpha/docs/notes.md' in out and '3600 seconds' in out, out)
    before = head()
    rc, out = invoke('sync')
    check('the first run only notes the edit', rc == 0 and head() == before and mirror.read_text() == phone_text, out)
    rc, out = invoke('sync')
    check('an edit that has not stayed unchanged long enough keeps waiting', rc == 0 and head() == before and mirror.read_text() == phone_text, out)
    invoke('configure', '--edit-settle-seconds', '0')
    rc, out = invoke('plan')
    check('plan previews the note edit that would apply', rc == 0 and 'PHONE EDIT alpha: would apply text edits to 1 note(s): docs/notes.md' in out, out)
    rc, out = invoke('sync')
    _, log = sh(['git', 'log', '-1', '--format=%s%n%B'], cwd=alpha)
    check('a settled phone note edit is committed once', rc == 0 and head() != before and 'Phone added this paragraph.' in note.read_text(), out)
    check('the note edit has human provenance and counts only', 'Update notes from Obsidian' in log and 'Bridge-Ops: toggle=0 rename=0 text-edit=1' in log
          and 'Phone added' not in log and 'user-typed' in log and 'updated_by: human' in note.read_text()
          and 'Edit notes via Obsidian iCloud bridge' in note.read_text(), log)
    check('the stamped note returns to the vault', mirror.read_text() == note.read_text(), out)
    status = (vault / '_folderwise-sync-status.md').read_text()
    check('the status report counts the note edit', '| Edited |' in status and '| alpha |' in status and '| 0 | 0 | 1 |' in status, status)
    after = head()
    rc, out = invoke('sync')
    check('an unchanged run after a note edit creates no commit', rc == 0 and head() == after, out)
    base = mirror.read_text()

    # ** patterns reach notes in nested folders and whole trees.
    for rel in ('journal/2026/entry.md', 'archive/old.md'):
        deep = vault / 'alpha' / rel
        deep.write_text(deep.read_text().replace('## Change Log', 'Deep phone text.\n\n## Change Log'))
    invoke('plan')
    rc, out = invoke('plan')
    check('plan shows nested notes matched by ** patterns', 'PHONE EDIT WAITING alpha/journal/2026/entry.md' in out and 'PHONE EDIT WAITING alpha/archive/old.md' in out, out)
    invoke('sync')
    rc, out = invoke('sync')
    check('nested notes matched by ** patterns are imported', rc == 0 and 'Deep phone text.' in (alpha / 'journal/2026/entry.md').read_text()
          and 'Deep phone text.' in (alpha / 'archive/old.md').read_text(), out)
    base = mirror.read_text()

    # Front matter formatting rewritten by Obsidian is ignored; real changes and generated regions are protected.
    front = base.split('---\n', 2)[1]
    reformatted = base.replace(front, front.replace('status: draft', 'status:    draft'), 1).replace('Phone added this paragraph.', 'Phone edited again.')
    mirror.write_text(reformatted)
    invoke('sync')
    rc, out = invoke('sync')
    check('harmless front matter reformatting is ignored and the Mac front matter is kept', rc == 0 and 'Phone edited again.' in note.read_text()
          and 'status: draft' in note.read_text() and 'status:    draft' not in note.read_text(), out)
    base = mirror.read_text()
    pause_and_resolve('front matter changes are refused', base.replace('status: draft', 'status: archived'), 'front matter cannot be edited')
    pause_and_resolve('front matter cannot be removed from the phone', base.split('---\n', 2)[2], 'front matter cannot be added or removed')
    pause_and_resolve('broken front matter is refused', base.replace('title: Notes', 'title: [unclosed', 1), 'front matter cannot be edited')
    pause_and_resolve('the change log cannot be edited from the phone', base.replace('| human |', '| robot |', 1), 'generated blocks')
    pause_and_resolve('generated-block markers cannot be added', base.replace('Original paragraph.', 'Original paragraph. <!-- x:start -->'), 'markers cannot be added')
    pause_and_resolve('a note cannot be emptied', '', 'empties the note')
    pause_and_resolve('a note cannot lose more than half its lines', base.replace(lines, ''), 'removes more than half')
    pause_and_resolve('a very large paste is refused', base + 'x' * 300000, 'under 256 KB')
    pause_and_resolve('a huge rewrite is refused', base.replace('## Change Log', ''.join(f'Pasted {i}\n' for i in range(250)) + '\n## Change Log'), 'more than 200 lines')
    pause_and_resolve('a phone edit that fails project lint leaves the Mac note unchanged', base.replace('Original paragraph.', 'See [missing](missing-file.md).'), 'missing', runs=2)
    other_before = other.read_text()
    pause_and_resolve('notes outside the patterns are still refused', other_before.replace('## Change Log', 'Sneaky edit\n\n## Change Log'), 'only checkbox on/off changes are supported', path=other, key='alpha/docs/other.md')

    # The Mac and the phone both changed the note; only the Mac copy is kept until resolved.
    mirror.write_text(base.replace('Original paragraph.', 'Phone side change.'))
    invoke('sync')
    note.write_text(note.read_text().replace('Original paragraph.', 'Mac side change.'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Mac edit', cwd=alpha)
    commit(alpha, 'Mac edit')
    before = head()
    rc, out = invoke('sync')
    check('a note edited on both sides is paused with the file named', rc == 1 and 'changed on the Mac after it was exported' in out and head() == before
          and 'Phone side change.' in mirror.read_text(), out)
    invoke('resolve', 'alpha/docs/notes.md')
    rc, out = invoke('sync')
    check('resolve keeps the Mac version and resumes the project', rc == 0 and 'Mac side change.' in mirror.read_text() and 'Phone side change.' not in mirror.read_text(), out)
    base = mirror.read_text()

    # A copy saved from an older export would undo newer Mac text, so it is refused.
    older = base
    note.write_text(note.read_text().replace('Mac side change.', 'Newer Mac text.'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Newer Mac text', cwd=alpha)
    commit(alpha, 'Newer Mac text')
    invoke('sync')
    check('the vault copy follows the newer Mac text', 'Newer Mac text.' in mirror.read_text())
    base = mirror.read_text()
    pause_and_resolve('a phone copy saved from an older export is refused (its change log differs)', older.replace('Phone edited again.', 'Phone edited again, stale.'), 'generated blocks')

    # Task toggles in an editable note still use the task path; a toggle and a text edit of the same note conflict.
    mirror.write_text(base.replace('- [ ] A handwritten task', '- [x] A handwritten task'))
    rc, out = invoke('sync')
    _, log = sh(['git', 'log', '-1', '--format=%s'], cwd=alpha)
    check('toggles in an editable note stay ordinary task imports', rc == 0 and '- [x] A handwritten task' in note.read_text() and 'Update task completion' in log, out)
    base = mirror.read_text()
    mirror.write_text(base.replace('Phone edited again.', 'Phone edit plus a view toggle.'))
    invoke('sync')
    view.write_text(view.read_text().replace('- [x] A handwritten task', '- [ ] A handwritten task'))
    before = head()
    rc, out = invoke('sync')
    check('a note edit and a task change in the same note pause the project', rc == 1 and 'edited on the phone and one of its tasks' in out and head() == before, out)
    invoke('resolve', 'alpha/docs/notes.md')
    view.write_text(view.read_text().replace('- [ ] A handwritten task', '- [x] A handwritten task'))
    invoke('sync')
    base = mirror.read_text()

    # CRLF notes keep their line endings.
    local('docs_new.py', 'docs/notes-windows.md', '--type', 'plan', '--title', 'Windows', '--by', 'human', cwd=alpha)
    windows = alpha / 'docs/notes-windows.md'
    windows.write_bytes(windows.read_text().replace('## Change Log', 'Windows paragraph.\n\n## Change Log').replace('\n', '\r\n').encode())
    commit(alpha, 'Add CRLF note')
    invoke('sync')
    copy = vault / 'alpha/docs/notes-windows.md'
    copy.write_text(copy.read_text().replace('Windows paragraph.', 'Windows paragraph edited.'))
    invoke('sync')
    rc, out = invoke('sync')
    raw = windows.read_bytes()
    check('a note edit keeps CRLF line endings in the source', rc == 0 and b'Windows paragraph edited.\r\n' in raw and b'\n' not in raw.replace(b'\r\n', b''), out)

    # Projects without patterns are not affected, and the global switch turns the feature off again.
    beta_note = vault / 'beta/README.md'
    saved = beta_note.read_text()
    beta_note.write_text(saved + '\nUnlisted project edit.\n')
    rc, out = invoke('sync')
    check('a project without patterns still refuses note edits', rc == 1 and 'Paused projects: beta.' in (vault / '_folderwise-sync-status.md').read_text(), out)
    beta_note.write_text(saved)
    invoke('sync')
    invoke('configure', '--text-edits', 'off')
    mirror.write_text(base.replace('Phone edited again.', 'Edit while the switch is off.'))
    rc, out = invoke('sync')
    check('turning the bridge switch off refuses note edits again', rc == 1 and 'only checkbox' in out, out)
    mirror.write_text(base)
    rc, out = invoke('sync')
    check('and the project recovers when the edit is undone', rc == 0, out)


def s_ibridge_transient():
    """A brief iCloud file lock (EDEADLK) is retried quietly; the third consecutive failure is reported."""
    root = CTX['root'] / 'transient-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf = home / 'config.json'
    rc, out = sh(['uv', 'run', '--quiet', str(source / '_tools/new_project.py'), '--name', 'alpha', '--description', 'Fictional lock test', '--no-prompt'], cwd=source)
    rc, out = tool('icloud_bridge.py', '--config', conf, 'setup', '--source', source, '--vault', vault, '--notifications', 'off', '--no-schedule')
    check('transient sandbox is set up', rc == 0, out)
    code = ("import errno, sys\nsys.path.insert(0, %r)\nimport icloud_bridge as bridge\n"
            "def locked(*args, **kwargs):\n    raise OSError(errno.EDEADLK, 'Resource deadlock avoided')\n"
            "bridge.requests = locked\nsys.argv = ['icloud_bridge.py', '--config', %r, 'sync']\nsys.exit(bridge.main())\n") % (str(source / '_tools'), str(conf))
    files_before = sorted(p.relative_to(vault).as_posix() for p in vault.rglob('*') if p.is_file() and '.obsidian' not in p.parts)

    def locked_run():
        return sh(['uv', 'run', '--quiet', '--with', 'pyyaml', '--with', 'tzdata', 'python', '-c', code], cwd=source)

    for number in (1, 2):
        rc, out = locked_run()
        check(f'a brief iCloud lock is deferred quietly (run {number})', rc == 0 and 'Deferred: iCloud is busy' in out
              and json.loads((home / 'last-run.json').read_text()).get('deferred') == number, out)
    rc, out = locked_run()
    check('the third consecutive lock failure is reported', rc == 1 and 'Resource deadlock avoided' in out, out)
    check('a locked run never removes exported files', sorted(p.relative_to(vault).as_posix() for p in vault.rglob('*') if p.is_file() and '.obsidian' not in p.parts) == files_before)
    rc, out = tool('icloud_bridge.py', '--config', conf, 'sync')
    check('a normal run clears the deferral counter', rc == 0 and 'deferred' not in json.loads((home / 'last-run.json').read_text()), out)


def s_ibridge_status():
    """The status report is the source of truth. A mocked transport (plain file copies between the Mac source and the vault,
    standing in for iCloud) drives every outcome, and each one is asserted in the report, the CLI output and the last-run record."""
    root = CTX['root'] / 'status-sandbox'
    source, vault, home = root / 'source', root / 'vault', root / 'state'
    source.mkdir(parents=True)
    for name in ('_tools', '_template'):
        shutil.copytree(CTX['root'] / name, source / name, ignore=shutil.ignore_patterns('__pycache__'))
    conf, status_file = home / 'config.json', vault / '_folderwise-sync-status.md'
    fake = root / 'fakebin'
    fake.mkdir()
    for executable in ('open', 'codesign', 'launchctl'):
        (fake / executable).write_text('#!/bin/sh\nexit 0\n')
        (fake / executable).chmod(0o755)
    (fake / 'open').write_text('#!/bin/sh\ncat "' + str(home / 'notification-message.txt') + '" >> "' + str(root / 'banners') + '"\necho >> "' + str(root / 'banners') + '"\nexit 0\n')
    (fake / 'osacompile').write_text('#!' + sys.executable + '\nimport pathlib,plistlib,sys\np=pathlib.Path(sys.argv[2])/"Contents"\n(p/"Resources").mkdir(parents=True)\n(p/"Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"applet"}))\n(p/"Resources/main.scpt").write_bytes(pathlib.Path(sys.argv[3]).read_bytes())\n')
    (fake / 'osacompile').chmod(0o755)

    def invoke(*args, extra=None):
        return tool('icloud_bridge.py', '--config', conf, *args, env={'PATH': str(fake) + os.pathsep + os.environ['PATH'], **(extra or {})})

    def local(name, *args, cwd=None):
        return sh(['uv', 'run', '--quiet', str(source / '_tools' / name), *map(str, args)], cwd=cwd or source)

    def commit(project, message):
        sh(['git', 'add', '-A'], cwd=project)
        return sh(['git', 'commit', '-qm', message], cwd=project)

    def banners():
        return (root / 'banners').read_text() if (root / 'banners').exists() else ''

    def section(text, title):
        m = re.search(r'^## ' + re.escape(title) + r'\n\n(.*?)(?=\n## |\Z)', text, re.S | re.M)
        return m[1].strip() if m else None

    def bullets(text):
        return [line[2:] for line in (section(text, 'Issues') or '').splitlines() if line.startswith('- ')]

    def observe(label, rc_expected, issues=(), present=(), absent=(), extra=None, command='sync'):
        """Run one sync and judge it by its report: issues, sections, consistency with the CLI and last-run record, and privacy."""
        rc, out = invoke(command, extra=extra)
        text = status_file.read_text()
        listed = bullets(text)
        problems = []
        if rc != rc_expected:
            problems.append(f'rc {rc} != {rc_expected}')
        if rc_expected == 0 and section(text, 'Issues') != 'None.':
            problems.append('Issues is not None.')
        problems += [f'issue missing: {s}' for s in issues if not any(s in b for b in listed)]
        problems += [f'report missing: {s}' for s in present if s not in text]
        problems += [f'report has: {s}' for s in absent if s in text]
        if command == 'sync' and listed != [line[6:] for line in out.splitlines() if line.startswith('ERROR ')]:
            problems.append('report issues differ from the ERROR lines on the CLI')
        if command == 'sync' and json.loads((home / 'last-run.json').read_text())['issues'] != listed:
            problems.append('report issues differ from last-run.json')
        problems += [f'report leaks {s}' for s in ('PHONE-SECRET', str(source), str(home)) if s in text]
        check(label, not problems, out + '\n' + text + '\nPROBLEMS: ' + '; '.join(problems))
        return out, text

    for name in ('alpha', 'beta', 'gamma'):
        rc, out = local('new_project.py', '--name', name, '--description', 'Fictional status test', '--no-prompt')
        check('status sandbox creates ' + name, rc == 0, out)
        local('docs_new.py', 'docs/checklist.md', '--type', 'plan', '--title', 'Checklist', '--by', 'human', cwd=source / name)
    alpha, beta, gamma = (source / n for n in ('alpha', 'beta', 'gamma'))
    commit(gamma, 'Add checklist')
    local('docs_new.py', 'docs/notes.md', '--type', 'plan', '--title', 'Notes', '--by', 'human', cwd=alpha)
    doc = alpha / 'docs/checklist.md'
    doc.write_text(doc.read_text().replace('## Change Log', '- [ ] A1 task\n- [ ] A2 task\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add tasks', cwd=alpha)
    notes = alpha / 'docs/notes.md'
    notes.write_text(notes.read_text().replace('## Change Log', 'Original paragraph.\n\n## Change Log'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Add body', cwd=alpha)
    (alpha / '.docs.yaml').write_text((alpha / '.docs.yaml').read_text() + '\nfolderwise-ibridgerename: true\nfolderwise-ibridgeedit:\n  - "docs/notes*.md"\n')
    commit(alpha, 'Add tasks, note and settings')
    (beta / 'data').mkdir(exist_ok=True)
    (beta / 'data/tasks.csv').write_text('id,title,done\nrow-1,B1 task,false\n')
    (beta / 'scripts').mkdir(exist_ok=True)
    (beta / 'scripts/adapter.py').write_text(
        "import csv,json,os,sys\nfrom pathlib import Path\nop=sys.argv[1]\n"
        "if os.environ.get('BRIDGE_FAIL')==op:\n print('adapter '+op+' refused',file=sys.stderr);sys.exit(1)\n"
        "p=Path('data/tasks.csv');rows=list(csv.DictReader(p.open()))\n"
        "if op=='list':\n print(json.dumps([dict(id=r['id'],title=r['title'],checked=r['done']=='true',path='docs/checklist.md') for r in rows]))\n"
        "elif op=='apply':\n changes={c['id']:c['checked'] for c in json.load(sys.stdin)}\n for r in rows:\n  if r['id'] in changes: r['done']='true' if changes[r['id']] else 'false'\n"
        " with p.open('w',newline='') as f:\n  w=csv.DictWriter(f,fieldnames=['id','title','done']);w.writeheader();w.writerows(rows)\n"
        " note=Path('docs/checklist.md');text=note.read_text();s=text.index('<!-- tasks:start -->');e=text.index('<!-- tasks:end -->')\n"
        " note.write_text(text[:s]+'<!-- tasks:start -->\\n'+''.join('- [ ] '+r['title']+'\\n' for r in rows if r['done']=='false')+text[e:])\n")
    doc = beta / 'docs/checklist.md'
    doc.write_text(doc.read_text().replace('## Change Log', '<!-- tasks:start -->\n- [ ] B1 task\n<!-- tasks:end -->\n\n## Change Log'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Add generated task', cwd=beta)
    commit(beta, 'Add adapter')
    rc, out = tool('icloud_bridge.py', '--config', conf, 'setup', '--source', source, '--vault', vault, '--notifications', 'errors', '--no-schedule',
                   env={'PATH': str(fake) + os.pathsep + os.environ['PATH']})
    check('status sandbox setup reports the missing adapter', rc == 0, out)
    cfg = json.loads(conf.read_text())
    cfg['adapters'] = {'beta': [sys.executable, 'scripts/adapter.py']}
    conf.write_text(json.dumps(cfg))
    invoke('configure', '--text-edits', 'on', '--edit-settle-seconds', '0')
    views = {n: vault / f'_Folderwise Tasks/{n}.md' for n in ('alpha', 'beta', 'gamma')}
    mirror = vault / 'alpha/docs/notes.md'

    def heads():
        return {n: sh(['git', 'rev-parse', 'HEAD'], cwd=source / n)[1] for n in ('alpha', 'beta', 'gamma')}

    def flip(text, title):
        """Toggle the checkbox of the task with this title in a generated view."""
        return re.sub(r'- \[( |x)\] ' + re.escape(title), lambda m: '- [' + ('x' if m[1] == ' ' else ' ') + '] ' + title, text, count=1)

    def phone(path, edit):
        """Mock transport, phone to Mac: the phone saves a file and iCloud delivers it into the vault."""
        path.write_text(edit(path.read_text()))

    # --- success paths -------------------------------------------------------------------------------------------
    out, text = observe('a clean export reports no issues and its sizes', 0, present=['# Folderwise sync status', 'Mode: **full**', 'Estimated managed export', '## Omitted files'],
                        absent=['Paused projects', 'Phone edits not applied', 'Recent imports', 'iCloud conflict copies'])
    check('the status report is a bridge-owned file with a recorded hash', json.loads((home / 'report.json').read_text())['hash'] == hashlib.sha256(status_file.read_bytes()).hexdigest())
    stamp = status_file.stat().st_mtime_ns
    observe('an unchanged run leaves the report byte-for-byte alone', 0)
    check('and does not rewrite it', status_file.stat().st_mtime_ns == stamp)
    observe('plan never changes the report', 0, command='plan')
    check('plan left the report alone', status_file.stat().st_mtime_ns == stamp)
    phone(views['alpha'], lambda s: s.replace('- [ ] A1 task', '- [x] A1 task'))
    out, text = observe('a toggle import is listed', 0, present=['## Recent imports', '| alpha |'])
    check('the listed commit is the import commit', sh(['git', 'rev-parse', '--short', 'HEAD'], cwd=alpha)[1].strip() in text, text)
    phone(views['alpha'], lambda s: s.replace('A2 task', 'A2 renamed'))
    out, text = observe('a rename import adds a second row', 0, present=['| 0 | 1 | 0 |'])
    phone(mirror, lambda s: s.replace('Original paragraph.', 'Original paragraph.\n\nPhone note edit.'))
    out, text = observe('a note edit waiting out its quiet period is listed, not failed', 0, present=['## Phone edits waiting', '- alpha/docs/notes.md'])
    out, text = observe('a settled note edit is imported and counted', 0, present=['| 0 | 0 | 1 |'], absent=['Phone edits waiting'])
    phone(views['beta'], lambda s: s.replace('- [ ] B1 task', '- [x] B1 task'))
    observe('an adapter toggle import is listed', 0, present=['| beta |'])
    observe('a lean mode export lists the files it leaves out and why', 0, command='plan')
    invoke('configure', '--mode', 'lean')
    out, text = observe('lean mode lists excluded files with the reason', 0, present=['excluded by lean mode', 'beta/data/tasks.csv'])
    invoke('configure', '--mode', 'full')
    img = alpha / 'docs/pic.png'
    img.write_bytes(b'12345678')
    notes.write_text(notes.read_text().replace('Original paragraph.', '![pic](pic.png)\n\nOriginal paragraph.'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Add images', cwd=alpha)
    commit(alpha, 'Add images')
    invoke('configure', '--mode', 'lean', '--max-image-bytes', '4')
    out, text = observe('image budget omissions are listed with sizes and reasons', 0, present=['exceeds per-image limit', 'alpha/docs/pic.png'])
    alerts = banners().count('needs attention')
    check('an actionable omission alerts', alerts >= 1, banners())
    observe('the same omission is not announced again', 0)
    check('and does not add an alert', banners().count('needs attention') == alerts, banners())
    invoke('configure', '--mode', 'full', '--unlimited-images')
    observe('lifting the limit clears the omission', 0, absent=['exceeds per-image limit'])

    # --- phone edits that cannot be applied ---------------------------------------------------------------------
    before = heads()
    phone(views['alpha'], lambda s: s + 'PHONE-SECRET new line\n')
    out, text = observe('an added phone line is rejected, restored and named without echoing the text', 0, present=['## Phone edits not applied', '_Folderwise Tasks/alpha.md', 'number of lines changed'], absent=['PHONE-SECRET'])
    check('the rejected view is restored and nothing was committed', 'PHONE-SECRET' not in views['alpha'].read_text() and heads() == before)
    check('rejected phone edits send an alert', banners().count('needs attention') == alerts + 1, banners())
    phone(views['alpha'], lambda s: re.sub(r'(A1 task[^\n]*\))', r'\1 PHONE-SECRET', s, count=1))
    observe('typing after a task link is rejected', 0, present=['keep the checkbox and the trailing source link'], absent=['PHONE-SECRET'])
    phone(views['alpha'], lambda s: s.replace('A2 renamed', 'A2 [x](http://example.com) PHONE-SECRET'))
    observe('a link typed into a title is rejected with its reason', 0, present=['links or images'], absent=['PHONE-SECRET'])
    phone(views['gamma'], lambda s: s.replace('gamma tasks', 'gamma tasks PHONE-SECRET'))
    observe('a title edit is refused when renames are off for the project', 0, present=['_Folderwise Tasks/gamma.md'], absent=['PHONE-SECRET'])
    phone(views['alpha'], lambda s: s.replace('A1 task', 'TMPX').replace('A2 renamed', 'A1 task').replace('TMPX', 'A2 renamed'))
    observe('swapped titles are refused', 0, present=['already used by another task'])

    # --- project problems pause only that project ---------------------------------------------------------------
    (alpha / 'scratch.txt').write_text('uncommitted\n')
    phone(views['alpha'], lambda s: flip(s, 'A1 task'))
    out, text = observe('a dirty project is paused and named', 1, issues=['uncommitted Mac changes'], present=['Paused projects: alpha.', 'other projects keep syncing'])
    alerts = banners().count('needs attention')
    observe('the same pause is not announced again', 1, issues=['uncommitted Mac changes'])
    check('and does not add an alert', banners().count('needs attention') == alerts, banners())
    (alpha / 'scratch.txt').unlink()
    observe('fixing the cause clears the pause', 0, absent=['Paused projects'])
    hook = alpha / '.git/hooks/pre-commit'
    original_hook = hook.read_text()
    hook.write_text('#!/bin/sh\necho intentional hook rejection >&2\nexit 1\n')
    phone(views['alpha'], lambda s: flip(s, 'A1 task'))
    observe('a failing Git hook pauses the project and shows the hook text', 1, issues=['intentional hook rejection'], present=['Paused projects: alpha.'])
    hook.write_text(original_hook)
    observe('repairing the hook resumes and imports', 0, present=['| alpha |'])
    phone(views['beta'], lambda s: s.replace('- [x] B1 task', '- [ ] B1 task'))
    observe('an adapter apply failure pauses only the adapter project', 1, issues=['adapter apply refused'], present=['Paused projects: beta.'], extra={'BRIDGE_FAIL': 'apply'})
    observe('an adapter validate failure pauses only the adapter project', 1, issues=['adapter validate refused'], present=['Paused projects: beta.'], extra={'BRIDGE_FAIL': 'validate'})
    out, text = observe('an adapter list failure pauses the project and keeps its export', 1, issues=['adapter list refused'], present=['Paused projects: beta.'], extra={'BRIDGE_FAIL': 'list'})
    check('a paused project keeps its previous vault files', (vault / 'beta/docs/checklist.md').exists() and views['beta'].exists())
    observe('the adapter project imports once the adapter works again', 0, absent=['Paused projects'])
    phone(mirror, lambda s: s.replace('Original paragraph.', 'Edited ' + 'line\n' * 250 + 'Original paragraph.'))
    observe('an over-large note edit is refused and the project paused', 1, issues=['alpha/docs/notes.md', 'more than 200 lines'], present=['Paused projects: alpha.'])
    invoke('resolve', 'alpha/docs/notes.md')
    observe('resolve restores the Mac note and the project resumes', 0, absent=['Paused projects'])
    phone(mirror, lambda s: s.replace('status: draft', 'status: archived'))
    observe('a front matter edit is refused with the file named', 1, issues=['alpha/docs/notes.md', 'front matter'], present=['Paused projects: alpha.'])
    invoke('resolve', 'alpha/docs/notes.md')
    phone(views['alpha'], lambda s: s.replace('- [ ] A1 task', '- [x] A1 task'))
    notes.write_text(notes.read_text().replace('Original paragraph.', 'Mac side text.'))
    local('docs_stamp.py', 'docs/notes.md', '--by', 'human', '--summary', 'Mac edit', cwd=alpha)
    commit(alpha, 'Mac edit while the phone edits')
    observe('a Mac change to a note with no pending phone edit simply exports', 0)
    # A view toggle for a task renamed on the Mac is a recorded rejection, not a pause.
    doc = alpha / 'docs/checklist.md'
    doc.write_text(doc.read_text().replace('A1 task', 'A1 mac'))
    local('docs_stamp.py', 'docs/checklist.md', '--by', 'human', '--summary', 'Rename on Mac', cwd=alpha)
    commit(alpha, 'Rename on Mac')
    phone(views['alpha'], lambda s: flip(s, 'A1 task'))
    observe('a pending toggle for a task renamed on the Mac is rejected with that reason', 0, present=['changed or disappeared on Mac'])

    # --- bridge-wide problems freeze every export ---------------------------------------------------------------
    dashboard = vault / 'Tasks.md'
    saved = dashboard.read_text()
    local('docs_new.py', 'docs/late.md', '--type', 'plan', '--title', 'Late', '--by', 'human', cwd=gamma)
    commit(gamma, 'Add late doc')
    dashboard.write_text(saved + 'PHONE-SECRET dashboard edit\n')
    out, text = observe('an edit to the generated dashboard freezes every export', 1, issues=['Tasks.md: only checkbox on/off changes are supported'], absent=['Paused projects'])
    check('a frozen run exports nothing new', not (vault / 'gamma/docs/late.md').exists())
    dashboard.write_text(saved)
    observe('restoring the dashboard unfreezes the export', 0)
    check('and the held-back document arrives', (vault / 'gamma/docs/late.md').exists())
    collision = vault / 'gamma/docs/collide.md'
    collision.write_text('unrelated vault file\n')
    local('docs_new.py', 'docs/collide.md', '--type', 'plan', '--title', 'Collide', '--by', 'human', cwd=gamma)
    commit(gamma, 'Add colliding doc')
    observe('a new source file colliding with an unowned vault file pauses its project', 1, issues=['gamma/docs/collide.md: unexpected vault edit or unowned file'], present=['Paused projects: gamma.'])
    check('the colliding vault file is preserved', collision.read_text() == 'unrelated vault file\n')
    collision.unlink()
    observe('removing the collision resumes the project', 0, absent=['Paused projects'])
    (home / 'export.json').write_text(json.dumps({'writes': {'gamma/docs/late.md': {'before': 'a' * 64, 'after': 'b' * 64, 'data': ''}}, 'removes': {}, 'state': {'files': {}, 'tasks': {}}}))
    observe('an interrupted export journal that no longer matches is reported', 1, issues=['changed during interrupted export'])
    (home / 'export.json').unlink()
    observe('removing the journal recovers', 0)
    victim = vault / 'gamma/README.md'
    saved_readme = victim.read_text()
    victim.unlink()
    victim.symlink_to(vault / 'Tasks.md')
    observe('a symlink in the vault is refused and reported', 1, issues=['symlink not supported'])
    victim.unlink()
    victim.write_text(saved_readme)
    observe('replacing the symlink with the file recovers', 0)
    victim.unlink()
    victim.mkdir()
    observe('a directory masquerading as an exported file is reported', 1, issues=['expected a file'])
    victim.rmdir()
    observe('removing the directory restores the export', 0)
    check('the exported file is back', victim.exists())
    invoke('disable', 'alpha')
    commit(alpha, 'Disable bridge for alpha')
    phone(views['alpha'], lambda s: flip(s, 'A1 mac'))
    observe('disabling a project with a pending phone edit freezes everything with that reason', 1, issues=['disabled project has pending phone edits'])
    invoke('enable', 'alpha')
    commit(alpha, 'Enable bridge for alpha')
    observe('enabling the project again imports the preserved edit', 0, absent=['disabled project'])

    # --- iCloud artefacts (mocked) -------------------------------------------------------------------------------
    (vault / 'alpha/docs/notes 2.md').write_text('iCloud conflict copy\n')
    (vault / 'alpha/docs/checklist (conflicted copy).md').write_text('another copy\n')
    out, text = observe('mock iCloud conflict copies are listed and never imported', 0, present=['## iCloud conflict copies', 'alpha/docs/notes 2.md', 'alpha/docs/checklist (conflicted copy).md'])
    check('conflict copies are left in place for the user', (vault / 'alpha/docs/notes 2.md').read_text() == 'iCloud conflict copy\n')
    (vault / 'alpha/docs/notes 2.md').unlink()
    (vault / 'alpha/docs/checklist (conflicted copy).md').unlink()
    observe('deleting the copies clears the section', 0, absent=['iCloud conflict copies'])

    # --- status report ownership ---------------------------------------------------------------------------------
    saved_report = status_file.read_text()
    status_file.write_text('User-owned notes\n')
    rc, out = invoke('sync')
    check('an edited status report is never overwritten and the CLI says why', rc == 1 and 'has unowned edits' in out and status_file.read_text() == 'User-owned notes\n', out)
    status_file.write_text(saved_report)
    observe('restoring the report resumes normal syncing', 0)
    legacy = vault / 'Bridge Status.md'
    legacy.write_text('old report with my notes\n')
    observe('an unowned legacy report is flagged in the report and preserved', 1, issues=['Bridge Status.md: legacy report has unowned edits'])
    legacy.unlink()
    observe('removing the legacy report clears the warning', 0)

    # --- doctor, source and config -------------------------------------------------------------------------------
    rc, out = invoke('doctor')
    check('doctor agrees with a clean report', rc == 0, out)
    cfg = json.loads(conf.read_text())
    good = dict(cfg)
    cfg['source'] = str(root / 'missing-source')
    conf.write_text(json.dumps(cfg))
    rc, out = invoke('sync')
    check('an unavailable source is reported in the status file and removes nothing', rc == 1 and 'source directory is unavailable' in status_file.read_text()
          and views['alpha'].exists() and (vault / 'alpha/docs/notes.md').exists(), out)
    conf.write_text(json.dumps(good))
    observe('restoring the source recovers', 0)
    cfg['notifications'] = 'sometimes'
    conf.write_text(json.dumps(cfg))
    rc, out = invoke('sync')
    check('an invalid bridge config stops before any export and says so on the CLI', rc == 1 and 'invalid mode or notification setting' in out, out)
    conf.write_text(json.dumps(good))
    phone(views['alpha'], lambda s: s + 'PHONE-SECRET again\n')
    observe('doctor reports the last issue state', 0, command='sync')
    rc, out = invoke('doctor')
    check('doctor stays healthy after handled rejections', rc == 0, out)
    check('alerts carry no task or document text', 'PHONE-SECRET' not in banners() and all(l.startswith('Folderwise bridge needs attention.') for l in banners().splitlines() if l.strip()), banners())


def s_ibridge_setup():
    """Verify explicit vault setup, persistent project defaults, and safe uninstall."""
    root=CTX['root']/'obsidian-setup-sandbox';source=root/'source';source.mkdir(parents=True)
    vault,home=root/'cloud-vault',root/'state';config=home/'config.json'
    for name in ['_tools','_template']:
        shutil.copytree(CTX['root']/name,source/name,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['.gitignore','.gitattributes','AGENTS.md','uv.toml']:
        shutil.copy2(SRC_TOOLS.parent/name,source/name)
    for name in ['README.md','LICENSE']:(source/name).write_text('Fictional setup root\n')
    sh(['git','init','-q','-b','main'],cwd=source);sh(['git','add','-A'],cwd=source);sh(['git','commit','-qm','Fixture framework'],cwd=source)
    sh(['git','remote','add','origin',str(source)],cwd=source)
    fake=root/'fakebin';fake.mkdir()
    for name in ['open','codesign','launchctl']:
        p=fake/name;p.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(root/'os-calls')+'"\nexit 0\n');p.chmod(0o755)
    opener=fake/'open'
    opener.write_text(opener.read_text().replace('exit 0', 'cat "'+str(home/'notification-message.txt')+'" > "'+str(root/'notification-body')+'"\ncat "'+str(home/'notification-message.txt')+'" >> "'+str(root/'os-calls')+'"\nexit 0'))
    compiler=fake/'osacompile'
    compiler.write_text('#!'+sys.executable+'\nimport pathlib,plistlib,sys\np=pathlib.Path(sys.argv[2])/"Contents"\n(p/"Resources").mkdir(parents=True)\n(p/"Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"applet","CFBundleIconName":"applet"}))\n(p/"Resources/Assets.car").write_bytes(b"compiler icon catalog")\n(p/"Resources/main.scpt").write_bytes(pathlib.Path(sys.argv[3]).read_bytes())\n')
    compiler.chmod(0o755)
    env={'PATH':str(fake)+os.pathsep+os.environ['PATH'],'HOME':str(root/'fake-home')}

    def local(name,*args):
        return sh(['uv','run','--quiet',str(source/'_tools'/name),*map(str,args)],cwd=source,env=env)

    def invoke(*args):
        return local('icloud_bridge.py','--config',config,*args)

    def create(name,*extra):
        return local('new_project.py','--name',name,'--description','Fictional opt-in lifecycle','--no-prompt',*extra)

    rc,out=create('before');before=source/'before'
    check('fresh framework creates projects with bridge sync disabled',rc==0 and 'folderwise-ibridgesync:' not in '\n'.join(x for x in (before/'.docs.yaml').read_text().splitlines() if not x.startswith('#')),out)
    check('fresh framework does not create a root vault',not (source/'.obsidian').exists() and not (source/'.folderwise-obsidian.json').exists())
    create('explicit-off','--icloud-disabled')
    setup=['setup','--source',source,'--vault',vault,'--notifications','off','--no-schedule']
    rc,out=invoke(*setup,'--dry-run')
    check('setup preview does not create vaults or enable project defaults',rc==0 and 'Preview export:' in out and 'before/README.md' in out and 'explicit-off/README.md' not in out and not vault.exists() and not config.exists()
          and not (source/'.obsidian').exists() and 'folderwise-ibridgesync: true\n' not in (before/'.docs.yaml').read_text(),out)
    # Existing settings and device layout are always user-owned.
    (source/'.obsidian').mkdir();(source/'.obsidian/app.json').write_text('{"userPreference":true}\n')
    (source/'.obsidian/workspace.json').write_text('{"deviceLayout":"keep"}\n')
    rc,out=invoke(*setup)
    check('setup creates parent/iCloud vaults and enrolls existing projects',rc==0 and (vault/'.obsidian/app.json').exists()
          and 'folderwise-ibridgesync: true\n' in (before/'.docs.yaml').read_text(),out)
    check('setup preserves deliberate existing project opt-outs','folderwise-ibridgesync: false' in (source/'explicit-off/.docs.yaml').read_text())
    check('setup enrollment leaves source project clean',sh(['git','status','--porcelain'],cwd=before)[1]=='')
    check('setup persists future-project opt-in',json.loads((source/'.folderwise-obsidian.json').read_text())['enabled'] is True)
    check('setup preserves existing settings and workspace',(source/'.obsidian/app.json').read_text()=='{"userPreference":true}\n'
          and (source/'.obsidian/workspace.json').read_text()=='{"deviceLayout":"keep"}\n')
    core=json.loads((vault/'.obsidian/core-plugins.json').read_text())
    tasks=json.loads((vault/'.obsidian/plugins/obsidian-tasks-plugin/data.json').read_text())
    dv=json.loads((vault/'.obsidian/plugins/dataview/data.json').read_text())
    check('reviewed defaults cover core navigation and boolean task behavior',core['graph'] and core['backlink']
          and not core['sync'] and not tasks['setDoneDate'] and not tasks['setCancelledDate']
          and not dv['enableDataviewJs'] and not dv['taskCompletionTracking'])
    check('defaults omit plugin executables and device workspaces',not (vault/'.obsidian/workspace.json').exists()
          and not (vault/'.obsidian/plugins/obsidian-tasks-plugin/main.js').exists())
    rc,out=create('after')
    check('separate new_project process inherits enabled bridge default',rc==0 and 'folderwise-ibridgesync: true\n' in (source/'after/.docs.yaml').read_text(),out)
    rc,out=create('after-off','--icloud-disabled')
    check('per-project flag still overrides an installed bridge',rc==0 and 'folderwise-ibridgesync: false\n' in (source/'after-off/.docs.yaml').read_text(),out)
    rc,out=invoke('plan');check('new opted-in project appears without re-running setup',rc==0 and 'after/README.md' in out and 'after-off/README.md' not in out,out)
    (vault/'.obsidian/graph.json').write_text('{"customGraph":true}\n')
    rc,out=invoke('vault-init');check('repeat vault initialization preserves customization',rc==0 and (vault/'.obsidian/graph.json').read_text()=='{"customGraph":true}\n',out)
    if sys.platform=='darwin':
        rc,out=invoke('schedule-enable');check('setup lifecycle can schedule against fake OS services',rc==0,out)
    cli=source/'_tools/framework_checkout.py'
    rc,out=sh([sys.executable,str(cli),'--minimal','--omit','README.md','--remove-obsidian','--dry-run'],cwd=source,env=env)
    check('checkout helper previews removal without uninstalling',rc==0 and (source/'.folderwise-obsidian.json').exists(),out)
    rc,out=sh([sys.executable,str(cli),'--minimal','--omit','README.md','--remove-obsidian'],cwd=source,env=env)
    check('checkout helper can remove README and Obsidian integration together',rc==0 and not (source/'README.md').exists()
          and not (source/'.folderwise-obsidian.json').exists() and not json.loads(config.read_text())['enabled'],out)
    check('uninstall removes unchanged owned defaults but preserves customized files',not (vault/'.obsidian/app.json').exists()
          and (vault/'.obsidian/graph.json').read_text()=='{"customGraph":true}\n'
          and (source/'.obsidian/app.json').read_text()=='{"userPreference":true}\n'
          and (source/'.obsidian/workspace.json').exists())
    check('uninstall preserves project documents and eligibility flags',(before/'README.md').exists() and 'folderwise-ibridgesync: true\n' in (before/'.docs.yaml').read_text())
    rc,out=create('after-uninstall')
    check('new projects default to bridge disabled after uninstall',rc==0 and 'folderwise-ibridgesync: true\n' not in (source/'after-uninstall/.docs.yaml').read_text(),out)
    rc,out=invoke('sync');check('uninstalled bridge cannot continue syncing',rc==1 and 'uninstalled' in out,out)
    if sys.platform=='darwin':
        check('uninstall stops the owned scheduled job',not json.loads((home/'schedule.json').read_text())['enabled'])
    rc,out=invoke(*setup);check('reinstall restores the persistent future-project default',rc==0 and json.loads((source/'.folderwise-obsidian.json').read_text())['enabled'],out)
    # A hook-rejected enrollment never mutates live project state or enables future defaults.
    invoke('uninstall');create('hook-blocked')
    hook=source/'hook-blocked/.git/hooks/pre-commit';original=hook.read_text();hook.write_text('#!/bin/sh\necho setup hook blocked >&2\nexit 1\n')
    rc,out=invoke(*setup)
    check('setup hook rejection preserves clean source and leaves integration disabled',rc==1 and 'setup hook blocked' in out
          and not json.loads((source/'.folderwise-obsidian.json').read_text())['enabled']
          and sh(['git','status','--porcelain'],cwd=source/'hook-blocked')[1]=='',out)
    hook.write_text(original);rc,out=invoke(*setup);check('incomplete setup can retry after hook repair',rc==0,out)
    invoke('uninstall')
    if sys.platform=='darwin':
        # HOME points at the test sandbox; even the plist path is isolated.
        rc,out=invoke('setup','--source',source,'--vault',vault,'--notifications','errors')
        calls=(root/'os-calls').read_text()
        check('one setup command initializes sync and announces the schedule',rc==0 and 'scheduled every 5 minutes' in calls
              and (root/'fake-home/Library/LaunchAgents/org.folderwise.ibridge.plist').exists(),out)
        invoke('uninstall')
    # Failed initial sync must not activate the persistent creation default.
    cloud_readme=vault/'before/README.md';saved=cloud_readme.read_text();cloud_readme.write_text(saved+'Unsupported phone edit\n')
    rc,out=invoke(*setup)
    check('failed setup sync leaves future projects disabled',rc==1 and not json.loads(config.read_text())['enabled']
          and not json.loads((source/'.folderwise-obsidian.json').read_text())['enabled'],out)
    rc,out=create('after-failed-setup')
    check('new process stays opted out after an incomplete setup',rc==0 and 'folderwise-ibridgesync: true\n' not in (source/'after-failed-setup/.docs.yaml').read_text(),out)
    cloud_readme.write_text(saved);rc,out=invoke(*setup);check('setup resumes after resolving a pending vault edit',rc==0,out)
    rc,out=local('icloud_bridge.py','--config',home/'other.json',*setup)
    check('setup refuses another configuration taking over the parent vault',rc==1 and 'another bridge configuration' in out,out)
    assets=source/'_tools/obsidian_defaults';assets.rename(source/'_tools/saved-defaults')
    rc,out=invoke('vault-init');check('missing defaults payload is diagnosed',rc==1 and 'defaults are missing' in out,out)
    (source/'_tools/saved-defaults').rename(assets)
    invoke('uninstall');create('dirty-enrollment')
    dirty=source/'dirty-enrollment/README.md';saved=dirty.read_text();dirty.write_text(saved+'Uncommitted change\n')
    rc,out=invoke(*setup)
    check('setup preflight protects existing source work',rc==1 and 'commit local changes before setup' in out
          and dirty.read_text().endswith('Uncommitted change\n'),out)
    dirty.write_text(saved)
    create('missing-hook');(source/'missing-hook/.git/hooks/pre-commit').unlink()
    rc,out=invoke(*setup);check('setup enrollment still validates through a framework hook when one is missing',rc==0,out)
    manifest=home/'vault-defaults.json';saved=manifest.read_text();record=json.loads(saved);record[str(root/'unrelated-vault')]={};manifest.write_text(json.dumps(record))
    rc,out=invoke('uninstall');check('uninstall refuses ownership records outside its configured vaults',rc==1 and 'unrelated vault' in out,out)
    manifest.write_text(saved);invoke('uninstall')
    rc,out=sh([sys.executable,str(cli),'--minimal','--remove-obsidian'],cwd=source,env=env)
    check('checkout removal is safe when integration is already uninstalled',rc==0 and 'No configured Obsidian' in out,out)

    profile=source/'.folderwise-obsidian.json';profile.write_text('[]')
    rc,out=create('bad-profile')
    check('new_project rejects invalid persistent profiles before creating files',rc==2 and not (source/'bad-profile').exists(),out)
    profile.unlink()


SECTIONS = [
    ("create", s_create), ("new_doc", s_new_doc_and_index), ("stamp", s_stamp_and_hook), ("hook", s_hook_fail_closed),
    ("lint", s_lint_rules), ("timezone", s_timezone), ("links", s_links), ("staged_source", s_staged_source), ("markdown_fences", s_markdown_fences), ("toc", s_toc), ("mv", s_mv),
    ("tables", s_tables), ("stale", s_stale_index_recent), ("sync", s_sync),
    ("ibridge", s_ibridge), ("ibridge_rename", s_ibridge_rename), ("ibridge_isolation", s_ibridge_isolation), ("ibridge_notes", s_ibridge_notes), ("ibridge_transient", s_ibridge_transient), ("ibridge_status", s_ibridge_status), ("ibridge_setup", s_ibridge_setup), ("doctor", s_doctor), ("layout", s_layout), ("cli_errors", s_cli_errors), ("failure_paths", s_failure_paths), ("uv_cache", s_uv_cache),
    ("framework_checkout", s_framework_checkout), ("framework_index", s_framework_index), ("ci_allowlist", s_ci_allowlist),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", dest="keyword", help="run only sections whose name contains this")
    ap.add_argument("--keep", action="store_true", help="keep the temp folder")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="docs-selftest-")).resolve()
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(SRC_TOOLS, tmp / "_tools", ignore=ignore)
    shutil.copytree(SRC_TEMPLATE, tmp / "_template", ignore=ignore)
    CTX.update(root=tmp, tools=tmp / "_tools", proj=tmp / "proj")
    selected = [(n, f) for n, f in SECTIONS if not args.keyword or args.keyword in n]
    # later sections build on earlier ones, so the project is always created first
    if selected and selected[0][0] != "create":
        selected.insert(0, SECTIONS[0])
        selected.insert(1, SECTIONS[1])
    for name, fn in selected:
        print(f"[{name}]", flush=True)
        try:
            fn()
        except Exception as e:  # a crash in one section must not hide the others
            check(f"section {name} ran without crashing", False, repr(e))
    failed = [r for r in RESULTS if not r[0]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + ("" if not failed else f"; {len(failed)} FAILED"))
    if args.keep:
        print(f"kept: {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
