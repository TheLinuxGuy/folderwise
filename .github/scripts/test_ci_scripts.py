"""Tests for the CI and release tooling. They use fictional fixtures in temporary directories only.

  uv run --with coverage==7.16.2 --with pyyaml python -m unittest discover -s .github/scripts -v

This is CI tooling, not production code: it is outside the coverage scope but gated in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rb = load("release_build")
try:
    cc = load("ci_coverage")
except ImportError:  # coverage not installed in this interpreter
    cc = None

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True).stdout.strip()


FIXTURE_FILES = {  # fictional framework repository: path -> (mode, text)
    "README.md": (0o644, "# Fictional\n"), "AGENTS.md": (0o644, "rules\n"), "LICENSE": (0o644, "MIT\n"), "CONTRIBUTING.md": (0o644, "c\n"),
    "uv.toml": (0o644, "# portable\n"), ".gitignore": (0o644, "/*\n"), ".gitattributes": (0o644, "* text=auto\n"),
    "_tools/tool.py": (0o755, "print('tool')\n"), "_tools/lib.py": (0o644, "X = 1\n"),
    "_tools/framework-hooks/pre-commit": (0o755, "#!/bin/sh\n"),
    "_template/.docs.yaml": (0o644, "schema_version: 1\n"), "_template/.gitignore": (0o644, "*.tmp\n"), "docs/guide.md": (0o644, "# Guide\n"),
    ".github/workflows/ci.yml": (0o644, "name: CI\n"), ".coveragerc": (0o644, "[run]\n"), "codecov.yml": (0o644, "a: b\n"), "ruff.toml": (0o644, "x=1\n"),
}


def make_repo(root: Path, extra: dict[str, tuple[int, str]] | None = None) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for rel, (mode, text) in {**FIXTURE_FILES, **(extra or {})}.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(mode)
    git(repo, "add", "-A", "-f")
    git(repo, "commit", "-q", "-m", "fixture")
    return repo, git(repo, "rev-parse", "HEAD")


def build_args(repo, commit, out, report, version="1.2.3"):
    return argparse.Namespace(repo=repo, commit=commit, version=version, manifest=rb.MANIFEST, out=out, report=report)


class VersionTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        for v, pre in [("0.1.0", False), ("1.2.3", False), ("10.20.30", False), ("1.2.3-rc.1", True), ("1.0.0-alpha", True), ("1.0.0-0.3.7", True)]:
            self.assertEqual(rb.check_version(v), (True, pre), v)
        for v in ["v1.2.3", "1.2", "1.2.3.4", "01.2.3", "1.2.3-", "1.2.3+build.5", "1.2.3-01", "", " 1.2.3", "1.2.3\n../x", "latest"]:
            self.assertFalse(rb.check_version(v)[0], repr(v))


class ManifestTests(unittest.TestCase):
    rules = rb.load_manifest("include a.md\ninclude docs/**\nexclude .github/**  # comment\n")

    def test_classification(self):
        self.assertEqual(rb.classify("a.md", self.rules), "include")
        self.assertEqual(rb.classify("docs/x/y.md", self.rules), "include")
        self.assertEqual(rb.classify(".github/workflows/ci.yml", self.rules), "exclude")

    def test_unclassified_and_conflicting_paths_fail(self):
        with self.assertRaises(rb.BuildError):
            rb.classify("new-root-file.txt", self.rules)
        with self.assertRaises(rb.BuildError):
            rb.classify("docs/a", rb.load_manifest("include docs/**\nexclude docs/**\n"))

    def test_bad_syntax_fails(self):
        for text in ["keep a.md", "include", "include /abs", "include ../x"]:
            with self.assertRaises(rb.BuildError, msg=text):
                rb.load_manifest(text)

    def test_real_manifest_classifies_every_tracked_file(self):
        rules = rb.load_manifest(rb.MANIFEST.read_text())
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\n")
        for path in filter(None, tracked):
            if (REPO / path).exists():
                rb.classify(path, rules)

    def test_real_manifest_never_includes_ci_or_private_paths(self):
        rules = rb.load_manifest(rb.MANIFEST.read_text())
        for path in [".github/workflows/ci.yml", ".github/scripts/ci_coverage.py", ".coveragerc", "codecov.yml", "ruff.toml"]:
            self.assertEqual(rb.classify(path, rules), "exclude", path)


class PrivatePathTests(unittest.TestCase):
    def test_private_paths_are_rejected(self):
        for path in [".env", "docs/.env.local", "_tools/key.pem", "a/id_rsa", ".obsidian/app.json", "_template/.claude/settings.local.json", "proj/.docs.yaml",
                     "_tools/__pycache__/x.pyc", ".github/workflows/ci.yml", "_tools/.coverage", "coverage.xml", "docs/credentials.json"]:
            self.assertTrue(rb.private_reason(path), path)

    def test_public_paths_are_accepted(self):
        for path in ["README.md", "_template/.docs.yaml", "_template/.gitignore", "_template/.claude/settings.json", "_tools/framework-hooks/pre-commit", "docs/obsidian.md"]:
            self.assertIsNone(rb.private_reason(path), path)


class ArchiveInspectionTests(unittest.TestCase):
    prefix = "folderwise-1.0.0/"
    expected = {"README.md", "_tools/a.py"}

    def members(self, *extra):
        base = [("folderwise-1.0.0/", 0o40755, "dir"), ("folderwise-1.0.0/_tools/", 0o40755, "dir"),
                ("folderwise-1.0.0/README.md", 0o100644, "file"), ("folderwise-1.0.0/_tools/a.py", 0o100755, "file")]
        return base + list(extra)

    def errors(self, *extra):
        return rb.archive_errors(self.members(*extra), self.prefix, self.expected)

    def test_clean_archive(self):
        self.assertEqual(self.errors(), [])

    def test_rejections(self):
        cases = {
            "traversal": ("folderwise-1.0.0/../evil", 0o100644, "file"),
            "absolute": ("/etc/passwd", 0o100644, "file"),
            "backslash": ("folderwise-1.0.0\\evil", 0o100644, "file"),
            "windows drive": ("C:/evil", 0o100644, "file"),
            "outside prefix": ("other/README.md", 0o100644, "file"),
            "unexpected file": ("folderwise-1.0.0/extra.txt", 0o100644, "file"),
            "unexpected dir": ("folderwise-1.0.0/secret/", 0o40755, "dir"),
            "symlink": ("folderwise-1.0.0/link", 0o120777, "file"),
            "special": ("folderwise-1.0.0/fifo", 0o10644, "other"),
            "duplicate": ("folderwise-1.0.0/README.md", 0o100644, "file"),
        }
        for label, member in cases.items():
            self.assertTrue(self.errors(member), label)

    def test_private_content_is_rejected_even_if_expected(self):
        errors = rb.archive_errors([("p/.env", 0o100644, "file")], "p/", {".env"})
        self.assertTrue(any("credential" in e for e in errors), errors)

    def test_missing_expected_file(self):
        errors = rb.archive_errors(self.members()[:3], self.prefix, self.expected)
        self.assertTrue(any("_tools/a.py: expected but missing" in e for e in errors), errors)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="folderwise-release-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def build(self, repo, commit, name="out", version="1.2.3"):
        out, report = self.tmp / name, self.tmp / f"{name}.json"
        self.assertEqual(rb.cmd_build(build_args(repo, commit, out, report, version)), 0)
        return out, json.loads(report.read_text())

    def test_build_packages_only_approved_tracked_files(self):
        repo, commit = make_repo(self.tmp)
        (repo / "untracked-private.txt").write_text("not committed")
        out, report = self.build(repo, commit)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["SHA256SUMS", "folderwise-1.2.3.tar.gz", "folderwise-1.2.3.zip"])
        paths = set(report["files"])
        self.assertEqual(paths, {"README.md", "AGENTS.md", "LICENSE", "CONTRIBUTING.md", "uv.toml", ".gitignore", ".gitattributes", "_tools/tool.py", "_tools/lib.py",
                                 "_tools/framework-hooks/pre-commit", "_template/.docs.yaml", "_template/.gitignore", "docs/guide.md", "RELEASE-INFO.json"})
        self.assertEqual(set(report["excluded"]), {".github/workflows/ci.yml", ".coveragerc", "codecov.yml", "ruff.toml"})
        self.assertEqual(report["files"]["_tools/tool.py"]["mode"], "755")
        self.assertEqual(report["files"]["_tools/lib.py"]["mode"], "644")
        info = json.loads(zipfile.ZipFile(out / "folderwise-1.2.3.zip").read("folderwise-1.2.3/RELEASE-INFO.json"))
        self.assertEqual((info["version"], info["commit"], info["tag"], info["prerelease"]), ("1.2.3", commit, "v1.2.3", False))
        self.assertEqual(rb.cmd_verify_sums(argparse.Namespace(dir=out, version="1.2.3")), 0)

    def test_both_formats_hold_identical_content_and_modes(self):
        repo, commit = make_repo(self.tmp)
        out, _ = self.build(repo, commit, version="2.0.0-rc.1")
        zf, tf = zipfile.ZipFile(out / "folderwise-2.0.0-rc.1.zip"), tarfile.open(out / "folderwise-2.0.0-rc.1.tar.gz")
        z = {i.filename: (zf.read(i), (i.external_attr >> 16) & 0o777) for i in zf.infolist() if not i.is_dir()}
        t = {m.name: (tf.extractfile(m).read(), m.mode & 0o777) for m in tf.getmembers() if m.isfile()}
        self.assertEqual(z, t)
        self.assertEqual(t["folderwise-2.0.0-rc.1/_tools/tool.py"][1], 0o755)
        self.assertIn("folderwise-2.0.0-rc.1/_template/.gitignore", t)
        self.assertTrue(json.loads(t["folderwise-2.0.0-rc.1/RELEASE-INFO.json"][0])["prerelease"])

    def test_build_is_reproducible(self):
        repo, commit = make_repo(self.tmp)
        a, _ = self.build(repo, commit, "a")
        b, _ = self.build(repo, commit, "b")
        self.assertEqual((a / "SHA256SUMS").read_text(), (b / "SHA256SUMS").read_text())

    def test_build_uses_the_selected_commit_not_the_working_tree(self):
        repo, commit = make_repo(self.tmp)
        (repo / "README.md").write_text("# edited after the commit\n")
        _, report = self.build(repo, commit)
        self.assertEqual(report["files"]["README.md"]["sha256"], hashlib.sha256(b"# Fictional\n").hexdigest())

    def test_unclassified_tracked_file_fails_the_build(self):
        repo, commit = make_repo(self.tmp, {"new-root-file.txt": (0o644, "x")})
        with self.assertRaisesRegex(rb.BuildError, "not classified"):
            self.build(repo, commit)

    def test_private_content_in_an_approved_directory_fails_the_build(self):
        for extra in ({"_tools/token.pem": (0o644, "x")}, {"docs/.env": (0o644, "x")}, {"docs/project/.docs.yaml": (0o644, "x")},
                      {"_tools/__pycache__/x.cpython-312.pyc": (0o644, "x")}):
            with self.subTest(extra=list(extra)):
                shutil.rmtree(self.tmp / "repo", ignore_errors=True)
                repo, commit = make_repo(self.tmp, extra)
                with self.assertRaises(rb.BuildError):
                    self.build(repo, commit, name=f"o{abs(hash(list(extra)[0]))}")

    def test_symlink_and_nested_repository_fail_the_build(self):
        repo, _ = make_repo(self.tmp)
        os.symlink("README.md", repo / "docs" / "link.md")
        git(repo, "add", "-A", "-f")
        git(repo, "commit", "-q", "-m", "symlink")
        with self.assertRaises(rb.BuildError):
            self.build(repo, git(repo, "rev-parse", "HEAD"))

    def test_non_empty_output_directory_is_refused(self):
        repo, commit = make_repo(self.tmp)
        (self.tmp / "out").mkdir()
        (self.tmp / "out" / "stale.zip").write_text("x")
        with self.assertRaisesRegex(rb.BuildError, "must be empty"):
            self.build(repo, commit)

    def test_invalid_version_is_refused(self):
        repo, commit = make_repo(self.tmp)
        with self.assertRaises(rb.BuildError):
            self.build(repo, commit, version="v1.0.0")

    def test_tampered_checksums_and_extra_assets_are_detected(self):
        repo, commit = make_repo(self.tmp)
        out, _ = self.build(repo, commit)
        (out / "extra.txt").write_text("x")
        with self.assertRaisesRegex(rb.BuildError, "exactly"):
            rb.cmd_verify_sums(argparse.Namespace(dir=out, version="1.2.3"))
        (out / "extra.txt").unlink()
        with open(out / "folderwise-1.2.3.zip", "ab") as fh:
            fh.write(b"tampered")
        with self.assertRaisesRegex(rb.BuildError, "checksum mismatch"):
            rb.cmd_verify_sums(argparse.Namespace(dir=out, version="1.2.3"))

    @unittest.skipUnless(shutil.which("unzip") and shutil.which("tar"), "system unzip/tar not available")
    def test_system_extraction_matches_build_report(self):
        repo, commit = make_repo(self.tmp)
        out, _ = self.build(repo, commit)
        report = self.tmp / "out.json"
        for fmt, cmd in (("zip", ["unzip", "-q", str(out / "folderwise-1.2.3.zip")]), ("tgz", ["tar", "-xzf", str(out / "folderwise-1.2.3.tar.gz")])):
            fresh = self.tmp / f"fresh-{fmt}"
            fresh.mkdir()
            subprocess.run(cmd, cwd=fresh, check=True)
            args = argparse.Namespace(root=fresh / "folderwise-1.2.3", report=report)
            self.assertEqual(rb.cmd_check_tree(args), 0)
            (fresh / "folderwise-1.2.3" / "stray.txt").write_text("x")
            with self.assertRaisesRegex(rb.BuildError, "unexpected file"):
                rb.cmd_check_tree(args)

    def test_commit_must_be_reachable_from_origin_default_branch(self):
        repo, commit = make_repo(self.tmp)
        git(repo, "update-ref", "refs/remotes/origin/main", commit)
        git(repo, "switch", "-q", "-c", "side")
        (repo / "README.md").write_text("side branch only\n")
        git(repo, "commit", "-q", "-am", "side")
        side = git(repo, "rev-parse", "HEAD")
        ns = lambda c: argparse.Namespace(repo=repo, commit=c, default_branch="main")  # noqa: E731
        self.assertEqual(rb.cmd_resolve_commit(ns("")), 0)
        self.assertEqual(rb.cmd_resolve_commit(ns(commit)), 0)
        with self.assertRaisesRegex(rb.BuildError, "not reachable"):
            rb.cmd_resolve_commit(ns(side))

    def test_existing_tag_blocks_a_release(self):
        repo, commit = make_repo(self.tmp)
        git(repo, "tag", "v9.9.9")
        with self.assertRaisesRegex(rb.BuildError, "already exists"):
            rb.cmd_check_tag_free(argparse.Namespace(repo=repo, tag="v9.9.9"))

    def test_notes_mention_commit_and_leave_maintainer_sections(self):
        out = self.tmp / "notes.md"
        rb.cmd_notes(argparse.Namespace(version="1.0.0-rc.1", commit="a" * 40, out=out))
        text = out.read_text()
        self.assertIn("pre-release", text)
        self.assertIn("a" * 40, text)
        self.assertIn("Compatibility notes", text)
        self.assertIn("Upgrade notes", text)


@unittest.skipIf(cc is None, "coverage is not installed")
class CoverageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="folderwise-cov-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "_tools").mkdir()
        self.cli = "import sys\n\ndef main():\n    return 0\n\nif __name__ == '__main__':\n    sys.exit(main())\n"
        (self.tmp / "_tools" / "cli.py").write_text(self.cli)
        (self.tmp / "_tools" / "lib.py").write_text("X = 1\n")
        (self.tmp / "_tools" / "selftest.py").write_text(self.cli)

    def test_entry_guard_detection(self):
        self.assertEqual(cc.entry_guard_line(self.cli), 7)
        self.assertIsNone(cc.entry_guard_line("X = 1\n"))
        self.assertEqual(cc.entry_guard_line('if __name__ == "__main__":\n    run()\n'), 2)

    def test_marker_detection(self):
        self.assertEqual(cc.marker_line('x = 1\nerrs.append("edited but Change Log unchanged (run)")\n', "Change Log unchanged"), 2)
        self.assertIsNone(cc.marker_line("x = 1\n", "missing"))

    def test_cli_execution_passes(self):
        executed = {"_tools/cli.py": {1, 3, 4, 6, 7}, "_tools/lib.py": {1}}
        self.assertEqual(cc.evidence_errors(executed, self.tmp, 100), [])

    def test_harness_only_import_is_not_cli_execution(self):
        """The negative control: importing modules (what the harness does in-process) must not satisfy the evidence check."""
        executed = {"_tools/cli.py": {1, 3, 4, 6}, "_tools/lib.py": {1}}
        errors = cc.evidence_errors(executed, self.tmp, 100)
        self.assertEqual(len(errors), 1)
        self.assertIn("CLI entry point never executed", errors[0])

    def test_unmapped_temporary_paths_and_missing_subprocesses_are_reported(self):
        executed = {"_tools/cli.py": {7}, "/tmp/docs-selftest-abc/_tools/cli.py": {7}}
        errors = "\n".join(cc.evidence_errors(executed, self.tmp, 3))
        self.assertIn("outside _tools/", errors)
        self.assertIn("only 3 Python processes", errors)

    def test_hook_path_must_be_executed(self):
        src = self.cli.replace("    return 0", "    return 'edited but Change Log unchanged'")
        (self.tmp / "_tools" / "docs_lint.py").write_text(src)
        executed = {"_tools/cli.py": {7}, "_tools/docs_lint.py": {1, 3, 7}}
        errors = cc.evidence_errors(executed, self.tmp, 100)
        self.assertTrue(any("pre-commit hook path" in e for e in errors), errors)
        executed["_tools/docs_lint.py"].add(4)
        self.assertEqual(cc.evidence_errors(executed, self.tmp, 100), [])

    def test_runtime_config_measures_repo_and_selftest_copies_but_not_the_harness(self):
        text = cc.runtime_config(Path("/data"), Path("/repo"))
        self.assertIn("parallel = True", text)
        self.assertIn("branch = True", text)
        self.assertIn("/repo/_tools/*", text)
        self.assertIn("*/docs-selftest-*/_tools/*", text)
        self.assertIn("*/selftest.py", text)

    def test_threshold_is_the_agreed_policy(self):
        self.assertEqual(cc.LINE_THRESHOLD, 85.0)

    def test_summary_reports_line_and_branch_numbers(self):
        report = {"totals": {"covered_lines": 90, "num_statements": 100, "covered_branches": 15, "num_branches": 20},
                  "files": {"_tools/a.py": {"summary": {"covered_lines": 90, "num_statements": 100, "missing_lines": 10, "covered_branches": 15,
                                                       "num_branches": 20, "num_partial_branches": 3}}}}
        text = cc.summary_markdown(report, 85.0, True)
        self.assertIn("90.00% lines (PASS, gate 85%)", text)
        self.assertIn("Branch coverage 75.00%", text)
        self.assertIn("`_tools/a.py`", text)
        self.assertIn("FAIL", cc.summary_markdown(report, 85.0, False))


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class WorkflowPolicyTests(unittest.TestCase):
    """Guard rails on the workflow files themselves. They run in CI; a contributor can also edit them, which is
    why workflow, coverage-policy and guard changes are flagged for careful review (CODEOWNERS), not trusted blindly."""

    @staticmethod
    def wf(name):
        data = yaml.safe_load((REPO / ".github" / "workflows" / name).read_text())
        data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 parses the key `on` as True
        return data

    def uses(self, wf):
        return [s["uses"] for j in wf["jobs"].values() for s in j.get("steps", []) if "uses" in s] + \
               [j["uses"] for j in wf["jobs"].values() if "uses" in j]

    def test_every_external_action_is_pinned_to_a_commit_sha(self):
        for name in ("ci.yml", "release.yml"):
            for use in self.uses(self.wf(name)):
                if not use.startswith("./"):
                    self.assertRegex(use, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", f"{name}: {use}")

    def test_every_job_has_a_timeout_and_every_checkout_drops_credentials(self):
        for name in ("ci.yml", "release.yml"):
            for job_id, job in self.wf(name)["jobs"].items():
                if "uses" not in job:
                    self.assertIn("timeout-minutes", job, f"{name}:{job_id}")
                for step in job.get("steps", []):
                    if str(step.get("uses", "")).startswith("actions/checkout@"):
                        self.assertIs(step["with"].get("persist-credentials"), False, f"{name}:{job_id}")

    def test_ci_runs_for_every_pull_request_including_documentation_only_changes(self):
        on = self.wf("ci.yml")["on"]
        self.assertEqual({"pull_request", "push", "workflow_dispatch", "workflow_call"}, set(on))
        self.assertEqual(on["push"]["branches"], ["main"])
        for trigger in ("pull_request", "push"):
            for key in (on[trigger] or {}):
                self.assertNotIn(key, {"paths", "paths-ignore"}, f"{trigger}: path filters would skip documentation-only PRs")

    def test_ci_is_unprivileged(self):
        ci = self.wf("ci.yml")
        self.assertEqual(ci["permissions"], {"contents": "read"})
        for job in ci["jobs"].values():
            self.assertNotIn("permissions", job)
        self.assertNotIn("pull_request_target", ci["on"])
        self.assertIn("pull_request", str(ci["concurrency"]["cancel-in-progress"]))

    def test_gate_job_depends_on_everything_and_fails_on_skips(self):
        jobs = self.wf("ci.yml")["jobs"]
        gate = jobs["ci-gate"]
        self.assertEqual(gate["name"], "CI gate")
        self.assertEqual(gate["if"].strip(), "${{ always() }}")
        self.assertEqual(set(gate["needs"]), set(jobs) - {"ci-gate"})
        script = "\n".join(s.get("run", "") for s in gate["steps"])
        self.assertIn("!= success", script.replace('"', "").replace("'", ""))

    def test_release_workflow_is_manual_and_only_the_draft_job_can_write(self):
        release = self.wf("release.yml")
        self.assertEqual(set(release["on"]), {"workflow_dispatch"})
        self.assertEqual(release["permissions"], {"contents": "read"})
        writers = [j for j, job in release["jobs"].items() if (job.get("permissions") or {}).get("contents") == "write"]
        self.assertEqual(writers, ["draft"])
        text = (REPO / ".github/workflows/release.yml").read_text()
        self.assertIn("--draft", text)
        self.assertNotIn("gh release edit", text)
        self.assertNotRegex(text, r"--draft=false|--latest|gh release upload")

    def test_codecov_policy(self):
        cfg = yaml.safe_load((REPO / "codecov.yml").read_text())
        status = cfg["coverage"]["status"]
        self.assertEqual(status["patch"]["default"]["target"], "90%")
        self.assertTrue(status["project"]["default"]["informational"])

    def test_coverage_scope_is_not_widened(self):
        text = "\n".join(l for l in (REPO / ".coveragerc").read_text().splitlines() if not l.lstrip().startswith("#"))
        omitted = re.search(r"^omit =\n((?:    .+\n)+)", text, re.M).group(1).split()
        self.assertEqual(omitted, ["_tools/selftest.py", "_tools/__pycache__/*"])
        self.assertNotIn("exclude_also", text)
        self.assertNotIn("exclude_lines", text)
        self.assertNotIn("fail_under", text)


if __name__ == "__main__":
    unittest.main()
