# mcp-doctor

Health check and linter for Model Context Protocol servers: connect, list everything, flag what will confuse a model, and score it.

[![CI](https://github.com/ahmad-punch/mcp-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmad-punch/mcp-doctor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

## Demo

A real run against the reference `server-everything`:

```text
$ mcp-doctor check --stdio "npx -y @modelcontextprotocol/server-everything"
╭─────────────────────────────────────────── mcp-doctor ───────────────────────────────────────────╮
│ mcp-servers/everything 2.0.1  protocol 2026-07-28                                                │
│ target      npx -y @modelcontextprotocol/server-everything                                       │
│ listed      22 tools, 7 resources, 3 templates, 4 prompts                                        │
│ latency     initialize 1282 ms, tools/list 4 ms                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
Findings                                                                                            
┏━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity ┃ Rule ┃ Target                              ┃ Problem                                  ┃
┡━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ warning  │ T006 │ tool:get-resource-reference         │ parameters without description:          │
│          │      │                                     │ resourceType                             │
│ info     │ T005 │ tool:echo                           │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:get-annotated-message          │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:get-resource-links             │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:get-resource-reference         │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:get-structured-content         │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:get-sum                        │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:gzip-file-as-resource          │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:simulate-research-query        │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-list-changed           │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-long-running-operation │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-resource-update        │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-sampling-request       │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-sampling-request-async │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
│ info     │ T005 │ tool:trigger-url-elicitation        │ additionalProperties is unrestricted     │
│          │      │                                     │ while properties are declared            │
└──────────┴──────┴─────────────────────────────────────┴──────────────────────────────────────────┘
How to fix
  T006  Give every property a description; the model sees nothing else about what to pass.
  T005  Set "additionalProperties": false so typos in argument names fail loudly instead of being 
ignored.
Score 93/100  (0 error, 1 warning, 14 info)
```

## Why

An MCP server can pass its own unit tests and still be hard for a model to use: tools with no description, parameters nobody explained, a `required` list pointing at a renamed field, a `delete_*` tool with no destructive hint, a tool that hangs when called. Clients surface these as vague failures much later. mcp-doctor talks to the server the way a client does and reports each problem with a rule ID, a severity, and the fix, so you can catch it locally or in CI.

## Install

```bash
pip install mcp-doctor        # or: pipx install mcp-doctor
```

From a clone (Python 3.10+):

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/mcp-doctor check --stdio ".venv/bin/python examples/messy_server.py" --smoke
```

## Usage

```bash
# A server you start with a command (stdio)
mcp-doctor check --stdio "npx -y @modelcontextprotocol/server-everything"

# A running Streamable HTTP or SSE server
mcp-doctor check --url http://localhost:8000/mcp --header "Authorization: Bearer $TOKEN"
mcp-doctor check --url http://localhost:8000/sse --transport sse

# A server already defined in Claude Desktop, Claude Code, Cursor, or .mcp.json
mcp-doctor check --config ~/.claude.json --server github
mcp-doctor check --config .mcp.json            # every server in the file

# Also call each tool that needs no arguments, with a per-call timeout
mcp-doctor check --stdio "python server.py" --smoke --smoke-timeout 5
mcp-doctor check --stdio "python server.py" --smoke --args 'get_note={"name": "welcome"}'

# CI-friendly output and gating
mcp-doctor check --stdio "python server.py" --json > report.json
mcp-doctor check --stdio "python server.py" --fail-on warning --ignore T005,S001
mcp-doctor check --stdio "python server.py" --rules T001,T006

# List rules; write a GitHub Actions workflow
mcp-doctor rules
mcp-doctor init-ci --stdio "node build/index.js"
```

Exit codes: `0` clean (below `--fail-on`), `1` findings at or above `--fail-on` (default `error`), `2` bad arguments, `3` server unreachable.

Smoke calls skip tools that have required parameters (unless you pass `--args`), and tools whose name or annotations say they change state (`delete_*`, `destructiveHint: true`), so a health check never deletes your data.

### Rules

| ID | Severity | Checks for |
| --- | --- | --- |
| C001 | warning | Initialize took longer than 5s |
| C002 | warning | tools/list took longer than 1s |
| C003 | error | A list request for an advertised capability failed |
| P001 | warning | Prompt has no description |
| P002 | info | Prompt argument without description |
| P003 | warning | Prompt references an undeclared argument |
| P004 | error | Prompt declares the same argument twice |
| R001 | error | Resource URI is not a valid URI |
| R002 | error | Resource template is not a valid RFC 6570 template |
| R003 | info | Resource or template without description |
| R004 | error | Duplicate resource URI |
| S001 | info | Server sends no `instructions` |
| S002 | warning | Server exposes no tools, resources, or prompts |
| T001 | error | Tool has no description |
| T002 | warning | Tool description shorter than 20 characters |
| T003 | error | Input schema is not `type: "object"` |
| T004 | warning | Input schema has no `properties` |
| T005 | info | Input schema allows arbitrary extra properties |
| T006 | warning | Tool parameters without descriptions |
| T007 | error | `required` names a property that does not exist |
| T008 | error | Tool name is not portable (`^[a-zA-Z0-9_-]{1,64}$`) |
| T009 | error | Duplicate tool name |
| T010 | warning | Near-duplicate tool names |
| T011 | warning | More than 40 tools |
| T012 | warning | Mutating tool without readOnlyHint/destructiveHint |
| T013 | error | Output schema is not valid JSON Schema |
| T014 | error | Input schema is not valid JSON Schema |
| X001 | error | Tool call failed with a protocol error |
| X002 | error | Tool call timed out |
| X003 | warning | Tool returned isError for a valid call |

Scoring: 100 minus 10 per error, 4 per warning, 1 per info, counting at most three findings per rule so one systemic issue cannot hide everything else.

## How it works

1. **Connect** with the official `mcp` Python SDK over stdio, Streamable HTTP, or SSE, timing the handshake.
2. **Snapshot** `tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` (following pagination) as raw wire-format JSON, so malformed payloads are seen as sent.
3. **Lint** the snapshot with a registry of rules. Each rule is a record (ID, severity, title, fix hint) plus a pure function over the snapshot, which is what makes `--rules`, `--ignore`, the table above, and the unit tests all derive from one definition.
4. **Smoke** (optional) calls safe tools with `{}` under a timeout and turns protocol errors, timeouts, and `isError` results into X-series findings.
5. **Report** as rich tables or JSON, with a 0-100 score and an exit code for CI.

See [docs/DESIGN.md](docs/DESIGN.md) for the main trade-off.

## Roadmap

- `--watch` mode that re-checks a local server on file changes.
- SARIF output so findings show up as GitHub code-scanning annotations.
- Per-repo `mcp-doctor.toml` for rule overrides and smoke arguments.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
New rules need an entry in `tests/test_rules.py` that makes them fire.

## License

MIT, see [LICENSE](LICENSE).
