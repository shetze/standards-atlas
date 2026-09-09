"""Synthetic regressions for the IEC61508-0 scope transport failures."""

from __future__ import annotations

import pytest

from standards_atlas.application.context.scope_targets import ScopeTargetResolver
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ScopeReach,
    StandardReference,
    StructuralContext,
    StructuralNodeKind,
    TextBlock,
)

PART_EVIDENCE = "This synthetic scope governs Parts 1, 2, 3 and 4 of IEC 61508."


def document(part="0", year=2005, key=None):
    clauses = tuple(
        Clause(
            id=ClauseId(value=f"clause-{part}-{coordinate}"),
            reference=StandardReference(
                standard="IEC 61508", part=part, year=year, clause=coordinate
            ),
            clause_type=ClauseType.SCOPE if coordinate in {"4.5", "4.7"} else ClauseType.CLAUSE,
            content=(
                TextBlock(
                    id=f"text-{coordinate}",
                    text=(
                        PART_EVIDENCE if coordinate == "4.7" else "Synthetic local scope example."
                    ),
                ),
            ),
            structural_context=StructuralContext(node_kind=StructuralNodeKind.LEAF),
        )
        for coordinate in ("1", "4.5", "4.7", "7", "7.1", "7.2", "G")
    )
    return EngineeringDocument(
        key=DocumentKey(value=key or f"IEC61508-{part}"),
        title="Synthetic standard",
        document_type=DocumentType.STANDARD,
        clauses=clauses,
    )


def resolver(*extra):
    parts = tuple(document(str(p), 2010) for p in range(1, 5))
    return ScopeTargetResolver(document(), parts + extra)


@pytest.mark.parametrize("descendants,kind", [(False, "clause"), (True, "subtree")])
def test_explicit_clause_never_becomes_whole_document(descendants, kind):
    (reach,) = resolver().resolve(
        "IEC 61508-0:2005 4.5", include_descendants=descendants, source_clause_id="clause-0-4.5"
    )
    assert reach.kind.value == kind
    assert reach.clause_id == "clause-0-4.5"
    assert reach.reference == "IEC 61508-0:2005 4.5"
    assert reach.part is None
    assert ScopeReach.model_validate(reach.model_dump()) == reach


@pytest.mark.parametrize(
    "reference",
    [
        "Parts 1, 2, 3 and 4 of IEC 61508",
        "Parts 1 to 4 of IEC 61508",
        "Parts 1, 2, 3 and 4",
        "1, 2, 3 and 4 of IEC 61508",
    ],
)
def test_part_list_resolves_all_physical_parts_not_source_or_clause_numbers(reference):
    reaches = resolver().resolve(
        reference,
        include_descendants=True,
        source_clause_id="clause-0-4.7",
        evidence=(PART_EVIDENCE,),
    )
    assert [r.document_key for r in reaches] == [f"IEC61508-{p}" for p in range(1, 5)]
    assert [r.part for r in reaches] == [f"Part {p}" for p in range(1, 5)]
    assert all(
        r.kind.value == "part" and r.clause_id is None and r.reference is None for r in reaches
    )
    assert all(ScopeReach.model_validate(r.model_dump()) == r for r in reaches)


def test_unlabelled_list_does_not_guess_that_numbers_are_parts():
    with pytest.raises(ValueError, match="cannot identify scope target"):
        resolver().resolve(
            "1, 2, 3 and 4 of IEC 61508",
            include_descendants=True,
            source_clause_id="clause-0-4.5",
            evidence=(PART_EVIDENCE,),
        )


def test_part_list_is_atomic_when_a_target_is_missing():
    with pytest.raises(ValueError, match="Part 4.*found 0"):
        ScopeTargetResolver(document(), (document("1"), document("2"), document("3"))).resolve(
            "Parts 1, 2, 3 and 4 of IEC 61508",
            include_descendants=True,
            source_clause_id="clause-0-4.7",
        )


def test_part_editions_must_not_be_guessed():
    index = resolver(document("1", 2005, "IEC61508-1-2005"))
    with pytest.raises(ValueError, match="Part 1.*found 2"):
        index.resolve(
            "Part 1 of IEC 61508", include_descendants=True, source_clause_id="clause-0-4.7"
        )
    (reach,) = index.resolve(
        "Part 1 of IEC 61508:2010", include_descendants=True, source_clause_id="clause-0-4.7"
    )
    assert reach.document_key == "IEC61508-1"


@pytest.mark.parametrize(
    "reference,key,kind,part",
    [
        ("this document", "IEC61508-0", "document", None),
        ("IEC 61508-0:2005", "IEC61508-0", "document", None),
        ("this part", "IEC61508-0", "part", "Part 0"),
        ("IEC 61508-1:2010", "IEC61508-1", "document", None),
        ("IEC61508-1", "IEC61508-1", "document", None),
    ],
)
def test_whole_targets_do_not_receive_clause_addresses(reference, key, kind, part):
    (reach,) = resolver().resolve(
        reference, include_descendants=True, source_clause_id="clause-0-4.7"
    )
    assert reach.document_key == key and reach.kind.value == kind and reach.part == part
    assert reach.clause_id is None and reach.reference is None


def test_qualified_external_clause_uses_its_actual_target_document():
    (reach,) = resolver().resolve(
        "IEC 61508-1:2010 7.1", include_descendants=False, source_clause_id="clause-0-4.7"
    )
    assert reach.document_key == "IEC61508-1"
    assert reach.clause_id == "clause-1-7.1"
    assert reach.reference == "IEC 61508-1:2010 7.1"


def test_clause_ranges_expand_only_when_complete():
    index = resolver()
    assert (
        len(index.resolve("7.1 to 7.2", include_descendants=False, source_clause_id="clause-0-4.7"))
        == 2
    )
    (reach,) = index.resolve(
        "7.1 to 7.3", include_descendants=False, source_clause_id="clause-0-4.7"
    )
    assert reach.reference == "7.1 to 7.3" and reach.clause_id is None


@pytest.mark.parametrize("target", ["IEC 9999", "the software lifecycle", " "])
def test_unidentified_region_is_not_an_empty_success_or_a_local_document(target):
    with pytest.raises(ValueError):
        resolver().resolve(target, include_descendants=True, source_clause_id="clause-0-4.7")


def test_condition_reference_is_not_used_to_replace_scope_target():
    (reach,) = resolver().resolve(
        "4.5", include_descendants=False, source_clause_id="clause-0-4.7", evidence=(PART_EVIDENCE,)
    )
    assert reach.clause_id == "clause-0-4.5"


def test_boolean_is_not_coerced_from_a_truthy_string():
    with pytest.raises(ValueError, match="boolean"):
        resolver().resolve("4.5", include_descendants="false", source_clause_id="clause-0-4.7")


@pytest.mark.parametrize(
    "target",
    [
        "IEC 61508-2 Figure 2 and Table 1",
        "Figure 2 and Table 1 of IEC 61508-2",
        "IEC 61508-2:2010 Figures 2 to 3 and Table 1",
    ],
)
@pytest.mark.parametrize("descendants,kind", [(False, "clause"), (True, "subtree")])
def test_missing_object_ids_preserve_the_whole_citation_without_widening(target, descendants, kind):
    (reach,) = resolver().resolve(
        target, include_descendants=descendants, source_clause_id="clause-0-4.7"
    )
    assert reach.document_key == "IEC61508-2"
    assert reach.reference == target
    assert reach.clause_id is None and reach.part is None
    assert reach.kind.value == kind
    assert ScopeReach.model_validate(reach.model_dump(mode="json")) == reach


def test_mixed_object_group_is_atomic_when_only_table_exists():
    target = document("2", 2010)
    table = target.clauses[0].model_copy(
        update={
            "id": ClauseId(value="table-1"),
            "clause_type": ClauseType.TABLE,
        }
    )
    target = target.model_copy(update={"clauses": (*target.clauses, table)})
    index = ScopeTargetResolver(document(), (target,))
    text = "IEC 61508-2 Figure 2 and Table 1"
    (reach,) = index.resolve(text, include_descendants=False, source_clause_id="clause-0-4.7")
    assert reach.reference == text and reach.clause_id is None


def test_mixed_object_group_expands_only_when_both_exact_targets_exist():
    target = document("2", 2010)
    base = target.clauses[0]
    table = base.model_copy(
        update={
            "id": ClauseId(value="table-1"),
            "clause_type": ClauseType.TABLE,
        }
    )
    figure = base.model_copy(
        update={
            "id": ClauseId(value="figure-2"),
            "clause_type": ClauseType.MISC,
            "reference": base.reference.model_copy(update={"clause": "Figure 2"}),
        }
    )
    target = target.model_copy(update={"clauses": (*target.clauses, table, figure)})
    reaches = ScopeTargetResolver(document(), (target,)).resolve(
        "IEC 61508-2 Figure 2 and Table 1",
        include_descendants=False,
        source_clause_id="clause-0-4.7",
    )
    assert [r.clause_id for r in reaches] == ["figure-2", "table-1"]
    assert [r.reference for r in reaches] == [
        "IEC 61508-2:2010 Figure 2",
        "IEC 61508-2:2010 Table 1",
    ]


def test_ambiguous_figure_document_edition_is_still_an_error():
    with pytest.raises(ValueError, match="ambiguous scope citation"):
        resolver(document("2", 2005, "IEC61508-2-2005")).resolve(
            "IEC 61508-2 Figure 2",
            include_descendants=False,
            source_clause_id="clause-0-4.7",
        )
