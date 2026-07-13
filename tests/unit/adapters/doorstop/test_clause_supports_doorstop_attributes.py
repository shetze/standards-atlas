from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)
from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopItemAttributes,
    DoorstopReference,
)

import pytest

def test_clause_supports_doorstop_attributes() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(
            standard="Example",
            year=2025,
            clause="5.1",
        ),
        clause_type=ClauseType.REQUIREMENT,
        doorstop=DoorstopItemAttributes(
            active=True,
            derived=False,
            normative=None,
            level="5.1",
            reviewed=None,
            links=("REQ-0001",),
            references=(
                DoorstopReference(
                    path="evidence/test-report.pdf",
                    type="file",
                ),
            ),
            extended={
                "verification-method": "analysis",
                "safety-level": "SIL 2",
            },
        ),
    )

    assert clause.doorstop is not None
    assert clause.doorstop.links == ("REQ-0001",)
    assert clause.doorstop.extended["safety-level"] == "SIL 2"

def test_file_reference_does_not_require_keyword() -> None:
    reference = DoorstopReference(
        path="evidence/test-report.pdf",
        type="file",
    )

    assert reference.keyword is None


def test_pattern_reference_requires_keyword() -> None:
    with pytest.raises(ValueError, match="keyword is required"):
        DoorstopReference(
            path=r".*\.md",
            type="pattern",
        )
