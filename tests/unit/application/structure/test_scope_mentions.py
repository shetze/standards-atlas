from standards_atlas.application.structure.scope_mentions import (
    extract_structural_scope_mentions,
)


def test_detects_scope_of_this_clause():
    mention = extract_structural_scope_mentions(
        "The scope of this clause is limited to onboard software."
    )[0]
    assert mention.direction_hint == "self"
    assert mention.cardinality == 1


def test_detects_scope_of_numbered_following_clauses():
    mention = extract_structural_scope_mentions(
        "The scope of the following three clauses is limited to SIL 2."
    )[0]
    assert mention.direction_hint == "forward"
    assert mention.cardinality == 3


def test_scope_heading_targets_subtree():
    mention = extract_structural_scope_mentions("", heading="Scope of verification")[0]
    assert mention.source == "heading"
    assert mention.direction_hint == "subtree"
