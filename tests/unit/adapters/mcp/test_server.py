import asyncio

import pytest

from standards_atlas.adapters.mcp import McpServerConfig, create_mcp_server
from standards_atlas.application.services.evaluation import (
    ClauseDescriptor,
    ClauseFilter,
    DocumentDescriptor,
    SamplingStrategy,
)
from standards_atlas.domain.model import ClauseType, DocumentType


@pytest.fixture(scope="module", autouse=True)
def require_mcp() -> None:
    pytest.importorskip("mcp")


class FakeProvider:
    clause = ClauseDescriptor(
        id="clause-1",
        document_key="standard-1",
        reference="1",
        clause_reference="1",
        clause_type=ClauseType.CLAUSE,
        title="Scope",
        text="The system shall be safe.",
    )

    def list_documents(self):
        return (
            DocumentDescriptor(
                key="standard-1",
                title="Standard One",
                document_type=DocumentType.STANDARD,
                clause_count=1,
            ),
        )

    def get_clause(self, clause_id):
        if clause_id != self.clause.id:
            raise KeyError(clause_id)
        return self.clause

    def list_clauses(self, *, filters=None, limit=None, offset=0):
        return (self.clause,)

    def search_clauses(self, query, *, filters=None, limit=20):
        return (self.clause,)

    def sample_clauses(
        self,
        *,
        count,
        strategy=SamplingStrategy.RANDOM,
        filters: ClauseFilter | None = None,
        seed=0,
    ):
        return (self.clause,)


def test_registers_read_only_tools_and_resources() -> None:
    server = create_mcp_server(McpServerConfig(), FakeProvider())

    tools = asyncio.run(server.list_tools())
    resources = asyncio.run(server.list_resources())
    templates = asyncio.run(server.list_resource_templates())

    assert {tool.name for tool in tools} == {
        "list_standards",
        "get_clause",
        "list_clauses",
        "search_clauses",
        "sample_clauses",
    }
    assert {str(resource.uri) for resource in resources} == {"standards-atlas://documents"}
    assert {template.uriTemplate for template in templates} == {
        "standards-atlas://clauses/{clause_id}"
    }
