"""A small, well-described MCP server that passes every mcp-doctor rule that matters.

mcp-doctor check --stdio "python examples/clean_server.py" --smoke
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field

server = MCPServer(
    "tidy-notes",
    version="1.0.0",
    instructions="Read-only access to a small notebook. List notes first, then fetch one by name.",
)
_NOTES: dict[str, str] = {"welcome": "Thanks for trying tidy-notes."}

NoteName = Annotated[str, Field(description="Exact note name, as returned by list_notes.")]


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_notes() -> list[str]:
    """List the names of every note in the notebook, sorted alphabetically."""
    return sorted(_NOTES)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_note(name: NoteName) -> str:
    """Return the full text of one note. Fails if no note has that exact name."""
    return _NOTES[name]


@server.resource("notes://index", description="Newline-separated list of note names.")
def note_index() -> str:
    """Every note name, one per line."""
    return "\n".join(sorted(_NOTES))


@server.prompt(description="Ask the model to summarise one note in three bullet points.")
def summarize(name: Annotated[str, Field(description="Name of the note to summarise.")]) -> str:
    """Summarise a note."""
    return f"Summarise the note called {name} in three bullet points."


if __name__ == "__main__":
    server.run()
