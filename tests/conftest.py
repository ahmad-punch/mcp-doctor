from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from mcp_doctor.models import Snapshot

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))


def good_tool(name: str = "get_note", **overrides: Any) -> dict[str, Any]:
    """A tool definition that passes every rule; tests override one field at a time."""
    tool: dict[str, Any] = {
        "name": name,
        "description": "Return the full text of one note by its exact name.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Exact note name."}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    }
    tool.update(overrides)
    return tool


@pytest.fixture
def make_snapshot() -> Any:
    def build(**fields: Any) -> Snapshot:
        fields.setdefault("instructions", "Notes server.")
        fields.setdefault("tools", [good_tool()])
        return Snapshot(**fields)

    return build
