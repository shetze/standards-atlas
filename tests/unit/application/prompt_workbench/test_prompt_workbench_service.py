from __future__ import annotations

import pytest

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationResult,
)
from standards_atlas.application.prompt_workbench.models import (
    ModelCatalogEntry,
    ModelGenerationDefaults,
    PromptExperimentRequest,
)
from standards_atlas.application.prompt_workbench.service import PromptExperimentService
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    DocumentDescriptor,
)
from standards_atlas.domain.model import ClauseType, DocumentType


class Clauses:
    clause = ClauseDescriptor(
        id="clause-a",
        document_key="TEST",
        reference="TEST:2026 1",
        clause_reference="1",
        content_hash="sha256:" + "d" * 64,
        clause_type=ClauseType.CLAUSE,
        text="The supplier shall verify the result.",
    )

    def get_clause(self, clause_id):
        if clause_id != self.clause.id:
            raise KeyError(clause_id)
        return self.clause

    def list_clauses(self, *, filters=None, limit=None, offset=0):
        del filters, limit, offset
        return (self.clause,)

    def list_documents(self):
        return (
            DocumentDescriptor(
                key="TEST",
                title="Test standard",
                document_type=DocumentType.STANDARD,
                year=2026,
                clause_count=1,
            ),
        )


class Prompts:
    prompt = PromptDefinition(
        task="classification",
        version="1.0.0",
        system_prompt="Return the classification.",
        user_template="{content}\n{context_json}",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {"kind": {"type": "string", "enum": ["requirement"]}},
        },
    )

    def load_prompt(self, task, version):
        assert (task, version) == ("classification", "1.0.0")
        return self.prompt


class Models:
    model = ModelCatalogEntry(
        id="granite",
        model_ref="hf.co/example/granite:Q4_K_M",
        generation=ModelGenerationDefaults(max_output_tokens=384),
    )

    def get_model(self, model_id):
        assert model_id == "granite"
        return self.model


class Gateway:
    def __init__(self) -> None:
        self.request = None

    def health(self):
        return LlmHealth(available=True, models=("hf.co/example/granite:Q4_K_M",))

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value={"kind": "description"},
            model=request.model or "unknown",
            provider="test",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=12,
        )


def test_runs_auditable_experiment_and_reports_full_schema_errors() -> None:
    gateway = Gateway()
    result = PromptExperimentService(
        clauses=Clauses(), prompts=Prompts(), models=Models(), gateway=gateway
    ).run(
        PromptExperimentRequest(
            clause_identifier="TEST:1",
            prompt_task="classification",
            prompt_version="1.0.0",
            model_id="granite",
            context_variant="none",
            use_cache=True,
        )
    )

    assert gateway.request.model == "hf.co/example/granite:Q4_K_M"
    assert gateway.request.max_tokens == 384
    assert gateway.request.metadata["clause"]["content_hash"] == "sha256:" + "d" * 64
    assert gateway.request.metadata["use_cache"] is True
    assert result.schema_valid is False
    assert "$.kind" in result.schema_errors[0]


def test_rejects_reasoning_mode_not_declared_by_model() -> None:
    service = PromptExperimentService(
        clauses=Clauses(), prompts=Prompts(), models=Models(), gateway=Gateway()
    )

    request = PromptExperimentRequest(
        clause_identifier="clause-a",
        prompt_task="classification",
        prompt_version="1.0.0",
        model_id="granite",
        context_variant="none",
        reasoning_enabled=True,
    )

    with pytest.raises(ValueError, match="does not support reasoning mode"):
        service.run(request)
