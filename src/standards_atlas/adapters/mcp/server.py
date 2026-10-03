"""Inbound MCP adapter for read-only and explicitly bounded preparation workflows."""

from __future__ import annotations

import json
from typing import Any

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.service import McpClauseService
from standards_atlas.application.services.evaluation import ClauseProvider


def create_mcp_server(config: McpServerConfig, provider: ClauseProvider | None = None) -> Any:
    """Create the optional FastMCP server without importing MCP at package import time."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as exc:
        raise RuntimeError("MCP support is not installed. Run 'uv sync --extra mcp'.") from exc

    development_scope = None
    if config.is_ap03_development:
        from standards_atlas.adapters.mcp.development import McpDevelopmentScope

        development_scope = McpDevelopmentScope(config)

    clause_service = McpClauseService(
        provider or EngineeringDocumentClauseProvider(config.workspace),
        config,
        development_scope=development_scope,
    )
    mcp = FastMCP(
        config.name,
        json_response=True,
        stateless_http=config.http.stateless,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(config.http.allowed_hosts),
            allowed_origins=list(config.http.allowed_origins),
        ),
    )
    read = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

    def tool_call(operation: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return operation(*args, **kwargs)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            message = exc.args[0] if exc.args else str(exc)
            raise ToolError(str(message)) from exc

    @mcp.tool(annotations=read)
    def get_server_info() -> dict[str, Any]:
        """Read loaded runtime/schema policy and the active server-side exposure profile."""
        return clause_service.get_server_info()

    @mcp.tool(annotations=read)
    def list_standards() -> list[dict[str, Any]]:
        """List standards visible through this server-side scope."""
        return tool_call(clause_service.list_documents)

    @mcp.tool(annotations=read)
    def get_clause(clause_id: str) -> dict[str, Any]:
        """Read one exposed clause by its stable Standards Atlas clause identifier."""
        return tool_call(clause_service.get_clause, clause_id)

    @mcp.tool(annotations=read)
    def list_clauses(
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        min_text_length: int | None = None,
        max_text_length: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List clauses after the active server-side source policy has been applied."""
        return tool_call(
            clause_service.list_clauses,
            document_keys=document_keys,
            clause_types=clause_types,
            min_text_length=min_text_length,
            max_text_length=max_text_length,
            limit=limit,
            offset=offset,
        )

    @mcp.tool(annotations=read)
    def search_clauses(
        query: str,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search only source text visible through the active server-side scope."""
        return tool_call(
            clause_service.search_clauses,
            query,
            document_keys=document_keys,
            clause_types=clause_types,
            limit=limit,
        )

    @mcp.tool(annotations=read)
    def sample_clauses(
        count: int,
        strategy: str = "random",
        seed: int = 0,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Sample only the source population visible through the active server-side scope."""
        return tool_call(
            clause_service.sample_clauses,
            count=count,
            strategy=strategy,
            seed=seed,
            document_keys=document_keys,
            clause_types=clause_types,
        )

    if config.is_ap03_development:
        assert development_scope is not None
        from standards_atlas.adapters.mcp.development import (
            McpCodexOptimizationService,
            McpDevelopmentExperimentService,
            McpDevelopmentReviewService,
        )

        review_service = McpDevelopmentReviewService(development_scope)
        experiment_service = McpDevelopmentExperimentService(development_scope)
        optimization_service = McpCodexOptimizationService(development_scope)

        @mcp.tool(annotations=read)
        def list_review_packages(limit: int = 20, offset: int = 0) -> dict[str, Any]:
            """List registered S08 assertion packages projected to Development only."""
            return tool_call(review_service.list_packages, limit=limit, offset=offset)

        @mcp.tool(annotations=read)
        def get_review_package(handle: str) -> dict[str, Any]:
            """Read one Development-only assertion review contract; no human write authority."""
            return tool_call(review_service.get_package, handle)

        @mcp.tool(annotations=read)
        def list_review_cases(handle: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
            """Page Development assertion cases; Holdout is not an accepted parameter or result."""
            return tool_call(review_service.list_cases, handle, limit=limit, offset=offset)

        @mcp.tool(annotations=read)
        def get_review_case(handle: str, case_id: str) -> dict[str, Any]:
            """Read exact bound Development source surfaces and separate proposal state."""
            return tool_call(review_service.get_case, handle, case_id)

        @mcp.tool(annotations=read)
        def list_development_experiments(limit: int = 20, offset: int = 0) -> dict[str, Any]:
            """List explicitly registered Development experiment identities."""
            return tool_call(experiment_service.list_experiments, limit=limit, offset=offset)

        @mcp.tool(annotations=read)
        def get_development_experiment_manifest(experiment_id: str) -> dict[str, Any]:
            """Read one approved Development manifest without arbitrary filesystem paths."""
            return tool_call(experiment_service.get_manifest, experiment_id)

        @mcp.tool(annotations=read)
        def get_development_experiment_state(experiment_id: str) -> dict[str, Any]:
            """Read sanitized attempt status; private raw paths/messages are never exposed."""
            return tool_call(experiment_service.get_state, experiment_id)

        @mcp.tool(annotations=read)
        def get_development_experiment_comparison(experiment_id: str) -> dict[str, Any]:
            """Read fixed-path comparison after Development manifest/scope validation."""
            return tool_call(experiment_service.get_comparison, experiment_id)

        write_proposal = {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }

        @mcp.tool(annotations=write_proposal)
        def submit_prompt_variant_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
            """Validate/stage one prompt proposal; never run a model or alter Golden."""
            return tool_call(optimization_service.submit_prompt_variant_proposal, proposal)

        # No MCP resources or media/table/formula tools are registered in this profile.  A resource
        # URI or client allowlist therefore cannot bypass the same clause/review/experiment scope.
        return mcp

    @mcp.tool()
    def list_knowledge_tables(
        document_keys: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List addressable tables projected from structured clause content."""
        return tool_call(
            clause_service.list_knowledge_tables,
            document_keys=document_keys,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    def get_knowledge_table(table_id: str) -> dict[str, Any]:
        """Read one table artifact, including its lossless row records."""
        return tool_call(clause_service.get_knowledge_table, table_id)

    @mcp.tool()
    def list_knowledge_records(
        table_id: str, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List addressable row records for one knowledge table."""
        return tool_call(
            clause_service.list_knowledge_records,
            table_id,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    def get_knowledge_record(record_id: str) -> dict[str, Any]:
        """Read one lossless table-row record by its stable identifier."""
        return tool_call(clause_service.get_knowledge_record, record_id)

    @mcp.tool()
    def list_untranscribed_formulas(
        document_keys: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List visual-only formulas that do not yet have a transcription artifact."""
        return tool_call(
            clause_service.list_untranscribed_formulas,
            document_keys=document_keys,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    def get_formula(formula_id: str) -> dict[str, Any]:
        """Read one formula image, source evidence and adjacent text context."""
        return tool_call(clause_service.get_formula, formula_id)

    @mcp.tool()
    def submit_formula_transcription(
        formula_id: str,
        latex: str,
        actor: str,
        provider: str | None = None,
        model: str | None = None,
        confidence: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Persist a LaTeX transcription and deterministically apply it to its formula block."""
        return tool_call(
            clause_service.submit_formula_transcription,
            formula_id,
            latex=latex,
            actor=actor,
            provider=provider,
            model=model,
            confidence=confidence,
            notes=notes,
        )

    @mcp.resource("standards-atlas://documents")
    def documents_resource() -> str:
        """Return the exposed document catalog as JSON."""
        return json.dumps(clause_service.list_documents(), ensure_ascii=False, indent=2)

    @mcp.resource("standards-atlas://clauses/{clause_id}")
    def clause_resource(clause_id: str) -> str:
        """Return one exposed clause as JSON."""
        try:
            payload = clause_service.get_clause(clause_id)
        except (KeyError, ValueError) as exc:
            message = exc.args[0] if exc.args else str(exc)
            raise ValueError(str(message)) from exc
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource("standards-atlas://knowledge-tables/{table_id}")
    def knowledge_table_resource(table_id: str) -> str:
        """Return one addressable table artifact as JSON."""
        try:
            payload = clause_service.get_knowledge_table(table_id)
        except (KeyError, ValueError) as exc:
            message = exc.args[0] if exc.args else str(exc)
            raise ValueError(str(message)) from exc
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if config.review.enabled:
        from standards_atlas.adapters.mcp.review_tools import register_review_tools

        register_review_tools(mcp, config, tool_call)

    return mcp


def run_mcp_server(config: McpServerConfig) -> None:
    """Run the configured MCP server in the foreground."""
    server = create_mcp_server(config)
    if config.transport == "streamable-http":
        from standards_atlas.adapters.mcp.http import run_http_server

        run_http_server(server, config)
        return
    server.run(transport="stdio")
