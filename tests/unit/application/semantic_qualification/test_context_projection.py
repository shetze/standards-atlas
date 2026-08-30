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
