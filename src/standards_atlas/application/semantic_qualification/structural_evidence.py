"""Deterministic statement-function evidence derived from clause structure and wording."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from standards_atlas.application.semantic_qualification.applicability_semantics import (
    derive_explicit_applicability_subtype,
)
from standards_atlas.domain.model import ApplicabilityFunction, StatementFunction


@dataclass(frozen=True)
class StructuralEvidence:
    """High-precision evidence used to fuse structure with model predictions."""

    primary_function: StatementFunction | None = None
    statement_functions: tuple[StatementFunction, ...] = ()
    scope_context: bool = False
    applicability_subtype: ApplicabilityFunction | None = None
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.primary_function is not None:
            result["primary_function"] = self.primary_function.value
        if self.statement_functions:
            result["statement_functions"] = [item.value for item in self.statement_functions]
        if self.scope_context:
            result["scope_context"] = True
        if self.applicability_subtype is not None:
            result["applicability_subtype"] = self.applicability_subtype.value
        if result:
            result["confidence"] = self.confidence
            result["evidence"] = list(self.evidence)
        return result


def derive_structural_evidence(
    context: dict[str, object], *, confidence: float = 0.95
) -> StructuralEvidence:
    """Derive conservative priors from normalized structure and explicit wording.

    Title/section signals determine the primary communicative function. Explicit
    lexical markers may add secondary functions, but only high-precision markers
    are used so that deterministic evidence does not become a second language model.
    """

    title = str(context.get("title") or "").strip().lower()
    text = str(context.get("text") or "").strip().lower()
    values = {
        str(context.get("clause_type", "")).lower(),
        str(context.get("canonical_section", "")).lower(),
        *(str(item).lower() for item in context.get("structural_roles", ()) or ()),
        *(str(item).lower() for item in context.get("document_categories", ()) or ()),
        *(str(item).lower() for item in context.get("domain_categories", ()) or ()),
    }
    evidence: list[str] = []
    functions: list[StatementFunction] = []
    primary: StatementFunction | None = None

    def add(function: StatementFunction, source: str, *, make_primary: bool = False) -> None:
        nonlocal primary
        if function not in functions:
            functions.append(function)
        evidence.append(source)
        if make_primary and primary is None:
            primary = function

    title_rules = (
        (r"\bexamples?\b", StatementFunction.EXAMPLE, "title:example"),
        (r"\b(style guide|guidelines?|guidance)\b", StatementFunction.GUIDELINE, "title:guideline"),
        (
            r"\bdefinitions?\b|\bterms and definitions\b",
            StatementFunction.DEFINITION,
            "title:definition",
        ),
        (r"\bobjectives?\b", StatementFunction.OBJECTIVE, "title:objective"),
        (r"\brationale\b", StatementFunction.RATIONALE, "title:rationale"),
        (r"\bassumptions?\b", StatementFunction.ASSUMPTION, "title:assumption"),
        (r"\bprerequisites?\b", StatementFunction.PREREQUISITE, "title:prerequisite"),
        (r"\bnotes?\b", StatementFunction.NOTE, "title:note"),
        (r"\b(warnings?|cautions?)\b", StatementFunction.WARNING, "title:warning"),
    )
    for pattern, function, source in title_rules:
        if re.search(pattern, title):
            add(function, source, make_primary=True)
            break

    if primary is None:
        if "requirement" in values:
            add(StatementFunction.REQUIREMENT, "structure:requirement", make_primary=True)
        elif values & {"definition", "term", "terminology"}:
            add(StatementFunction.DEFINITION, "structure:definition", make_primary=True)
        elif "example" in values:
            add(StatementFunction.EXAMPLE, "structure:example", make_primary=True)
        elif "note" in values:
            add(StatementFunction.NOTE, "structure:note", make_primary=True)

    # Explicit negative guidance is condemnation even when phrased epistemically,
    # e.g. "should not be regarded as complete".
    if re.search(r"\bshould\s+not\b", text):
        add(StatementFunction.CONDEMNATION, "text:should-not", make_primary=primary is None)
    if re.search(r"\bshall\s+not\b", text):
        add(StatementFunction.PROHIBITION, "text:shall-not", make_primary=primary is None)
    elif re.search(r"\bshall\b", text) and primary is None:
        add(StatementFunction.REQUIREMENT, "text:shall", make_primary=True)

    warning_marker = re.search(r"\b(be aware|warning|caution)\b", text)
    adverse_consequence = re.search(
        r"\b(risk|unsafe|incorrect|unreliable|questionable|fault|failure|harm|"
        r"insufficient|invalid|adverse|undesirable|not complete|not exhaustive)\b",
        text,
    )
    if warning_marker and adverse_consequence:
        add(StatementFunction.WARNING, "text:explicit-warning")

    own_scope = bool(values & {"scope", "applicability"}) or bool(
        re.search(r"\bscope\b|\bfield of application\b", title)
    )
    ancestor_headings = context.get("ancestor_headings", ()) or ()
    inherited_scope = False
    if not own_scope and not title:
        for ancestor in ancestor_headings:
            ancestor_title = (
                (str(ancestor.get("title") or "") if isinstance(ancestor, dict) else str(ancestor))
                .strip()
                .lower()
            )
            if re.search(r"\bscope\b|\bfield of application\b", ancestor_title):
                inherited_scope = True
                evidence.append("ancestor-title:scope")
                break
    scope_context = own_scope or inherited_scope
    if own_scope:
        evidence.append("structure:scope")

    # Explicit applicability wording is semantically meaningful anywhere in the
    # document, not only inside a structural Scope section. Scope remains an
    # additional structural signal, while lexical applicability evidence is
    # evaluated independently.
    applicability_subtype = _derive_applicability_subtype(text)
    if applicability_subtype is not None:
        evidence.append(f"text:{applicability_subtype.value}")

    return StructuralEvidence(
        primary_function=primary,
        statement_functions=tuple(functions),
        scope_context=scope_context,
        applicability_subtype=applicability_subtype,
        confidence=confidence if functions or scope_context or applicability_subtype else 0.0,
        evidence=tuple(dict.fromkeys(evidence)),
    )


def _derive_applicability_subtype(text: str) -> ApplicabilityFunction | None:
    """Return a conservative subtype for explicit applicability wording."""

    return derive_explicit_applicability_subtype(text)
