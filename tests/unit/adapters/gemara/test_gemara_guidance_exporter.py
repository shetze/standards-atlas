from pathlib import Path

import pytest
import yaml

from standards_atlas.adapters.gemara import GemaraGuidanceExporter, GemaraGuidanceMapper
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
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
) -> Clause:
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=clause_type,
        heading=heading,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"text-{identifier}", text=text),) if text else (),
    )


def _document() -> PublicationDocument:
    engineering = EngineeringDocument(
        key=DocumentKey(value="SAMPLE-1"),
        title="Sample Standard - Part 1",
        document_type=DocumentType.STANDARD,
        year=2026,
        version="2026-09",
        source="sample-source",
        clauses=(
            _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
            _clause("section-4", "4", "Requirements", parent="root"),
            _clause(
                "req-4-1",
                "4.1",
                "Design requirements",
                parent="section-4",
                text="The system shall provide deterministic behavior.",
                clause_type=ClauseType.REQUIREMENT,
            ),
        ),
    )
    return PublicationDocument.from_engineering_document(engineering)


def test_maps_document_to_guidance_catalog_with_structural_group() -> None:
    catalog = GemaraGuidanceMapper(gemara_version="v-test").map(_document())

    assert catalog.metadata.gemara_version == "v-test"
    assert catalog.metadata.version == "2026-09"
    assert catalog.metadata.author.id == "standards-atlas"
    assert [group.id for group in catalog.groups] == ["sample-1-root", "section-4"]
    assert len(catalog.guidelines) == 1
    assert catalog.guidelines[0].id == "req-4-1"
    assert catalog.guidelines[0].group == "section-4"
    assert catalog.guidelines[0].objective == "The system shall provide deterministic behavior."


def test_export_is_byte_deterministic_and_matches_golden_fixture(tmp_path: Path) -> None:
    exporter = GemaraGuidanceExporter(GemaraGuidanceMapper(gemara_version="v-test"))
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    exporter.export_document(_document(), first)
    exporter.export_document(_document(), second)

    assert first.read_bytes() == second.read_bytes()
    golden = Path("tests/fixtures/gemara/sample-guidance.yaml")
    assert first.read_text(encoding="utf-8") == golden.read_text(encoding="utf-8")
    payload = yaml.safe_load(first.read_text(encoding="utf-8"))
    assert payload["metadata"]["type"] == "GuidanceCatalog"
    assert payload["metadata"]["gemara-version"] == "v-test"
    assert payload["type"] == "Standard"
    assert payload["guidelines"][0]["state"] == "Active"
    assert "recommendations" not in payload["guidelines"][0]


def test_heading_only_leaf_is_not_invented_as_guidance() -> None:
    document = _document().model_copy(
        update={
            "clauses": _document().clauses + (_clause("empty", "5", "Heading only", parent="root"),)
        }
    )

    catalog = GemaraGuidanceMapper().map(document)

    assert "empty" not in {guideline.id for guideline in catalog.guidelines}


def test_rejects_identifier_collisions_after_normalization() -> None:
    document = _document().model_copy(
        update={
            "clauses": (
                _clause("root", "0", "Part 1", clause_type=ClauseType.TOC),
                _clause("section/4", "4", "Requirements A", parent="root"),
                _clause("section 4", "5", "Requirements B", parent="root"),
                _clause("req-a", "4.1", "A", parent="section/4", text="Requirement A."),
                _clause("req-b", "5.1", "B", parent="section 4", text="Requirement B."),
            )
        }
    )

    with pytest.raises(ValueError, match="group id collision"):
        GemaraGuidanceMapper().map(document)


def test_semantic_objective_aggregates_requirements_recommendations_and_rationale() -> None:
    from standards_atlas.domain.model import (
        AnnotationId,
        AnnotationType,
        AnnotationVisibility,
        ClauseAnnotation,
        SemanticClassification,
        StatementFunction,
    )

    objective = _clause(
        "obj-6",
        "6.1",
        "Objective",
        parent="section-4",
        text="Software shall be developed systematically.",
        clause_type=ClauseType.OBJECTIVE,
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.OBJECTIVE,))
    )
    requirement = _clause(
        "req-6-a",
        "6.1.1",
        "Planning",
        parent="obj-6",
        text="A software development plan shall be established.",
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.REQUIREMENT,))
    )
    recommendation = _clause(
        "rec-6-b",
        "6.1.2",
        "Tooling",
        parent="obj-6",
        text="Automated tooling should be used where practical.",
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.RECOMMENDATION,))
    )
    rationale = _clause(
        "rat-6-c",
        "6.1.3",
        "Rationale",
        parent="obj-6",
        text="Systematic development reduces avoidable faults.",
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.RATIONALE,))
    )
    document = _document().model_copy(
        update={
            "clauses": _document().clauses[:2]
            + (objective, requirement, recommendation, rationale),
            "annotations": (
                ClauseAnnotation(
                    id=AnnotationId(value="annotation-1"),
                    clause_id=objective.id,
                    annotation_type=AnnotationType.EXPLANATION,
                    visibility=AnnotationVisibility.PUBLIC,
                    content="This objective establishes the engineering intent.",
                ),
            ),
        }
    )

    catalog = GemaraGuidanceMapper().map(document)

    assert len(catalog.guidelines) == 1
    guideline = catalog.guidelines[0]
    assert guideline.id == "obj-6"
    assert guideline.objective == "Software shall be developed systematically."
    assert [statement.id for statement in guideline.statements] == ["req-6-a"]
    assert guideline.statements[0].text == "A software development plan shall be established."
    assert guideline.recommendations == ("Automated tooling should be used where practical.",)
    assert guideline.rationale is not None
    assert guideline.rationale.goals == ("Software shall be developed systematically.",)
    assert "Systematic development reduces avoidable faults." in guideline.rationale.importance
    assert "This objective establishes the engineering intent." in guideline.rationale.importance
    assert {item.id for item in catalog.guidelines} == {"obj-6"}


def test_positive_applicability_becomes_valid_metadata_group_reference() -> None:
    from standards_atlas.domain.model import (
        ApplicabilityFunction,
        SemanticClassification,
        StatementFunction,
    )

    objective = _clause(
        "obj-7",
        "7.1",
        "Objective",
        parent="section-4",
        text="The verification strategy shall be defined.",
        clause_type=ClauseType.OBJECTIVE,
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.OBJECTIVE,))
    )
    applicability = _clause(
        "app-7",
        "7.1.1",
        "High integrity systems",
        parent="obj-7",
        text="This guidance applies to high integrity systems.",
    ).with_semantic_classification(
        SemanticClassification(
            applicability_present=True,
            applicability_functions=(ApplicabilityFunction.INCLUSION,),
        )
    )
    document = _document().model_copy(
        update={
            "clauses": _document().clauses[:2]
            + (
                objective,
                applicability,
            )
        }
    )

    catalog = GemaraGuidanceMapper().map(document)

    assert catalog.metadata.applicability_groups is not None
    assert [group.id for group in catalog.metadata.applicability_groups] == ["app-app-7"]
    assert catalog.guidelines[0].applicability == ("app-app-7",)


def test_exclusion_is_not_misrepresented_as_positive_applicability() -> None:
    from standards_atlas.domain.model import (
        ApplicabilityFunction,
        SemanticClassification,
        StatementFunction,
    )

    objective = _clause(
        "obj-8",
        "8.1",
        "Objective",
        parent="section-4",
        text="The process shall be controlled.",
        clause_type=ClauseType.OBJECTIVE,
    ).with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.OBJECTIVE,))
    )
    exclusion = _clause(
        "exclude-8",
        "8.1.1",
        "Exclusion",
        parent="obj-8",
        text="This requirement does not apply to prototypes.",
    ).with_semantic_classification(
        SemanticClassification(
            applicability_present=True,
            applicability_functions=(ApplicabilityFunction.EXCLUSION,),
        )
    )
    document = _document().model_copy(
        update={
            "clauses": _document().clauses[:2]
            + (
                objective,
                exclusion,
            )
        }
    )

    catalog = GemaraGuidanceMapper().map(document)

    assert catalog.metadata.applicability_groups is None
    assert catalog.guidelines[0].applicability is None
    assert {item.id for item in catalog.guidelines} == {"obj-8", "exclude-8"}


def test_scope_is_projected_to_front_matter() -> None:
    scope = _clause(
        "scope-1",
        "1",
        "Scope",
        text="This standard applies to railway software.",
        clause_type=ClauseType.SCOPE,
    )
    document = _document().model_copy(update={"clauses": _document().clauses + (scope,)})

    catalog = GemaraGuidanceMapper().map(document)

    assert catalog.front_matter == "This standard applies to railway software."
    assert "scope-1" not in {guideline.id for guideline in catalog.guidelines}
