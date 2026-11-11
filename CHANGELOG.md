# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [0.2.0] - 2026-11-11

### Added
- `--format sarif` writes SARIF 2.1.0 for GitHub code scanning. Every rule is a `reportingDescriptor` and every finding a `result`, located at the server script from `--stdio`, the server's entry in `--config`, or `--source-file`, plus a logical location naming the tool, resource, or prompt.
- `mcp-doctor.toml`, or `[tool.mcp-doctor]` in `pyproject.toml`, to disable rules, change their severity, and supply smoke-test arguments. Found in the working directory or passed with `--settings`; invalid files exit 2 with the key and how to fix it.
- README section with a GitHub Actions job that uploads the SARIF report with `github/codeql-action/upload-sarif`.

### Changed
- `--json` is now shorthand for `--format json`.
- Exit code 2 also covers an invalid settings file.
- Python 3.10 installs `tomli` to read TOML; 3.11 and later use the standard library.

## [0.1.0] - 2026-10-28

### Added
- `mcp-doctor check` for stdio (`--stdio`), Streamable HTTP and SSE (`--url`, `--transport`, `--header`) servers, and servers defined in Claude Desktop, Claude Code, Cursor, or `.mcp.json` configs (`--config`, `--server`).
- 27 static rules across tools, resources, prompts, server metadata, and latency, plus 3 smoke-test rules.
- `--smoke` calls tools that need no arguments under a timeout, skipping tools that look destructive; `--args` supplies arguments for others.
- 0-100 health score, rich terminal report, `--json`, `--fail-on`, `--rules`, and `--ignore`.
- `mcp-doctor rules` to list every rule and `mcp-doctor init-ci` to write a GitHub Actions workflow.
- Example servers in `examples/` that fail and pass the checks.
