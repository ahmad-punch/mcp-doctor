"""Per-repository settings from ``mcp-doctor.toml`` or ``[tool.mcp-doctor]`` in ``pyproject.toml``.

The file holds what would otherwise be repeated on every command line::

    [rules]
    disable = ["T005", "S001"]

    [rules.severity]
    T002 = "info"
    X003 = "error"

    [smoke.args]
    get_note = { name = "welcome" }

Settings are validated up front and every error names the key and says how to fix it,
because a typo in a CI-only file otherwise shows up as a rule that quietly still fires.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_doctor.models import JSONDict, Severity
from mcp_doctor.rules import known_ids

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SETTINGS_FILE = "mcp-doctor.toml"
PYPROJECT_FILE = "pyproject.toml"
_PYPROJECT_PREFIX = "tool.mcp-doctor."
_SEVERITIES = ", ".join(f'"{severity.value}"' for severity in Severity)


class SettingsError(Exception):
    """Raised when a settings file cannot be read or is invalid. The message says how to fix it."""


@dataclass(frozen=True)
class Settings:
    """Rule overrides and smoke-test arguments for one repository. The defaults change nothing."""

    path: Path | None = None
    disabled: frozenset[str] = frozenset()
    severity: dict[str, Severity] = field(default_factory=dict)
    smoke_args: dict[str, JSONDict] = field(default_factory=dict)


@dataclass(frozen=True)
class _Source:
    """Where a table came from, so errors can name the file and the full key."""

    path: Path
    prefix: str

    def error(self, key: str, problem: str) -> SettingsError:
        return SettingsError(f"{self.path}: {self.prefix}{key} {problem}")


def discover_settings(directory: Path) -> Settings:
    """Load ``mcp-doctor.toml`` from ``directory``, else ``[tool.mcp-doctor]`` from its pyproject.toml.

    Returns empty settings when neither exists, so a repository without a file behaves as before.
    """
    candidate = directory / SETTINGS_FILE
    if candidate.is_file():
        return read_settings(candidate)
    pyproject = directory / PYPROJECT_FILE
    if pyproject.is_file():
        table = _pyproject_table(pyproject, _read_toml(pyproject))
        if table is not None:
            return _parse(table, _Source(pyproject, _PYPROJECT_PREFIX))
    return Settings()


def read_settings(path: Path) -> Settings:
    """Load settings from an explicit file: a pyproject.toml or a standalone ``mcp-doctor.toml``."""
    data = _read_toml(path)
    if path.name != PYPROJECT_FILE:
        return _parse(data, _Source(path, ""))
    table = _pyproject_table(path, data)
    if table is None:
        raise SettingsError(
            f"{path} has no [tool.mcp-doctor] table; add one, or put the settings in {SETTINGS_FILE} instead"
        )
    return _parse(table, _Source(path, _PYPROJECT_PREFIX))


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise SettingsError(f"settings file not found: {path}") from exc
    except OSError as exc:
        raise SettingsError(f"could not read {path}: {exc.strerror}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"{path} is not valid TOML: {exc}") from exc


def _pyproject_table(path: Path, data: dict[str, Any]) -> dict[str, Any] | None:
    tool = data.get("tool")
    table = tool.get("mcp-doctor") if isinstance(tool, dict) else None
    if table is not None and not isinstance(table, dict):
        raise SettingsError(f"{path}: tool.mcp-doctor must be a table; write it as [tool.mcp-doctor]")
    return table


def _parse(data: dict[str, Any], source: _Source) -> Settings:
    _check_keys(data, {"rules", "smoke"}, source, "")
    rules = _table(data, "rules", source, "")
    _check_keys(rules, {"disable", "severity"}, source, "rules.")
    smoke = _table(data, "smoke", source, "")
    _check_keys(smoke, {"args"}, source, "smoke.")
    return Settings(
        path=source.path,
        disabled=_disabled(rules.get("disable", []), source),
        severity=_severity(_table(rules, "severity", source, "rules."), source),
        smoke_args=_smoke_args(_table(smoke, "args", source, "smoke."), source),
    )


def _check_keys(table: dict[str, Any], allowed: set[str], source: _Source, prefix: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise source.error(
            f"{prefix}{unknown[0]}", f"is not a setting mcp-doctor knows; use one of: {', '.join(sorted(allowed))}"
        )


def _table(parent: dict[str, Any], key: str, source: _Source, prefix: str) -> dict[str, Any]:
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise source.error(f"{prefix}{key}", f"must be a table; write it as [{source.prefix}{prefix}{key}]")
    return value


def _disabled(value: Any, source: _Source) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise source.error("rules.disable", 'must be a list of rule IDs, e.g. disable = ["T005", "S001"]')
    ids = frozenset(item.strip().upper() for item in value)
    unknown = sorted(ids - known_ids())
    if unknown:
        listed = ", ".join(unknown)
        raise source.error("rules.disable", f"names unknown rule(s) {listed}; run `mcp-doctor rules` to list them")
    return ids


def _severity(table: dict[str, Any], source: _Source) -> dict[str, Severity]:
    known = known_ids()
    overrides: dict[str, Severity] = {}
    for key, value in table.items():
        rule_id = key.strip().upper()
        if rule_id not in known:
            raise source.error(f"rules.severity.{key}", "is not a rule ID; run `mcp-doctor rules` to list them")
        try:
            overrides[rule_id] = Severity(value.strip().lower() if isinstance(value, str) else value)
        except ValueError:
            raise source.error(f"rules.severity.{key}", f"must be one of {_SEVERITIES}, got {value!r}") from None
    return overrides


def _smoke_args(table: dict[str, Any], source: _Source) -> dict[str, JSONDict]:
    for name, value in table.items():
        key = f"smoke.args.{name}"
        if not isinstance(value, dict):
            raise source.error(key, f'must be a table of arguments, e.g. {name} = {{ name = "welcome" }}')
        try:
            json.dumps(value)
        except TypeError:
            raise source.error(key, "may only hold strings, numbers, booleans, arrays and tables, not dates") from None
    return dict(table)
