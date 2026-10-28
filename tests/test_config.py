from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_doctor.config import ConfigError, load_servers, select_server
from mcp_doctor.targets import TargetError, TransportKind, parse_headers, stdio_target, url_target


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_claude_desktop_layout_with_env_expansion(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "files": {"command": "npx", "args": ["-y", "pkg", "${ROOT}"], "env": {"TOKEN": "${TOKEN:-none}"}},
                "remote": {"type": "http", "url": "https://example.com/mcp", "headers": {"Authorization": "${AUTH}"}},
            }
        },
    )
    servers = load_servers(path, environ={"ROOT": "/data", "AUTH": "Bearer x"})

    assert servers["files"].args == ["-y", "pkg", "/data"]
    assert servers["files"].env == {"TOKEN": "none"}
    assert servers["remote"].transport is TransportKind.HTTP
    assert servers["remote"].headers == {"Authorization": "Bearer x"}


def test_claude_code_project_servers(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "mcpServers": {"a": {"command": "a"}},
            "projects": {"/repo": {"mcpServers": {"a": {"command": "b"}, "sse": {"type": "sse", "url": "http://x"}}}},
        },
    )
    servers = load_servers(path, environ={})

    assert set(servers) == {"a", "a@/repo", "sse"}
    assert servers["sse"].transport is TransportKind.SSE


def test_errors_tell_user_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_servers(tmp_path / "missing.json")
    with pytest.raises(ConfigError, match="defines no MCP servers"):
        load_servers(_write(tmp_path, {}))
    with pytest.raises(ConfigError, match="is not set"):
        load_servers(_write(tmp_path, {"mcpServers": {"a": {"command": "${NOPE}"}}}), environ={})
    servers = load_servers(_write(tmp_path, {"mcpServers": {"a": {"command": "a"}}}), environ={})
    with pytest.raises(ConfigError, match="available: a"):
        select_server(servers, "b", tmp_path)


def test_target_parsing() -> None:
    target = stdio_target('python "my server.py" --flag')
    assert target.command == "python"
    assert target.args == ["my server.py", "--flag"]
    assert parse_headers(["Authorization: Bearer t"]) == {"Authorization": "Bearer t"}
    with pytest.raises(TargetError):
        url_target("localhost:8000")
    with pytest.raises(TargetError):
        parse_headers(["no-colon"])
