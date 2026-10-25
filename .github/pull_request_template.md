## What changed and why

## Validation

- [ ] `uv run _tools/selftest.py` passes (the complete suite)
- [ ] Changed behavior has a self-test and a README entry
- [ ] Only fictional examples; no real documents, identifiers, credentials, or machine-specific paths
- [ ] `python3 _tools/framework_guard.py` passes after staging

## Needs careful review (check if touched)

- [ ] Workflows, `.github/scripts/`, `.coveragerc`, `codecov.yml`, `ruff.toml`
- [ ] `.gitignore` allowlist or `_tools/framework_guard.py`
- [ ] Coverage thresholds or exclusions (state the reason; do not lower thresholds to pass)
