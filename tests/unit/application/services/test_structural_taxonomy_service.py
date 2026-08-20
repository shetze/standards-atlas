from pathlib import Path

from standards_atlas.application.services.structural_taxonomy_service import (
    StructuralTaxonomyService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ReferenceMention,
    ReferenceMentionKind,
    ReferenceResolutionStatus,
    ReferenceTarget,
    StandardReference,
    TextBlock,
)


class _Repo:
    def __init__(self, document):
        self.document = document

    def load(self, key):
        return self.document

    def save(self, document):
        self.document = document
        return Path("document.json")


def _clause(identifier, reference, title, parent=None, text=""):
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="TEST", clause=reference),
        clause_type=ClauseType.CLAUSE,
        title=title,
        parent_id=ClauseId(value=parent) if parent else None,
        content=(TextBlock(id=f"{identifier}-text", text=text),) if text else (),
    )


def test_materializes_hierarchy_siblings_and_context_content():
    root = _clause("c7", "7", "Verification", text="This section introduces verification.")
    first = _clause("c71", "7.1", "Planning", parent="c7")
    second = _clause("c72", "7.2", "Execution", parent="c7")
    doc = EngineeringDocument(
        key=DocumentKey(value="test"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(root, first, second),
    )
    result = StructuralTaxonomyService(_Repo(doc)).classify("test").document
    root_ctx = result.clauses[0].structural_context
    first_ctx = result.clauses[1].structural_context
    second_ctx = result.clauses[2].structural_context

    assert root_ctx.node_kind.value == "node"
    assert root_ctx.child_clause_ids == ("c71", "c72")
    assert first_ctx.node_kind.value == "leaf"
    assert first_ctx.ancestors[0].clause_id == "c7"
    assert first_ctx.contextual_content_clause_ids == ("c7",)
    assert first_ctx.sibling.is_first is True
    assert first_ctx.sibling.next_clause_id == "c72"
    assert second_ctx.sibling.is_last is True
    assert second_ctx.sibling.previous_clause_id == "c71"


def test_materializes_reference_mentions_as_structural_edges():
    target = _clause("c7", "7", "Target")
    source = _clause("c8", "8", "Source").model_copy(
        update={
            "reference_mentions": (
                ReferenceMention(
                    kind=ReferenceMentionKind.CLAUSE,
                    surface_text="Clause 7",
                    start_offset=0,
                    end_offset=8,
                    reference="7",
                    status=ReferenceResolutionStatus.RESOLVED,
                    targets=(ReferenceTarget(clause_id="c7", reference="7"),),
                ),
            )
        }
    )
    doc = EngineeringDocument(
        key=DocumentKey(value="test"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(target, source),
    )
    result = StructuralTaxonomyService(_Repo(doc)).classify("test").document
    edge = result.clauses[1].structural_context.references[0]
    assert edge.target_clause_id == "c7"
    assert edge.target_reference == "7"
    assert edge.status == "resolved"


def test_materializes_scope_reach_for_following_siblings():
    source = _clause(
        "c70", "7.0", "Applicability", text="The scope of the following two clauses is limited."
    )
    first = _clause("c71", "7.1", "First")
    second = _clause("c72", "7.2", "Second")
    third = _clause("c73", "7.3", "Third")
    doc = EngineeringDocument(
        key=DocumentKey(value="test"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(source, first, second, third),
    )
    result = StructuralTaxonomyService(_Repo(doc)).classify("test").document
    ctx = result.clauses[0].structural_context
    assert ctx.scope_mentions[0].direction_hint == "forward"
    assert ctx.scope_mentions[0].cardinality == 2
    assert [edge.target_clause_id for edge in ctx.scopes] == ["c71", "c72"]


def test_materializes_scope_heading_as_subtree_edges():
    root = _clause("c7", "7", "Scope of verification")
    child = _clause("c71", "7.1", "Planning", parent="c7")
    grandchild = _clause("c711", "7.1.1", "Details", parent="c71")
    doc = EngineeringDocument(
        key=DocumentKey(value="test"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(root, child, grandchild),
    )
    result = StructuralTaxonomyService(_Repo(doc)).classify("test").document
    ctx = result.clauses[0].structural_context
    assert ctx.scope_mentions[0].direction_hint == "subtree"
    assert [edge.target_clause_id for edge in ctx.scopes] == ["c71", "c711"]
