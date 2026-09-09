"""Bounded, source-grounded semantics; no literal standard body or special clause ID."""

import json
from pathlib import Path

import pytest

from standards_atlas.application.context.information_routing import InformationRoutingPolicy
from standards_atlas.application.references.catalog import ReferenceDocumentCatalog
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
    TextBlock,
)

FIXTURE = json.loads(Path("tests/fixtures/context/information-routing.json").read_text())


def document(part="0", text="", *, year=2010, key=None):
    return EngineeringDocument(
        key=DocumentKey(value=key or f"IEC61508-{part}"),
        title="Synthetic routing regression",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"p{part}-{coordinate}"),
                clause_type=ClauseType.CLAUSE,
                reference=StandardReference(
                    standard="IEC 61508",
                    part=part,
                    year=year,
                    clause=coordinate,
                ),
                content=(TextBlock(id="body", text=text),) if coordinate == "4.9" and text else (),
                structural_context=StructuralContext(node_kind="leaf"),
            )
            for coordinate in ("4.9", "A", "6", "7", "8")
        ),
    )


def world():
    text = "\n\n".join(FIXTURE[k] for k in ("faq", "reading", "interpretation"))
    source = document(text=text)
    external = tuple(document(str(part)) for part in (1, 2, 3, 5, 6))
    catalog = ReferenceDocumentCatalog(source, external)
    scope = ScopeDeclaration(
        source_clause_id="p0-4.9",
        reaches=tuple(
            ScopeReach(
                kind="clause",
                document_key=t.document_key,
                reference=t.reference,
                clause_id=t.clause_id,
            )
            for text in FIXTURE["scope_targets"]
            for t in catalog.targets(text, "p0-4.9")
        ),
        conditions=(FIXTURE["interpretation"],),
        evidence=(FIXTURE["reading"],),
    )
    faq_target = catalog.targets("Annex A", "p0-4.9")[0]
    faq_scope = ScopeDeclaration(
        source_clause_id="p0-4.9",
        reaches=(
            ScopeReach(
                kind="clause",
                document_key=source.key.value,
                clause_id=faq_target.clause_id,
                reference=faq_target.reference,
            ),
        ),
        evidence=(FIXTURE["faq"],),
    )
    routing = ContextRouting(
        scopes=(scope, faq_scope),
        references=(
            ReferenceRouting(
                source_clause_id="p0-4.9",
                target=faq_target,
                role="provides_applicability",
                evidence=(FIXTURE["faq"],),
            ),
        ),
    )
    source = source.model_copy(
        update={
            "clauses": (
                source.clauses[0].with_context_routing(routing),
                *source.clauses[1:],
            )
        }
    )
    return source, external


def test_reading_and_faq_scopes_become_complete_references_with_no_fabricated_ids():
    source, external = world()
    repaired = repair_context_routing(source, documents=external)
    routing = repaired.document.clauses[0].context_routing
    assert not routing.scopes
    assert len(routing.references) == 11
    assert {e.role for e in routing.references} == {"other"}
    assert {e.target.clause_id for e in routing.references if e.target.clause_id} == {
        "p0-A",
        "p5-A",
        "p1-6",
        "p1-7",
        "p1-8",
        "p6-A",
        "p2-7",
        "p3-7",
    }
    assert [e.target.reference for e in routing.references if e.target.clause_id is None] == [
        "IEC 61508-1 Figure 2 and Table 1",
        "IEC 61508-2 Figure 2 and Table 1",
        "IEC 61508-3 Figure 3 and Table 1",
    ]
    assert all(e.evidence for e in routing.references)
    assert all(
        " ".join(q.split()) in " ".join(source.clauses[0].plain_text.split())
        for e in routing.references
        for q in e.evidence
    )
    assert repaired.report["informational_scopes_reclassified"] == 2
    assert repaired.report["reference_roles_corrected"] == 1
    assert repaired.report["requires_review"] == 0
    assert repaired.report["unresolved_references_after"] == 3
    assert source.clauses[0].content == repaired.document.clauses[0].content
    assert repaired.document.clauses[0].context_routing != source.clauses[0].context_routing
    again = repair_context_routing(repaired.document, documents=external)
    assert again.report["clauses_changed"] == 0
    assert again.document.model_dump_json() == repaired.document.model_dump_json()
    assert not any(
        m.range_start == "61508" for m in repaired.document.clauses[0].reference_mentions
    )


def test_scopes_with_confirmed_authority_are_never_reclassified():
    source, external = world()
    original = source.clauses[0].confirm_authoritative("enrichments.context_routing")
    source = source.model_copy(update={"clauses": (original, *source.clauses[1:])})
    result = repair_context_routing(source, documents=external)
    assert result.document.clauses[0].context_routing == original.context_routing
    assert result.report["protected_clauses"] == 1
    assert result.report["informational_scopes_reclassified"] == 0


def test_unverified_scope_evidence_is_not_silently_removed():
    source, external = world()
    routing = source.clauses[0].context_routing
    altered = routing.scopes[0].model_copy(
        update={"evidence": ("Further information see Annex Z.",)}
    )
    result = InformationRoutingPolicy(source, external).normalize(ContextRouting(scopes=(altered,)))
    assert result.scopes == (altered,)
    assert not result.references


@pytest.mark.parametrize(
    "text",
    [
        "This restriction applies to Table 1.",
        "This clause applies to Annex A.",
        "For further information see Annex A. Its provisions shall apply to this document.",
        "The following restrictions govern Table 1.",
        "This document covers low-voltage equipment; for further information see Annex A.",
    ],
)
def test_genuine_scopes_do_not_require_conditions_or_numeric_target_ids(text):
    source = document(text=text)
    scope = ScopeDeclaration(
        source_clause_id="p0-4.9",
        reaches=(ScopeReach(kind="clause", reference="Table 1"),),
        evidence=(text,),
    )
    routing = ContextRouting(scopes=(scope,))
    assert InformationRoutingPolicy(source).normalize(routing) == routing


def test_mixed_context_is_preserved_and_reported_instead_of_deleting_scope():
    source = document(
        text="For further information see Annex A.\n\nThe restrictions apply to Table 1."
    )
    scope = ScopeDeclaration(
        source_clause_id="p0-4.9",
        reaches=(ScopeReach(kind="clause", reference="Table 1"),),
        evidence=("For further information see Annex A.",),
    )
    diagnostics = []
    after = InformationRoutingPolicy(source).normalize(
        ContextRouting(scopes=(scope,)), diagnostics=diagnostics
    )
    assert after.scopes == (scope,)
    assert diagnostics[0]["status"] == "requires_review"


@pytest.mark.parametrize(
    ("text", "role"),
    [
        ("For further information see Annex A, which defines the terminology.", "defines"),
        ("For further information see Annex A for the exception.", "provides_exception"),
        (
            "For further information see Annex A for applicability details.",
            "provides_applicability",
        ),
        ("For further information see Annex A for the procedure.", "provides_procedure"),
    ],
)
def test_explicitly_supported_reference_roles_are_preserved(text, role):
    source = document(text=text)
    edge = ReferenceRouting(
        source_clause_id="p0-4.9",
        target=ReferenceTarget(reference="Annex A"),
        role=role,
        evidence=(text,),
    )
    routing = ContextRouting(references=(edge,))
    assert InformationRoutingPolicy(source).normalize(routing) == routing


def test_unknown_document_and_ambiguous_edition_never_get_local_ids():
    source = document()
    external = (document("3"), document("3", year=2001, key="old-3"))
    catalog = ReferenceDocumentCatalog(source, external)
    for text in ("IEC 61508-3 Clause 7", "IEC 61508-9 Clause 7"):
        (target,) = catalog.targets(text, "p0-4.9")
        assert target.reference == text
        assert target.document_key is None
        assert target.clause_id is None
    (target,) = catalog.targets("IEC 61508-3:2001 Clause 7", "p0-4.9")
    assert target.document_key == "old-3"
    assert target.clause_id == "p3-7"


@pytest.mark.parametrize("evidence_mode", ["whole_clause", "unverified", "missing"])
def test_broad_or_unverified_evidence_cannot_bypass_the_semantic_guard(evidence_mode):
    source, external = world()
    clause = source.clauses[0]
    evidence = {
        "whole_clause": (clause.plain_text,),
        "unverified": ("For further information see Annex Z.",),
        "missing": (),
    }[evidence_mode]
    scope = clause.context_routing.scopes[0].model_copy(update={"evidence": evidence})
    diagnostics = []
    result = InformationRoutingPolicy(source, external).normalize(
        ContextRouting(scopes=(scope,)), diagnostics=diagnostics
    )
    assert result.scopes == (scope,)
    assert diagnostics[0]["status"] == "requires_review"
    assert diagnostics[0]["reason"] == "informational_source_requires_direct_scope_evidence"
