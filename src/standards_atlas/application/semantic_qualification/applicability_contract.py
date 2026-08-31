"""Qualification-only applicability contract and projection helpers."""

from __future__ import annotations

from enum import StrEnum

from standards_atlas.domain.model import ApplicabilityFunction


class ApplicabilityPolarity(StrEnum):
    """Binary applicability direction used by qualification."""

    INCLUDED = "included"
    EXCLUDED = "excluded"


def project_applicability_polarity(
    value: ApplicabilityFunction | str | None,
) -> ApplicabilityPolarity | None:
    """Project only inclusion/exclusion into qualification polarity.

    Exception and condition semantics deliberately have no representation in the
    qualification contract and therefore project to ``None``.
    """
    if value is None:
        return None
    raw = value.value if isinstance(value, ApplicabilityFunction) else str(value)
    if raw == ApplicabilityFunction.INCLUSION.value:
        return ApplicabilityPolarity.INCLUDED
    if raw == ApplicabilityFunction.EXCLUSION.value:
        return ApplicabilityPolarity.EXCLUDED
    return None
