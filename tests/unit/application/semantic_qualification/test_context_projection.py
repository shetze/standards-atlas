from standards_atlas.application.semantic_qualification.context_projection import (
    project_cbox_context,
)


def test_projects_readable_cbox_context_without_internal_bookkeeping() -> None:
    context = {
        "knowledge_domain": "functional-safety",
        "document_key": "ISO26262-5",
        "clause_id": "opaque-clause-id",
        "reference": "8.4.2",
        "heading": "Evaluation of hardware architectural metrics",
        "parent_id": "opaque-parent-id",
        "ancestor_headings": [
            {
                "clause_id": "parent-id",
                "reference": "8.4",
                "heading": "Evaluation of the hardware architecture",
            },
            {
                "clause_id": "grandparent-id",
                "reference": "8",
                "heading": "Hardware architectural metrics",
            },
        ],
        "structural_roles": ["requirement", "explanation"],
        "clause_type": "clause",
        "canonical_section": "body",
        "document_categories": ["normative_technical_elements"],
        "structural_context": {
            "sibling": {"index": 1, "count": 3, "previous_clause_id": "x", "next_clause_id": "y"}
        },
        "eligibility": {"eligible": True, "reason": "internal"},
        "content_profile": "text_dominant",
        "table_block_count": 0,
        "context_routing": {
            "scopes": [
                {
                    "source_clause_id": "opaque-clause-id",
                    "reaches": [
                        {
                            "kind": "subtree",
                            "document_key": "ISO26262-5",
                            "reference": "8.4",
                        }
                    ],
                    "conditions": ["for safety-related hardware elements"],
                    "exclusions": [],
                    "qualifications": [],
                    "evidence": [],
                }
            ],
            "references": [
                {
                    "source_clause_id": "opaque-clause-id",
                    "target": {
                        "document_key": "ISO26262-5",
                        "reference": "8.4.1",
                    },
                    "role": "provides_procedure",
                    "evidence": [],
                }
            ],
        },
    }

    projected = project_cbox_context(context)

    assert 'ISO26262-5 8.4.2, "Evaluation of hardware architectural metrics"' in projected
    assert '8.4, "Evaluation of the hardware architecture"' in projected
    assert "clause 2 of 3 sibling clauses" in projected
    assert (
        "Scope routing: this declaration governs the subtree rooted at ISO26262-5 8.4." in projected
    )
    assert "Scope conditions: for safety-related hardware elements." in projected
    assert "ISO26262-5 8.4.1 provides procedure for this clause" in projected
    assert "opaque-clause-id" not in projected
    assert "opaque-parent-id" not in projected
    assert "eligibility" not in projected
    assert "requirement" not in projected
    assert "explanation" not in projected
    assert "text_dominant" not in projected


def test_projects_uninterpreted_reference_mentions_without_clause_ids() -> None:
    context = {
        "document_key": "IEC61508-3",
        "reference": "7.4.2",
        "reference_mentions": [
            {
                "surface_text": "IEC 61508-2, 7.4.3",
                "targets": [
                    {
                        "document_key": "IEC61508-2",
                        "clause_id": "opaque-target-id",
                        "reference": "7.4.3",
                        "title": "Design requirements",
                    }
                ],
            }
        ],
    }

    projected = project_cbox_context(context)

    assert "The clause contains references to IEC61508-2 7.4.3." in projected
    assert "opaque-target-id" not in projected


def test_projection_is_stable_for_sparse_context() -> None:
    assert project_cbox_context({"document_key": "EN50126-1", "reference": "6.2"}) == (
        "This clause is EN50126-1 6.2."
    )


def test_full_context_frame_preserves_existing_projection() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        FULL_CONTEXT_V1,
        frame_cbox_context,
    )
    from standards_atlas.application.semantic_qualification.context_projection import (
        render_cbox_context,
    )

    context = {
        "document_key": "ISO26262-5",
        "reference": "8.4.2",
        "heading": "Evaluation",
        "clause_type": "clause",
        "canonical_section": "body",
        "ancestor_headings": [{"reference": "8.4", "heading": "Architecture"}],
        "structural_context": {"sibling": {"index": 0, "count": 2}},
        "document_categories": ["normative_technical_elements"],
        "semantic_sections": ["requirements"],
        "context_routing": {
            "scopes": [
                {
                    "reaches": [
                        {"kind": "subtree", "document_key": "ISO26262-5", "reference": "8.4"}
                    ],
                    "conditions": ["for hardware elements"],
                }
            ],
            "references": [
                {
                    "target": {"document_key": "ISO26262-5", "reference": "8.4.1"},
                    "role": "provides_procedure",
                }
            ],
        },
    }

    frame = frame_cbox_context(context, FULL_CONTEXT_V1)

    assert frame.policy_id == "full-context"
    assert frame.policy_version == "1"
    assert render_cbox_context(frame) == project_cbox_context(context)


def test_frame_policy_can_omit_context_without_inventing_replacements() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        CBoxFramePolicy,
        frame_cbox_context,
    )
    from standards_atlas.application.semantic_qualification.context_projection import (
        render_cbox_context,
    )

    context = {
        "document_key": "EN50126-1",
        "reference": "4.2",
        "heading": "Purpose",
        "canonical_section": "scope",
        "ancestor_headings": [{"reference": "4", "heading": "Scope"}],
        "semantic_sections": ["scope"],
        "context_routing": {
            "scopes": [{"conditions": ["when used for railway applications"]}],
        },
    }
    policy = CBoxFramePolicy(
        id="minimal-test",
        version="1",
        canonical_section=False,
        ancestor_identity=False,
        ancestor_heading=False,
        semantic_sections=False,
        scope_routing=False,
        reference_routing=False,
        reference_mentions=False,
        clause_type=False,
        sibling_position=False,
        document_categories=False,
    )

    frame = frame_cbox_context(context, policy)
    rendered = render_cbox_context(frame)

    assert frame.values == {
        "document_key": "EN50126-1",
        "reference": "4.2",
        "heading": "Purpose",
    }
    assert rendered == 'This clause is EN50126-1 4.2, "Purpose".'
    assert "Scope" not in rendered
    assert "railway applications" not in rendered


def test_framing_does_not_expose_opaque_or_bookkeeping_fields() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        FULL_CONTEXT_V1,
        frame_cbox_context,
    )

    context = {
        "document_key": "IEC61508-3",
        "reference": "7.4.2",
        "clause_id": "opaque-clause-id",
        "eligibility": {"eligible": True},
        "structural_roles": ["requirement"],
        "ancestor_headings": [
            {"clause_id": "opaque-parent-id", "reference": "7.4", "heading": "Design"}
        ],
        "structural_context": {
            "sibling": {
                "index": 1,
                "count": 3,
                "previous_clause_id": "opaque-prev",
                "next_clause_id": "opaque-next",
            }
        },
    }

    frame = frame_cbox_context(context, FULL_CONTEXT_V1)

    serialized = repr(frame.values)
    assert "opaque" not in serialized
    assert "eligibility" not in frame.values
    assert "structural_roles" not in frame.values


def test_versioned_cbox_frame_identifier_resolves_full_context_policy() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        FULL_CONTEXT_V1,
        cbox_frame_key,
        resolve_cbox_frame_policy,
    )

    assert cbox_frame_key(FULL_CONTEXT_V1) == "full-context-v1"
    assert resolve_cbox_frame_policy("full-context-v1") is FULL_CONTEXT_V1


def test_applicability_minimal_frame_exposes_only_identity_and_heading() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        APPLICABILITY_MINIMAL_V1,
        frame_cbox_context,
    )

    context = {
        "document_key": "EN50126-1",
        "reference": "4.2",
        "heading": "Purpose",
        "clause_type": "narrative",
        "canonical_section": "scope",
        "ancestor_headings": [{"reference": "4", "heading": "Scope"}],
        "document_categories": ["scope"],
        "semantic_sections": ["scope"],
        "context_routing": {
            "scopes": [{"conditions": ["for railway applications"]}],
            "references": [{"role": "applicability", "target": {"reference": "7.2"}}],
        },
        "reference_mentions": [{"surface_text": "7.2", "reference": "7.2"}],
    }

    frame = frame_cbox_context(context, APPLICABILITY_MINIMAL_V1)

    assert frame.values == {
        "document_key": "EN50126-1",
        "reference": "4.2",
        "heading": "Purpose",
    }


def test_applicability_isolated_frame_exposes_only_identity() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        APPLICABILITY_ISOLATED_V1,
        frame_cbox_context,
    )

    context = {
        "document_key": "EN50126-1",
        "reference": "4.2",
        "heading": "Applicability",
        "canonical_section": "scope",
        "ancestor_headings": [{"reference": "4", "heading": "Scope"}],
    }

    frame = frame_cbox_context(context, APPLICABILITY_ISOLATED_V1)

    assert frame.values == {"document_key": "EN50126-1", "reference": "4.2"}


def test_versioned_applicability_frame_identifiers_resolve() -> None:
    from standards_atlas.application.semantic_qualification.context_framing import (
        APPLICABILITY_ISOLATED_V1,
        APPLICABILITY_MINIMAL_V1,
        resolve_cbox_frame_policy,
    )

    assert resolve_cbox_frame_policy("applicability-minimal-v1") is APPLICABILITY_MINIMAL_V1
    assert resolve_cbox_frame_policy("applicability-isolated-v1") is APPLICABILITY_ISOLATED_V1
