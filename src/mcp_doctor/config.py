"""Read server definitions from the config files MCP clients already use.

Supported shapes:

* ``{"mcpServers": {...}}`` used by Claude Desktop, Cursor, Windsurf, and project ``.mcp.json``.
* Claude Code's ``~/.claude.json``: a top-level ``mcpServers`` plus per-project
  ``projects.<path>.mcpServers``.

Each entry is either ``{"command", "args", "env", "cwd"}`` (stdio) or
``{"type": "http" | "sse", "url", "headers"}``. ``${VAR}`` and ``${VAR:-default}``
references are expanded from the environment, as Claude Code does.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp_doctor.targets import Target, TransportKind

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(Exception):
    """Raised when a config file cannot be used. The message says what to do next."""


def load_servers(path: Path, environ: Mapping[str, str] | None = None) -> dict[str, Target]:
    """Return every server defined in ``path``, keyed by name."""
    data = _read_json(path)
    env = os.environ if environ is None else environ
    servers: dict[str, Target] = {}
    for name, entry in _server_entries(data):
        servers[name] = _to_target(name, entry, env, path)
    if not servers:
        raise ConfigError(
            f"{path} defines no MCP servers; expected an 'mcpServers' object "
            "(Claude Desktop, Cursor, .mcp.json) or Claude Code's ~/.claude.json layout"
        )
    return servers


def select_server(servers: dict[str, Target], name: str, path: Path) -> Target:
    """Pick one server by name, or explain which names exist."""
    if name in servers:
        return servers[name]
    available = ", ".join(sorted(servers)) or "(none)"
    raise ConfigError(f"no server named {name!r} in {path}; available: {available}")


def default_config_paths(home: Path | None = None, cwd: Path | None = None) -> list[Path]:
    """Config files that common MCP clients read, in the order mcp-doctor looks at them."""
    home = home or Path.home()
    cwd = cwd or Path.cwd()
    candidates = [
        cwd / ".mcp.json",
        cwd / ".cursor" / "mcp.json",
        home / ".claude.json",
        home / ".cursor" / "mcp.json",
        _claude_desktop_config(home),
    ]
    return [path for path in candidates if path.is_file()]


def _claude_desktop_config(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        text = path.expanduser().read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc.strerror}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object at the top level")
    return data


def _server_entries(data: dict[str, Any]) -> list[tuple[str, Any]]:
    entries: list[tuple[str, Any]] = list(_mapping(data.get("mcpServers")).items())
    seen = {name for name, _ in entries}
    for project, settings in _mapping(data.get("projects")).items():
        for name, entry in _mapping(_mapping(settings).get("mcpServers")).items():
            qualified = name if name not in seen else f"{name}@{project}"
            seen.add(qualified)
            entries.append((qualified, entry))
    return entries


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_target(name: str, entry: Any, env: Mapping[str, str], path: Path) -> Target:
    if not isinstance(entry, dict):
        raise ConfigError(f"server {name!r} in {path} must be a JSON object")
    kind = str(entry.get("type", "")).lower()
    if "url" in entry:
        return Target(
            name=name,
            transport=TransportKind.SSE if kind == "sse" else TransportKind.HTTP,
            url=_expand(str(entry["url"]), env),
            headers={k: _expand(str(v), env) for k, v in _mapping(entry.get("headers")).items()},
        )
    if "command" in entry:
        return Target(
            name=name,
            transport=TransportKind.STDIO,
            command=_expand(str(entry["command"]), env),
            args=[_expand(str(arg), env) for arg in entry.get("args") or []],
            env={k: _expand(str(v), env) for k, v in _mapping(entry.get("env")).items()},
            cwd=_expand(str(entry["cwd"]), env) if entry.get("cwd") else None,
        )
    raise ConfigError(f"server {name!r} in {path} has neither 'command' (stdio) nor 'url' (http/sse)")


def _expand(value: str, env: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        var, default = match.group(1), match.group(2)
        if var in env:
            return env[var]
        if default is not None:
            return default
        raise ConfigError(f"config references ${{{var}}} but it is not set; export it or add a :-default")

    return _ENV_REF.sub(replace, value)
