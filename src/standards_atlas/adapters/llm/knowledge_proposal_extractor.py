"""Structured LLM adapter for source-bound assertion-centred knowledge proposals."""

from __future__ import annotations

from collections.abc import Mapping

from standards_atlas.application.context.input_binding import ContextSourcePackage
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.evaluation.source_bound_prompt import semantic_prompt_repository
from standards_atlas.application.knowledge_proposal_extraction.pipeline import (
    parse_knowledge_proposal_result,
    prepare_knowledge_proposal_request,
)
from standards_atlas.application.knowledge_proposal_extraction.source_bound_contract import (
    KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
    KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
)
from standards_atlas.application.ports.knowledge_proposals import ClauseKnowledgeProposalResult
from standards_atlas.application.ports.llm_gateway import LlmGateway
from standards_atlas.domain.model import Clause, KnowledgeProposalProvenance


class OntologyGuidedKnowledgeProposalExtractor:
    """Propose source-bound entities and assertions from one target clause."""

    def __init__(
        self,
        gateway: LlmGateway,
        *,
        model: str | None = None,
        provider: str | None = None,
        prompt_version: str = "ontology-guided-assertions-source-bound-v1",
        task_schema_version: str = "1.0.0",
        extractor_version: str = "4.0.0",
        prompt_repository: PromptRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._provider = provider
        self._prompt_version = prompt_version
        self._task_schema_version = task_schema_version
        self._extractor_version = extractor_version
        self._prompt_repository = prompt_repository or semantic_prompt_repository()

    def provenance(self) -> KnowledgeProposalProvenance:
        return KnowledgeProposalProvenance(
            extractor="ontology-guided-llm",
            extractor_version=self._extractor_version,
            model=self._model,
            provider=self._provider,
            semantic_task="formal-semantic-knowledge-proposal",
            prompt_version=self._prompt_version,
            request_contract_id=KNOWLEDGE_PROPOSAL_REQUEST_CONTRACT,
            output_contract_id=KNOWLEDGE_PROPOSAL_OUTPUT_CONTRACT,
            source_binding_contract_id="source-bound-context-binding-v1",
        )

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        source_package: ContextSourcePackage,
        interpretation_context: Mapping[str, object] | None = None,
    ) -> ClauseKnowledgeProposalResult:
        prepared = prepare_knowledge_proposal_request(
            clause,
            document_key=document_key,
            ontology_versions=ontology_versions,
            source_package=source_package,
            interpretation_context=interpretation_context,
            prompt_repository=self._prompt_repository,
            prompt_version=self._prompt_version,
            task_schema_version=self._task_schema_version,
            model=self._model,
            temperature=0.0,
        )
        result = self._gateway.generate_structured(prepared.generation_request)
        return parse_knowledge_proposal_result(
            prepared,
            result,
            extractor_version=self._extractor_version,
        )
