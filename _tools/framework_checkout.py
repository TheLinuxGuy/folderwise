#!/usr/bin/env python3
"""Configure a pull-only framework checkout beside independent knowledge repositories.

  python3 _tools/framework_checkout.py --minimal --dry-run   preview local setup
  python3 _tools/framework_checkout.py --minimal             keep only runtime files
  python3 _tools/framework_checkout.py --update              enforce minimal setup and pull
  python3 _tools/framework_checkout.py --full                restore all tracked files

Only tracked root directories beginning with '_' are included. Root Git rules, agent
instructions, README.md, LICENSE and uv.toml stay present by default. No knowledge project is changed.
Requires Git 2.25+ and Python 3.10+. Archives without Git metadata cannot use this tool.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = ('/_*/', '/.gitignore', '/.gitattributes', '/AGENTS.md', '/README.md', '/LICENSE', '/uv.toml')
OPTIONAL_FILES = ('README.md', 'LICENSE')
OMIT_KEY = 'folderwise.omittedRootFiles'
SETTINGS = {
    'core.hooksPath': '_tools/framework-hooks',
    'pull.ff': 'only',
    'submodule.recurse': 'false',
    'fetch.recurseSubmodules': 'false',
    'folderwise.pullOnly': 'true',
    'push.default': 'nothing',
    'remote.origin.pushurl': 'no-push://folderwise-pull-only',
}


def git(*args: str, data: str | None = None) -> str:
    result = subprocess.run(['git', '-C', str(ROOT), *args], input=data,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'git {args[0]} failed')
    return result.stdout


def preflight(remember_deletions: bool) -> set[str]:
    if Path(git('rev-parse', '--show-toplevel').strip()).resolve() != ROOT:
        raise RuntimeError('Run the tool from a framework checkout with its own Git root.')
    git('rev-parse', '--verify', 'HEAD')
    git('remote', 'get-url', 'origin')
    changes = git('status', '--porcelain', '-z', '--untracked-files=no').split('\0')
    deleted = {entry[3:] for entry in changes if remember_deletions
               and entry[:3] == ' D ' and entry[3:] in OPTIONAL_FILES}
    allowed = {' D ' + name for name in deleted}
    if any(entry and entry not in allowed for entry in changes):
        raise RuntimeError('Tracked files have local changes. Commit or save them before changing the checkout.')
    for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = Path(git('rev-parse', '--git-path', name).strip())
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            raise RuntimeError('Finish the current Git operation before changing the checkout.')
    return deleted


def excluded_directories() -> list[str]:
    return [name for name in git('ls-tree', '-d', '--name-only', '-z', 'HEAD').split('\0')
            if name and not name.startswith('_')]


def check_leftovers() -> None:
    # Restrict the search to upstream framework directories. Never walk knowledge projects.
    for name in excluded_directories():
        for options in ((), ('--ignored',)):
            if git('ls-files', '--others', '--exclude-standard', *options, '-z', '--', name):
                raise RuntimeError(f'{name}/ contains untracked or ignored files. Move those files elsewhere first; nothing was deleted.')


def minimal(omitted: set[str]) -> None:
    patterns = [pattern for pattern in PATTERNS if pattern[1:] not in omitted]
    git('sparse-checkout', 'set', '--no-cone', '--stdin', data='\n'.join(patterns) + '\n')
    git('config', '--local', '--replace-all', OMIT_KEY, ' '.join(sorted(omitted)))
    for key, value in SETTINGS.items():
        git('config', '--local', '--replace-all', key, value)


def verify() -> None:
    remaining = [name for name in excluded_directories() if (ROOT / name).exists()]
    if remaining:
        raise RuntimeError(f'Excluded directories remain: {", ".join(remaining)}. Inspect local contents; nothing will be deleted automatically.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--minimal', action='store_true', help='enable the minimal pull-only checkout')
    mode.add_argument('--update', action='store_true', help='enable minimal checkout, then pull --ff-only')
    mode.add_argument('--full', action='store_true', help='restore full checkout; retain pull-only safeguards')
    parser.add_argument('--dry-run', action='store_true', help='check prerequisites and print the plan without changing anything')
    parser.add_argument('--omit', choices=OPTIONAL_FILES, nargs='+', default=[],
                        help='persistently omit these optional root files in minimal mode')
    parser.add_argument('--include', choices=OPTIONAL_FILES, nargs='+', default=[],
                        help='restore optional root files previously omitted')
    args = parser.parse_args()
    if args.full and (args.omit or args.include):
        parser.error('--omit/--include require --minimal or --update')
    if set(args.omit) & set(args.include):
        parser.error('a file cannot be both included and omitted')
    try:
        deleted = preflight(remember_deletions=not args.full)
        omitted = set(git('config', '--local', '--default', '', '--get', OMIT_KEY).split())
        if not omitted <= set(OPTIONAL_FILES):
            raise RuntimeError(f'Invalid {OMIT_KEY}; only README.md and LICENSE may be omitted.')
        omitted = (omitted | deleted | set(args.omit)) - set(args.include)
        if not args.full:
            check_leftovers()
        if args.update:
            git('symbolic-ref', '--quiet', 'HEAD')
            git('rev-parse', '--verify', '@{upstream}')
        if args.full:
            print('Restore all tracked files and clear optional-file omissions. Pull-only safeguards remain configured.')
        else:
            print('Minimal checkout patterns:\n' + '\n'.join(p for p in PATTERNS if p[1:] not in omitted))
            if omitted:
                print('Remember omitted root files: ' + ', '.join(sorted(omitted)))
            print('Configure local pull-only safeguards; independent project repositories stay untouched.')
            if args.update:
                print('Then run git pull --ff-only and reapply the sparse rules.')
        if args.dry_run:
            return 0
        if args.full:
            git('sparse-checkout', 'disable')
            git('config', '--local', '--replace-all', OMIT_KEY, '')
        else:
            minimal(omitted)
            restore = sorted(deleted & set(args.include))
            if restore:
                git('restore', '--worktree', '--', *restore)
            if args.update:
                print(git('pull', '--ff-only'), end='')
                git('sparse-checkout', 'reapply')
            verify()
        print('Done. Run uv run _tools/selftest.py to verify the installation.')
        return 0
    except (RuntimeError, OSError) as exc:
        print(f'framework checkout: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
