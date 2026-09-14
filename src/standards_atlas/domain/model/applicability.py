"""Canonical applicability semantics for clause-level context."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class ApplicabilityPolarity(StrEnum):
    """Direction of an explicit applicability statement."""

    INCLUDED = "included"
    EXCLUDED = "excluded"


class ClauseApplicability(BaseModel):
    """Minimal accepted applicability state for one clause.

    Applicability deliberately models only the semantics Standards Atlas needs at
    the document/context boundary: whether explicit applicability semantics are
    present and, when resolved, whether they include or exclude the governed
    normative content. Conditions, exceptions, techniques and other target detail
    are not part of this canonical contract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    present: bool = False
    polarity: ApplicabilityPolarity | None = None

    @model_validator(mode="after")
    def absent_applicability_has_no_polarity(self) -> ClauseApplicability:
        if not self.present and self.polarity is not None:
            raise ValueError("absent applicability cannot define polarity")
        return self
