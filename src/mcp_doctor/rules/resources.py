"""Rules about resources and resource templates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from mcp_doctor.models import JSONDict, Severity, Snapshot
from mcp_doctor.rules.registry import Scope, Violation, resource_rule, rule, template_rule
from mcp_doctor.rules.uri import template_problem, uri_problem


def _has_description(item: JSONDict) -> bool:
    value = item.get("description")
    return isinstance(value, str) and bool(value.strip())


@resource_rule(
    "R001",
    Severity.ERROR,
    "Resource URI is not a valid URI",
    "Use an absolute RFC 3986 URI with a scheme (file:///path, myapp://item/1) and percent-encode spaces.",
)
def invalid_resource_uri(resource: JSONDict) -> Iterator[str]:
    problem = uri_problem(resource.get("uri"))
    if problem:
        yield problem


@template_rule(
    "R002",
    Severity.ERROR,
    "Resource template is not a valid RFC 6570 template",
    "Write uriTemplate as an absolute URI with {variable} expressions, e.g. myapp://users/{id}.",
)
def invalid_resource_template(template: JSONDict) -> Iterator[str]:
    problem = template_problem(template.get("uriTemplate"))
    if problem:
        yield problem


@rule(
    "R003",
    Severity.INFO,
    Scope.RESOURCE,
    "Resource or template without description",
    "Describe what the resource contains so a model can decide whether to read it.",
)
def resource_without_description(snapshot: Snapshot) -> Iterator[Violation]:
    for resource in snapshot.resources:
        if not _has_description(resource):
            yield f"resource:{resource.get('uri')}", "resource has no description"
    for template in snapshot.resource_templates:
        if not _has_description(template):
            yield f"template:{template.get('uriTemplate')}", "resource template has no description"


@rule(
    "R004",
    Severity.ERROR,
    Scope.RESOURCE,
    "Duplicate resource URI",
    "Each resource needs a unique URI; reads of a duplicated URI are ambiguous.",
)
def duplicate_resource_uris(snapshot: Snapshot) -> Iterator[Violation]:
    counts = Counter(r.get("uri") for r in snapshot.resources if isinstance(r.get("uri"), str))
    for uri, count in counts.items():
        if count > 1:
            yield f"resource:{uri}", f"URI is listed {count} times"
