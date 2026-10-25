#!/usr/bin/env python3
"""Build and verify Folderwise release archives from one explicit Git commit.

  release_build.py validate-version VERSION           print GITHUB_OUTPUT lines (version, tag, prerelease)
  release_build.py resolve-commit [--commit SHA]      full SHA, which must be reachable from origin/<default branch>
  release_build.py check-tag-free TAG                 fail if the tag already exists locally or on origin
  release_build.py build --version V --commit SHA     folderwise-V.zip, folderwise-V.tar.gz, SHA256SUMS, build-report.json
  release_build.py verify-sums --dir DIR --version V  DIR holds exactly the three assets and the checksums match
  release_build.py check-tree --root DIR --report R   an extracted archive equals the build report (paths, modes, hashes)
  release_build.py notes --version V --commit SHA     draft release notes (maintainer sections to fill in)

Only files tracked at the commit and approved by .github/release-manifest.txt are packaged. Every tracked file
must be classified by the manifest, so a new file cannot slip into (or silently out of) a release. Included paths
must also pass _tools/framework_guard.py, and the finished archives are read back and checked again.
Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / ".github" / "release-manifest.txt"
DEFAULT_BRANCH = "main"
INFO_NAME = "RELEASE-INFO.json"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?$")
PRIVATE_PARTS = {".git", ".github", ".cache", ".obsidian", "__pycache__", "node_modules", ".ruff_cache", ".ci-coverage", "htmlcov"}
PRIVATE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".pyc", ".pyo")
PRIVATE_NAMES = {"id_rsa", "id_ed25519", "credentials.json", "settings.local.json", ".DS_Store", "coverage.xml"}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- pure checks

def check_version(version: str) -> tuple[bool, bool]:
    """Return (valid, prerelease). Plain SemVer: no leading 'v', no build metadata."""
    m = SEMVER.match(version)
    return bool(m), bool(m and m.group(4))


def load_manifest(text: str) -> list[tuple[str, str]]:
    rules = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, pattern = line.partition(" ")
        pattern = pattern.strip()
        if kind not in {"include", "exclude"} or not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
            raise BuildError(f"release-manifest.txt line {n}: expected 'include PATH' or 'exclude PATH', got {raw!r}")
        rules.append((kind, pattern))
    return rules


def matches(pattern: str, path: str) -> bool:
    return path.startswith(pattern[:-2]) if pattern.endswith("/**") else path == pattern


def classify(path: str, rules: list[tuple[str, str]]) -> str:
    kinds = {kind for kind, pattern in rules if matches(pattern, path)}
    if not kinds:
        raise BuildError(f"{path}: tracked but not classified by release-manifest.txt (add an include or exclude rule)")
    if len(kinds) > 1:
        raise BuildError(f"{path}: matched by both include and exclude rules")
    return kinds.pop()


def private_reason(path: str) -> str | None:
    """Independent of framework_guard: private or generated content must never be packaged."""
    parts = PurePosixPath(path).parts
    name = parts[-1]
    if any(p in PRIVATE_PARTS for p in parts):
        return "repository metadata, CI configuration, caches or vault configuration"
    if name == ".docs.yaml" and path != "_template/.docs.yaml":
        return "knowledge-project configuration"
    if name == ".env" or (name.startswith((".env.", ".coverage")) and name != ".coveragerc"):
        return "environment, credential or coverage data file"
    if name in PRIVATE_NAMES or name.endswith(PRIVATE_SUFFIXES):
        return "credential, local-settings or generated file"
    return None


def archive_errors(members: list[tuple[str, int, str]], prefix: str, expected: set[str]) -> list[str]:
    """members: (name, unix mode, kind) with kind in {'file', 'dir', 'other'}. `expected`: file paths relative to prefix."""
    errors, seen = [], set()
    expected_dirs = {str(p) for f in expected for p in PurePosixPath(f).parents if str(p) != "."}
    for name, mode, kind in members:
        label = repr(name)
        if kind == "other" or stat.S_ISLNK(mode):
            errors.append(f"{label}: links and special files are not allowed")
            continue
        if name in seen:
            errors.append(f"{label}: duplicate entry")
        seen.add(name)
        bare = name.rstrip("/")
        if not name or name.startswith("/") or "\\" in name or re.match(r"^[A-Za-z]:", name) or ".." in bare.split("/") or "" in bare.split("/"):
            errors.append(f"{label}: absolute path, backslash or traversal")
            continue
        if bare == prefix.rstrip("/") and kind == "dir":
            continue
        if not bare.startswith(prefix):
            errors.append(f"{label}: outside the top-level folder {prefix}")
            continue
        rel = bare[len(prefix):]
        if kind == "dir":
            if rel not in expected_dirs:
                errors.append(f"{label}: unexpected directory")
        elif rel not in expected:
            errors.append(f"{label}: unexpected file")
        else:
            why = private_reason(rel)
            if why:
                errors.append(f"{label}: {why}")
    present = {n.rstrip("/")[len(prefix):] for n, _, k in members if k == "file" and n.startswith(prefix)}
    for rel in sorted(expected - present):
        errors.append(f"{prefix}{rel}: expected but missing")
    return errors


def sums_text(files: dict[str, bytes]) -> str:
    return "".join(f"{hashlib.sha256(files[n]).hexdigest()}  {n}\n" for n in sorted(files))


# ---------------------------------------------------------------- git access

def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and r.returncode:
        raise BuildError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r


def full_sha(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").stdout.decode().strip()


def tracked_entries(repo: Path, commit: str) -> list[tuple[str, str, str]]:
    out = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).stdout
    entries = []
    for item in filter(None, out.split(b"\0")):
        meta, raw = item.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        entries.append((mode if kind == "blob" else "160000", sha, raw.decode("utf-8", errors="surrogateescape")))
    return entries


def load_guard():
    spec = importlib.util.spec_from_file_location("framework_guard_for_release", REPO / "_tools" / "framework_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- build

def plan_files(repo: Path, commit: str, rules: list[tuple[str, str]]) -> tuple[dict[str, tuple[int, bytes]], list[str]]:
    guard = load_guard()
    files, excluded = {}, []
    for mode, sha, path in tracked_entries(repo, commit):
        if classify(path, rules) == "exclude":
            excluded.append(path)
            continue
        problem = guard.validate_entry(mode, path) or private_reason(path)
        if problem:
            raise BuildError(f"{path}: refusing to package ({problem})")
        files[path] = (0o755 if mode == "100755" else 0o644, git(repo, "cat-file", "blob", sha).stdout)
    if not files:
        raise BuildError("nothing to package")
    return files, sorted(excluded)


def release_info(version: str, commit: str, committed: int) -> bytes:
    info = {
        "name": "folderwise",
        "version": version,
        "tag": f"v{version}",
        "prerelease": check_version(version)[1],
        "commit": commit,
        "commit_date": dt.datetime.fromtimestamp(committed, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": "https://github.com/TheLinuxGuy/folderwise",
    }
    return (json.dumps(info, indent=2) + "\n").encode()


def write_zip(path: Path, prefix: str, files: dict[str, tuple[int, bytes]], committed: int) -> None:
    stamp = dt.datetime.fromtimestamp(max(committed, 315532800), dt.timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted({prefix.rstrip("/")} | {prefix + str(p) for f in files for p in PurePosixPath(f).parents if str(p) != "."}):
            info = zipfile.ZipInfo(name + "/", stamp)
            info.create_system, info.external_attr = 3, (stat.S_IFDIR | 0o755) << 16 | 0x10
            zf.writestr(info, b"")
        for name in sorted(files):
            mode, data = files[name]
            info = zipfile.ZipInfo(prefix + name, stamp)
            info.create_system, info.compress_type, info.external_attr = 3, zipfile.ZIP_DEFLATED, (stat.S_IFREG | mode) << 16
            zf.writestr(info, data)


def write_tar_gz(path: Path, prefix: str, files: dict[str, tuple[int, bytes]], committed: int) -> None:
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=9) as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tf:
        def add(info: tarfile.TarInfo, data: bytes = b"") -> None:
            info.mtime, info.uid, info.gid, info.uname, info.gname = committed, 0, 0, "", ""
            tf.addfile(info, io.BytesIO(data) if info.isreg() else None)
        for name in sorted({prefix.rstrip("/")} | {prefix + str(p) for f in files for p in PurePosixPath(f).parents if str(p) != "."}):
            info = tarfile.TarInfo(name)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            add(info)
        for name in sorted(files):
            mode, data = files[name]
            info = tarfile.TarInfo(prefix + name)
            info.size, info.mode = len(data), mode
            add(info, data)


def read_members(path: Path) -> list[tuple[str, int, str]]:
    members = []
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for i in zf.infolist():
                mode = i.external_attr >> 16
                kind = "dir" if i.is_dir() else "file" if stat.S_ISREG(mode) else "other"
                members.append((i.filename, mode, kind))
    else:
        with tarfile.open(path, "r:gz") as tf:
            for m in tf.getmembers():
                members.append((m.name, m.mode | (stat.S_IFDIR if m.isdir() else stat.S_IFLNK if m.issym() else stat.S_IFREG if m.isreg() else 0),
                                "dir" if m.isdir() else "file" if m.isreg() else "other"))
    return members


def cmd_build(args) -> int:
    ok, _ = check_version(args.version)
    if not ok:
        raise BuildError(f"{args.version!r} is not a valid version (use MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-prerelease.N, no leading v)")
    repo = args.repo.resolve()
    commit = full_sha(repo, args.commit)
    committed = int(git(repo, "show", "-s", "--format=%ct", commit).stdout.decode().strip())
    rules = load_manifest(args.manifest.read_text())
    files, excluded = plan_files(repo, commit, rules)
    files[INFO_NAME] = (0o644, release_info(args.version, commit, committed))
    prefix = f"folderwise-{args.version}/"
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise BuildError(f"{out} must be empty")
    zip_path, tar_path = out / f"folderwise-{args.version}.zip", out / f"folderwise-{args.version}.tar.gz"
    write_zip(zip_path, prefix, files, committed)
    write_tar_gz(tar_path, prefix, files, committed)
    for archive in (zip_path, tar_path):
        problems = archive_errors(read_members(archive), prefix, set(files))
        if problems:
            raise BuildError(f"{archive.name} failed inspection:\n  " + "\n  ".join(problems))
    assets = {p.name: p.read_bytes() for p in (zip_path, tar_path)}
    (out / "SHA256SUMS").write_text(sums_text(assets))
    report = {
        "version": args.version, "commit": commit, "prefix": prefix,
        "files": {n: {"mode": f"{m:o}", "sha256": hashlib.sha256(d).hexdigest()} for n, (m, d) in sorted(files.items())},
        "excluded": excluded,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"built {prefix.rstrip('/')} from {commit}: {len(files)} files packaged, {len(excluded)} tracked files excluded")
    for name in sorted(os.listdir(out)):
        print(f"  {name}  {(out / name).stat().st_size} bytes")
    return 0


def cmd_verify_sums(args) -> int:
    expected = {f"folderwise-{args.version}.zip", f"folderwise-{args.version}.tar.gz", "SHA256SUMS"}
    present = {p.name for p in args.dir.iterdir()}
    if present != expected:
        raise BuildError(f"release assets must be exactly {sorted(expected)}, found {sorted(present)}")
    for line in (args.dir / "SHA256SUMS").read_text().splitlines():
        digest, _, name = line.partition("  ")
        if name not in expected or hashlib.sha256((args.dir / name).read_bytes()).hexdigest() != digest:
            raise BuildError(f"checksum mismatch or unexpected entry in SHA256SUMS: {line!r}")
    print("SHA256SUMS verified for both archives")
    return 0


def cmd_check_tree(args) -> int:
    report = json.loads(args.report.read_text())
    root = args.root.resolve()
    if root.name != report["prefix"].rstrip("/"):
        raise BuildError(f"extracted folder is {root.name}, expected {report['prefix']}")
    actual, problems = {}, []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath, name)
            if p.is_symlink():
                problems.append(f"{p.relative_to(root)}: symlink")
        for name in filenames:
            p = Path(dirpath, name)
            actual[p.relative_to(root).as_posix()] = p
    for rel in sorted(set(actual) - set(report["files"])):
        problems.append(f"{rel}: unexpected file after extraction")
    for rel, want in sorted(report["files"].items()):
        p = actual.get(rel)
        if p is None:
            problems.append(f"{rel}: missing after extraction")
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != want["sha256"]:
            problems.append(f"{rel}: content differs from the build")
        if bool(p.stat().st_mode & 0o100) != (want["mode"] == "755"):
            problems.append(f"{rel}: executable bit not preserved (expected mode {want['mode']})")
    for rel in (".gitignore", ".gitattributes", "_template/.docs.yaml", "_template/.gitignore", "_tools/framework-hooks/pre-commit", INFO_NAME):
        if rel not in actual:
            problems.append(f"{rel}: required file missing")
    if problems:
        raise BuildError("extracted archive does not match the build:\n  " + "\n  ".join(problems))
    print(f"{root.name}: {len(actual)} files match the build report (paths, hashes, executable bits, hidden files)")
    return 0


def cmd_resolve_commit(args) -> int:
    repo = args.repo.resolve()
    branch = f"origin/{args.default_branch}"
    commit = full_sha(repo, args.commit or branch)
    if git(repo, "merge-base", "--is-ancestor", commit, branch, check=False).returncode != 0:
        raise BuildError(f"{commit} is not reachable from {branch}; releases are built only from the default branch history")
    print(commit)
    return 0


def cmd_check_tag_free(args) -> int:
    repo = args.repo.resolve()
    if git(repo, "tag", "--list", args.tag).stdout.strip():
        raise BuildError(f"tag {args.tag} already exists locally")
    remote = git(repo, "ls-remote", "--tags", "origin", f"refs/tags/{args.tag}").stdout.strip()
    if remote:
        raise BuildError(f"tag {args.tag} already exists on origin; published releases are immutable, choose a new version")
    print(f"tag {args.tag} is free")
    return 0


def cmd_validate_version(args) -> int:
    ok, pre = check_version(args.version)
    if not ok:
        raise BuildError(f"{args.version!r} is not a valid version: use MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rc.1 (no leading 'v', no build metadata)")
    print(f"version={args.version}\ntag=v{args.version}\nprerelease={str(pre).lower()}")
    return 0


def cmd_notes(args) -> int:
    v, c = args.version, args.commit
    pre = check_version(v)[1]
    text = f"""## Folderwise {v}{' (pre-release)' if pre else ''}

Source commit: [`{c[:12]}`](https://github.com/TheLinuxGuy/folderwise/commit/{c}) (full SHA `{c}`).
Every file in the archives is a tracked file at that commit; `RELEASE-INFO.json` records the version and commit.

### Compatibility notes

_Maintainer: replace this line before publishing (supported Python, uv, operating systems, behavior changes)._

### Upgrade notes

_Maintainer: replace this line before publishing. Clone installs: `git pull --ff-only`. Archive installs: follow "Upgrading an archive install" in docs/framework-checkout.md; independent knowledge projects are never modified._

### Install

Download `folderwise-{v}.zip` or `folderwise-{v}.tar.gz` together with `SHA256SUMS`, verify, extract, and run the self-test as described in docs/framework-checkout.md ("Install from a release archive"). Cloning the repository is recommended if you want Git-based upgrades.

```bash
shasum -a 256 -c SHA256SUMS --ignore-missing
```

"""
    args.out.write_text(text)
    print(f"wrote {args.out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *flags):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        for flag, kw in flags:
            p.add_argument(flag, **kw)
        return p

    repo = ("--repo", dict(type=Path, default=REPO))
    add("validate-version", cmd_validate_version, ("version", {}))
    add("resolve-commit", cmd_resolve_commit, repo, ("--commit", dict(default="")), ("--default-branch", dict(default=DEFAULT_BRANCH)))
    add("check-tag-free", cmd_check_tag_free, repo, ("tag", {}))
    add("build", cmd_build, repo, ("--version", dict(required=True)), ("--commit", dict(required=True)),
        ("--manifest", dict(type=Path, default=MANIFEST)), ("--out", dict(type=Path, required=True)), ("--report", dict(type=Path, required=True)))
    add("verify-sums", cmd_verify_sums, ("--dir", dict(type=Path, required=True)), ("--version", dict(required=True)))
    add("check-tree", cmd_check_tree, ("--root", dict(type=Path, required=True)), ("--report", dict(type=Path, required=True)))
    add("notes", cmd_notes, ("--version", dict(required=True)), ("--commit", dict(required=True)), ("--out", dict(type=Path, required=True)))
    args = ap.parse_args()
    try:
        return args.fn(args)
    except BuildError as e:
        print(f"release_build: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
