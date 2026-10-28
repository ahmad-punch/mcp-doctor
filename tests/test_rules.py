"""One positive case per static rule, plus a clean snapshot that triggers nothing."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import good_tool
from mcp_doctor.models import Severity, Snapshot, Timings
from mcp_doctor.rules import all_rules, get_rule, lint

_SCHEMA = good_tool()["inputSchema"]

CASES: dict[str, dict[str, Any]] = {
    "T001": {"tools": [good_tool(description="")]},
    "T002": {"tools": [good_tool(description="Gets it.")]},
    "T003": {"tools": [good_tool(inputSchema={"type": "string"})]},
    "T004": {"tools": [good_tool(inputSchema={"type": "object"})]},
    "T005": {"tools": [good_tool(inputSchema={**_SCHEMA, "additionalProperties": True})]},
    "T006": {"tools": [good_tool(inputSchema={"type": "object", "properties": {"q": {"type": "string"}}})]},
    "T007": {"tools": [good_tool(inputSchema={**_SCHEMA, "required": ["name", "ghost"]})]},
    "T008": {"tools": [good_tool(name="get note!")]},
    "T009": {"tools": [good_tool(), good_tool()]},
    "T010": {"tools": [good_tool("get_note"), good_tool("getNote")]},
    "T011": {"tools": [good_tool(f"tool_{i}") for i in range(41)]},
    "T012": {"tools": [good_tool("delete_note", annotations={})]},
    "T013": {"tools": [good_tool(outputSchema={"type": "object", "properties": {"n": {"type": 5}}})]},
    "T014": {"tools": [good_tool(inputSchema={**_SCHEMA, "required": "name"})]},
    "S001": {"instructions": None},
    "S002": {"tools": []},
    "C001": {"timings": Timings(initialize_ms=6000)},
    "C002": {"timings": Timings(tools_list_ms=1500)},
    "C003": {"list_errors": {"prompts/list": "Method not found (code -32601)"}},
    "R001": {"resources": [{"uri": "not a uri", "name": "x", "description": "Something useful."}]},
    "R002": {"resource_templates": [{"uriTemplate": "notes://{bad name}", "name": "x", "description": "Notes."}]},
    "R003": {"resources": [{"uri": "notes://all", "name": "all"}]},
    "R004": {"resources": [{"uri": "notes://a", "name": "a", "description": "A note."}] * 2},
    "P001": {"prompts": [{"name": "summarize"}]},
    "P002": {"prompts": [{"name": "summarize", "description": "Summarise.", "arguments": [{"name": "note"}]}]},
    "P003": {"prompts": [{"name": "summarize", "description": "Summarise {note}."}]},
    "P004": {
        "prompts": [
            {
                "name": "summarize",
                "description": "Summarise a note.",
                "arguments": [{"name": "n", "description": "Note."}, {"name": "n", "description": "Note."}],
            }
        ]
    },
}


def test_every_static_rule_has_a_case() -> None:
    static = {rule.id for rule in all_rules() if rule.check is not None}
    assert static == set(CASES)


def test_clean_snapshot_has_no_findings(make_snapshot: Any) -> None:
    assert lint(make_snapshot()) == []


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_fires(rule_id: str, make_snapshot: Any) -> None:
    findings = lint(make_snapshot(**CASES[rule_id]))

    matching = [f for f in findings if f.rule == rule_id]
    assert matching, f"{rule_id} did not fire; got {[f.rule for f in findings]}"
    assert all(f.severity is get_rule(rule_id).severity for f in matching)


@pytest.mark.parametrize(
    "uri",
    ["file:///tmp/notes.txt", "notes://all", "https://example.com/a%20b", "urn:isbn:0451450523"],
)
def test_valid_resource_uris_pass(uri: str, make_snapshot: Any) -> None:
    snapshot = make_snapshot(resources=[{"uri": uri, "name": "n", "description": "A resource."}])
    assert [f.rule for f in lint(snapshot)] == []


@pytest.mark.parametrize("name", ["read_file", "listNotes", "query-db", "readOnly"])
def test_read_only_names_do_not_need_annotations(name: str, make_snapshot: Any) -> None:
    snapshot = make_snapshot(tools=[good_tool(name, annotations={})])
    assert "T012" not in {f.rule for f in lint(snapshot)}


def test_findings_sorted_by_severity() -> None:
    snapshot = Snapshot(tools=[good_tool(description=""), good_tool("deleteAll", annotations={})])
    severities = [f.severity.rank for f in lint(snapshot)]
    assert severities == sorted(severities)
    assert lint(snapshot)[0].severity is Severity.ERROR


def test_ignore_skips_rule(make_snapshot: Any) -> None:
    assert lint(make_snapshot(instructions=None), ignore={"S001"}) == []
