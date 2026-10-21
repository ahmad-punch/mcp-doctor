"""The rule registry: every check mcp-doctor knows about, as data.

A rule is a frozen record (ID, severity, scope, title, fix hint) plus an optional check
function. The CLI's ``--rules`` listing, ``--ignore``, scoring, the JSON report, and the
README table are all derived from these records, so a rule is defined in exactly one place.

Check functions never build ``Finding`` objects themselves. They yield ``(target, message)``
pairs and the engine attaches the rule's severity and hint, which keeps severities
consistent and lets tests assert on rule IDs alone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mcp_doctor.models import JSONDict, Severity, Snapshot

Violation = tuple[str, str]
"""A ``(target, message)`` pair yielded by a check."""

SnapshotCheck = Callable[[Snapshot], Iterable[Violation]]
ItemCheck = Callable[[JSONDict], Iterable[str]]


class Scope(str, Enum):
    """What a rule looks at. Also used to group rules in listings."""

    SERVER = "server"
    CONNECTION = "connection"
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
    SMOKE = "smoke"


@dataclass(frozen=True)
class Rule:
    """A single lint rule. ``check`` is ``None`` for rules emitted by the smoke runner."""

    id: str
    severity: Severity
    scope: Scope
    title: str
    hint: str
    check: SnapshotCheck | None = None


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    """Add a rule to the registry. IDs must be unique."""
    if rule.id in _REGISTRY:
        raise ValueError(f"duplicate rule id {rule.id!r}")
    _REGISTRY[rule.id] = rule
    return rule


def declare(rule_id: str, severity: Severity, scope: Scope, title: str, hint: str) -> Rule:
    """Register a rule whose findings are produced outside the static engine (e.g. smoke tests)."""
    return register(Rule(rule_id, severity, scope, title, hint))


def rule(
    rule_id: str, severity: Severity, scope: Scope, title: str, hint: str
) -> Callable[[SnapshotCheck], SnapshotCheck]:
    """Register a check that sees the whole snapshot (cross-item rules, server rules)."""

    def decorator(fn: SnapshotCheck) -> SnapshotCheck:
        register(Rule(rule_id, severity, scope, title, hint, fn))
        return fn

    return decorator


def _item_rule(
    attribute: str, prefix: str, key: str, scope: Scope
) -> Callable[[str, Severity, str, str], Callable[[ItemCheck], ItemCheck]]:
    """Build a decorator factory for checks that look at one listed item at a time."""

    def factory(rule_id: str, severity: Severity, title: str, hint: str) -> Callable[[ItemCheck], ItemCheck]:
        def decorator(fn: ItemCheck) -> ItemCheck:
            def check(snapshot: Snapshot) -> Iterator[Violation]:
                items: list[JSONDict] = getattr(snapshot, attribute)
                for item in items:
                    target = f"{prefix}:{display_name(item, key)}"
                    for message in fn(item):
                        yield target, message

            register(Rule(rule_id, severity, scope, title, hint, check))
            return fn

        return decorator

    return factory


tool_rule = _item_rule("tools", "tool", "name", Scope.TOOL)
resource_rule = _item_rule("resources", "resource", "uri", Scope.RESOURCE)
template_rule = _item_rule("resource_templates", "template", "uriTemplate", Scope.RESOURCE)
prompt_rule = _item_rule("prompts", "prompt", "name", Scope.PROMPT)


def display_name(item: JSONDict, key: str) -> str:
    """A printable identifier for an item, even when the server sent garbage."""
    value: Any = item.get(key)
    if isinstance(value, str) and value:
        return value
    return f"<missing {key}>" if value is None else repr(value)


def all_rules() -> list[Rule]:
    """Every registered rule, sorted by ID."""
    return [_REGISTRY[rule_id] for rule_id in sorted(_REGISTRY)]


def get_rule(rule_id: str) -> Rule:
    """Look up a rule by ID. Raises ``KeyError`` for unknown IDs."""
    return _REGISTRY[rule_id]


def known_ids() -> set[str]:
    """The set of registered rule IDs, used to validate ``--ignore``."""
    return set(_REGISTRY)
