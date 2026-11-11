"""SARIF output: structure, locations, and the ``--format sarif`` command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from conftest import EXAMPLES
from mcp_doctor.cli import app
from mcp_doctor.models import Finding, Report, Severity, Snapshot
from mcp_doctor.rules import all_rules, get_rule
from mcp_doctor.sarif import SourceFile, find_source, to_sarif
from mcp_doctor.targets import Target, TransportKind, stdio_target

runner = CliRunner()
ROOT = EXAMPLES.parent
MESSY = f"{sys.executable} {EXAMPLES / 'messy_server.py'}"
SARIF_LEVELS = {"none", "note", "warning", "error"}


def assert_valid_sarif(log: dict[str, Any]) -> None:
    """Check the properties the SARIF 2.1.0 schema requires, plus the ones GitHub relies on."""
    assert log["version"] == "2.1.0"
    assert log["$schema"].endswith("sarif-2.1.0.json")
    assert isinstance(log["runs"], list)
    assert log["runs"]
    for run in log["runs"]:
        driver = run["tool"]["driver"]
        assert driver["name"] == "mcp-doctor"
        rule_ids = [rule["id"] for rule in driver["rules"]]
        assert len(rule_ids) == len(set(rule_ids))
        for rule in driver["rules"]:
            assert rule["shortDescription"]["text"]
            assert rule["help"]["text"]
            assert rule["defaultConfiguration"]["level"] in SARIF_LEVELS
        for invocation in run["invocations"]:
            assert isinstance(invocation["executionSuccessful"], bool)
        for result in run["results"]:
            assert result["message"]["text"]
            assert result["level"] in SARIF_LEVELS
            assert rule_ids[result["ruleIndex"]] == result["ruleId"]
            assert result["locations"]
            for location in result["locations"]:
                assert location["logicalLocations"][0]["fullyQualifiedName"]
                physical = location.get("physicalLocation")
                if physical is not None:
                    assert not Path(physical["artifactLocation"]["uri"]).is_absolute()
                    assert physical["region"]["startLine"] >= 1


def _finding(rule_id: str, target: str, severity: Severity | None = None) -> Finding:
    rule = get_rule(rule_id)
    return Finding(rule=rule_id, severity=severity or rule.severity, target=target, message="m", hint=rule.hint)


def _report(*findings: Finding, name: str = "notes") -> Report:
    return Report(target=name, connected=True, snapshot=Snapshot(server_name=name), findings=list(findings))


def _sarif(reports: list[Report], sources: list[SourceFile | None] | None = None) -> dict[str, Any]:
    log: dict[str, Any] = json.loads(to_sarif(reports, sources or [None] * len(reports), all_rules()))
    assert_valid_sarif(log)
    return log


def test_every_rule_is_a_reporting_descriptor() -> None:
    driver = _sarif([_report()])["runs"][0]["tool"]["driver"]

    assert [rule["id"] for rule in driver["rules"]] == [rule.id for rule in all_rules()]
    t001 = next(rule for rule in driver["rules"] if rule["id"] == "T001")
    assert t001["defaultConfiguration"]["level"] == "error"
    assert t001["help"]["text"] == get_rule("T001").hint


def test_results_carry_level_logical_location_and_fingerprint() -> None:
    report = _report(_finding("T005", "tool:get_note"), _finding("T002", "tool:get_note", Severity.ERROR))
    results = _sarif([report])["runs"][0]["results"]

    assert [(r["ruleId"], r["level"]) for r in results] == [("T005", "note"), ("T002", "error")]
    logical = results[0]["locations"][0]["logicalLocations"][0]
    assert logical == {"name": "get_note", "fullyQualifiedName": "notes/tool:get_note", "kind": "function"}
    assert results[0]["message"]["text"] == "tool:get_note: m"
    assert "physicalLocation" not in results[0]["locations"][0]
    assert len({next(iter(r["partialFingerprints"].values())) for r in results}) == 2


def test_physical_location_points_at_the_definition() -> None:
    source = SourceFile(uri="server.py", lines=("import x", "", "def get_note(name):", "    pass"))
    report = _report(_finding("T006", "tool:get_note"), _finding("S001", "server"))
    results = _sarif([report], [source])["runs"][0]["results"]

    physical = [r["locations"][0]["physicalLocation"] for r in results]
    assert physical[0] == {
        "artifactLocation": {"uri": "server.py", "uriBaseId": "%SRCROOT%"},
        "region": {"startLine": 3},
    }
    assert physical[1]["region"]["startLine"] == 1


def test_config_source_points_at_the_server_entry() -> None:
    lines = ("{", '  "mcpServers": {', '    "other": {"command": "a"},', '    "notes": {"command": "b"}', "  }", "}")
    assert SourceFile(uri=".mcp.json", lines=lines, anchor="notes").line_for("get_note") == 4


def test_name_match_respects_word_boundaries() -> None:
    source = SourceFile(uri="s.py", lines=("def get_note_v2():", "def get_note():"))
    assert source.line_for("get_note") == 2


def test_unreachable_server_becomes_a_tool_notification() -> None:
    down = Report(target="python gone.py", connected=False, connection_error="boom")
    run = _sarif([_report(name="up"), down])["runs"][0]

    assert run["invocations"][0]["executionSuccessful"] is False
    note = run["invocations"][0]["toolExecutionNotifications"][0]
    assert note["level"] == "error"
    assert "python gone.py" in note["message"]["text"]


def test_multiple_servers_are_named_in_messages() -> None:
    reports = [_report(_finding("S001", "server"), name="a"), _report(_finding("S001", "server"), name="b")]
    texts = [r["message"]["text"] for r in _sarif(reports)["runs"][0]["results"]]
    assert texts == ["a server: m", "b server: m"]


def test_find_source_prefers_script_then_config(tmp_path: Path) -> None:
    script = tmp_path / "server.py"
    script.write_text("print()\n", encoding="utf-8")
    config = tmp_path / ".mcp.json"
    config.write_text('{"mcpServers": {"notes": {}}}', encoding="utf-8")

    from_script = find_source(stdio_target(f"{sys.executable} {script}"), tmp_path, config)
    assert from_script is not None
    assert from_script.uri == "server.py"
    assert from_script.anchor is None

    from_config = find_source(stdio_target("npx -y pkg", name="notes"), tmp_path, config)
    assert from_config is not None
    assert (from_config.uri, from_config.anchor) == (".mcp.json", "notes")

    assert find_source(stdio_target("npx -y pkg"), tmp_path) is None
    http = Target(name="remote", transport=TransportKind.HTTP, url="http://localhost:1/mcp")
    assert find_source(http, tmp_path) is None


def test_find_source_ignores_files_outside_the_root(tmp_path: Path) -> None:
    script = tmp_path / "server.py"
    script.write_text("print()\n", encoding="utf-8")
    assert find_source(stdio_target(f"{sys.executable} {script}"), tmp_path / "repo") is None


def test_explicit_source_file_wins(tmp_path: Path) -> None:
    source = find_source(stdio_target("npx -y pkg"), tmp_path, override=Path("src/index.ts"))
    assert source is not None
    assert source.uri == "src/index.ts"


def test_cli_writes_sarif_for_the_example_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--format", "sarif"])

    assert result.exit_code == 1
    log = json.loads(result.stdout)
    assert_valid_sarif(log)
    results = log["runs"][0]["results"]
    assert "T001" in {r["ruleId"] for r in results}
    uris = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results}
    assert uris == {"examples/messy_server.py"}
    get_note_lines = {
        r["locations"][0]["physicalLocation"]["region"]["startLine"]
        for r in results
        if r["locations"][0]["logicalLocations"][0]["name"] == "get_note"
    }
    source_lines = (EXAMPLES / "messy_server.py").read_text(encoding="utf-8").splitlines()
    assert [source_lines[line - 1] for line in get_note_lines] == ["def get_note(name: str) -> str:"]


def test_json_flag_conflicts_with_sarif_format() -> None:
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--json", "--format", "sarif"])

    assert result.exit_code == 2
    assert "--json conflicts with --format sarif" in result.output
