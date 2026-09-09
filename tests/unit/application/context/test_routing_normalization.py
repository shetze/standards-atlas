"""Routing coordinates must not conceal contradictory provider-supplied IDs."""

from __future__ import annotations

import pytest

from standards_atlas.application.context.routing_normalization import (
    normalize_context_routing_targets,
)
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
)

SOURCE = "clause-174e433da9f5"
ANNEX = "clause-6c33a8db3934"
DOCUMENT = "IEC61508-3"


def _clause(id_: str, coordinate: str, *, part: str = "3", **kwargs) -> Clause:
    return Clause(
        id=ClauseId(value=id_),
        reference=StandardReference(standard="IEC 61508", part=part, year=2010, clause=coordinate),
        clause_type=kwargs.pop("clause_type", ClauseType.CLAUSE),
        **kwargs,
    )


def _document(*extra: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=DOCUMENT),
        title="Synthetic reference-resolution fixture",
        document_type=DocumentType.STANDARD,
        clauses=(
            _clause("section-7", "7"),
            _clause(SOURCE, "7.1.2.4"),
            _clause(ANNEX, "G", heading="Synthetic annex"),
            _clause("annex-g-1", "G.1"),
            *extra,
        ),
    )


def _routing(text: str, *, target_id: str | None = SOURCE, document_key=DOCUMENT):
    return ContextRouting(
        references=(
            ReferenceRouting(
                source_clause_id=SOURCE,
                target=ReferenceTarget(
                    document_key=document_key, clause_id=target_id, reference=text
                ),
                role="provides_exception",
                evidence=("Synthetic evidence remains unchanged.",),
            ),
        )
    )


@pytest.mark.parametrize("target_id", [SOURCE, ANNEX, None, "missing-id"])
@pytest.mark.parametrize(
    "text",
    ["Annex G", "G", " annex   G. ", "IEC 61508-3:2010 Annex G", "IEC 61508-3 G"],
)
def test_explicit_annex_overrides_unverified_target_id(text, target_id):
    document = _document()
    before = _routing(text, target_id=target_id)
    after = normalize_context_routing_targets(before, document)
    target = after.references[0].target
    assert target.clause_id == ANNEX
    assert target.document_key == DOCUMENT
    assert target.reference == "IEC 61508-3:2010 G"
    assert after.references[0].source_clause_id == SOURCE
    assert after.references[0].role == before.references[0].role
    assert after.references[0].evidence == before.references[0].evidence
    assert before.references[0].target.reference == text
    assert normalize_context_routing_targets(after, document) == after


@pytest.mark.parametrize("text", ["this clause", "this subclause", "THIS SECTION"])
def test_self_reference_uses_source_not_supplied_target_id(text):
    after = normalize_context_routing_targets(_routing(text, target_id=ANNEX), _document())
    assert after.references[0].target.clause_id == SOURCE
    assert after.references[0].target.reference == "IEC 61508-3:2010 7.1.2.4"


@pytest.mark.parametrize(
    ("text", "target_id", "coordinate"),
    [
        ("7", "section-7", "7"),
        ("Clause 7", "section-7", "7"),
        ("Subclause G.1", "annex-g-1", "G.1"),
        ("Annex G.1", "annex-g-1", "G.1"),
        ("IEC 61508-3:2010 7.1.2.4", SOURCE, "7.1.2.4"),
    ],
)
def test_explicit_coordinates_resolve_without_target_ids(text, target_id, coordinate):
    after = normalize_context_routing_targets(
        _routing(text, target_id=None, document_key=None), _document()
    )
    assert after.references[0].target.clause_id == target_id
    assert after.references[0].target.reference == f"IEC 61508-3:2010 {coordinate}"


@pytest.mark.parametrize(
    "text",
    ["Annex Z", "G.99", "Annex G and Annex H", "following clauses", "IEC 61508-2:2010 G"],
)
def test_unresolved_text_is_preserved_without_false_self_link(text):
    document = _document()
    after = normalize_context_routing_targets(_routing(text), document)
    assert after.references[0].target.reference == text
    assert after.references[0].target.clause_id is None
    assert normalize_context_routing_targets(after, document) == after


def test_duplicate_coordinates_remain_unresolved_even_with_valid_local_id():
    document = _document(_clause("duplicate-g", "G"))
    after = normalize_context_routing_targets(_routing("Annex G", target_id=ANNEX), document)
    assert after.references[0].target.reference == "Annex G"
    assert after.references[0].target.clause_id is None


def test_short_reference_stays_in_source_part_and_full_reference_can_address_other_part():
    document = _document(_clause("other-part-g", "G", part="2"))
    local = normalize_context_routing_targets(_routing("Annex G"), document)
    assert local.references[0].target.clause_id == ANNEX
    qualified = normalize_context_routing_targets(_routing("IEC 61508-2:2010 G"), document)
    assert qualified.references[0].target.clause_id == "other-part-g"


def test_external_reference_is_not_rebound_even_if_ids_overlap():
    before = _routing("Annex G", document_key="IEC61508-2")
    assert normalize_context_routing_targets(before, _document()) == before


def test_table_reference_does_not_collapse_to_annex_subclause():
    document = _document(_clause("table-g-1", "Table G.1", clause_type=ClauseType.TABLE))
    after = normalize_context_routing_targets(_routing("Table G.1"), document)
    assert after.references[0].target.clause_id == "table-g-1"
    assert after.references[0].target.reference == "IEC 61508-3:2010 Table G.1"


def test_rejected_target_title_is_not_attached_to_the_resolved_annex():
    before = _routing("Annex G")
    edge = before.references[0]
    before = before.model_copy(
        update={
            "references": (
                edge.model_copy(
                    update={"target": edge.target.model_copy(update={"title": "Wrong"})}
                ),
            )
        }
    )
    after = normalize_context_routing_targets(before, _document())
    assert after.references[0].target.title == "Synthetic annex"


def test_scope_reaches_resolve_explicit_text_instead_of_trusting_provider_ids():
    document = _document()
    before = _routing("Annex G").model_copy(
        update={
            "scopes": (
                ScopeDeclaration(
                    source_clause_id=SOURCE,
                    reaches=(
                        ScopeReach(kind="clause", clause_id="section-7", reference="7.1.2.4"),
                        ScopeReach(kind="subtree", clause_id=ANNEX, reference="7.1.2.4"),
                    ),
                ),
            )
        }
    )
    after = normalize_context_routing_targets(before, document)
    assert [r.reference for r in after.scopes[0].reaches] == [
        "IEC 61508-3:2010 7.1.2.4",
        "IEC 61508-3:2010 7.1.2.4",
    ]
    assert after.references[0].target.clause_id == ANNEX
