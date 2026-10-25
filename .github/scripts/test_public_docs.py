#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "tzdata"]
# ///
"""Validate the public documentation in a full development checkout. Required in CI.

Installation self-tests run separately and need no public README or docs/ directory.
Missing public documentation is an error here, never an optional skipped check.
"""
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SRC_TOOLS = Path(__file__).resolve().parents[2] / "_tools"
RESULTS = []


def check(label, condition, detail=""):
    RESULTS.append(bool(condition))
    print(("PASS " if condition else "FAIL ") + label, flush=True)
    if not condition and detail:
        print(detail[-600:])


def sh(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def public_documentation() -> list[tuple[str, str]]:
    """The landing README may link to a separate full command guide."""
    root = SRC_TOOLS.parent
    docs = [("README.md", (root / "README.md").read_text())]
    guide = root / "docs" / "guide.md"
    if not re.search(r'\]\(docs/guide\.md(?:#[^)]*)?\)', docs[0][1]):
        raise ValueError("README must link to docs/guide.md")
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
        keys |= set(re.findall(r'\bcfg(?:\.get\(|\[)"([a-z_][a-z_-]*)"', f.read_text()))
    for k in sorted(keys):
        check(f"public documentation covers the .docs.yaml setting '{k}'", f"`{k}`" in readme)


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
          bool(re.search(r'^## (?:[^\w\s]+\s+)?(Getting started|Quick start)\s*$', landing, re.M))
          and bool(re.search(r'```(?:bash|sh|zsh)\n', landing)))
    sys.path.insert(0, str(SRC_TOOLS))
    import docslib as dl  # noqa: E402
    for name, text in documents:
        anchors = dl.heading_anchors(text)
        for a in sorted(set(re.findall(r"\]\(#([^)]+)\)", text))):
            check(f"{name} in-page link resolves: #{a}", a in anchors)


def main():
    for fn in (s_docs_coverage, s_readme_commands):
        try:
            fn()
        except Exception as exc:
            check(fn.__name__, False, str(exc))
    print(f"{sum(RESULTS)}/{len(RESULTS)} public documentation checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
