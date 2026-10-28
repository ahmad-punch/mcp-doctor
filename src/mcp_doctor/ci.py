"""Generate a GitHub Actions workflow that runs mcp-doctor on every push."""

from __future__ import annotations

import shlex
from pathlib import Path

DEFAULT_WORKFLOW_PATH = Path(".github/workflows/mcp-doctor.yml")

_TEMPLATE = """\
name: mcp-doctor

on:
  push:
    branches: [main]
  pull_request:

jobs:
  mcp-doctor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Install mcp-doctor
        run: pip install mcp-doctor
      - name: Check MCP server
        run: mcp-doctor check --stdio {command} --smoke --fail-on {fail_on}
"""


def workflow(command: str, fail_on: str) -> str:
    """Return the workflow YAML for checking the server started by ``command``."""
    return _TEMPLATE.format(command=shlex.quote(command), fail_on=fail_on)


def write_workflow(path: Path, command: str, fail_on: str, force: bool) -> Path:
    """Write the workflow file, refusing to clobber an existing one unless ``force``."""
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite it or --output to pick another path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow(command, fail_on), encoding="utf-8")
    return path
