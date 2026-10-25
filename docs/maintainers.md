# Maintainer guide: CI, merge protection and releases

For people with admin rights on the GitHub repository. Contributors only need [CONTRIBUTING.md](../CONTRIBUTING.md).

## One-time GitHub setup

Do these once. Each is something the repository files cannot do for themselves.

1. **Codecov.** Sign in at codecov.io with GitHub, install the Codecov GitHub app for `TheLinuxGuy/folderwise` (free for public repositories), copy the repository upload token, and add it as an Actions secret named `CODECOV_TOKEN` (Settings > Secrets and variables > Actions). Add the same value under *Dependabot* secrets, otherwise Dependabot PRs cannot upload and `codecov/patch` never appears on them. Confirm that `codecov.yml` is picked up (Codecov shows the config on the repository page).
2. **Actions policy** (Settings > Actions > General): workflow permissions *Read repository contents* (the workflows also declare their own minimal permissions); *Require approval for all outside collaborators* (or at least first-time contributors) for fork PR workflows; do not enable "Send write tokens to workflows from pull requests" or "Send secrets to workflows from pull requests".
3. **Release immutability** (Settings > Releases > enable release immutability). This applies only to releases published afterwards. It can also be set with `gh api repos/TheLinuxGuy/folderwise/immutable-releases --method PUT` (read it back with the same path and no method; `enabled` must be `true`). Enable it before the first release is published.
4. **Merge protection** (below), applied only after the first successful CI run on `main` so the check names exist.

## Required checks and the ruleset

The default-branch ruleset requires pull requests (with **zero** required approvals, because this is a solo-maintained repository), the status checks `CI gate` (GitHub Actions) and `codecov/patch` (Codecov), blocks force pushes and deletion, uses branches that are up to date with `main`, and has **no bypass actors**.

`CI gate` is an aggregate: it `needs` every other job and fails if any of them failed, was cancelled, or was skipped. A new CI job must be added to its `needs` list (a unit test in `.github/scripts/test_ci_scripts.py` fails otherwise), so the single required name stays stable when matrix cells change.

Apply the ruleset with an authenticated `gh` (admin token) once the checks have run on `main`. The check names are final:

```bash
gh api repos/TheLinuxGuy/folderwise/rulesets --method POST --input - <<'JSON'
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "do_not_enforce_on_create": false,
      "required_status_checks": [
        {"context": "CI gate", "integration_id": 15368},
        {"context": "codecov/patch"}]}},
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ]
}
JSON
```

`15368` is the GitHub Actions app id, so only Actions can satisfy `CI gate`. `codecov/patch` is a commit status; it has no integration id here. Verify rather than assume:

```bash
gh api repos/TheLinuxGuy/folderwise/rulesets
gh api repos/TheLinuxGuy/folderwise/rules/branches/main
```

The ruleset was first applied with `CI gate` only. Add `codecov/patch` (append `{"context": "codecov/patch"}` to `required_status_checks` with `gh api repos/TheLinuxGuy/folderwise/rulesets/RULESET_ID --method PUT`) only after you have seen it reported on a documentation-only PR and a fork PR (see "Validating the system"); requiring a status that never reports blocks every merge. Until the ruleset is active, protection is **not** in force, whatever the files say.

### Reviewing changes to the guard rails

CODEOWNERS and the PR template flag workflows, `.github/scripts/`, `.coveragerc`, `codecov.yml`, `ruff.toml`, `.gitignore`, `_tools/framework_guard.py` and the self-test harness. The workflow policy unit tests and `CI gate` catch accidents, not intent: a PR that edits CI is judged by its own edited CI. Read those diffs before merging.

## Validating the system

Safe, repeatable demonstrations; use throwaway branches and close the PRs without merging, then delete the branches.

| Claim | How to see it |
|---|---|
| A failing test fails the required check | branch that breaks one `check(...)` in `_tools/selftest.py`; `Self-test` and `CI gate` go red |
| Overall coverage below 85% fails | `uv run .github/scripts/ci_coverage.py --fail-under 99` fails locally; on a PR, remove a covering test section |
| Changed-code coverage below 90% fails | PR adding an untested function to `_tools/docslib.py`; `codecov/patch` fails while the overall gate still passes |
| Documentation-only PRs complete | PR touching only `README.md`; every check, including `codecov/patch`, reports |
| Fork PRs work safely | PR from a fork of the repository; checks run with a read-only token, no secrets, tokenless Codecov upload |
| Archives pass installation tests | the **Prepare release** run; both formats on Linux and macOS |
| Private paths stay out | `selftest.py -k ci_allowlist` and `release_build.py` unit tests |

## Releases

Releases are manual. Nothing is built or published when a PR merges.

### Prepare

1. Make sure `main` has the commit you want and that CI is green on it.
2. Actions > **Prepare release** > Run workflow from `main`. Inputs: `version` (`1.2.3`, or a pre-release such as `1.2.3-rc.1`; no leading `v`) and optionally `commit` (a full SHA reachable from `main`; empty means the tip of `main`).
3. The workflow rejects a bad version, a commit not on `main`, an existing tag, and an existing draft or published release for that version. It runs the full CI against that exact commit (without the Codecov upload), builds `folderwise-VERSION.zip`, `folderwise-VERSION.tar.gz` and `SHA256SUMS` from the files **tracked at that commit** and approved by `.github/release-manifest.txt`, inspects the archive paths, extracts both archives in fresh directories on Linux and macOS with an empty uv cache, runs the archive installation test (self-test, fictional project, document workflow, hook commit and rejection, framework ignoring the project), and only then creates a **draft** release with all assets attached and the notes generated from merged PRs. It never publishes.

Archives contain `RELEASE-INFO.json` (version, tag, source commit, commit date). It is generated at build time, never tracked, and ignored by the framework repository.

### Review and publish

1. Open the draft from the run summary. Check the assets (exactly three), the source commit, and the pre-release flag for a pre-release version.
2. Replace the *Compatibility notes* and *Upgrade notes* placeholders, and skim the generated "What's Changed".
3. Confirm release immutability is enabled (one-time setup, above). Publish the draft by hand. Publishing creates the `vVERSION` tag at the recorded commit; with immutability on, the tag and assets can no longer change.

### Recover

- **Before publishing:** delete the draft (and re-run **Prepare release**) or edit its notes. Nothing is public.
- **After publishing:** do not try to replace assets. Fix the problem on `main`, then prepare a new version (for example `1.2.4`) and say in its upgrade notes that it supersedes the bad one. A bad published release can be marked as a pre-release or its notes edited to warn users; its tag and assets stay.
- **A failed run** leaves no release behind unless it got as far as the draft. Look for stale drafts under Releases before re-running; a stale draft for the same version makes the workflow refuse.

### What a release does not do

No PyPI publication, no standalone executables, no automatic releases. Archive users upgrade as described in [framework updates and existing folders](framework-checkout.md#upgrading-an-archive-install).

## Free-tier assumptions

Public repository, standard GitHub-hosted runners (Linux and macOS), no larger or self-hosted runners, Codecov's free tier for public repositories, no paid GitHub features. Actions artifacts are short-lived: coverage report 3 days, release assets from a preparation run 7 days (the published copies live on the release itself). No Actions cache is used (dependency installs are small and a clean cache is part of what the install checks prove).

## Updating pinned versions

Actions are pinned to full commit SHAs with the version in a comment; Dependabot proposes updates weekly. Pinned tools: uv (`UV_VERSION` in both workflows), ruff, zizmor, actionlint (checksum-verified download) and coverage.py (`ci_coverage.py` script metadata). When Python releases a new stable version, add it to the matrix next to `3.15` (the workflow files list it explicitly so a missing interpreter fails loudly instead of silently testing something else).

<!-- demo: documentation-only change -->
