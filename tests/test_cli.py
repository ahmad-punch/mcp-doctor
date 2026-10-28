from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import EXAMPLES
from mcp_doctor.cli import app
from mcp_doctor.smoke import SmokeArgsError, parse_tool_args

runner = CliRunner()
MESSY = f"{sys.executable} {EXAMPLES / 'messy_server.py'}"
CLEAN = f"{sys.executable} {EXAMPLES / 'clean_server.py'}"


def test_json_report_and_fail_on() -> None:
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--json"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)["reports"][0]
    assert report["connected"] is True
    assert "T001" in {f["rule"] for f in report["findings"]}
    assert 0 <= report["score"] < 100


def test_clean_server_passes_with_fail_on_warning() -> None:
    result = runner.invoke(app, ["check", "--stdio", CLEAN, "--fail-on", "warning"])

    assert result.exit_code == 0, result.stdout
    assert "Score" in result.stdout


def test_rules_option_limits_checks() -> None:
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--json", "--rules", "S001", "--fail-on", "never"])

    assert result.exit_code == 0
    assert {f["rule"] for f in json.loads(result.stdout)["reports"][0]["findings"]} == {"S001"}


def test_unknown_rule_is_a_usage_error() -> None:
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--ignore", "Z999"])

    assert result.exit_code == 2
    assert "mcp-doctor rules" in result.output


def test_config_check(tmp_path: Path) -> None:
    config = tmp_path / ".mcp.json"
    command, *args = CLEAN.split()
    config.write_text(json.dumps({"mcpServers": {"tidy": {"command": command, "args": args}}}), encoding="utf-8")

    result = runner.invoke(app, ["check", "--config", str(config), "--server", "tidy", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["reports"][0]["snapshot"]["serverName"] == "tidy-notes"


def test_conflicting_targets() -> None:
    result = runner.invoke(app, ["check", "--stdio", "x", "--url", "http://localhost:1"])
    assert result.exit_code == 2


def test_rules_listing() -> None:
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == 0
    assert "T001" in result.stdout
    assert "X002" in result.stdout


def test_init_ci_writes_workflow(tmp_path: Path) -> None:
    output = tmp_path / "wf.yml"
    args = ["init-ci", "--stdio", "node build/index.js", "--output", str(output), "--fail-on", "warning"]

    assert runner.invoke(app, args).exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert "mcp-doctor check --stdio 'node build/index.js' --smoke --fail-on warning" in text
    assert runner.invoke(app, args).exit_code == 2
    assert runner.invoke(app, [*args, "--force"]).exit_code == 0


def test_parse_tool_args() -> None:
    assert parse_tool_args(['get_note={"name": "welcome"}']) == {"get_note": {"name": "welcome"}}


@pytest.mark.parametrize("bad", ["nojson", "x=[1]", "x={bad"])
def test_parse_tool_args_rejects_bad_input(bad: str) -> None:
    with pytest.raises(SmokeArgsError):
        parse_tool_args([bad])
