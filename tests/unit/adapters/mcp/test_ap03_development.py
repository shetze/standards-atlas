from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.development import (
    McpDevelopmentReviewService,
    McpDevelopmentScope,
)
from standards_atlas.adapters.mcp.server import create_mcp_server
from standards_atlas.adapters.mcp.service import McpClauseService
from standards_atlas.adapters.mcp.tool_policy import registered_tool_names
from standards_atlas.application.assertion_qualification.assertion_review import (
    AssertionReviewSurface,
    AssertionReviewWorkbenchCase,
    ReviewOntologyOption,
    package_from_cases,
    write_assertion_review_package,
)
from standards_atlas.application.assertion_qualification.models import AssertionGoldenPartition
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    DocumentDescriptor,
)
from standards_atlas.domain.model import ClauseType, DocumentType, EvidenceSourceKind


def _surface(clause_id: str, text: str) -> AssertionReviewSurface:
    return AssertionReviewSurface(
        source_ref=f"surface-{clause_id}",
        source_clause_id=clause_id,
        source_kind=EvidenceSourceKind.BODY,
        label=f"source {clause_id}",
        text=text,
        start_offset=0,
        content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
    )


def _case(
    clause_id: str,
    *,
    partition: AssertionGoldenPartition,
    group: str,
    surfaces: tuple[AssertionReviewSurface, ...],
) -> AssertionReviewWorkbenchCase:
    return AssertionReviewWorkbenchCase(
        case_id=f"DOC:{clause_id}",
        document_key="DOC",
        clause_id=clause_id,
        reference=f"DOC:{clause_id}",
        partition=partition,
        source_group=group,
        source_package_sha256="sha256:" + hashlib.sha256(group.encode()).hexdigest(),
        surfaces=surfaces,
    )


def _config(tmp_path: Path, *, overlap: bool = False) -> McpServerConfig:
    review_workspace = tmp_path / "reviews"
    handle = "assertions"
    dev_surface = _surface("c-dev", "Development requirement")
    context_surface = _surface("c-context", "Development context")
    hold_surface = _surface("c-hold", "Reserved holdout")
    hold_surfaces = (hold_surface, context_surface) if overlap else (hold_surface,)
    package = package_from_cases(
        id="ap03",
        version="1",
        corpus_plan_sha256="a" * 64,
        ontology_versions=("core@2.0.0",),
        class_options=(ReviewOntologyOption(iri="https://example.test/WorkProduct", label="WP"),),
        predicate_options=(
            ReviewOntologyOption(iri="https://example.test/requires", label="requires"),
        ),
        cases=(
            _case(
                "c-dev",
                partition=AssertionGoldenPartition.DEVELOPMENT,
                group="dev-group",
                surfaces=(dev_surface, context_surface),
            ),
            _case(
                "c-hold",
                partition=AssertionGoldenPartition.HOLDOUT,
                group="hold-group",
                surfaces=hold_surfaces,
            ),
        ),
    )
    write_assertion_review_package(review_workspace / handle, package)
    return McpServerConfig.model_validate(
        {
            "profile": "ap03-development",
            "workspace": str(tmp_path / "atlas"),
            "allowed_document_keys": ["DOC"],
            "review": {"enabled": True, "workspace": str(review_workspace)},
            "ap03_development": {
                "review_handles": [handle],
                "project_root": str(tmp_path),
                "allowed_data_routes": ["synthetic-local"],
            },
        }
    )


class _Provider:
    def __init__(self) -> None:
        self.clauses = {
            "c-dev": _descriptor("c-dev", "Development requirement", heading="Development"),
            "c-context": _descriptor("c-context", "Development context", heading="Context"),
            "c-hold": _descriptor("c-hold", "Reserved holdout", heading="Holdout"),
        }
        self.batch_reads = 0

    def list_documents(self):
        raise AssertionError("Development profile must not enumerate hidden documents")

    def get_documents(self, document_keys):
        assert document_keys == ("DOC",)
        return (
            DocumentDescriptor(
                key="DOC",
                title="Synthetic Standard",
                document_type=DocumentType.STANDARD,
                clause_count=3,
            ),
        )

    def get_clause(self, clause_id):
        raise AssertionError("Development profile must use the exact batch lookup")

    def get_clauses(self, clause_ids, *, document_keys=()):
        self.batch_reads += 1
        assert document_keys == ("DOC",)
        return tuple(self.clauses[clause_id] for clause_id in clause_ids)

    def list_clauses(self, **kwargs):
        raise AssertionError(
            "Development profile must not enumerate the hidden provider population"
        )

    def search_clauses(self, *args, **kwargs):
        raise AssertionError("Development profile must not search the hidden provider population")

    def sample_clauses(self, **kwargs):
        raise AssertionError("Development profile must not sample the hidden provider population")


def _descriptor(clause_id: str, text: str, *, heading: str) -> ClauseDescriptor:
    return ClauseDescriptor(
        id=clause_id,
        document_key="DOC",
        reference=f"DOC:{clause_id}",
        clause_reference=clause_id,
        content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        clause_type=ClauseType.CLAUSE,
        heading=heading,
        text=text,
        ancestor_headings=(
            {"clause_id": "c-hold", "reference": "H", "heading": "Reserved ancestor"},
        ),
        reference_mentions=({"surface_text": "Reserved holdout", "target_clause_id": "c-hold"},),
        context_routing={"references": [{"clause_id": "c-hold"}]},
    )


def test_development_scope_rejects_source_overlap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="share source clauses"):
        McpDevelopmentScope(_config(tmp_path, overlap=True))


def test_direct_list_search_and_context_are_server_scoped(tmp_path: Path) -> None:
    config = _config(tmp_path)
    provider = _Provider()
    service = McpClauseService(provider, config)

    assert [item["id"] for item in service.list_clauses(limit=10)] == ["c-context", "c-dev"]
    assert [item["id"] for item in service.search_clauses("Development", limit=10)] == [
        "c-dev",
        "c-context",
    ]
    with pytest.raises(KeyError, match="not exposed"):
        service.get_clause("c-hold")
    exposed = service.get_clause("c-dev")
    assert exposed["ancestor_headings"] == []
    assert "Reserved" not in str(exposed)
    assert "reference_mentions" not in exposed
    assert "context_routing" not in exposed
    assert service.list_documents()[0]["clause_count"] == 2
    assert provider.batch_reads == 1


def test_media_paths_are_not_an_indirect_development_bypass(tmp_path: Path) -> None:
    service = McpClauseService(_Provider(), _config(tmp_path))
    for operation in (
        lambda: service.list_knowledge_tables(),
        lambda: service.get_knowledge_table("anything"),
        lambda: service.list_untranscribed_formulas(),
        lambda: service.get_formula("anything"),
    ):
        with pytest.raises(ValueError, match="not exposed"):
            operation()


def test_assertion_review_projection_has_no_holdout_parameter_or_case(tmp_path: Path) -> None:
    scope = McpDevelopmentScope(_config(tmp_path))
    service = McpDevelopmentReviewService(scope)

    page = service.list_cases("assertions")
    assert page["total"] == 1
    assert page["cases"][0]["case_id"] == "DOC:c-dev"
    assert "holdout" not in str(page).casefold()
    with pytest.raises(ValueError, match="outside"):
        service.get_case("assertions", "DOC:c-hold")
    package = service.get_package("assertions")
    assert package["capabilities"]["human_confirmation"] is False
    assert package["capabilities"]["holdout_read"] is False


def test_server_registers_only_development_tools_and_no_resources(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    config = _config(tmp_path)
    server = create_mcp_server(config, _Provider())

    tools = asyncio.run(server.list_tools())
    resources = asyncio.run(server.list_resources())
    templates = asyncio.run(server.list_resource_templates())

    assert tuple(sorted(tool.name for tool in tools)) == tuple(
        sorted(registered_tool_names(config))
    )
    assert not resources
    assert not templates
    names = {tool.name for tool in tools}
    assert "get_formula" not in names
    assert "submit_review_annotations" not in names
    assert not any("confirm" in name or "publish" in name for name in names)
