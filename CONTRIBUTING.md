# Contributing to Folderwise

Folderwise combines shared conventions, templates, and CLI tools for knowledge humans read and agents help maintain. Improvements should keep that workflow understandable and portable.

Read `AGENTS.md` before changing the framework. Run `uv run _tools/selftest.py` before and after edits. A changed CLI, setting, or behavior needs a meaningful self-test and corresponding README update. Targeted sections can be run with `-k`, but the complete suite must pass before submitting.

Use fictional examples. Never include real personal documents, balances, account identifiers, claim records, credentials, machine-specific paths, or your local vault configuration. Keep topic repositories outside the framework Git index. Run `python3 _tools/framework_guard.py` after staging to verify that index.

The template's agent permissions are shipped defaults, not a promise of a security boundary. Explain permission changes and avoid broadening them as an incidental fix. Test tools through their normal CLI and hook workflow.

Open an issue to discuss larger changes. For a pull request, describe the concrete behavior change and validation. Contributions are made under the project's MIT License.
