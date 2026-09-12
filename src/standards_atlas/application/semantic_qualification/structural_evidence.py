"""Deterministic statement-function evidence derived from clause structure and wording."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from standards_atlas.domain.model import StatementFunction

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.taxonomy_decisions import (
        ClauseDecisionPlan,
    )


@dataclass(frozen=True)
class StructuralEvidence:
    """High-precision evidence used to fuse structure with model predictions."""

    primary_function: StatementFunction | None = None
    statement_functions: tuple[StatementFunction, ...] = ()
    scope_context: bool = False
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
        if result:
            result["confidence"] = self.confidence
            result["evidence"] = list(self.evidence)
        return result


def derive_structural_evidence(
    context: dict[str, object], *, confidence: float = 0.95, policy: str = "legacy-v1"
) -> StructuralEvidence:
    """Derive conservative priors from normalized structure and explicit wording.

    Title/section signals determine the primary communicative function. Explicit
    lexical markers may add secondary functions, but only high-precision markers
    are used so that deterministic evidence does not become a second language model.
    """

    # Slice 2 is diagnostic-only. Keep the old baseline, including its title
    # read boundary, explicitly pinned until a qualified policy is activated.
    # New code must use taxonomy_structural_evidence(), backed by DecisionPlan.
    if policy != "legacy-v1":
        raise ValueError("production structural priors remain pinned to legacy-v1")
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

    return StructuralEvidence(
        primary_function=primary,
        statement_functions=tuple(functions),
        scope_context=scope_context,
        confidence=confidence if functions or scope_context else 0.0,
        evidence=tuple(dict.fromkeys(evidence)),
    )


def taxonomy_structural_evidence(plan: ClauseDecisionPlan) -> dict[str, Any]:
    """Project the shared rule plan, without confidence or synthetic model votes.

    Both pre-inference diagnostics and future post-inference consumers use this
    exact projection. The legacy production baseline above is not activated by it.
    """
    return {
        "policy": f"{plan.rules_id}@{plan.rules_version}",
        "rules_sha256": plan.rules_sha256,
        "source_sha256": plan.source_sha256,
        "plan_sha256": plan.fingerprint,
        "diagnostic_only": True,
        "attributes": {
            item.attribute: item.model_dump(mode="json", exclude={"attribute"})
            for item in plan.decisions
        },
    }
