# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [0.1.0] - 2026-10-28

### Added
- `mcp-doctor check` for stdio (`--stdio`), Streamable HTTP and SSE (`--url`, `--transport`, `--header`) servers, and servers defined in Claude Desktop, Claude Code, Cursor, or `.mcp.json` configs (`--config`, `--server`).
- 27 static rules across tools, resources, prompts, server metadata, and latency, plus 3 smoke-test rules.
- `--smoke` calls tools that need no arguments under a timeout, skipping tools that look destructive; `--args` supplies arguments for others.
- 0-100 health score, rich terminal report, `--json`, `--fail-on`, `--rules`, and `--ignore`.
- `mcp-doctor rules` to list every rule and `mcp-doctor init-ci` to write a GitHub Actions workflow.
- Example servers in `examples/` that fail and pass the checks.
