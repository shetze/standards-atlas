from __future__ import annotations

from pathlib import Path

from standards_atlas.application.assertion_qualification import AssertionQualificationReport

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/standards_atlas/application/assertion_qualification"


def test_slice_7a_qualification_is_proposal_only_and_has_no_adoption_boundary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assert "EngineeringDocument" not in source
    assert "DocumentKnowledge(" not in source
    assert "KnowledgeAdoption" not in source
    assert "semantic_qualification" not in source


def test_slice_7a_report_is_metric_only_without_acceptance_policy() -> None:
    fields = set(AssertionQualificationReport.model_fields)
    assert "passed" not in fields
    assert "accepted" not in fields
    assert "threshold" not in fields
    assert "adoption" not in fields
