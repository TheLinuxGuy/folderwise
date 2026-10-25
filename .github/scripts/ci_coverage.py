#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["coverage==7.16.2"]
# ///
"""Measure production-code coverage of the complete Folderwise self-test and enforce the overall gate.

  uv run .github/scripts/ci_coverage.py                 run the self-test under coverage, combine, report, gate
  uv run .github/scripts/ci_coverage.py --fail-under 99 prove the gate fails (exit 1) below the threshold

The self-test copies _tools/ and _template/ into a temporary folder and drives the copies through
`uv run` subprocesses and Git hooks, so wrapping selftest.py in `coverage run` would only measure the
harness. Instead a `sitecustomize` shim on PYTHONPATH starts coverage in every Python process that
inherits the environment (including uv's isolated script environments). Each process writes its own data
file; `.coveragerc` [paths] maps the temporary copies back to canonical `_tools/` paths, so reports stay
usable after the temporary folders are deleted.

Outputs (default `.ci-coverage/`, ignored by the framework repository):
  coverage.xml          line coverage only, uploaded to Codecov (its percentages count a partially
                        covered branch line as a miss, which would be an unagreed branch threshold)
  coverage-detail.json  line and branch coverage per file
  summary.md            human-readable summary (also appended to the Actions job summary)
Exit code 0 = self-test passed, evidence checks passed, line coverage >= threshold.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import coverage

ROOT = Path(__file__).resolve().parents[2]
LINE_THRESHOLD = 85.0  # overall production line coverage policy (percent)
MIN_PROCESSES = 30  # a harness-only run records a handful of data files; the real suite records >100
# Code reachable only through the installed Git pre-commit hook (docs_lint.py --staged rejecting an
# edit that was not stamped). Located by its message, not by line number.
HOOK_ONLY_MARKERS = {"_tools/docs_lint.py": "edited but Change Log unchanged"}
SHIM = "import coverage\ncoverage.process_startup()\n"


def runtime_config(data_dir: Path, root: Path) -> str:
    """Per-process measurement config: tools run from the repo or from docs-selftest-* copies."""
    roots = sorted({str(root), str(root.resolve())})
    include = "\n".join(f"    {r}/_tools/*" for r in roots)
    return (
        "[run]\nbranch = True\nparallel = True\n"
        f"data_file = {data_dir / '.coverage'}\n"
        f"include =\n{include}\n    **/docs-selftest-*/_tools/*\n    **/docs-selftest-*/**/_tools/*\n"
        "omit =\n    */selftest.py\n    */__pycache__/*\n"
        "disable_warnings = no-data-collected\n"
    )


def run_selftest(workdir: Path, root: Path) -> int:
    data_dir, shim_dir = workdir / "data", workdir / "shim"
    data_dir.mkdir(parents=True)
    shim_dir.mkdir()
    (shim_dir / "sitecustomize.py").write_text(SHIM)
    rc = workdir / "runtime.coveragerc"
    rc.write_text(runtime_config(data_dir, root))
    lib = str(Path(coverage.__file__).resolve().parent.parent)  # site-packages holding coverage
    env = dict(os.environ, COVERAGE_PROCESS_START=str(rc))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(shim_dir), lib, env.get("PYTHONPATH")]))
    return subprocess.run(["uv", "run", "--quiet", str(root / "_tools" / "selftest.py")], cwd=root, env=env).returncode


def combine(workdir: Path, root: Path) -> coverage.Coverage:
    os.chdir(root)  # relative paths in .coveragerc resolve against the repository root
    cov = coverage.Coverage(config_file=str(root / ".coveragerc"), data_file=str(workdir / "combined" / ".coverage"))
    cov.combine([str(workdir / "data")], keep=True, strict=True)
    cov.save()
    return cov


def entry_guard_line(source: str) -> int | None:
    """Line of the first statement under `if __name__ == "__main__":`, or None for library modules."""
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__" and node.test.comparators
                and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value == "__main__"):
            return node.body[0].lineno
    return None


def marker_line(source: str, marker: str) -> int | None:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and marker in node.value:
            return node.lineno
    return None


def evidence_errors(executed: dict[str, set[int]], root: Path, n_processes: int) -> list[str]:
    """Prove the data comes from real CLI and hook execution, not from the harness importing modules.

    `executed` maps canonical repo-relative paths to executed line numbers.
    """
    errors = []
    stray = sorted(p for p in executed if not p.startswith("_tools/"))
    if stray:
        errors.append(f"measured paths outside _tools/ (unmapped temporary copies?): {stray[:5]}")
    if n_processes < MIN_PROCESSES:
        errors.append(f"only {n_processes} Python processes were measured (expected >= {MIN_PROCESSES}): subprocess capture failed")
    for path in sorted((root / "_tools").glob("*.py")):
        rel = f"_tools/{path.name}"
        if rel == "_tools/selftest.py":
            continue
        source = path.read_text()
        guard = entry_guard_line(source)
        if guard is not None and guard not in executed.get(rel, set()):
            errors.append(f"{rel}: CLI entry point never executed (module was only imported or never run)")
        marker = HOOK_ONLY_MARKERS.get(rel)
        if marker:
            line = marker_line(source, marker)
            if line is None:
                errors.append(f"{rel}: hook-only marker {marker!r} no longer exists; update HOOK_ONLY_MARKERS")
            elif line not in executed.get(rel, set()):
                errors.append(f"{rel}: git pre-commit hook path was never executed (line {line})")
    return errors


def write_line_only_xml(cov: coverage.Coverage, workdir: Path, root: Path, out: Path) -> None:
    """Codecov counts a partially covered branch line as a miss; upload line data so the 85%/90% policy stays line-based."""
    data = cov.get_data()
    path = workdir / "lines-only" / ".coverage"
    path.parent.mkdir()
    lines = coverage.CoverageData(basename=str(path))
    lines.add_lines({f: sorted(data.lines(f) or []) for f in data.measured_files()})
    lines.write()
    plain = coverage.Coverage(config_file=str(root / ".coveragerc"), data_file=str(path), branch=False)
    plain.load()
    plain.xml_report(outfile=str(out))


def summary_markdown(report: dict, threshold: float, ok: bool) -> str:
    t = report["totals"]
    line_pct = 100.0 * t["covered_lines"] / t["num_statements"]
    rows = ["| File | Lines | Missed | Line % | Branches | Partial | Branch % |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, f in sorted(report["files"].items()):
        s = f["summary"]
        lp = 100.0 * s["covered_lines"] / s["num_statements"] if s["num_statements"] else 100.0
        bp = 100.0 * s["covered_branches"] / s["num_branches"] if s["num_branches"] else 100.0
        rows.append(f"| `{name}` | {s['num_statements']} | {s['missing_lines']} | {lp:.1f} | {s['num_branches']} | {s['num_partial_branches']} | {bp:.1f} |")
    branch_pct = 100.0 * t["covered_branches"] / t["num_branches"] if t["num_branches"] else 100.0
    head = (f"### Production coverage: {line_pct:.2f}% lines ({'PASS' if ok else 'FAIL'}, gate {threshold:g}%)\n\n"
            f"Branch coverage {branch_pct:.2f}% ({t['covered_branches']}/{t['num_branches']}), reported only: no branch threshold yet. "
            f"Scope: `_tools/**/*.py` except `selftest.py`; unexecuted files count as 0%.\n\n")
    return head + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fail-under", type=float, default=LINE_THRESHOLD, help=f"minimum overall line coverage (default {LINE_THRESHOLD:g})")
    ap.add_argument("--out", type=Path, default=ROOT / ".ci-coverage", help="report directory (default .ci-coverage/)")
    ap.add_argument("--keep-workdir", action="store_true", help="keep raw per-process data files and print their location")
    args = ap.parse_args()

    out = args.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    workdir = Path(tempfile.mkdtemp(prefix="folderwise-cov-")).resolve()
    try:
        rc = run_selftest(workdir, ROOT)
        if rc != 0:
            print(f"ci_coverage: self-test failed (exit {rc}); coverage is not meaningful.", file=sys.stderr)
            return 1
        n_processes = len(list((workdir / "data").glob(".coverage.*")))
        cov = combine(workdir, ROOT)
        cov.json_report(outfile=str(out / "coverage-detail.json"))
        write_line_only_xml(cov, workdir, ROOT, out / "coverage.xml")
        data = cov.get_data()
        executed = {f: set(data.lines(f) or []) for f in data.measured_files()}
    finally:
        if args.keep_workdir:
            print(f"ci_coverage: raw data kept in {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    report = json.loads((out / "coverage-detail.json").read_text())
    t = report["totals"]
    line_pct = 100.0 * t["covered_lines"] / t["num_statements"]
    problems = evidence_errors(executed, ROOT, n_processes)
    if line_pct < args.fail_under:
        problems.append(f"overall line coverage {line_pct:.2f}% is below the {args.fail_under:g}% gate")
    summary = summary_markdown(report, args.fail_under, not problems)
    if problems:
        summary += "\n**Problems**\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    (out / "summary.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(summary)
    print(summary)
    print(f"ci_coverage: {n_processes} Python processes measured; reports in {out}")
    for p in problems:
        print(f"ci_coverage: FAIL: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
