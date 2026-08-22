"""Conservative detection of explicit applicability semantics.

Applicability is intentionally narrower than generic conditional, prerequisite,
assumption, or structural scope semantics.  A clause is applicability-positive
only when the text explicitly changes which subject or normative content is in
scope, out of scope, excepted, or applicable under a condition.
"""

from __future__ import annotations

import re

from standards_atlas.domain.model import ApplicabilityFunction

_STATEMENT_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_EXCEPTION = re.compile(r"\b(except(?:ion)?|with the exception of|unless)\b", re.IGNORECASE)
_EXCLUSION = re.compile(
    r"\b(does not apply|do not apply|shall not apply|not applicable|excluded|excludes|"
    r"outside the scope|is out of scope)\b",
    re.IGNORECASE,
)
_INCLUSION = re.compile(
    r"\b(applies to|apply to|applicable to|is applicable|are applicable|within the scope|"
    r"in scope|covers|is covered by|are covered by)\b",
    re.IGNORECASE,
)
_CONDITION = re.compile(
    r"\b(if|when|where|whenever|provided that|subject to|only if)\b",
    re.IGNORECASE,
)


def detect_explicit_applicability_subtypes(text: str) -> set[ApplicabilityFunction]:
    """Return explicit applicability subtypes found in *text*.

    Conditional words alone are deliberately insufficient.  In particular,
    ``if``, ``when``, ``provided that``, and ``subject to`` only produce an
    applicability condition when the same statement also contains an explicit
    applicability predicate such as ``applies to`` or ``is applicable``.
    """

    detected: set[ApplicabilityFunction] = set()
    statements = tuple(item.strip() for item in _STATEMENT_SPLIT.split(text) if item.strip())
    if not statements and text.strip():
        statements = (text.strip(),)

    for statement in statements:
        subtype = classify_explicit_applicability_statement(statement)
        if subtype is not None:
            detected.add(subtype)
    return detected


def derive_explicit_applicability_subtype(text: str) -> ApplicabilityFunction | None:
    """Return one subtype only when explicit applicability semantics are unambiguous."""

    detected = detect_explicit_applicability_subtypes(text)
    if len(detected) == 1:
        return next(iter(detected))
    return None


def classify_explicit_applicability_statement(
    statement: str,
) -> ApplicabilityFunction | None:
    """Classify a single statement using explicit applicability evidence only."""

    if _EXCLUSION.search(statement):
        return ApplicabilityFunction.EXCLUSION

    has_inclusion = bool(_INCLUSION.search(statement))
    has_condition = bool(_CONDITION.search(statement))

    # A conditional is applicability only when the text explicitly predicates
    # applicability.  Generic action conditions remain prerequisites/process logic.
    if has_inclusion and has_condition:
        return ApplicabilityFunction.APPLICABILITY_CONDITION

    # ``except``/``unless`` is treated as an applicability exception only when it
    # carves out an explicit applicability/scope assertion.  Bare ``unless`` in a
    # requirement is ordinary conditional logic and must not become applicability.
    if _EXCEPTION.search(statement) and has_inclusion:
        return ApplicabilityFunction.EXCEPTION

    if has_inclusion:
        return ApplicabilityFunction.INCLUSION
    return None
