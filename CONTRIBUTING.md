# Contributing to Folderwise

Folderwise combines shared conventions, templates, and CLI tools for knowledge humans read and agents help maintain. Improvements should keep that workflow understandable and portable.

Read `AGENTS.md` before changing the framework. Run `uv run _tools/selftest.py` before and after edits. A changed CLI, setting, or behavior needs a meaningful self-test and corresponding README update. Targeted sections can be run with `-k`, but the complete suite must pass before submitting.

Use fictional examples. Never include real personal documents, balances, account identifiers, claim records, credentials, machine-specific paths, or your local vault configuration. Keep topic repositories outside the framework Git index. Run `python3 _tools/framework_guard.py` after staging to verify that index.

The template's agent permissions are shipped defaults, not a promise of a security boundary. Explain permission changes and avoid broadening them as an incidental fix. Test tools through their normal CLI and hook workflow.

Open an issue to discuss larger changes. For a pull request, describe the concrete behavior change and validation. Contributions are made under the project's MIT License.

## Checks that run on every pull request

CI (`.github/workflows/ci.yml`) runs on every PR, on pushes to `main`, and on manual dispatch. It has no path filters, so documentation-only PRs run everything. It uses the read-only token, no secrets (fork PRs get none), SHA-pinned actions, job timeouts, and cancels superseded PR runs.

| Check | What it proves |
|---|---|
| `Self-test (linux-py3.10)`, `(linux-py3.15)`, `(macos-py3.15)` | the complete `selftest.py` suite on each platform, with the job's interpreter reaching every `uv` child process |
| `Coverage gate` | the suite under coverage; at least 85% production line coverage; Codecov upload |
| `Clean install (linux-py3.10)`, `(macos-py3.15)` | the documented clone-and-uv setup on a runner with an empty uv cache, then a fictional project through creation, stamping, lint, hook commit and hook rejection |
| `Framework index guard` | only approved framework paths are tracked |
| `Ruff` | definite errors only (`ruff.toml`: syntax errors, undefined names, unused imports and variables); no formatting rules |
| `Workflow validation` | actionlint and zizmor on the workflow files |
| `CI script tests` | unit tests for the packaging, coverage and workflow-policy scripts |
| `CI gate` | fails unless every job above succeeded (failed, cancelled and skipped all fail) |

The repository ruleset on `main` requires `CI gate` and `codecov/patch`. Native Windows is not tested or supported.

Changes to workflows, `.github/scripts/`, `.coveragerc`, `codecov.yml`, `ruff.toml`, `.gitignore` and `_tools/framework_guard.py` are listed by CODEOWNERS and flagged on the PR: they decide what CI enforces and what may enter the public index. A PR runs its own version of CI, so CI alone cannot stop a PR from weakening CI; a maintainer has to read those diffs. Do not lower a threshold or widen an exclusion to make a check pass.

## Reproduce CI locally

```bash
uv run _tools/selftest.py
uv run .github/scripts/ci_coverage.py
uvx ruff@0.17.2 check --config ruff.toml .
python3 _tools/framework_guard.py
uv run --no-project --with coverage==7.16.2 --with pyyaml==6.0.3 python -m unittest discover -s .github/scripts -v
```

Select an interpreter the way CI does with `UV_PYTHON=3.10 uv run _tools/selftest.py`; uv child processes inherit it. Clean-install and archive checks: `python3 .github/scripts/install_check.py --help`. They need a fresh clone or extraction, never your working checkout.

## Coverage policy and measurement scope

- **Overall:** at least 85% production **line** coverage, enforced directly by `ci_coverage.py` in GitHub Actions, independent of Codecov.
- **Changed code:** at least 90% of executable lines a PR changes, enforced by Codecov's `codecov/patch` status (required).
- **Branches:** collected and shown in the job summary and the 3-day coverage artifact; no branch threshold yet. Codecov receives line data only, because it counts a partially covered branch line as a miss, which would be a hidden branch threshold.
- **Scope:** every `.py` file under `_tools/` except `selftest.py`. Files nothing executes still count (as 0%). No third-party or generated code is under `_tools/`.
- **How it is measured:** the self-test runs temporary copies of the tools through `uv run` subprocesses and Git hooks, so wrapping `selftest.py` in `coverage run` would measure only the harness. `ci_coverage.py` puts a `sitecustomize` shim on `PYTHONPATH`, so coverage starts in every Python process, including uv's isolated script environments. Each process writes its own data file; `.coveragerc` `[paths]` maps `docs-selftest-*` copies back to `_tools/`; reports are built after the temporary folders are gone. The run fails unless the data proves real execution: every CLI's `__main__` entry and the Git pre-commit hook path were executed, nothing was recorded outside `_tools/`, and enough processes were measured.
- Tests must cover real behavior and failure paths through the normal CLI and hook workflow. No artificial tests, `pragma: no cover`, or broad omits.

## Codecov

- Install the Codecov GitHub app for the repository and add its upload token as the Actions secret `CODECOV_TOKEN` (and as a Dependabot secret, so Dependabot PRs also report). Pushes to `main` use the token to establish the baseline.
- **Fork PRs** run with no secrets. `codecov-action` v4+ prefixes the fork branch name, which lets Codecov accept a tokenless upload for a public repository; uploads from fork PRs are therefore not required to succeed in the job itself, while the required `codecov/patch` status still has to appear. Never switch this workflow to `pull_request_target` to get a token.
- `codecov.yml`: `codecov/patch` target 90%; `codecov/project` is informational (the overall gate lives in Actions).
- Artifacts are kept 3 days (coverage report) or 7 days (release assets in a draft preparation), and Actions minutes and storage are free for public repositories on standard hosted runners, so the expected recurring cost is $0.

## Releases

Releases are prepared by a maintainer, never automatically. See [docs/maintainers.md](docs/maintainers.md) for the step-by-step: dispatch **Prepare release**, review the draft, publish by hand, and recover from a bad release (a published release is immutable; the fix is a new version).

