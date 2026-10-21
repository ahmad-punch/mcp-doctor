"""Rules about prompts and their arguments."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator

from mcp_doctor.models import JSONDict, Severity
from mcp_doctor.rules.registry import prompt_rule

_PLACEHOLDER = re.compile(r"\{\{?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}?\}")


def _arguments(prompt: JSONDict) -> list[JSONDict]:
    value = prompt.get("arguments")
    if not isinstance(value, list):
        return []
    return [arg for arg in value if isinstance(arg, dict)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


@prompt_rule(
    "P001",
    Severity.WARNING,
    "Prompt has no description",
    "Add a description; clients show it in their prompt picker.",
)
def prompt_without_description(prompt: JSONDict) -> Iterator[str]:
    if not _text(prompt.get("description")):
        yield "prompt has no description"


@prompt_rule(
    "P002",
    Severity.INFO,
    "Prompt argument without description",
    "Describe each argument so users know what to fill in.",
)
def undocumented_prompt_arguments(prompt: JSONDict) -> Iterator[str]:
    missing = [str(arg.get("name")) for arg in _arguments(prompt) if not _text(arg.get("description"))]
    if missing:
        yield "arguments without description: " + ", ".join(missing)


@prompt_rule(
    "P003",
    Severity.WARNING,
    "Prompt references an undeclared argument",
    "Declare every {placeholder} used in the prompt's title or description in its `arguments` list.",
)
def undeclared_prompt_arguments(prompt: JSONDict) -> Iterator[str]:
    declared = {arg.get("name") for arg in _arguments(prompt)}
    text = f"{_text(prompt.get('title'))} {_text(prompt.get('description'))}"
    undeclared = sorted({name for name in _PLACEHOLDER.findall(text) if name not in declared})
    if undeclared:
        yield "placeholders not declared as arguments: " + ", ".join(undeclared)


@prompt_rule(
    "P004",
    Severity.ERROR,
    "Prompt declares the same argument twice",
    "Remove the duplicate argument; clients cannot tell which definition applies.",
)
def duplicate_prompt_arguments(prompt: JSONDict) -> Iterator[str]:
    counts = Counter(arg.get("name") for arg in _arguments(prompt))
    duplicates = sorted(str(name) for name, count in counts.items() if count > 1)
    if duplicates:
        yield "duplicate arguments: " + ", ".join(duplicates)
