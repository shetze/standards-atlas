from __future__ import annotations

import json

from standards_atlas.application.prompt_workbench.context import (
    ClausePromptContextAssembler,
    list_context_variants,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor
from standards_atlas.domain.model import ClauseType


def _clause() -> ClauseDescriptor:
    return ClauseDescriptor(
        id="clause-a",
        document_key="EN50126-1",
        reference="EN 50126-1:2017 6.2",
        clause_reference="6.2",
        content_hash="sha256:" + "b" * 64,
        clause_type=ClauseType.CLAUSE,
        heading="Life cycle",
        text="The life cycle shall be defined.",
        structural_context={
            "node_kind": "leaf",
            "ancestors": [{"clause_id": "clause-6", "reference": "6", "heading": "Life cycle"}],
            "scope_mentions": [
                {
                    "source": "text",
                    "surface_text": "applies to all phases",
                    "direction_hint": "inclusion",
                    "cardinality": None,
                    "status": "detected",
                }
            ],
            "scopes": [],
            "references": [],
        },
        reference_mentions=({"surface_text": "Clause 5", "targets": []},),
        subject_context={"ambiguous_candidates": ["railway system"]},
    )


def test_lists_all_custom_and_versioned_cbox_variants() -> None:
    assert [item.id for item in list_context_variants()] == [
        "none",
        "applicability-isolated-v1",
        "applicability-minimal-v1",
        "full-context-v1",
        "routing-source-v1",
        "structural-context-v1",
    ]


def test_assembles_full_cbox_and_compatible_template_variables() -> None:
    assembled = ClausePromptContextAssembler().assemble(
        _clause(), variant_id="full-context-v1", document_title="RAMS"
    )

    assert assembled.selected_context["document_key"] == "EN50126-1"
    assert assembled.selected_context["reference"] == "6.2"
    assert 'This clause is EN50126-1 6.2, "Life cycle".' in assembled.context_text
    assert json.loads(assembled.values["metadata"])["document_title"] == "RAMS"
    assert "ancestors" in json.loads(assembled.values["structural_context"])


def test_structural_template_variable_obeys_selected_context_variant() -> None:
    assembler = ClausePromptContextAssembler()

    without_context = assembler.assemble(_clause(), variant_id="none")
    structural = assembler.assemble(_clause(), variant_id="structural-context-v1")

    assert json.loads(without_context.values["structural_context"]) == {}
    assert json.loads(structural.values["structural_context"])["node_kind"] == "leaf"


def test_routing_source_matches_context_enrichment_input_contract() -> None:
    assembled = ClausePromptContextAssembler().assemble(
        _clause(), variant_id="routing-source-v1", document_title="RAMS"
    )

    assert assembled.selected_context["document_title"] == "RAMS"
    assert assembled.selected_context["reference"] == "EN 50126-1:2017 6.2"
    assert assembled.selected_context["scope_mentions"][0]["direction_hint"] == "inclusion"
    assert "context_routing" not in assembled.selected_context
