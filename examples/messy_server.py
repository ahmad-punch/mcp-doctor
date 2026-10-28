"""An MCP server with the mistakes mcp-doctor looks for. Run it with mcp-doctor to see the report.

    mcp-doctor check --stdio "python examples/messy_server.py" --smoke
"""

from __future__ import annotations

import time

from mcp.server.mcpserver import MCPServer

server = MCPServer("messy-notes", version="0.0.1")
_NOTES: dict[str, str] = {"welcome": "hello"}


@server.tool()
def list_notes() -> list[str]:
    return sorted(_NOTES)


@server.tool()
def getNote(name: str) -> str:  # noqa: N802 - the camelCase name is the point
    """Get a note."""
    return _NOTES[name]


@server.tool()
def get_note(name: str) -> str:
    """Return the full text of a note, given its exact name."""
    return _NOTES[name]


@server.tool()
def delete_note(name: str) -> str:
    """Delete a note permanently. There is no undo."""
    _NOTES.pop(name, None)
    return f"deleted {name}"


@server.tool()
def sync_notes() -> str:
    """Synchronise notes with the remote store and report how many changed."""
    raise RuntimeError("remote store is not configured")


@server.tool()
def rebuild_index() -> str:
    """Rebuild the full-text search index over every note in the store."""
    time.sleep(3)
    return "index rebuilt"


@server.resource("notes://all")
def all_notes() -> str:
    return "\n".join(_NOTES)


@server.prompt()
def summarize(note: str) -> str:
    return f"Summarise this note: {note}"


if __name__ == "__main__":
    server.run()
