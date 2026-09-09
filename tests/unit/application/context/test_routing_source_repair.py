"""Regression cases from the reported IEC61508-3 routing corruption.

The clause/evidence fixture below is synthetic; coordinates mirror the report.
No private standard body or LLM runtime is required.
"""

import pytest

from standards_atlas.application.context.routing_normalization import (
    normalize_context_routing_targets,
)
from standards_atlas.application.references.extractor import (
    extract_reference_mentions,
    resolve_document_reference_mentions,
)
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
    StructuralContext,
    StructuralScopeEdge,
    TextBlock,
)

SOURCE = "clause-174e433da9f5"
DOC = "IEC61508-3"


def clause(coordinate, *, id_=None, text="", part="3", **kwargs):
    return Clause(
        id=ClauseId(value=id_ or f"target-{coordinate}"),
        reference=StandardReference(standard="IEC 61508", part=part, year=2010, clause=coordinate),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="source-text", text=text),) if text else (),
        **kwargs,
    )


def document(text=""):
    coordinates = ["6", "7", "7.2", "7.4.3", "7.4.4", "7.4.5", "7.4.8", "7.9", "A", "B", "C", "G"]
    coordinates += [f"7.2.2.{number}" for number in range(1, 13)]
    return EngineeringDocument(
        key=DocumentKey(value=DOC),
        title="Synthetic reference fixture",
        document_type=DocumentType.STANDARD,
        clauses=(clause("7.1.2.4", id_=SOURCE, text=text), *map(clause, coordinates)),
    )


def routing(text, *, id_=SOURCE, evidence=(), document_key=DOC):
    return ContextRouting(
        references=(
            ReferenceRouting(
                source_clause_id=SOURCE,
                target=ReferenceTarget(
                    document_key=document_key, clause_id=id_, reference=text, title="old"
                ),
                role="provides_exception",
                evidence=evidence,
            ),
        )
    )


CASES = [
    ("Annex G", ["G"]),
    ("7.4.3", ["7.4.3"]),
    ("7.2.2.12", ["7.2.2.12"]),
    ("7.2.2.1 to 7.2.2.9", [f"7.2.2.{n}" for n in range(1, 10)]),
    ("Annexes A and B", ["A", "B"]),
    ("7.4.5", ["7.4.5"]),
    ("7.4.4", ["7.4.4"]),
    ("Annex C", ["C"]),
    ("7.9", ["7.9"]),
    ("7.4.8", ["7.4.8"]),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
@pytest.mark.parametrize("overwritten", [False, True])
def test_reported_citations_repair_fresh_and_already_overwritten_targets(
    text,
    expected,
    overwritten,
):
    evidence = f"See {text} for the synthetic exception procedure."
    doc = document(evidence)
    before = routing(
        doc.clauses[0].reference.as_text() if overwritten else text, evidence=(evidence,)
    )
    diagnostics = []
    after = normalize_context_routing_targets(before, doc, diagnostics=diagnostics)
    assert [edge.target.reference for edge in after.references] == [
        f"IEC 61508-3:2010 {coordinate}" for coordinate in expected
    ]
    assert [edge.target.clause_id for edge in after.references] == [f"target-{c}" for c in expected]
    assert all(
        edge.evidence == (evidence,) and edge.role == before.references[0].role
        for edge in after.references
    )
    assert normalize_context_routing_targets(after, doc) == after
    if overwritten:
        assert diagnostics[0]["reason"] == "recovered_from_verbatim_source_evidence"


def test_true_self_and_annex_with_identical_corrupt_targets_remain_distinct():
    self_text = "The requirements of this clause may be customized."
    annex_text = "See Annex G for the synthetic data-driven example."
    doc = document(self_text + "\nNOTE 2 " + annex_text)
    first = routing(doc.clauses[0].reference.as_text(), evidence=(self_text,)).references[0]
    second = routing(doc.clauses[0].reference.as_text(), evidence=(annex_text,)).references[0]
    after = normalize_context_routing_targets(ContextRouting(references=(first, second)), doc)
    assert [edge.target.clause_id for edge in after.references] == [SOURCE, "target-G"]
    assert after.references[1].target.title != "old"


def test_unrelated_multiple_evidence_mentions_require_review_instead_of_guessing():
    evidence = "See 7.4.3 for an interface. Separately, Annex G describes an exception."
    doc = document(evidence)
    diagnostics = []
    after = normalize_context_routing_targets(
        routing("7", evidence=(evidence,)), doc, diagnostics=diagnostics
    )
    assert len(after.references) == 1
    assert after.references[0].target.clause_id is None
    assert diagnostics[0]["status"] == "ambiguous"
    assert diagnostics[0]["reason"] == "conflicting_evidence_requires_review"
    # A citation already consistent with one of the mentions is not changed to the other.
    after = normalize_context_routing_targets(routing("Annex G", evidence=(evidence,)), doc)
    assert after.references[0].target.clause_id == "target-G"


def test_unverified_evidence_never_overwrites_reference_text_with_an_invented_annex():
    evidence = "See Annex G for an exception."
    diagnostics = []
    after = normalize_context_routing_targets(
        routing("7", evidence=(evidence,)),
        document("No citation is present here."),
        diagnostics=diagnostics,
    )
    assert after.references[0].target.reference == "7"
    assert after.references[0].target.clause_id is None
    assert diagnostics[0]["status"] == "unverified"


def test_partial_ranges_are_not_collapsed_to_existing_endpoints():
    doc = document().model_copy(
        update={
            "clauses": tuple(
                item for item in document().clauses if item.reference.clause != "7.2.2.5"
            )
        }
    )
    after = normalize_context_routing_targets(routing("7.2.2.1 to 7.2.2.9"), doc)
    assert len(after.references) == 1
    assert after.references[0].target.clause_id is None
    assert after.references[0].target.reference == "7.2.2.1 to 7.2.2.9"


def test_scope_subclause_is_not_replaced_by_existing_parent_id():
    before = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id=SOURCE,
                reaches=(
                    ScopeReach(
                        kind="clause", document_key=DOC, clause_id="target-7", reference="7.4.4"
                    ),
                ),
            ),
        )
    )
    after = normalize_context_routing_targets(before, document())
    assert after.scopes[0].reaches[0].clause_id == "target-7.4.4"
    assert after.scopes[0].reaches[0].reference == "IEC 61508-3:2010 7.4.4"


def test_deterministic_scope_edges_correct_repeated_stale_labels():
    doc = document()
    ids = ("target-A", "target-B")
    source = doc.clauses[0].with_baseline_updates(
        structural_context=StructuralContext(
            node_kind="node",
            scopes=tuple(
                StructuralScopeEdge(
                    source_clause_id=SOURCE,
                    target_clause_id=id_,
                    status="resolved",
                    surface_text="following clauses",
                )
                for id_ in ids
            ),
        )
    )
    doc = doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    before = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id=SOURCE,
                reaches=tuple(
                    ScopeReach(kind="subtree", document_key=DOC, clause_id=id_, reference="7.1.2.4")
                    for id_ in ids
                ),
            ),
        )
    )
    after = normalize_context_routing_targets(before, doc)
    assert [reach.clause_id for reach in after.scopes[0].reaches] == list(ids)
    assert [reach.reference for reach in after.scopes[0].reaches] == [
        "IEC 61508-3:2010 A",
        "IEC 61508-3:2010 B",
    ]


def test_conditions_do_not_determine_scope_target():
    before = ContextRouting(
        scopes=(
            ScopeDeclaration(
                source_clause_id=SOURCE,
                reaches=(
                    ScopeReach(
                        kind="clause", document_key=DOC, clause_id="target-7", reference="7"
                    ),
                ),
                conditions=("use the procedure of 7.4.4",),
                evidence=("use the procedure of 7.4.4",),
            ),
        )
    )
    after = normalize_context_routing_targets(before, document("use the procedure of 7.4.4"))
    assert after.scopes[0].reaches[0].clause_id == "target-7"


def test_extraction_provides_annex_list_range_and_bare_subclause_targets_before_llm():
    text = "See Annex G; compare 7.4.3; use clauses 7.2.2.1 to 7.2.2.9 and Annexes A and B."
    doc = document(text)
    source = doc.clauses[0].with_baseline_updates(
        reference_mentions=extract_reference_mentions(text)
    )
    doc = doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    result = resolve_document_reference_mentions(doc)
    targets = {
        target.clause_id for m in result.clauses[0].reference_mentions for target in m.targets
    }
    assert {"target-G", "target-7.4.3", "target-A", "target-B", "target-7.2.2.5"} <= targets
    assert all(
        text[m.start_offset : m.end_offset] == m.surface_text
        for m in result.clauses[0].reference_mentions
    )


@pytest.mark.parametrize("text", ["IEC 61508-2:2010 7.4.3", "7.4.3 of IEC 61508-2:2010"])
def test_foreign_edition_does_not_leak_into_local_bare_mentions(text):
    doc = document(text)
    source = doc.clauses[0].with_baseline_updates(
        reference_mentions=extract_reference_mentions(text)
    )
    result = resolve_document_reference_mentions(
        doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    )
    assert result.clauses[0].reference_mentions
    assert not any(m.targets for m in result.clauses[0].reference_mentions)


def test_repair_retains_reviewed_routing_and_is_idempotent():
    from standards_atlas.domain.model.knowledge_state import ConfirmedAttribute

    text = "See Annex G for the synthetic exception."
    doc = document(text)
    source = doc.clauses[0].model_copy(
        update={
            "enrichments": doc.clauses[0].enrichments.model_copy(
                update={"context_routing": routing("7.1.2.4", evidence=(text,))}
            )
        }
    )
    doc = doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    repaired = repair_context_routing(doc)
    assert repaired.document.clauses[0].context_routing.references[0].target.clause_id == "target-G"
    assert repair_context_routing(repaired.document).report["clauses_changed"] == 0
    source = source.model_copy(
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
    protected = repair_context_routing(
        doc.model_copy(update={"clauses": (source, *doc.clauses[1:])})
    )
    assert protected.document.clauses[0].context_routing == source.context_routing
    assert protected.report["protected_clauses"] == 1


@pytest.mark.parametrize("text", ["Annex A and Table A.1", "Table A.1 and Annex A"])
def test_mixed_reference_kinds_and_unprefixed_table_coordinates_remain_distinct(text):
    doc = document()
    table = Clause(
        id=ClauseId(value="table-A.1"),
        reference=StandardReference(standard="IEC 61508", part="3", year=2010, clause="A.1"),
        clause_type=ClauseType.TABLE,
    )
    doc = doc.model_copy(update={"clauses": (*doc.clauses, clause("A.1"), table)})
    after = normalize_context_routing_targets(routing(text), doc)
    assert {edge.target.clause_id for edge in after.references} == {"target-A", "table-A.1"}
    assert normalize_context_routing_targets(after, doc) == after
