"""The rule set. Importing this package registers every rule."""

from mcp_doctor.rules import prompts, resources, server, smoke, tools
from mcp_doctor.rules.engine import lint
from mcp_doctor.rules.registry import Rule, Scope, all_rules, get_rule, known_ids

__all__ = [
    "Rule",
    "Scope",
    "all_rules",
    "get_rule",
    "known_ids",
    "lint",
    "prompts",
    "resources",
    "server",
    "smoke",
    "tools",
]
