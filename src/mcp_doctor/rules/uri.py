"""RFC 3986 URI and RFC 6570 URI Template syntax checks, without network access."""

from __future__ import annotations

import re

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_URI_CHARS = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*$")
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_EXPRESSION = re.compile(r"\{([^{}]*)\}")
_VARSPEC = re.compile(r"^(?:[A-Za-z0-9_]|%[0-9A-Fa-f]{2})(?:\.?(?:[A-Za-z0-9_]|%[0-9A-Fa-f]{2}))*(?::[1-9]\d{0,3}|\*)?$")
_OPERATORS = "+#./;?&"


def uri_problem(uri: object) -> str | None:
    """Explain why ``uri`` is not an absolute RFC 3986 URI, or return ``None`` when it is."""
    if not isinstance(uri, str) or not uri:
        return "URI is missing or not a string"
    if not _SCHEME.match(uri):
        return "URI has no scheme (expected something like file:// or myapp://)"
    if uri.endswith(":") and uri.count(":") == 1:
        return "URI has a scheme but nothing after it"
    if not _URI_CHARS.match(uri):
        bad = sorted({ch for ch in uri if not _URI_CHARS.match(ch)})
        return "URI contains characters that must be percent-encoded: " + " ".join(repr(ch) for ch in bad)
    if _BAD_PERCENT.search(uri):
        return "URI contains a '%' that is not followed by two hex digits"
    return None


def template_problem(template: object) -> str | None:
    """Explain why ``template`` is not a valid RFC 6570 URI template, or return ``None``."""
    if not isinstance(template, str) or not template:
        return "URI template is missing or not a string"
    for match in _EXPRESSION.finditer(template):
        problem = _expression_problem(match.group(1))
        if problem:
            return problem
    literal = _EXPRESSION.sub("x", template)
    if "{" in literal or "}" in literal:
        return "URI template has unbalanced braces"
    problem = uri_problem(literal)
    return problem.replace("URI", "URI template", 1) if problem else None


def _expression_problem(body: str) -> str | None:
    if not body:
        return "URI template contains an empty expression '{}'"
    if body[0] in _OPERATORS:
        body = body[1:]
    for varspec in body.split(","):
        if not _VARSPEC.match(varspec):
            return f"URI template variable {varspec!r} is not a valid RFC 6570 varspec"
    return None
