#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# ///
"""Fail unless this uv-launched process runs the interpreter the job selected.

The self-test starts every tool through `uv run`, so the interpreter chosen for the job (UV_PYTHON) must
reach those child processes. Run it as `EXPECT_PYTHON=3.10 uv run .github/scripts/check_interpreter.py`.
"""
import os
import sys

want = os.environ.get("EXPECT_PYTHON", "")
got = f"{sys.version_info.major}.{sys.version_info.minor}"
print(f"interpreter: {sys.executable}\nversion: {sys.version.split()[0]}\nUV_PYTHON: {os.environ.get('UV_PYTHON', '')}")
if not want:
    sys.exit("check_interpreter: set EXPECT_PYTHON to the job's Python version, for example 3.10")
if got != want:
    sys.exit(f"check_interpreter: uv child process runs Python {got}, expected {want}")
print(f"ok: uv child processes run Python {got}")
