from standards_atlas.adapters.mcp import McpClauseService, McpServerConfig
from standards_atlas.application.services.evaluation import (
    ClauseDescriptor,
    ClauseFilter,
    DocumentDescriptor,
    SamplingStrategy,
)
from standards_atlas.domain.model import ClauseType, DocumentType, SemanticRole


class FakeClauseProvider:
    def __init__(self) -> None:
        self.clauses = (
            ClauseDescriptor(
                id="clause-a",
                document_key="allowed",
                reference="1",
                clause_reference="1",
                content_hash="sha256:" + "a" * 64,
                clause_type=ClauseType.CLAUSE,
                title="Allowed clause",
                text="shall be verified",
                semantic_roles=(SemanticRole.REQUIREMENTS,),
            ),
            ClauseDescriptor(
                id="clause-b",
                document_key="hidden",
                reference="2",
                clause_reference="2",
                content_hash="sha256:" + "b" * 64,
                clause_type=ClauseType.CLAUSE,
                title="Hidden clause",
                text="hidden text",
            ),
        )

    def list_documents(self):
        return (
            DocumentDescriptor(
                key="allowed",
                title="Allowed",
                document_type=DocumentType.STANDARD,
                clause_count=1,
            ),
            DocumentDescriptor(
                key="hidden",
                title="Hidden",
                document_type=DocumentType.STANDARD,
                clause_count=1,
            ),
        )

    def get_clause(self, clause_id):
        return next(clause for clause in self.clauses if clause.id == clause_id)

    def list_clauses(self, *, filters=None, limit=None, offset=0):
        clauses = self._filtered(filters)
        return clauses[offset:] if limit is None else clauses[offset : offset + limit]

    def search_clauses(self, query, *, filters=None, limit=20):
        return tuple(
            clause
            for clause in self._filtered(filters)
            if query.casefold() in clause.text.casefold()
        )[:limit]

    def sample_clauses(
        self,
        *,
        count,
        strategy=SamplingStrategy.RANDOM,
        filters=None,
        seed=0,
    ):
        return self._filtered(filters)[:count]

    def _filtered(self, filters: ClauseFilter | None):
        filters = filters or ClauseFilter()
        return tuple(
            clause
            for clause in self.clauses
            if not filters.document_keys or clause.document_key in filters.document_keys
        )


def test_applies_document_allowlist_and_text_exposure_policy() -> None:
    service = McpClauseService(
        FakeClauseProvider(),
        McpServerConfig.model_validate(
            {
                "allowed_document_keys": ["allowed"],
                "limits": {"max_clause_characters": 5},
            }
        ),
    )

    assert [document["key"] for document in service.list_documents()] == ["allowed"]
    assert service.get_clause("clause-a")["text"] == "shall"
    assert [clause["id"] for clause in service.list_clauses()] == ["clause-a"]


def test_rejects_requests_above_configured_limits() -> None:
    service = McpClauseService(
        FakeClauseProvider(),
        McpServerConfig.model_validate({"limits": {"max_results": 2, "max_sample_size": 1}}),
    )

    try:
        service.list_clauses(limit=3)
    except ValueError as exc:
        assert "maximum of 2" in str(exc)
    else:
        raise AssertionError("expected result limit validation")

    try:
        service.sample_clauses(count=2)
    except ValueError as exc:
        assert "maximum of 1" in str(exc)
    else:
        raise AssertionError("expected sample limit validation")
