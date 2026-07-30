"""Transport-neutral request handling for the MCP clause adapter."""

from __future__ import annotations

from typing import Any

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseFilter,
    SamplingStrategy,
)
from standards_atlas.application.services.evaluation import ClauseProvider


class McpClauseService:
    """Apply exposure policy and request limits around a ClauseProvider."""

    def __init__(self, provider: ClauseProvider, config: McpServerConfig) -> None:
        self._provider = provider
        self._config = config

    def list_documents(self) -> list[dict[str, Any]]:
        documents = self._provider.list_documents()
        if self._config.allowed_document_keys:
            allowed = set(self._config.allowed_document_keys)
            documents = tuple(item for item in documents if item.key in allowed)
        return [item.model_dump(mode="json") for item in documents]

    def get_clause(self, clause_id: str) -> dict[str, Any]:
        clause = self._provider.get_clause(clause_id)
        self._ensure_document_allowed(clause.document_key)
        return self._serialize_clause(clause.model_dump(mode="json"))

    def list_clauses(
        self,
        *,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        statement_functions: list[str] | None = None,
        min_text_length: int | None = None,
        max_text_length: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        bounded_limit = self._bounded_result_limit(limit)
        filters = self._filters(
            document_keys=document_keys,
            clause_types=clause_types,
            statement_functions=statement_functions,
            min_text_length=min_text_length,
            max_text_length=max_text_length,
        )
        clauses = self._provider.list_clauses(
            filters=filters,
            limit=bounded_limit,
            offset=offset,
        )
        return [self._serialize_clause(item.model_dump(mode="json")) for item in clauses]

    def search_clauses(
        self,
        query: str,
        *,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        statement_functions: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        bounded_limit = self._bounded_result_limit(limit)
        clauses = self._provider.search_clauses(
            query,
            filters=self._filters(
                document_keys=document_keys,
                clause_types=clause_types,
                statement_functions=statement_functions,
            ),
            limit=bounded_limit,
        )
        return [self._serialize_clause(item.model_dump(mode="json")) for item in clauses]

    def sample_clauses(
        self,
        *,
        count: int,
        strategy: str = SamplingStrategy.RANDOM.value,
        seed: int = 0,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        statement_functions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if count > self._config.limits.max_sample_size:
            raise ValueError(
                f"count exceeds configured maximum of {self._config.limits.max_sample_size}"
            )
        clauses = self._provider.sample_clauses(
            count=count,
            strategy=SamplingStrategy(strategy),
            seed=seed,
            filters=self._filters(
                document_keys=document_keys,
                clause_types=clause_types,
                statement_functions=statement_functions,
            ),
        )
        return [self._serialize_clause(item.model_dump(mode="json")) for item in clauses]

    def _filters(
        self,
        *,
        document_keys: list[str] | None = None,
        clause_types: list[str] | None = None,
        statement_functions: list[str] | None = None,
        min_text_length: int | None = None,
        max_text_length: int | None = None,
    ) -> ClauseFilter:
        keys = tuple(document_keys or ())
        if self._config.allowed_document_keys:
            allowed = set(self._config.allowed_document_keys)
            if keys:
                keys = tuple(key for key in keys if key in allowed)
                if not keys:
                    raise ValueError("requested documents are not exposed by this server")
            else:
                keys = self._config.allowed_document_keys
        return ClauseFilter.model_validate(
            {
                "document_keys": keys,
                "clause_types": tuple(clause_types or ()),
                "statement_functions": tuple(statement_functions or ()),
                "min_text_length": min_text_length,
                "max_text_length": max_text_length,
            }
        )

    def _bounded_result_limit(self, limit: int) -> int:
        if limit < 1:
            raise ValueError("limit must be positive")
        if limit > self._config.limits.max_results:
            raise ValueError(
                f"limit exceeds configured maximum of {self._config.limits.max_results}"
            )
        return limit

    def _ensure_document_allowed(self, document_key: str) -> None:
        allowed = self._config.allowed_document_keys
        if allowed and document_key not in allowed:
            raise KeyError("clause is not exposed by this server")

    def _serialize_clause(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._config.expose.clause_text:
            payload["text"] = ""
        else:
            payload["text"] = payload["text"][: self._config.limits.max_clause_characters]
        return payload
