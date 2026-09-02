from __future__ import annotations

from dataclasses import dataclass

from starlette.testclient import TestClient

from standards_atlas.adapters.web import (
    PromptWorkbenchHttpConfig,
    PromptWorkbenchWebDependencies,
    create_prompt_workbench_app,
)
from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    StructuredGenerationResult,
)
from standards_atlas.application.prompt_workbench import (
    ModelCatalogEntry,
    PromptCatalogEntry,
    PromptExperimentService,
)
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
        content_hash="sha256:" + "a" * 64,
        clause_type=ClauseType.CLAUSE,
        heading="Scope",
        text="The supplier shall verify the result.",
    )

    def list_documents(self):
        return (
            DocumentDescriptor(
                key="TEST", title="Test", document_type=DocumentType.STANDARD, clause_count=1
            ),
        )

    def get_clause(self, clause_id):
        if clause_id != self.clause.id:
            raise KeyError(clause_id)
        return self.clause

    def list_clauses(self, *, filters=None, limit=None, offset=0):
        del filters
        return (self.clause,)[offset:limit]

    def search_clauses(self, query, *, filters=None, limit=20):
        del filters, limit
        return (self.clause,) if query.casefold() in self.clause.text.casefold() else ()


class Prompts:
    definition = PromptDefinition(
        task="classification",
        version="1.0.0",
        description="Classify one clause.",
        system_prompt="Return JSON.",
        user_template="{content}\n{context_json}",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {"kind": {"type": "string"}},
        },
    )

    def list_prompts(self):
        return (
            PromptCatalogEntry(
                task="classification", version="1.0.0", placeholders=("content", "context_json")
            ),
        )

    def load_prompt(self, task, version):
        if (task, version) != ("classification", "1.0.0"):
            raise KeyError((task, version))
        return self.definition


class Models:
    model = ModelCatalogEntry(id="granite", model_ref="hf.co/example/granite:Q4")

    def list_models(self):
        return (self.model,)

    def get_model(self, model_id):
        if model_id != self.model.id:
            raise KeyError(model_id)
        return self.model


class Gateway:
    def health(self):
        return LlmHealth(True, ("hf.co/example/granite:Q4",))

    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={"kind": "requirement"},
            model=request.model or "",
            provider="test",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=5,
        )


@dataclass(frozen=True)
class RuntimeStatus:
    running: bool
    detail: str | None = None
    models: tuple[str, ...] = ()
    endpoint_available: bool = True


class Runtime:
    activated = None

    def health(self):
        return LlmHealth(True, ("hf.co/example/granite:Q4",))

    def activate(self, model_ref):
        self.activated = model_ref
        return RuntimeStatus(True, models=(model_ref,))


def _client(*, max_body=1_048_576):
    clauses, prompts, models, gateway, runtime = (
        Clauses(),
        Prompts(),
        Models(),
        Gateway(),
        Runtime(),
    )
    service = PromptExperimentService(
        clauses=clauses, prompts=prompts, models=models, gateway=gateway
    )
    app = create_prompt_workbench_app(
        PromptWorkbenchWebDependencies(
            clauses=clauses,
            prompts=prompts,
            models=models,
            experiments=service,
            runtime=runtime,
        ),
        PromptWorkbenchHttpConfig(
            extra_allowed_hosts=("testserver",), max_request_body_bytes=max_body
        ),
    )
    return TestClient(app), runtime


def test_serves_ui_catalogs_and_local_security_headers() -> None:
    client, _ = _client()

    page = client.get("/")
    prompts = client.get("/api/prompts")

    assert page.status_code == 200
    assert "Prompt Workbench" in page.text
    assert page.headers["content-security-policy"].startswith("default-src 'self'")
    assert prompts.json()["items"][0]["task"] == "classification"


def test_resolves_clause_previews_context_and_runs_experiment() -> None:
    client, _ = _client()

    clause = client.get("/api/clauses/resolve", params={"identifier": "TEST:1"})
    context = client.get(
        "/api/context-preview", params={"identifier": "clause-a", "variant": "none"}
    )
    result = client.post(
        "/api/experiments",
        json={
            "clause_identifier": "clause-a",
            "prompt_task": "classification",
            "prompt_version": "1.0.0",
            "model_id": "granite",
            "context_variant": "none",
        },
    )

    assert clause.json()["text"].startswith("The supplier")
    assert context.json()["variant"]["id"] == "none"
    assert result.status_code == 200
    assert result.json()["output"] == {"kind": "requirement"}
    assert result.json()["validation"]["valid"] is True


def test_activates_manifest_model_and_rejects_non_local_host() -> None:
    client, runtime = _client()

    activated = client.post("/api/models/activate", json={"model_id": "granite"})
    rejected = client.get("/api/runtime", headers={"host": "example.test"})

    assert activated.status_code == 200
    assert runtime.activated == "hf.co/example/granite:Q4"
    assert rejected.status_code == 403


def test_rejects_oversized_body() -> None:
    client, _ = _client(max_body=20)

    response = client.post("/api/experiments", content=b"x" * 21)

    assert response.status_code == 413


def test_rejects_non_loopback_bind() -> None:
    try:
        PromptWorkbenchHttpConfig(host="0.0.0.0")
    except ValueError as error:
        assert "loopback" in str(error)
    else:  # pragma: no cover - explicit failure message is more useful here
        raise AssertionError("non-loopback bind was accepted")
