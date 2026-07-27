"""MCP server factory for read-only Standards Atlas clause access."""

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
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Run 'uv sync --extra mcp'."
        ) from exc

    clause_service = McpClauseService(
        provider or EngineeringDocumentClauseProvider(config.workspace),
        config,
    )
    mcp = FastMCP(config.name, json_response=True)

    def tool_call(operation: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return operation(*args, **kwargs)
        except (KeyError, ValueError) as exc:
            message = exc.args[0] if exc.args else str(exc)
            raise ToolError(str(message)) from exc

    @mcp.tool()
    def list_standards() -> list[dict[str, Any]]:
        """List standards available to this server, including clause counts."""
        return clause_service.list_documents()

    @mcp.tool()
    def get_clause(clause_id: str) -> dict[str, Any]:
        """Read one exposed clause by its stable Standards Atlas clause identifier."""
        return tool_call(clause_service.get_clause, clause_id)

    @mcp.tool()
    def list_clauses(
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        semantic_roles: list[str] | None = None,
        min_text_length: int | None = None,
        max_text_length: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List exposed clauses with optional metadata and text-length filters."""
        return tool_call(
            clause_service.list_clauses,
            document_keys=document_keys,
            clause_types=clause_types,
            semantic_roles=semantic_roles,
            min_text_length=min_text_length,
            max_text_length=max_text_length,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    def search_clauses(
        query: str,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        semantic_roles: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search exposed clause titles, references, and text for all query terms."""
        return tool_call(
            clause_service.search_clauses,
            query,
            document_keys=document_keys,
            clause_types=clause_types,
            semantic_roles=semantic_roles,
            limit=limit,
        )

    @mcp.tool()
    def sample_clauses(
        count: int,
        strategy: str = "random",
        seed: int = 0,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        semantic_roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Create a reproducible random or document-balanced sample of exposed clauses."""
        return tool_call(
            clause_service.sample_clauses,
            count=count,
            strategy=strategy,
            seed=seed,
            document_keys=document_keys,
            clause_types=clause_types,
            semantic_roles=semantic_roles,
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

    return mcp


def run_mcp_server(config: McpServerConfig) -> None:
    """Run the configured MCP server in the foreground."""
    create_mcp_server(config).run(transport=config.transport)
