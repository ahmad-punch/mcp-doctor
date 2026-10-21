"""Rules about tools: descriptions, input/output schemas, names, and annotations."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator

from mcp_doctor.models import JSONDict, Severity, Snapshot
from mcp_doctor.rules.registry import Scope, Violation, rule, tool_rule
from mcp_doctor.rules.schema import properties_of, required_of, schema_error

MIN_DESCRIPTION_LENGTH = 20
MAX_TOOL_COUNT = 40
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

MUTATING_VERBS = frozenset(
    {
        "delete", "remove", "rm", "write", "send", "pay", "drop", "destroy", "purge",
        "truncate", "overwrite", "transfer", "kill", "terminate", "update", "edit",
        "move", "rename", "create", "post", "publish", "deploy", "execute", "exec",
    }
)  # fmt: skip

_WORD_BOUNDARY = re.compile(r"[^a-zA-Z0-9]+|(?<=[a-z0-9])(?=[A-Z])")


def _description(tool: JSONDict) -> str:
    value = tool.get("description")
    return value.strip() if isinstance(value, str) else ""


def name_tokens(name: str) -> list[str]:
    """Split a tool name into lowercase words on separators and camelCase boundaries."""
    return [token.lower() for token in _WORD_BOUNDARY.split(name) if token]


def suggests_mutation(name: str) -> bool:
    """True when any word in the tool name is a verb that usually changes state."""
    return any(token in MUTATING_VERBS for token in name_tokens(name))


def _normalised(name: str) -> str:
    return re.sub(r"[\s_.-]", "", name).lower()


@tool_rule(
    "T001",
    Severity.ERROR,
    "Tool has no description",
    "Add a description saying what the tool does and when a model should pick it.",
)
def tool_without_description(tool: JSONDict) -> Iterator[str]:
    if not _description(tool):
        yield "tool has no description; models choose tools by reading it"


@tool_rule(
    "T002",
    Severity.WARNING,
    f"Tool description shorter than {MIN_DESCRIPTION_LENGTH} characters",
    "Expand the description: what it does, what it returns, and when not to use it.",
)
def short_description(tool: JSONDict) -> Iterator[str]:
    text = _description(tool)
    if text and len(text) < MIN_DESCRIPTION_LENGTH:
        yield f"description is only {len(text)} characters: {text!r}"


@tool_rule(
    "T003",
    Severity.ERROR,
    'Input schema is not `type: "object"`',
    'Set the root of inputSchema to {"type": "object", "properties": {...}}; the spec requires it.',
)
def input_schema_not_object(tool: JSONDict) -> Iterator[str]:
    schema = tool.get("inputSchema")
    if schema is None:
        yield "tool has no inputSchema"
    elif not isinstance(schema, dict):
        yield f"inputSchema is a {type(schema).__name__}, not an object"
    elif schema.get("type") != "object":
        yield f"inputSchema root type is {schema.get('type')!r}, expected 'object'"


@tool_rule(
    "T004",
    Severity.WARNING,
    "Input schema has no `properties`",
    'Declare "properties": {} even for tools that take no arguments; some clients reject the schema.',
)
def schema_without_properties(tool: JSONDict) -> Iterator[str]:
    schema = tool.get("inputSchema")
    if isinstance(schema, dict) and schema.get("type") == "object" and "properties" not in schema:
        yield "inputSchema declares no properties"


@tool_rule(
    "T005",
    Severity.INFO,
    "Input schema allows arbitrary extra properties",
    'Set "additionalProperties": false so typos in argument names fail loudly instead of being ignored.',
)
def unrestricted_additional_properties(tool: JSONDict) -> Iterator[str]:
    schema = tool.get("inputSchema")
    if not properties_of(schema) or not isinstance(schema, dict):
        return
    additional = schema.get("additionalProperties", True)
    if additional is True:
        yield "additionalProperties is unrestricted while properties are declared"


@tool_rule(
    "T006",
    Severity.WARNING,
    "Tool parameters without descriptions",
    "Give every property a description; the model sees nothing else about what to pass.",
)
def undocumented_parameters(tool: JSONDict) -> Iterator[str]:
    missing = [
        name
        for name, spec in properties_of(tool.get("inputSchema")).items()
        if not (isinstance(spec, dict) and isinstance(spec.get("description"), str) and spec["description"].strip())
    ]
    if missing:
        yield "parameters without description: " + ", ".join(sorted(missing))


@tool_rule(
    "T007",
    Severity.ERROR,
    "`required` names a property that does not exist",
    "Remove the stale name from `required` or add the property it refers to.",
)
def required_unknown_property(tool: JSONDict) -> Iterator[str]:
    schema = tool.get("inputSchema")
    known = properties_of(schema)
    unknown = [name for name in required_of(schema) if name not in known]
    if unknown:
        yield "required lists unknown properties: " + ", ".join(unknown)


@tool_rule(
    "T008",
    Severity.ERROR,
    "Tool name is not portable (`^[a-zA-Z0-9_-]{1,64}$`)",
    "Rename the tool using only letters, digits, '_' and '-', at most 64 characters.",
)
def invalid_tool_name(tool: JSONDict) -> Iterator[str]:
    name = tool.get("name")
    if not isinstance(name, str) or not TOOL_NAME_PATTERN.match(name):
        yield f"tool name {name!r} will be rejected by several LLM APIs"


@rule(
    "T009",
    Severity.ERROR,
    Scope.TOOL,
    "Duplicate tool name",
    "Tool names must be unique; rename or remove the duplicate registration.",
)
def duplicate_tool_names(snapshot: Snapshot) -> Iterator[Violation]:
    counts: dict[str, int] = defaultdict(int)
    for tool in snapshot.tools:
        name = tool.get("name")
        if isinstance(name, str):
            counts[name] += 1
    for name, count in counts.items():
        if count > 1:
            yield f"tool:{name}", f"tool name is listed {count} times"


@rule(
    "T010",
    Severity.WARNING,
    Scope.TOOL,
    "Near-duplicate tool names",
    "Pick one naming convention and merge or clearly differentiate tools that differ only in case or separators.",
)
def near_duplicate_tool_names(snapshot: Snapshot) -> Iterator[Violation]:
    groups: dict[str, set[str]] = defaultdict(set)
    for tool in snapshot.tools:
        name = tool.get("name")
        if isinstance(name, str):
            groups[_normalised(name)].add(name)
    for names in groups.values():
        if len(names) > 1:
            ordered = sorted(names)
            yield f"tool:{ordered[0]}", "names differ only by case or separators: " + ", ".join(ordered)


@rule(
    "T011",
    Severity.WARNING,
    Scope.TOOL,
    f"More than {MAX_TOOL_COUNT} tools",
    "Every tool definition costs context on every request; split the server or gate rarely used tools.",
)
def too_many_tools(snapshot: Snapshot) -> Iterator[Violation]:
    if len(snapshot.tools) > MAX_TOOL_COUNT:
        yield "server", f"server exposes {len(snapshot.tools)} tools (limit {MAX_TOOL_COUNT})"


@tool_rule(
    "T012",
    Severity.WARNING,
    "Mutating tool without readOnlyHint/destructiveHint",
    "Add annotations with readOnlyHint and destructiveHint so clients can ask before running it.",
)
def mutating_tool_without_annotations(tool: JSONDict) -> Iterator[str]:
    name = tool.get("name")
    if not isinstance(name, str) or not suggests_mutation(name):
        return
    annotations = tool.get("annotations")
    hints = annotations if isinstance(annotations, dict) else {}
    if "readOnlyHint" not in hints and "destructiveHint" not in hints:
        yield "name suggests it changes state but no readOnlyHint/destructiveHint is declared"


@tool_rule(
    "T013",
    Severity.ERROR,
    "Output schema is not valid JSON Schema",
    "Fix outputSchema so it validates as JSON Schema; clients use it to check structuredContent.",
)
def invalid_output_schema(tool: JSONDict) -> Iterator[str]:
    if "outputSchema" not in tool or tool["outputSchema"] is None:
        return
    error = schema_error(tool["outputSchema"])
    if error:
        yield f"outputSchema is invalid {error}"


@tool_rule(
    "T014",
    Severity.ERROR,
    "Input schema is not valid JSON Schema",
    "Fix inputSchema so it validates as JSON Schema draft 2020-12 (or the dialect named in $schema).",
)
def invalid_input_schema(tool: JSONDict) -> Iterator[str]:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        return
    error = schema_error(schema)
    if error:
        yield f"inputSchema is invalid {error}"
