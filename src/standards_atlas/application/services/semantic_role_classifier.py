"""Deterministic semantic-role classification for standard clauses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from standards_atlas.domain.model.semantic_role import SemanticRole

if TYPE_CHECKING:
    from standards_atlas.application.ports.semantic_role_classifier import (
        SemanticRoleClassifierExtension,
    )


@dataclass(frozen=True)
class SemanticRoleEvidence:
    """Traceable reason for assigning a semantic role."""

    kind: str
    value: str
    confidence: float


@dataclass(frozen=True)
class SemanticRoleContext:
    """Context used to classify one clause heading."""

    reference: str
    heading: str
    ancestor_roles: tuple[SemanticRole, ...] = ()
    ancestor_headings: tuple[str, ...] = ()
    annex_status: str | None = None


@dataclass(frozen=True)
class SemanticRoleClassification:
    """Roles, confidence, and evidence produced by a classifier."""

    roles: tuple[SemanticRole, ...] = ()
    confidence: float = 0.0
    evidence: tuple[SemanticRoleEvidence, ...] = ()
    classifier: str = "deterministic"


@dataclass(frozen=True)
class _HeadingRule:
    role: SemanticRole
    pattern: re.Pattern[str]
    confidence: float = 1.0


_RULES = (
    _HeadingRule(SemanticRole.FOREWORD, re.compile(r"^(?:european\s+)?foreword$", re.I)),
    _HeadingRule(SemanticRole.INTRODUCTION, re.compile(r"^introduction$", re.I)),
    _HeadingRule(SemanticRole.SCOPE, re.compile(r"^(?:general\s+)?scope$", re.I)),
    _HeadingRule(
        SemanticRole.NORMATIVE_REFERENCES,
        re.compile(r"^normative\s+references?$", re.I),
    ),
    _HeadingRule(
        SemanticRole.TERMS_AND_DEFINITIONS,
        re.compile(
            r"^(?:terms?(?:,?\s+definitions?)?(?:\s+and\s+abbreviations?)?|"
            r"terms?\s+and\s+definitions?|definitions?)$",
            re.I,
        ),
    ),
    _HeadingRule(
        SemanticRole.ABBREVIATIONS,
        re.compile(r"^(?:abbreviations?|acronyms?|symbols?|notation)$", re.I),
    ),
    _HeadingRule(SemanticRole.OBJECTIVES, re.compile(r"^objectives?$", re.I)),
    _HeadingRule(
        SemanticRole.REQUIREMENTS,
        re.compile(r"^(?:general\s+)?requirements?$", re.I),
    ),
    _HeadingRule(
        SemanticRole.RECOMMENDATIONS,
        re.compile(r"^(?:recommendations?|guidance)$", re.I),
    ),
    _HeadingRule(SemanticRole.INPUTS, re.compile(r"^inputs?$", re.I)),
    _HeadingRule(SemanticRole.OUTPUTS, re.compile(r"^outputs?$", re.I)),
    _HeadingRule(
        SemanticRole.WORK_PRODUCTS,
        re.compile(r"^(?:work\s+products?|deliverables?)$", re.I),
    ),
    _HeadingRule(SemanticRole.VERIFICATION, re.compile(r"^(?:software\s+)?verification$", re.I)),
    _HeadingRule(SemanticRole.VALIDATION, re.compile(r"^(?:software\s+)?validation$", re.I)),
    _HeadingRule(SemanticRole.ASSESSMENT, re.compile(r"^(?:software\s+)?assessment$", re.I)),
    _HeadingRule(SemanticRole.COMPLIANCE, re.compile(r"^compliance$", re.I)),
    _HeadingRule(SemanticRole.CONFORMANCE, re.compile(r"^conformance$", re.I)),
    _HeadingRule(SemanticRole.BIBLIOGRAPHY, re.compile(r"^bibliography(?:\s+of\s+.+)?$", re.I)),
)

_TOKEN_ROLES = (
    (SemanticRole.OBJECTIVES, re.compile(r"\bobjectives?\b", re.I)),
    (SemanticRole.REQUIREMENTS, re.compile(r"\brequirements?\b", re.I)),
    (SemanticRole.RECOMMENDATIONS, re.compile(r"\brecommendations?\b|\bguidance\b", re.I)),
    (SemanticRole.VERIFICATION, re.compile(r"\bverification\b", re.I)),
    (SemanticRole.VALIDATION, re.compile(r"\bvalidation\b", re.I)),
    (SemanticRole.ASSESSMENT, re.compile(r"\bassessment\b", re.I)),
    (SemanticRole.INPUTS, re.compile(r"\binputs?\b", re.I)),
    (SemanticRole.OUTPUTS, re.compile(r"\boutputs?\b", re.I)),
    (SemanticRole.WORK_PRODUCTS, re.compile(r"\bwork\s+products?\b", re.I)),
)


class SemanticRoleClassifier:
    """Classify clause roles using deterministic rules and optional fallback.

    The optional extension is intentionally defined by an application port. A
    future LLM adapter can implement that port without changing this service or
    the domain model. The extension is consulted only below ``fallback_threshold``.
    """

    def __init__(
        self,
        extension: SemanticRoleClassifierExtension | None = None,
        *,
        fallback_threshold: float = 0.8,
    ) -> None:
        self._extension = extension
        self._fallback_threshold = fallback_threshold

    def classify(self, context: SemanticRoleContext) -> SemanticRoleClassification:
        deterministic = self.classify_deterministically(context)
        if (
            self._extension is None
            or deterministic.confidence >= self._fallback_threshold
        ):
            return deterministic

        extended = self._extension.classify(context)
        if extended is None or extended.confidence <= deterministic.confidence:
            return deterministic
        return extended

    def classify_deterministically(
        self,
        context: SemanticRoleContext,
    ) -> SemanticRoleClassification:
        heading = _normalize_heading(context.heading)

        # Terms are structural containers: descendants remain terms even when
        # their own names contain words such as "scope" or "requirement".
        if SemanticRole.TERMS_AND_DEFINITIONS in context.ancestor_roles:
            return SemanticRoleClassification(
                roles=(SemanticRole.TERMS_AND_DEFINITIONS,),
                confidence=0.98,
                evidence=(
                    SemanticRoleEvidence(
                        "ancestor_role",
                        SemanticRole.TERMS_AND_DEFINITIONS.value,
                        0.98,
                    ),
                ),
            )

        if _is_annex_heading(heading) or _is_annex_reference(context.reference):
            evidence = [SemanticRoleEvidence("annex_reference", context.reference, 1.0)]
            if context.annex_status:
                evidence.append(
                    SemanticRoleEvidence("annex_status", context.annex_status, 1.0)
                )
            return SemanticRoleClassification(
                roles=(SemanticRole.ANNEX,),
                confidence=1.0,
                evidence=tuple(evidence),
            )

        for rule in _RULES:
            if rule.pattern.fullmatch(heading):
                return SemanticRoleClassification(
                    roles=(rule.role,),
                    confidence=rule.confidence,
                    evidence=(
                        SemanticRoleEvidence("heading_exact", heading, rule.confidence),
                    ),
                )

        roles = _ordered_unique(
            role for role, pattern in _TOKEN_ROLES if pattern.search(heading)
        )
        if roles:
            return SemanticRoleClassification(
                roles=roles,
                confidence=0.86,
                evidence=tuple(
                    SemanticRoleEvidence("heading_token", role.value, 0.86)
                    for role in roles
                ),
            )

        return SemanticRoleClassification()


def _normalize_heading(value: str) -> str:
    heading = re.sub(r"\s+", " ", value).strip()
    heading = re.sub(
        r"^(?:0\.\d+(?:\.\d+)*|[1-9]\d*(?:\.\d+)*|[A-Z](?:\.\d+)*)\s+",
        "",
        heading,
    )
    return heading.strip(" :-")


def _is_annex_heading(heading: str) -> bool:
    return re.match(r"^annex\s+[A-Z]{1,2}\b", heading, re.I) is not None


def _is_annex_reference(reference: str) -> bool:
    return re.fullmatch(r"[A-Z]{1,2}(?:\.\d+)*", reference) is not None


def _ordered_unique(values: Iterable[SemanticRole]) -> tuple[SemanticRole, ...]:
    return tuple(dict.fromkeys(values))
