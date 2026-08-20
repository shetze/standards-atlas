"""Materialize deterministic semantic routing plans from structural taxonomy evidence."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.routing import (
    ClauseRoutingRecord,
    DeterministicRoutingEngine,
    DocumentRoutingArtifact,
    RoutingContractRepository,
    SemanticRoutingArtifactRepository,
    taxonomy_signal_profile,
)
from standards_atlas.domain.model import DocumentKey
from standards_atlas.domain.model.content import (
    ContentBlock,
    NoteBlock,
    TableBlock,
    render_block_as_plain_text,
)


class SemanticRoutingResult(BaseModel):
    """Summary of one persisted deterministic routing run."""

    model_config = ConfigDict(frozen=True)

    artifact: DocumentRoutingArtifact
    clauses_routed: int
    task_decisions: int


class SemanticRoutingService:
    """Route ontology tasks using only deterministic structural evidence."""

    def __init__(
        self,
        *,
        documents: EngineeringDocumentRepository,
        contracts: RoutingContractRepository,
        artifacts: SemanticRoutingArtifactRepository,
        engine: DeterministicRoutingEngine | None = None,
    ) -> None:
        self._documents = documents
        self._contracts = contracts
        self._artifacts = artifacts
        self._engine = engine or DeterministicRoutingEngine()

    def route(
        self,
        document_key: str,
        *,
        contract_id: str,
        contract_version: str,
    ) -> SemanticRoutingResult:
        document = self._documents.load(DocumentKey(value=document_key))
        contract = self._contracts.load(contract_id, contract_version)
        records: list[ClauseRoutingRecord] = []
        decisions = 0

        for clause in document.clauses:
            if clause.structural_profile is None or clause.structural_context is None:
                raise ValueError(
                    f"Clause {clause.id.value} has no structural taxonomy context; "
                    "run classify-taxonomy first"
                )
            signals = taxonomy_signal_profile(
                clause.structural_profile,
                heading=clause.title or "",
                node_kind=clause.structural_context.node_kind.value,
                content_profile=_content_profile(clause.content),
            )
            plan = self._engine.route(signals, contract)
            decisions += len(plan.decisions)
            records.append(
                ClauseRoutingRecord(
                    clause_id=clause.id.value,
                    reference=clause.reference.clause,
                    title=clause.title,
                    signals=signals,
                    plan=plan,
                )
            )

        artifact = DocumentRoutingArtifact(
            document_key=document.key.value,
            contract_id=contract.id,
            contract_version=contract.version,
            clauses=tuple(records),
        )
        self._artifacts.save(artifact)
        return SemanticRoutingResult(
            artifact=artifact,
            clauses_routed=len(records),
            task_decisions=decisions,
        )


def _content_profile(content: tuple[ContentBlock, ...]) -> str:
    table_count, table_length, non_table_length = _content_metrics(content)
    total_length = table_length + non_table_length
    table_dominant = (
        table_count > 0
        and table_length >= 200
        and total_length > 0
        and table_length / total_length >= 0.60
    )
    return "table_dominant" if table_dominant else "text_dominant"


def _content_metrics(content: tuple[ContentBlock, ...]) -> tuple[int, int, int]:
    table_count = 0
    table_length = 0
    non_table_length = 0
    for block in content:
        rendered_length = len(render_block_as_plain_text(block).strip())
        if isinstance(block, TableBlock):
            table_count += 1
            table_length += rendered_length
        elif isinstance(block, NoteBlock):
            nested_count, nested_table_length, nested_non_table_length = _content_metrics(
                block.content
            )
            table_count += nested_count
            table_length += nested_table_length
            non_table_length += nested_non_table_length
            if block.note_kind:
                non_table_length += len(block.note_kind.strip())
        else:
            non_table_length += rendered_length
    return table_count, table_length, non_table_length
