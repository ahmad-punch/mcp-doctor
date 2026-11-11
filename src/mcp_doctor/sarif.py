"""Render reports as SARIF 2.1.0 for GitHub code scanning and other SARIF viewers.

Every registered rule becomes a ``reportingDescriptor`` and every finding a ``result``.
GitHub only annotates results that point at a file in the repository, so each result gets
a physical location when mcp-doctor can tell which file defines the server: the file
passed with ``--source-file``, the script in the server's command line, or the ``--config``
file. The line is a best-effort match on the tool, resource, or prompt name (or, in a
client config, the server's entry). Every result also names its target as a logical
location, so nothing is lost when no file is known.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mcp_doctor import __version__
from mcp_doctor.models import Finding, JSONDict, Report, Severity
from mcp_doctor.rules.registry import Rule
from mcp_doctor.targets import Target, TransportKind

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFORMATION_URI = "https://github.com/ahmad-punch/mcp-doctor"
FINGERPRINT_KEY = "mcpDoctorFinding/v1"

SCRIPT_SUFFIXES = frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".go", ".rb", ".php", ".java"})

LEVELS = {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "note"}
_LOGICAL_KIND = {"tool": "function", "prompt": "function", "resource": "resource", "template": "resource"}


@dataclass(frozen=True)
class SourceFile:
    """A repository file that results point at.

    ``anchor`` is set for client config files: every result then points at the line that
    defines that server. Otherwise each result points at the first line naming its target.
    """

    uri: str
    lines: tuple[str, ...] = ()
    anchor: str | None = None

    def line_for(self, item: str) -> int:
        """The 1-based line to annotate for ``item``, or 1 when no line mentions it."""
        if self.anchor is not None:
            pattern = re.compile(re.escape(json.dumps(self.anchor)) + r"\s*:")
        elif item:
            pattern = re.compile(rf"(?<![\w-]){re.escape(item)}(?![\w-])")
        else:
            return 1
        return next((number for number, line in enumerate(self.lines, 1) if pattern.search(line)), 1)


def find_source(
    target: Target, root: Path, config: Path | None = None, override: Path | None = None
) -> SourceFile | None:
    """Pick the file a server's results should point at, relative to the repository ``root``."""
    if override is not None:
        return _load(override, root) or SourceFile(uri=override.as_posix())
    script = _script_in_command(target, root)
    if script is not None:
        return script
    return _load(config, root, anchor=target.name) if config is not None else None


def to_sarif(reports: Sequence[Report], sources: Sequence[SourceFile | None], rules: Sequence[Rule]) -> str:
    """Serialise reports as one SARIF run. ``sources`` lines up with ``reports``; ``rules`` covers every finding."""
    index = {rule.id: position for position, rule in enumerate(rules)}
    qualify = len(reports) > 1
    results: list[JSONDict] = []
    for report, source in zip(reports, sources, strict=True):
        server = _server_label(report)
        seen: Counter[str] = Counter()
        for item in report.findings:
            key = f"{server}\0{item.rule}\0{item.target}"
            seen[key] += 1
            results.append(_result(item, server, source, index, _fingerprint(key, seen[key]), qualify))
    run: JSONDict = {
        "tool": {
            "driver": {
                "name": "mcp-doctor",
                "version": __version__,
                "semanticVersion": __version__,
                "informationUri": INFORMATION_URI,
                "rules": [_descriptor(rule) for rule in rules],
            }
        },
        "invocations": [_invocation(reports)],
        "results": results,
    }
    return json.dumps({"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": [run]}, indent=2)


def _descriptor(rule: Rule) -> JSONDict:
    return {
        "id": rule.id,
        "shortDescription": {"text": rule.title},
        "help": {"text": rule.hint},
        "helpUri": f"{INFORMATION_URI}#rules",
        "defaultConfiguration": {"level": LEVELS[rule.severity]},
        "properties": {"tags": ["mcp", rule.scope.value]},
    }


def _result(
    item: Finding, server: str, source: SourceFile | None, index: dict[str, int], fingerprint: str, qualify: bool
) -> JSONDict:
    kind, _, name = item.target.partition(":")
    location: JSONDict = {}
    if source is not None:
        location["physicalLocation"] = {
            "artifactLocation": {"uri": source.uri, "uriBaseId": "%SRCROOT%"},
            "region": {"startLine": source.line_for(name)},
        }
    location["logicalLocations"] = [
        {
            "name": name or server,
            "fullyQualifiedName": f"{server}/{item.target}",
            "kind": _LOGICAL_KIND.get(kind, "module"),
        }
    ]
    prefix = f"{server} " if qualify else ""
    return {
        "ruleId": item.rule,
        "ruleIndex": index[item.rule],
        "level": LEVELS[item.severity],
        "message": {"text": f"{prefix}{item.target}: {item.message}"},
        "locations": [location],
        "partialFingerprints": {FINGERPRINT_KEY: fingerprint},
    }


def _invocation(reports: Sequence[Report]) -> JSONDict:
    notifications = [
        {"level": "error", "message": {"text": f"could not connect to {report.target}: {report.connection_error}"}}
        for report in reports
        if not report.connected
    ]
    return {"executionSuccessful": not notifications, "toolExecutionNotifications": notifications}


def _server_label(report: Report) -> str:
    if report.snapshot is not None and report.snapshot.server_name:
        return report.snapshot.server_name
    return report.target


def _fingerprint(key: str, occurrence: int) -> str:
    return hashlib.sha256(f"{key}\0{occurrence}".encode()).hexdigest()


def _script_in_command(target: Target, root: Path) -> SourceFile | None:
    if target.transport is not TransportKind.STDIO:
        return None
    base = Path(target.cwd) if target.cwd else Path()
    for part in [target.command or "", *target.args]:
        path = base / part
        if path.suffix in SCRIPT_SUFFIXES and path.is_file():
            source = _load(path, root)
            if source is not None:
                return source
    return None


def _load(path: Path, root: Path, anchor: str | None = None) -> SourceFile | None:
    """Read ``path`` as a source file if it lives under ``root``; files elsewhere cannot be annotated."""
    try:
        relative = path.resolve().relative_to(root.resolve())
        text = path.read_text(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return None
    return SourceFile(uri=relative.as_posix(), lines=tuple(text.splitlines()), anchor=anchor)
