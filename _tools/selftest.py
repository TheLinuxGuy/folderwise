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
import json
import os
import re
import shlex
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


def public_documentation() -> list[tuple[str, str]]:
    """The landing README may link to a separate full command guide."""
    root = SRC_TOOLS.parent
    docs = [("README.md", (root / "README.md").read_text())]
    guide = root / "docs" / "guide.md"
    if guide.is_file():
        if not re.search(r'\]\(docs/guide\.md(?:#[^)]*)?\)', docs[0][1]):
            raise ValueError("README must link to docs/guide.md when the guide exists")
        docs.append(("docs/guide.md", guide.read_text()))
    return docs


def s_docs_coverage():
    """Every tool/setting must appear in public docs; root AGENTS.md lists the tools."""
    readme = "\n".join(text for _, text in public_documentation())
    agents = (SRC_TOOLS.parent / "AGENTS.md").read_text()
    for f in sorted(SRC_TOOLS.glob("*.py")):
        if f.stem in ("docslib", "docsextra"):
            continue
        check(f"public documentation covers {f.name}", f.name in readme)
        check(f"root AGENTS.md lists {f.name}", f.name in agents)
    keys = {"schema_version", "project", "description"}
    for f in SRC_TOOLS.glob("*.py"):
        keys |= set(re.findall(r'\bcfg(?:\.get\(|\[)"([a-z_]+)"', f.read_text()))
    for k in sorted(keys):
        check(f"public documentation covers the .docs.yaml setting '{k}'", f"`{k}`" in readme)


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
    for name in (".gitignore", "README.md", "AGENTS.md", "uv.toml"):
        shutil.copy2(SRC_TOOLS.parent / name, root / name)
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


def s_readme_commands():
    """Every command in the root README's fenced blocks must be pasteable: real tool, real flags, no <placeholders>,
    `cd` into this very folder, and in-page links that resolve."""
    root = SRC_TOOLS.parent.resolve()
    documents = public_documentation()
    landing = documents[0][1]
    readme = "\n".join(text for _, text in documents)
    helps: dict[tuple, str] = {}

    def help_of(name, sub=None):
        if (name, sub) not in helps:
            rc, out = sh(["uv", "run", "--quiet", str(SRC_TOOLS / name), *([sub] if sub else []), "--help"], cwd=root)
            helps[(name, sub)] = out
        return helps[(name, sub)]

    seen_flags, n_cmds = set(), 0
    for block in re.findall(r"```(?:bash|sh|zsh)\n(.*?)```", readme, re.S):
        for raw in block.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            try:
                toks = shlex.split(raw, comments=True)
            except ValueError as e:
                check(f"README command parses: {raw[:60]}", False, str(e))
                continue
            for i, t in enumerate(toks):  # `cd <path>` must point into this folder
                if t == "cd" and i + 1 < len(toks):
                    example_root = (Path.home() / "folderwise").resolve()  # resolved like `target`, so a symlinked HOME works
                    target = Path(os.path.expanduser(toks[i + 1])).resolve()
                    if target == example_root or example_root in target.parents:
                        target = root / target.relative_to(example_root)
                    check(f"README cd path is inside Folderwise: {toks[i + 1][-45:]}", root == target or root in target.parents, str(target))
            if "uv" not in toks or "run" not in toks:
                continue
            n_cmds += 1
            args = toks[toks.index("run") + 1:]
            name = Path(args[0]).name
            check(f"README command has no <placeholders>: {name}", not re.search(r"<[^>]+>", raw), raw)
            check(f"README names an existing tool: {name}", (SRC_TOOLS / name).is_file(), raw)
            if not (SRC_TOOLS / name).is_file():
                continue
            rest = args[1:]
            sub = rest[0] if name == "docs_mv.py" and rest and rest[0] in ("mv", "heading") else None
            for flag in (t for t in rest if t.startswith("--")):
                if (name, sub, flag) not in seen_flags:
                    seen_flags.add((name, sub, flag))
                    check(f"README example uses a real flag: {name}{' ' + sub if sub else ''} {flag}", flag in help_of(name, sub), raw)
    sys.path.insert(0, str(SRC_TOOLS))
    import new_project as np_  # noqa: E402
    expected = np_.setup_prompt("homelab-inventory", "Inventory of home network hardware and software to allow for homelab v3 planning")
    check("public documentation shows the exact setup prompt (no drift)", expected in readme, expected[:80])
    check("public documentation retains the full command reference", n_cmds >= 10, f"{n_cmds} commands")
    check("landing README has a getting-started section and shell example",
          bool(re.search(r'^## (Getting started|Quick start)\s*$', landing, re.M))
          and bool(re.search(r'```(?:bash|sh|zsh)\n', landing)))
    sys.path.insert(0, str(SRC_TOOLS))
    import docslib as dl  # noqa: E402
    for name, text in documents:
        anchors = dl.heading_anchors(text)
        for a in sorted(set(re.findall(r"\]\(#([^)]+)\)", text))):
            check(f"{name} in-page link resolves: #{a}", a in anchors)


SECTIONS = [
    ("create", s_create), ("new_doc", s_new_doc_and_index), ("stamp", s_stamp_and_hook), ("hook", s_hook_fail_closed),
    ("lint", s_lint_rules), ("timezone", s_timezone), ("links", s_links), ("toc", s_toc), ("mv", s_mv),
    ("tables", s_tables), ("stale", s_stale_index_recent), ("sync", s_sync),
    ("doctor", s_doctor), ("layout", s_layout), ("cli_errors", s_cli_errors), ("failure_paths", s_failure_paths), ("uv_cache", s_uv_cache), ("docs_coverage", s_docs_coverage),
    ("readme_commands", s_readme_commands), ("framework_index", s_framework_index), ("ci_allowlist", s_ci_allowlist),
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
