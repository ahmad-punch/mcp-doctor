"""Small helpers for inspecting JSON Schema documents sent by servers."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, SchemaError
from jsonschema.validators import validator_for

from mcp_doctor.models import JSONDict

_MAX_ERROR_LENGTH = 160


def schema_error(schema: Any) -> str | None:
    """Return a one-line reason why ``schema`` is not valid JSON Schema, or ``None`` if it is.

    The dialect comes from ``$schema`` when present, defaulting to draft 2020-12 as the
    MCP specification does.
    """
    if not isinstance(schema, dict):
        return f"expected a JSON object, got {type(schema).__name__}"
    validator_cls = validator_for(schema, default=Draft202012Validator)
    try:
        validator_cls.check_schema(schema)
    except SchemaError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        message = exc.message.splitlines()[0]
        if len(message) > _MAX_ERROR_LENGTH:
            message = message[: _MAX_ERROR_LENGTH - 3] + "..."
        return f"at {location}: {message}"
    return None


def properties_of(schema: Any) -> JSONDict:
    """The ``properties`` mapping of an object schema, or an empty dict when absent or malformed."""
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict):
            return props
    return {}


def required_of(schema: Any) -> list[str]:
    """The ``required`` names of an object schema, ignoring non-string entries."""
    if isinstance(schema, dict):
        required = schema.get("required")
        if isinstance(required, list):
            return [name for name in required if isinstance(name, str)]
    return []
