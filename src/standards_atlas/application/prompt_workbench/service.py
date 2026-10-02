"""Headless orchestration of prompt-workbench experiments."""

from __future__ import annotations

from dataclasses import replace

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.evaluation.schema import validate_schema_errors
from standards_atlas.application.evaluation.source_bound_prompt import semantic_prompt_repository
from standards_atlas.application.knowledge_proposal_extraction.context import (
    assertion_context_source_package,
    assertion_interpretation_context,
)
from standards_atlas.application.knowledge_proposal_extraction.pipeline import (
    parse_knowledge_proposal_result,
    prepare_knowledge_proposal_request,
)
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    StructuredGenerationRequest,
)
from standards_atlas.application.prompt_workbench.catalogs import ModelCatalog, PromptCatalog
from standards_atlas.application.prompt_workbench.clauses import ClauseResolver
from standards_atlas.application.prompt_workbench.compiler import PromptCompiler
from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
from standards_atlas.application.prompt_workbench.models import (
    AssembledPromptContext,
    PromptExperimentRequest,
    PromptExperimentResult,
    SourceBoundKnowledgeExperimentRequest,
    SourceBoundKnowledgeExperimentResult,
    SourceBoundKnowledgePreviewResult,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    ClauseProvider,
)
from standards_atlas.domain.model import Clause, DocumentKey, EngineeringDocument

_SOURCE_BOUND_KNOWLEDGE_TASK = "formal-semantic-knowledge-proposal"
_SOURCE_BOUND_EXTRACTOR_VERSION = "4.0.0"


class PromptExperimentService:
    """Resolve, preview and execute prompt experiments.

    Generic historical Workbench experiments remain available.  The AP03 source-bound knowledge
    path is deliberately separate at the service surface but reuses the productive request/parser
    pipeline internally; it cannot accept browser-owned system prompts, schemas or context frames.
    """

    def __init__(
        self,
        *,
        clauses: ClauseProvider,
        prompts: PromptCatalog,
        models: ModelCatalog,
        gateway: LlmGateway,
        documents: EngineeringDocumentRepository | None = None,
        source_bound_prompt_repository: PromptRepository | None = None,
        context_assembler: ClausePromptContextAssembler | None = None,
        compiler: PromptCompiler | None = None,
    ) -> None:
        self._clauses = clauses
        self._resolver = ClauseResolver(clauses)
        self._prompts = prompts
        self._models = models
        self._gateway = gateway
        self._documents = documents
        self._source_bound_prompt_repository = (
            source_bound_prompt_repository or semantic_prompt_repository()
        )
        self._context_assembler = context_assembler or ClausePromptContextAssembler()
        self._compiler = compiler or PromptCompiler()

    def run(self, experiment: PromptExperimentRequest) -> PromptExperimentResult:
        """Run the generic Workbench flow only for non-source-bound tasks."""
        if experiment.prompt_task == _SOURCE_BOUND_KNOWLEDGE_TASK:
            raise ValueError(
                "formal-semantic-knowledge-proposal must use the source-bound "
                "Workbench preview/run path"
            )
        clause, context = self.assemble_context(
            experiment.clause_identifier,
            experiment.context_variant,
        )
        prompt = self._prompts.load_prompt(experiment.prompt_task, experiment.prompt_version)
        model = self._models.get_model(experiment.model_id)
        compiled = self._compiler.compile(
            prompt,
            context,
            system_prompt=experiment.system_prompt,
            user_template=experiment.user_template,
            output_schema=experiment.output_schema,
        )
        reasoning_enabled = self._resolve_reasoning_mode(model, experiment.reasoning_enabled)
        max_tokens = experiment.max_tokens or model.generation.max_output_tokens
        generation_request = StructuredGenerationRequest(
            task=prompt.task,
            system_prompt=compiled.system_prompt,
            user_prompt=compiled.user_prompt,
            output_schema=compiled.output_schema,
            prompt_version=prompt.version,
            model=model.model_ref,
            temperature=experiment.temperature,
            seed=experiment.seed,
            max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled,
            metadata={
                "prompt_workbench": True,
                "use_cache": experiment.use_cache,
                "model_id": model.id,
                "clause": {
                    "document_key": clause.document_key,
                    "clause_id": clause.id,
                    "reference": clause.clause_reference,
                    "content_hash": clause.content_hash,
                },
                "context_variant": context.variant.id,
                "selected_context": dict(context.selected_context),
                "prompt_placeholders": compiled.placeholders,
            },
        )
        generation_result = self._gateway.generate_structured(generation_request)
        schema_errors = validate_schema_errors(generation_result.value, compiled.output_schema)
        return PromptExperimentResult(
            clause=clause,
            model=model,
            compiled_prompt=compiled,
            generation_request=generation_request,
            generation_result=generation_result,
            schema_valid=not schema_errors,
            schema_errors=schema_errors,
        )

    def preview_source_bound_knowledge(
        self,
        experiment: SourceBoundKnowledgeExperimentRequest,
    ) -> SourceBoundKnowledgePreviewResult:
        """Compile the productive AP02/AP03 request without starting or calling a model."""

        document, clause, descriptor = self._resolve_domain_clause(experiment.clause_identifier)
        definition = self._source_bound_prompt_repository.load(
            _SOURCE_BOUND_KNOWLEDGE_TASK,
            experiment.prompt_version,
        )
        if definition.task_schema_version is None:
            raise ValueError(
                f"source-bound prompt {_SOURCE_BOUND_KNOWLEDGE_TASK}@{experiment.prompt_version} "
                "does not declare a task schema version"
            )
        model = (
            self._models.get_model(experiment.model_id) if experiment.model_id is not None else None
        )
        reasoning_enabled = (
            self._resolve_reasoning_mode(model, experiment.reasoning_enabled)
            if model is not None
            else experiment.reasoning_enabled
        )
        max_tokens = experiment.max_tokens
        if max_tokens is None and model is not None:
            max_tokens = model.generation.max_output_tokens
        source_package = assertion_context_source_package(document, clause)
        interpretation_context = assertion_interpretation_context(document, clause)
        prepared = prepare_knowledge_proposal_request(
            clause,
            document_key=document.key.value,
            ontology_versions=experiment.ontology_versions,
            source_package=source_package,
            interpretation_context=interpretation_context,
            prompt_repository=self._source_bound_prompt_repository,
            prompt_version=experiment.prompt_version,
            task_schema_version=definition.task_schema_version,
            model=model.model_ref if model is not None else None,
            temperature=experiment.temperature,
            seed=experiment.seed,
            max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled,
            metadata={
                "prompt_workbench": True,
                "prompt_workbench_mode": "source_bound_knowledge",
                "preview_only": True,
                "use_cache": experiment.use_cache,
                "model_id": model.id if model is not None else None,
                "clause": {
                    "document_key": descriptor.document_key,
                    "clause_id": descriptor.id,
                    "reference": descriptor.clause_reference,
                    "content_hash": descriptor.content_hash,
                },
            },
        )
        return SourceBoundKnowledgePreviewResult(
            clause=descriptor,
            model=model,
            source_package=source_package,
            interpretation_context=interpretation_context,
            generation_request=prepared.generation_request,
        )

    def run_source_bound_knowledge(
        self,
        experiment: SourceBoundKnowledgeExperimentRequest,
    ) -> SourceBoundKnowledgeExperimentResult:
        """Explicitly run the source-bound request and apply productive parsing/grounding."""

        if experiment.model_id is None:
            raise ValueError("source-bound Workbench run requires model_id")
        preview = self.preview_source_bound_knowledge(experiment)
        request = replace(
            preview.generation_request,
            metadata={
                **dict(preview.generation_request.metadata),
                "preview_only": False,
            },
        )
        generation_result = self._gateway.generate_structured(request)
        schema_errors = validate_schema_errors(generation_result.value, request.output_schema)
        proposal_result = None
        parser_error = None
        if not schema_errors:
            document, clause, _ = self._resolve_domain_clause(experiment.clause_identifier)
            source_package = preview.source_package
            prepared = prepare_knowledge_proposal_request(
                clause,
                document_key=document.key.value,
                ontology_versions=experiment.ontology_versions,
                source_package=source_package,
                interpretation_context=preview.interpretation_context,
                prompt_repository=self._source_bound_prompt_repository,
                prompt_version=experiment.prompt_version,
                task_schema_version=self._source_bound_prompt_repository.load(
                    _SOURCE_BOUND_KNOWLEDGE_TASK, experiment.prompt_version
                ).task_schema_version
                or "",
                model=preview.model.model_ref if preview.model is not None else None,
                temperature=experiment.temperature,
                seed=request.seed,
                max_tokens=request.max_tokens,
                reasoning_enabled=request.reasoning_enabled,
                metadata={
                    "prompt_workbench": True,
                    "prompt_workbench_mode": "source_bound_knowledge",
                    "preview_only": False,
                    "use_cache": experiment.use_cache,
                    "model_id": experiment.model_id,
                    "clause": dict(request.metadata["clause"]),
                },
            )
            # The exact generated request must be the one we executed; rebuilding here is a guard
            # against hidden preview/run drift rather than a separate request implementation.
            if prepared.generation_request != request:
                raise ValueError("source-bound Workbench preview/run request drift detected")
            try:
                proposal_result = parse_knowledge_proposal_result(
                    prepared,
                    generation_result,
                    extractor_version=_SOURCE_BOUND_EXTRACTOR_VERSION,
                )
            except ValueError as error:
                parser_error = str(error)
        return SourceBoundKnowledgeExperimentResult(
            preview=SourceBoundKnowledgePreviewResult(
                clause=preview.clause,
                model=preview.model,
                source_package=preview.source_package,
                interpretation_context=preview.interpretation_context,
                generation_request=request,
            ),
            generation_result=generation_result,
            schema_valid=not schema_errors,
            schema_errors=schema_errors,
            proposal_result=proposal_result,
            parser_error=parser_error,
        )

    def resolve_clause(self, identifier: str) -> ClauseDescriptor:
        """Resolve a clause for interactive inspection without running inference."""
        return self._resolver.resolve(identifier)

    def assemble_context(
        self,
        clause_identifier: str,
        variant_id: str,
    ) -> tuple[ClauseDescriptor, AssembledPromptContext]:
        """Resolve a clause and expose the exact generic context used for compilation."""
        clause = self._resolver.resolve(clause_identifier)
        document_title = next(
            (
                item.title
                for item in self._clauses.list_documents()
                if item.key == clause.document_key
            ),
            None,
        )
        context = self._context_assembler.assemble(
            clause,
            variant_id=variant_id,
            document_title=document_title,
        )
        return clause, context

    def _resolve_domain_clause(
        self, identifier: str
    ) -> tuple[EngineeringDocument, Clause, ClauseDescriptor]:
        if self._documents is None:
            raise ValueError(
                "source-bound Prompt Workbench requires an EngineeringDocument repository"
            )
        descriptor = self._resolver.resolve(identifier)
        document = self._documents.load(DocumentKey(value=descriptor.document_key))
        clause = next((item for item in document.clauses if item.id.value == descriptor.id), None)
        if clause is None:
            raise ValueError(
                f"resolved clause {descriptor.id!r} is not present in document "
                f"{descriptor.document_key!r}"
            )
        return document, clause, descriptor

    @staticmethod
    def _resolve_reasoning_mode(model, requested: bool | None) -> bool:
        reasoning_enabled = requested
        if reasoning_enabled is None:
            reasoning_enabled = model.generation.reasoning_enabled
        reasoning_mode = "enabled" if reasoning_enabled else "disabled"
        if reasoning_mode not in model.supported_reasoning_modes:
            raise ValueError(
                f"model {model.id!r} does not support reasoning mode {reasoning_mode!r}"
            )
        return reasoning_enabled
