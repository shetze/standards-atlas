"""Transport-neutral request handling for the MCP clause adapter."""

from __future__ import annotations

from typing import Any

from standards_atlas.adapters.filesystem import FileSystemKnowledgeTableRepository
from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseFilter,
    SamplingStrategy,
)
from standards_atlas.application.services.evaluation import ClauseProvider


class McpClauseService:
    """Apply exposure policy and request limits around a ClauseProvider."""

    def __init__(
        self,
        provider: ClauseProvider,
        config: McpServerConfig,
        knowledge_tables: FileSystemKnowledgeTableRepository | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._knowledge_tables = knowledge_tables or FileSystemKnowledgeTableRepository(
            config.workspace
        )

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

    def list_knowledge_tables(
        self,
        *,
        document_keys: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        bounded_limit = self._bounded_result_limit(limit)
        keys = self._allowed_document_keys(document_keys)
        tables = self._knowledge_tables.list_tables(keys)
        return [
            self._serialize_knowledge_table(item.model_dump(mode="json"), include_records=False)
            for item in tables[offset : offset + bounded_limit]
        ]

    def get_knowledge_table(self, table_id: str) -> dict[str, Any]:
        table = self._knowledge_tables.get_table(table_id)
        self._ensure_document_allowed(table.document_key)
        return self._serialize_knowledge_table(table.model_dump(mode="json"))

    def list_knowledge_records(
        self,
        table_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        bounded_limit = self._bounded_result_limit(limit)
        table = self._knowledge_tables.get_table(table_id)
        self._ensure_document_allowed(table.document_key)
        records = self._knowledge_tables.list_records(table_id, offset=offset, limit=bounded_limit)
        return [self._redact_source_evidence(item.model_dump(mode="json")) for item in records]

    def get_knowledge_record(self, record_id: str) -> dict[str, Any]:
        record = self._knowledge_tables.get_record(record_id)
        self._ensure_document_allowed(record.document_key)
        return self._redact_source_evidence(record.model_dump(mode="json"))

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

    def _allowed_document_keys(self, document_keys: list[str] | None) -> tuple[str, ...]:
        keys = tuple(document_keys or ())
        if not self._config.allowed_document_keys:
            return keys
        allowed = set(self._config.allowed_document_keys)
        if not keys:
            return self._config.allowed_document_keys
        filtered = tuple(key for key in keys if key in allowed)
        if not filtered:
            raise ValueError("requested documents are not exposed by this server")
        return filtered

    def _serialize_knowledge_table(
        self, payload: dict[str, Any], *, include_records: bool = True
    ) -> dict[str, Any]:
        if not include_records:
            payload.pop("records", None)
        return self._redact_source_evidence(payload)

    def _redact_source_evidence(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._redact_source_evidence(item) for item in value]
        if not isinstance(value, dict):
            return value
        redacted = {key: self._redact_source_evidence(item) for key, item in value.items()}
        if not self._config.expose.source_paths and "source_type" in redacted:
            redacted["locator"] = None
        return redacted

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
