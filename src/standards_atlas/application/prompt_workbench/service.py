"""Headless orchestration of one prompt-workbench experiment."""

from __future__ import annotations

from standards_atlas.application.evaluation.schema import validate_schema_errors
from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    StructuredGenerationRequest,
)
from standards_atlas.application.prompt_workbench.catalogs import ModelCatalog, PromptCatalog
from standards_atlas.application.prompt_workbench.clauses import ClauseResolver
from standards_atlas.application.prompt_workbench.compiler import PromptCompiler
from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
from standards_atlas.application.prompt_workbench.models import (
    PromptExperimentRequest,
    PromptExperimentResult,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseProvider


class PromptExperimentService:
    """Resolve, compile, execute, and validate one structured prompt experiment."""

    def __init__(
        self,
        *,
        clauses: ClauseProvider,
        prompts: PromptCatalog,
        models: ModelCatalog,
        gateway: LlmGateway,
        context_assembler: ClausePromptContextAssembler | None = None,
        compiler: PromptCompiler | None = None,
    ) -> None:
        self._clauses = clauses
        self._resolver = ClauseResolver(clauses)
        self._prompts = prompts
        self._models = models
        self._gateway = gateway
        self._context_assembler = context_assembler or ClausePromptContextAssembler()
        self._compiler = compiler or PromptCompiler()

    def run(self, experiment: PromptExperimentRequest) -> PromptExperimentResult:
        clause = self._resolver.resolve(experiment.clause_identifier)
        prompt = self._prompts.load_prompt(experiment.prompt_task, experiment.prompt_version)
        model = self._models.get_model(experiment.model_id)
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
            variant_id=experiment.context_variant,
            document_title=document_title,
        )
        compiled = self._compiler.compile(
            prompt,
            context,
            system_prompt=experiment.system_prompt,
            user_template=experiment.user_template,
            output_schema=experiment.output_schema,
        )
        reasoning_enabled = experiment.reasoning_enabled
        if reasoning_enabled is None:
            reasoning_enabled = model.generation.reasoning_enabled
        reasoning_mode = "enabled" if reasoning_enabled else "disabled"
        if reasoning_mode not in model.supported_reasoning_modes:
            raise ValueError(
                f"model {model.id!r} does not support reasoning mode {reasoning_mode!r}"
            )
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
