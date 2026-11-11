"""Per-repository settings: parsing, validation messages, and their effect on a check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import messy_server
import pytest
from mcp import Client
from typer.testing import CliRunner

from conftest import EXAMPLES
from mcp_doctor.cli import app
from mcp_doctor.doctor import CheckOptions, check_client
from mcp_doctor.models import Severity, SmokeStatus
from mcp_doctor.settings import Settings, SettingsError, discover_settings, read_settings

runner = CliRunner()
MESSY = f"{sys.executable} {EXAMPLES / 'messy_server.py'}"

FULL = """
[rules]
disable = ["t005", "S001"]

[rules.severity]
T002 = "info"
X003 = "Error"

[smoke.args]
get_note = { name = "welcome" }
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_every_setting(tmp_path: Path) -> None:
    path = _write(tmp_path, "mcp-doctor.toml", FULL)

    assert read_settings(path) == Settings(
        path=path,
        disabled=frozenset({"T005", "S001"}),
        severity={"T002": Severity.INFO, "X003": Severity.ERROR},
        smoke_args={"get_note": {"name": "welcome"}},
    )


def test_pyproject_table(tmp_path: Path) -> None:
    text = '[project]\nname = "x"\n\n[tool.mcp-doctor.rules]\ndisable = ["S001"]\n'
    path = _write(tmp_path, "pyproject.toml", text)

    assert read_settings(path).disabled == {"S001"}
    assert discover_settings(tmp_path).disabled == {"S001"}


def test_discovery_prefers_mcp_doctor_toml(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", '[tool.mcp-doctor.rules]\ndisable = ["S001"]\n')
    toml = _write(tmp_path, "mcp-doctor.toml", '[rules]\ndisable = ["T005"]\n')

    settings = discover_settings(tmp_path)
    assert (settings.path, settings.disabled) == (toml, {"T005"})


def test_no_settings_file_changes_nothing(tmp_path: Path) -> None:
    assert discover_settings(tmp_path) == Settings()
    _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')
    assert discover_settings(tmp_path) == Settings()


def test_explicit_pyproject_without_table(tmp_path: Path) -> None:
    path = _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')
    with pytest.raises(SettingsError, match=r"no \[tool.mcp-doctor\] table; add one"):
        read_settings(path)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[rules\n", r"not valid TOML: .*line 1"),
        ("[rule]\n", r"rule is not a setting mcp-doctor knows; use one of: rules, smoke"),
        ("[rules]\ndisabled = []\n", r"rules.disabled is not a setting .* use one of: disable, severity"),
        ('[rules]\ndisable = "T005"\n', r'rules.disable must be a list of rule IDs, e.g. disable = \["T005"'),
        ('[rules]\ndisable = ["Z999"]\n', r"rules.disable names unknown rule\(s\) Z999; run `mcp-doctor rules`"),
        ('rules = "all"\n', r"rules must be a table; write it as \[rules\]"),
        ('[rules.severity]\nZ999 = "info"\n', r"rules.severity.Z999 is not a rule ID"),
        ('[rules.severity]\nT002 = "low"\n', r'rules.severity.T002 must be one of "error", "warning", "info", got'),
        (
            '[smoke.args]\nget_note = "welcome"\n',
            r"smoke.args.get_note must be a table of arguments, e.g. get_note = \{",
        ),
        ("[smoke.args]\nget_note = { when = 2026-01-01 }\n", r"smoke.args.get_note may only hold .* not dates"),
    ],
)
def test_errors_name_the_key_and_the_fix(tmp_path: Path, text: str, message: str) -> None:
    path = _write(tmp_path, "mcp-doctor.toml", text)
    with pytest.raises(SettingsError, match=message) as info:
        read_settings(path)
    assert str(info.value).startswith(str(path))


def test_pyproject_errors_use_the_full_key(tmp_path: Path) -> None:
    path = _write(tmp_path, "pyproject.toml", '[tool.mcp-doctor.rules]\ndisable = "S001"\n')
    with pytest.raises(SettingsError, match=r"tool.mcp-doctor.rules.disable must be a list"):
        read_settings(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="settings file not found"):
        read_settings(tmp_path / "mcp-doctor.toml")


async def test_severity_overrides_change_findings_and_score() -> None:
    baseline = await check_client(Client(messy_server.server), "messy", CheckOptions())
    options = CheckOptions(severity={"T001": Severity.INFO})
    report = await check_client(Client(messy_server.server), "messy", options)

    assert {f.severity for f in report.findings if f.rule == "T001"} == {Severity.INFO}
    assert report.score > baseline.score
    severities = [f.severity.rank for f in report.findings]
    assert severities == sorted(severities)


def test_cli_applies_discovered_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "mcp-doctor.toml", '[rules]\ndisable = ["S001"]\n\n[rules.severity]\nT001 = "warning"\n')
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["check", "--stdio", MESSY, "--json"])

    assert result.exit_code == 0, result.output
    findings = json.loads(result.stdout)["reports"][0]["findings"]
    assert "S001" not in {f["rule"] for f in findings}
    assert {f["severity"] for f in findings if f["rule"] == "T001"} == {"warning"}


def test_rules_option_overrides_disable(tmp_path: Path) -> None:
    settings = _write(tmp_path, "mcp-doctor.toml", '[rules]\ndisable = ["S001"]\n')

    result = runner.invoke(
        app, ["check", "--stdio", MESSY, "--json", "--settings", str(settings), "--rules", "S001", "--fail-on", "never"]
    )

    assert {f["rule"] for f in json.loads(result.stdout)["reports"][0]["findings"]} == {"S001"}


def test_cli_reports_invalid_settings(tmp_path: Path) -> None:
    settings = _write(tmp_path, "mcp-doctor.toml", '[rules]\ndisable = ["Z999"]\n')

    result = runner.invoke(app, ["check", "--stdio", MESSY, "--settings", str(settings)])

    assert result.exit_code == 2
    assert "rules.disable names unknown rule(s) Z999" in " ".join(result.output.split())


def test_example_settings_supply_smoke_args() -> None:
    settings = ["--settings", str(EXAMPLES / "mcp-doctor.toml")]
    smoke = ["--smoke", "--smoke-timeout", "1", "--args", 'get_note={"name": "missing"}']
    result = runner.invoke(app, ["check", "--stdio", MESSY, "--json", *settings, *smoke])

    report = json.loads(result.stdout)["reports"][0]
    statuses = {r["tool"]: r["status"] for r in report["smoke"]}
    assert statuses["getNote"] == SmokeStatus.OK.value
    assert statuses["get_note"] == SmokeStatus.TOOL_ERROR.value  # --args wins over the settings file
    assert {f["severity"] for f in report["findings"] if f["rule"] == "T010"} == {"error"}
