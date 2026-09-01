from pathlib import Path

import yaml

from standards_atlas.adapters.gemara import GemaraControlExporter, GemaraControlMapper
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    NormativeStatus,
    SemanticClassification,
    StandardReference,
    StatementFunction,
    TextBlock,
)


def _clause(
    identifier: str,
    reference: str,
    heading: str,
    *,
    text: str = "",
    parent: str | None = None,
    clause_type: ClauseType = ClauseType.CLAUSE,
    statement_functions: tuple[StatementFunction, ...] = (),
    normative_status: NormativeStatus = NormativeStatus.UNSPECIFIED,
) -> Clause:
    clause = Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=clause_type,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        normative_status=normative_status,
        content=(TextBlock(id=f"text-{identifier}", text=text),) if text else (),
    )
    if statement_functions:
        clause = clause.with_semantic_classification(
            SemanticClassification(statement_functions=statement_functions)
        )
    return clause


def _document(*clauses: Clause) -> PublicationDocument:
    engineering = EngineeringDocument(
        key=DocumentKey(value="SAMPLE-1"),
        title="Sample Standard - Part 1",
        document_type=DocumentType.STANDARD,
        year=2026,
        version="2026-09",
        source="sample-source",
        clauses=clauses,
    )
    return PublicationDocument.from_engineering_document(engineering)


def test_objective_with_normative_children_becomes_control() -> None:
    document = _document(
        _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
        _clause("section-4", "4", "Requirements", parent="root"),
        _clause(
            "obj-4",
            "4.1",
            "Objective",
            parent="section-4",
            text="The system shall behave deterministically.",
            clause_type=ClauseType.OBJECTIVE,
            statement_functions=(StatementFunction.OBJECTIVE,),
        ),
        _clause(
            "req-4-1",
            "4.1.1",
            "Scheduling",
            parent="obj-4",
            text="Scheduling shall be deterministic.",
            statement_functions=(StatementFunction.REQUIREMENT,),
        ),
        _clause(
            "req-4-2",
            "4.1.2",
            "Failure handling",
            parent="obj-4",
            text="Unsafe scheduling shall be prohibited.",
            statement_functions=(StatementFunction.PROHIBITION,),
        ),
    )

    catalog = GemaraControlMapper(gemara_version="v-test").map(document)

    assert catalog.metadata.type == "ControlCatalog"
    assert catalog.metadata.gemara_version == "v-test"
    assert catalog.metadata.applicability_groups is not None
    assert [group.id for group in catalog.metadata.applicability_groups] == ["all"]
    assert catalog.controls is not None
    assert len(catalog.controls) == 1
    control = catalog.controls[0]
    assert control.id == "obj-4"
    assert control.group == "section-4"
    assert control.objective == "The system shall behave deterministically."
    assert [item.id for item in control.assessment_requirements] == [
        "ar-req-4-1",
        "ar-req-4-2",
    ]
    assert all(item.applicability == ("all",) for item in control.assessment_requirements)


def test_standalone_requirement_becomes_single_requirement_control() -> None:
    document = _document(
        _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
        _clause("section-4", "4", "Requirements", parent="root"),
        _clause(
            "req-4-1",
            "4.1",
            "Design",
            parent="section-4",
            text="The design shall be documented.",
            clause_type=ClauseType.REQUIREMENT,
        ),
    )

    control = GemaraControlMapper().map(document).controls[0]

    assert control.id == "control-req-4-1"
    assert control.objective == "The design shall be documented."
    assert control.assessment_requirements[0].id == "ar-req-4-1"
    assert control.assessment_requirements[0].text == "The design shall be documented."


def test_nonbinding_and_informative_clauses_do_not_become_assessment_requirements() -> None:
    document = _document(
        _clause(
            "recommendation",
            "5.1",
            "Recommendation",
            text="Automation should be considered.",
            statement_functions=(StatementFunction.RECOMMENDATION,),
        ),
        _clause(
            "informative",
            "5.2",
            "Informative requirement wording",
            text="The example shall remain illustrative.",
            clause_type=ClauseType.REQUIREMENT,
            normative_status=NormativeStatus.INFORMATIVE,
        ),
    )

    catalog = GemaraControlMapper().map(document)

    assert catalog.controls is None


def test_objective_without_assessment_requirement_does_not_invent_control() -> None:
    document = _document(
        _clause(
            "obj-6",
            "6.1",
            "Objective",
            text="The lifecycle should support assurance.",
            clause_type=ClauseType.OBJECTIVE,
            statement_functions=(StatementFunction.OBJECTIVE,),
        )
    )

    assert GemaraControlMapper().map(document).controls is None


def test_control_export_is_deterministic_and_writes_traceability(tmp_path: Path) -> None:
    document = _document(
        _clause(
            "req-7",
            "7.1",
            "Verification",
            text="Verification shall be performed.",
            clause_type=ClauseType.REQUIREMENT,
        )
    )
    exporter = GemaraControlExporter(GemaraControlMapper(gemara_version="v-test"))
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    exporter.export_document(document, first)
    exporter.export_document(document, second)

    assert first.read_bytes() == second.read_bytes()
    payload = yaml.safe_load(first.read_text(encoding="utf-8"))
    assert payload["metadata"]["type"] == "ControlCatalog"
    assert payload["metadata"]["applicability-groups"][0]["id"] == "all"
    assert payload["controls"][0]["assessment-requirements"][0]["applicability"] == ["all"]

    sidecar = first.with_suffix(".yaml.traceability.json")
    traceability = __import__("json").loads(sidecar.read_text(encoding="utf-8"))
    assert traceability["document_key"] == "SAMPLE-1"
    assert len(traceability["exported_artifact_sha256"]) == 64
    assert traceability["entries"] == [
        {
            "clause_id": "req-7",
            "gemara_entry_id": "ar-req-7",
            "entry_type": "assessment_requirement",
            "owner_control_id": "control-req-7",
        },
        {
            "clause_id": "req-7",
            "gemara_entry_id": "control-req-7",
            "entry_type": "control",
            "owner_control_id": "control-req-7",
        },
    ]
