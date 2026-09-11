"""Synthetic contract: only allowlisted, null external IDs may change."""

import pytest

from standards_atlas.application.context.reference_target_repair import (
    ReferenceTargetRepairAllowlist,
    edge_sha256,
    source_text_sha256,
)
from standards_atlas.application.references.diagnostics import TargetDiagnostics
from standards_atlas.application.services.context_routing_repair import repair_context_routing
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    ContextRouting,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ReferenceRouting,
    ReferenceTarget,
    ScopeDeclaration,
    ScopeReach,
    StandardReference,
    TextBlock,
)


def document(part, coordinates=("1", "7.1", "7.2"), year=2026, key=None):
    return EngineeringDocument(
        key=DocumentKey(value=key or f"IEC99999-{part}"),
        title="Synthetic external target fixture",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"p{part}-{year}-{coordinate}"),
                clause_type=ClauseType.CLAUSE,
                reference=StandardReference(
                    standard="IEC 99999", part=str(part), year=year, clause=coordinate
                ),
            )
            for coordinate in coordinates
        ),
    )


def fixture(reference="IEC 99999-2:2026 7.1", evidence=None, text=None, key="IEC99999-2"):
    evidence = evidence or f"See {reference} for an example."
    doc = document(1)
    source = doc.clauses[0].with_baseline_updates(
        content=(TextBlock(id="text", text=text or evidence),)
    )
    routing = ContextRouting(
        references=(
            ReferenceRouting(
                source_clause_id=source.id.value,
                target=ReferenceTarget(document_key=key, reference=reference, title="Keep me"),
                role="provides_procedure",
                evidence=(evidence,),
            ),
        ),
        scopes=(
            ScopeDeclaration(
                source_clause_id=source.id.value,
                reaches=(ScopeReach(kind="clause", reference="missing"),),
                conditions=("condition",),
                exclusions=("exclusion",),
                qualifications=("qualification",),
                evidence=("scope evidence",),
            ),
        ),
    )
    source = source.model_copy(
        update={"enrichments": source.enrichments.model_copy(update={"context_routing": routing})}
    )
    return doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})


def allowlist(doc):
    source = doc.clauses[0]
    return ReferenceTargetRepairAllowlist.model_validate(
        {
            "contract": "context-reference-target-allowlist-v1",
            "entries": [
                {
                    "source_document_key": doc.key.value,
                    "source_clause_id": source.id.value,
                    "reference_index": 0,
                    "source_text_sha256": source_text_sha256(source),
                    "edge_sha256": edge_sha256(source.context_routing.references[0]),
                    "target_document_key": "IEC99999-2",
                    "target_clause_id": "p2-2026-7.1",
                    "target_reference": "IEC 99999-2:2026 7.1",
                }
            ],
        }
    )


def repair(doc, selection=None, documents=None):
    return repair_context_routing(
        doc,
        documents=(document(2),) if documents is None else documents,
        reference_targets_only=True,
        allowlist=selection or allowlist(doc),
    )


def test_only_missing_id_changes_and_second_repair_is_a_noop():
    before = fixture()
    selection = allowlist(before)
    result = repair(before, selection)
    source = result.document.clauses[0]
    old_edge = before.clauses[0].context_routing.references[0]
    new_edge = source.context_routing.references[0]
    assert new_edge.target.clause_id == "p2-2026-7.1"
    assert new_edge == old_edge.model_copy(
        update={"target": old_edge.target.model_copy(update={"clause_id": "p2-2026-7.1"})}
    )
    assert source.context_routing.scopes == before.clauses[0].context_routing.scopes
    assert source.baseline == before.clauses[0].baseline
    assert source.provenance == before.clauses[0].provenance
    assert result.report["baseline_clauses_refreshed"] == 0
    assert result.report["reference_ids_completed"] == 1
    assert result.report["reference_roles_corrected"] == 0
    assert result.report["references_before"] == result.report["references_after"]
    again = repair(result.document, selection)
    assert again.document == result.document
    assert again.report["clauses_changed"] == 0


@pytest.mark.parametrize(
    "reference,evidence,text,key,reason",
    [
        ("IEC 99999-2:2025 7.1", None, None, "IEC99999-2", "not_a_unique_single_target"),
        ("IEC 99999-2:2026 7.9", None, None, "IEC99999-2", "not_a_unique_single_target"),
        ("IEC 99999-2:2026 7.1 and 7.2", None, None, "IEC99999-2", "not_a_unique_single_target"),
        ("IEC 99999-2:2026 7.1 and 7.9", None, None, "IEC99999-2", "not_a_unique_single_target"),
        ("IEC 99999-2:2026 7.1", None, None, "IEC99999-1", "document_key_mismatch"),
        (
            "IEC 99999-2:2026 7.1",
            "See IEC 99999-2:2026 7.2.",
            None,
            "IEC99999-2",
            "target_not_supported_by_verbatim_source",
        ),
        (
            "IEC 99999-2:2026 7.1",
            None,
            "No reference is present.",
            "IEC99999-2",
            "target_not_supported_by_verbatim_source",
        ),
        (
            "IEC 99999-2:2026 7.1",
            "See IEC 99999-2:2026 7.1 and 7.9.",
            None,
            "IEC99999-2",
            "target_not_supported_by_verbatim_source",
        ),
    ],
)
def test_unsafe_or_compound_targets_never_change(reference, evidence, text, key, reason):
    doc = fixture(reference, evidence=evidence, text=text, key=key)
    result = repair(doc)
    assert result.document == doc
    assert result.report["diagnostics"][0]["reason"] == reason


def test_complete_source_list_can_prove_an_existing_single_address_without_expanding_it():
    doc = fixture(evidence="See IEC 99999-2:2026 7.1 and 7.2.")
    result = repair(doc)
    assert result.report["reference_ids_completed"] == 1
    assert result.report["references_after"] == 1


def test_stale_source_and_edge_are_rejected():
    doc = fixture()
    selection = allowlist(doc)
    changed = fixture(text=doc.clauses[0].plain_text + " Another sentence.")
    assert repair(changed, selection).report["diagnostics"][0]["reason"] == "source_text_changed"
    changed = fixture(reference="IEC 99999-2:2026 7.2", text=doc.clauses[0].plain_text)
    assert repair(changed, selection).report["diagnostics"][0]["reason"] == "edge_changed"


def test_protected_values_and_existing_wrong_ids_are_never_rewritten():
    from standards_atlas.domain.model.knowledge_state import ConfirmedAttribute

    doc = fixture()
    selection = allowlist(doc)
    source = doc.clauses[0]
    protected = source.model_copy(
        update={
            "provenance": source.provenance.model_copy(
                update={
                    "confirmed_attributes": (
                        ConfirmedAttribute(
                            path="enrichments.context_routing", authority="reviewer"
                        ),
                    )
                }
            )
        }
    )
    doc = doc.model_copy(update={"clauses": (protected, *doc.clauses[1:])})
    assert repair(doc, selection).document == doc
    assert repair(doc, selection).report["protected_clauses"] == 1
    edge = source.context_routing.references[0]
    source = source.model_copy(
        update={
            "enrichments": source.enrichments.model_copy(
                update={
                    "context_routing": source.context_routing.model_copy(
                        update={
                            "references": (
                                edge.model_copy(
                                    update={
                                        "target": edge.target.model_copy(
                                            update={"clause_id": "wrong"}
                                        )
                                    }
                                ),
                            )
                        }
                    )
                }
            )
        }
    )
    doc = doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    assert repair(doc, selection).document == doc
    assert repair(doc, selection).report["diagnostics"][0]["reason"] == "already_addressed"


def test_allowlist_is_mandatory_and_duplicate_entries_are_invalid():
    doc = fixture()
    with pytest.raises(ValueError, match="requires --allowlist"):
        repair_context_routing(doc, reference_targets_only=True)
    with pytest.raises(ValueError, match="requires --reference-targets-only"):
        repair_context_routing(doc, allowlist=allowlist(doc))
    payload = allowlist(doc).model_dump()
    payload["entries"] *= 2
    with pytest.raises(ValueError, match="duplicate source edges"):
        ReferenceTargetRepairAllowlist.model_validate(payload)
    empty = allowlist(doc).model_copy(update={"entries": ()})
    assert repair(doc, empty).document == doc


def test_missing_or_ambiguous_target_catalog_never_changes_values():
    doc = fixture(reference="IEC 99999-2 7.1")
    assert repair(doc, documents=()).document == doc
    assert repair(doc, documents=(document(2), document(2, year=2025, key="old"))).document == doc


@pytest.mark.parametrize(
    "text,key,reason",
    [
        ("IEC 99999-2:2026", "IEC99999-2", "document_reference"),
        ("IEC 99999-2:2026", "IEC99999-1", "document_key_mismatch"),
        ("Table 1", None, "object_not_indexed"),
        ("IEC 99999-2:2026 Table 1", "IEC99999-2", "object_not_indexed"),
        ("IEC 99999-2:2025 7.1", "IEC99999-2", "edition_mismatch"),
        ("IEC 99999-3:2026 7.1", None, "target_document_not_loaded"),
        ("7.9", None, "unresolved_clause"),
        ("7.1", None, "addressable_clause"),
    ],
)
def test_diagnostics_do_not_conflate_missing_ids_with_semantic_failures(text, key, reason):
    doc = fixture()
    classifier = TargetDiagnostics(doc, (document(2),))
    assert classifier.reason(text, key, doc.clauses[0].id.value) == reason
