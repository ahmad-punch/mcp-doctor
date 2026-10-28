# Contributing

Thanks for helping. Setup takes a minute:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest -q
```

## Adding a rule

1. Pick the module in `src/mcp_doctor/rules/` that matches the scope (tools, resources, prompts, server).
2. Register it with `@tool_rule`, `@resource_rule`, `@prompt_rule`, or `@rule`, giving it the next free ID, a severity, a short title, and a fix hint that tells the server author what to change.
3. Yield a message for each violation; the engine attaches severity and hint.
4. Add a case to `CASES` in `tests/test_rules.py`. The suite fails if a rule has no case.

Keep pull requests focused, and describe how you verified the change against a real server.
