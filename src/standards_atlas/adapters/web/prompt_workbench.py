"""Loopback-only HTTP adapter for the prompt workbench."""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import ValidationError

from standards_atlas.adapters.llm.ramalama_server import RamaLamaServerError
from standards_atlas.application.knowledge_proposal_extraction.source_bound_contract import (
    source_package_request_payload,
)
from standards_atlas.application.ports.llm_gateway import (
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from standards_atlas.application.prompt_workbench import (
    AmbiguousClauseIdentifierError,
    ClauseNotFoundError,
    ModelCatalog,
    PromptCatalog,
    PromptCompilationError,
    PromptExperimentRequest,
    PromptExperimentResult,
    PromptExperimentService,
    SourceBoundKnowledgeExperimentRequest,
    SourceBoundKnowledgeExperimentResult,
    SourceBoundKnowledgePreviewResult,
    list_context_variants,
)
from standards_atlas.application.semantic_qualification.clause_access import ClauseProvider


class PromptWorkbenchRuntime(Protocol):
    """Runtime operations used by the HTTP adapter."""

    def health(self): ...

    def activate(self, model_ref: str): ...


@dataclass(frozen=True)
class PromptWorkbenchHttpConfig:
    """Safe defaults for a local development-only web service."""

    host: str = "127.0.0.1"
    port: int = 8765
    max_request_body_bytes: int = 1_048_576
    extra_allowed_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _is_loopback_host(self.host):
            raise ValueError("prompt workbench must bind to a loopback host")
        if not 1 <= self.port <= 65_535:
            raise ValueError("prompt workbench port must be between 1 and 65535")
        if self.max_request_body_bytes < 1:
            raise ValueError("max_request_body_bytes must be positive")

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({"localhost", "127.0.0.1", "::1", self.host, *self.extra_allowed_hosts})


@dataclass(frozen=True)
class PromptWorkbenchWebDependencies:
    clauses: ClauseProvider
    prompts: PromptCatalog
    models: ModelCatalog
    experiments: PromptExperimentService
    runtime: PromptWorkbenchRuntime


def create_prompt_workbench_app(
    dependencies: PromptWorkbenchWebDependencies,
    config: PromptWorkbenchHttpConfig | None = None,
):
    """Create the Starlette application without starting a process."""
    try:
        from starlette.applications import Starlette
        from starlette.concurrency import run_in_threadpool
        from starlette.responses import FileResponse, JSONResponse
        from starlette.routing import Mount, Route
        from starlette.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover - exercised through the CLI boundary
        raise RuntimeError(
            "Prompt workbench dependencies are missing; install the 'chat' extra"
        ) from exc

    http = config or PromptWorkbenchHttpConfig()
    assets = Path(__file__).resolve().parents[2] / "resources" / "web" / "prompt_workbench"

    async def index(_request):
        return FileResponse(assets / "index.html")

    async def health(_request):
        runtime_health = await run_in_threadpool(dependencies.runtime.health)
        return JSONResponse(
            {
                "service": "prompt-workbench",
                "status": "ok",
                "runtime": _health_json(runtime_health),
            }
        )

    async def prompts(_request):
        return JSONResponse(
            {
                "items": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in dependencies.prompts.list_prompts()
                ]
            }
        )

    async def prompt(request):
        definition = dependencies.prompts.load_prompt(
            request.path_params["task"], request.path_params["version"]
        )
        return JSONResponse(
            {
                "task": definition.task,
                "version": definition.version,
                "description": definition.description,
                "task_schema_version": definition.task_schema_version,
                "qualification_status": definition.qualification_status,
                "baseline_id": definition.baseline_id,
                "variant_id": definition.variant_id,
                "policy_id": definition.policy_id,
                "policy_version": definition.policy_version,
                "policy_sha256": definition.policy_sha256,
                "example_set_id": definition.example_set_id,
                "example_set_version": definition.example_set_version,
                "example_set_partition": definition.example_set_partition,
                "example_set_sha256": definition.example_set_sha256,
                "system_prompt": definition.system_prompt,
                "user_template": definition.user_template,
                "output_schema": definition.output_schema,
            }
        )

    async def models(_request):
        return JSONResponse(
            {"items": [item.model_dump(mode="json") for item in dependencies.models.list_models()]}
        )

    async def context_variants(_request):
        return JSONResponse(
            {"items": [item.model_dump(mode="json") for item in list_context_variants()]}
        )

    async def clauses(request):
        query = (request.query_params.get("q") or "").strip()
        limit = _query_limit(request.query_params.get("limit"))
        if query:
            items = dependencies.clauses.search_clauses(query, limit=limit)
        else:
            items = dependencies.clauses.list_clauses(limit=limit)
        return JSONResponse({"items": [_clause_summary(item) for item in items]})

    async def resolve_clause(request):
        identifier = request.query_params.get("identifier") or ""
        clause = dependencies.experiments.resolve_clause(identifier)
        return JSONResponse(clause.model_dump(mode="json"))

    async def context_preview(request):
        identifier = request.query_params.get("identifier") or ""
        variant = request.query_params.get("variant") or "full-context-v1"
        clause, context = dependencies.experiments.assemble_context(identifier, variant)
        return JSONResponse(
            {
                "clause": _clause_summary(clause),
                "variant": context.variant.model_dump(mode="json"),
                "context_text": context.context_text,
                "canonical_context": context.canonical_context,
                "selected_context": context.selected_context,
                "template_values": context.values,
            }
        )

    async def runtime(_request):
        runtime_health = await run_in_threadpool(dependencies.runtime.health)
        return JSONResponse(_health_json(runtime_health))

    async def activate_model(request):
        payload = await request.json()
        if not isinstance(payload, Mapping):
            raise ValueError("request body must be a JSON object")
        model = dependencies.models.get_model(str(payload.get("model_id") or ""))
        status = await run_in_threadpool(dependencies.runtime.activate, model.model_ref)
        return JSONResponse(
            {
                "model": model.model_dump(mode="json"),
                "runtime": asdict(status),
            }
        )

    async def run_experiment(request):
        payload = await request.json()
        experiment = PromptExperimentRequest.model_validate(payload)
        result = await run_in_threadpool(dependencies.experiments.run, experiment)
        return JSONResponse(_experiment_json(result))

    async def source_bound_preview(request):
        payload = await request.json()
        experiment = SourceBoundKnowledgeExperimentRequest.model_validate(payload)
        result = await run_in_threadpool(
            dependencies.experiments.preview_source_bound_knowledge, experiment
        )
        return JSONResponse(_source_bound_preview_json(result))

    async def source_bound_run(request):
        payload = await request.json()
        experiment = SourceBoundKnowledgeExperimentRequest.model_validate(payload)
        result = await run_in_threadpool(
            dependencies.experiments.run_source_bound_knowledge, experiment
        )
        return JSONResponse(_source_bound_experiment_json(result))

    routes = [
        Route("/", index, methods=["GET"]),
        Route("/api/health", health, methods=["GET"]),
        Route("/api/prompts", prompts, methods=["GET"]),
        Route("/api/prompts/{task:str}/{version:str}", prompt, methods=["GET"]),
        Route("/api/models", models, methods=["GET"]),
        Route("/api/context-variants", context_variants, methods=["GET"]),
        Route("/api/clauses", clauses, methods=["GET"]),
        Route("/api/clauses/resolve", resolve_clause, methods=["GET"]),
        Route("/api/context-preview", context_preview, methods=["GET"]),
        Route("/api/runtime", runtime, methods=["GET"]),
        Route("/api/models/activate", activate_model, methods=["POST"]),
        Route("/api/experiments", run_experiment, methods=["POST"]),
        Route("/api/source-bound-knowledge/preview", source_bound_preview, methods=["POST"]),
        Route("/api/source-bound-knowledge/run", source_bound_run, methods=["POST"]),
        Mount("/assets", StaticFiles(directory=assets), name="assets"),
    ]
    app = Starlette(
        debug=False,
        routes=routes,
        exception_handlers={
            AmbiguousClauseIdentifierError: _ambiguous_handler,
            ClauseNotFoundError: _not_found_handler,
            KeyError: _not_found_handler,
            ValidationError: _validation_handler,
            PromptCompilationError: _bad_request_handler,
            ValueError: _bad_request_handler,
            LlmTimeoutError: _timeout_handler,
            LlmUnavailableError: _unavailable_handler,
            RamaLamaServerError: _unavailable_handler,
            LlmResponseError: _gateway_handler,
        },
    )
    app.add_middleware(RequestBodyLimitMiddleware, maximum=http.max_request_body_bytes)
    app.add_middleware(LocalRequestSecurityMiddleware, config=http)
    return app


def run_prompt_workbench_server(app, config: PromptWorkbenchHttpConfig) -> None:
    """Serve one prompt-workbench process in the foreground."""
    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Prompt workbench dependencies are missing; install the 'chat' extra"
        ) from exc
    uvicorn.run(app, host=config.host, port=config.port, workers=1)


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies, including chunked bodies."""

    def __init__(self, app, *, maximum: int) -> None:
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = next(
            (value for key, value in scope.get("headers", ()) if key == b"content-length"),
            None,
        )
        if length is not None:
            try:
                exceeds_limit = int(length) > self.maximum
            except ValueError:
                await _plain_asgi_error(send, 400, "invalid Content-Length header")
                return
            if exceeds_limit:
                await _plain_asgi_error(send, 413, "request body is too large")
                return
        messages = []
        consumed = 0
        more_body = True
        while more_body:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                more_body = bool(message.get("more_body", False))
                if consumed > self.maximum:
                    await _plain_asgi_error(send, 413, "request body is too large")
                    return
            else:
                more_body = False
        iterator = iter(messages)

        async def replay_receive():
            return next(iterator, {"type": "http.disconnect"})

        await self.app(scope, replay_receive, send)


class LocalRequestSecurityMiddleware:
    """Enforce loopback Host/Origin checks and browser hardening headers."""

    def __init__(self, app, *, config: PromptWorkbenchHttpConfig) -> None:
        self.app = app
        self.allowed_hosts = config.allowed_hosts

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin1"): value.decode("latin1") for key, value in scope["headers"]}
        host = _host_name(headers.get("host", ""))
        origin = headers.get("origin")
        if host not in self.allowed_hosts or (
            origin and (urlparse(origin).hostname or "").casefold() not in self.allowed_hosts
        ):
            await _plain_asgi_error(send, 403, "prompt workbench accepts local requests only")
            return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", ()))
                response_headers.extend(
                    (
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; "
                            b"connect-src 'self'; img-src 'self'; object-src 'none'; "
                            b"base-uri 'none'; frame-ancestors 'none'",
                        ),
                    )
                )
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, secure_send)


async def _plain_asgi_error(send, status: int, detail: str) -> None:
    body = json.dumps({"error": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _clause_summary(clause) -> dict[str, Any]:
    return {
        "id": clause.id,
        "document_key": clause.document_key,
        "reference": clause.reference,
        "clause_reference": clause.clause_reference,
        "heading": clause.heading,
        "text_preview": clause.text[:240],
        "content_hash": clause.content_hash,
    }


def _health_json(health) -> dict[str, Any]:
    return {
        "available": health.available,
        "models": list(health.models),
        "detail": health.detail,
    }


def _experiment_json(result: PromptExperimentResult) -> dict[str, Any]:
    generation = result.generation_result
    request = result.generation_request
    return {
        "clause": result.clause.model_dump(mode="json"),
        "model": result.model.model_dump(mode="json"),
        "compiled_prompt": {
            "system_prompt": result.compiled_prompt.system_prompt,
            "user_prompt": result.compiled_prompt.user_prompt,
            "output_schema": result.compiled_prompt.output_schema,
            "placeholders": result.compiled_prompt.placeholders,
            "context": {
                "variant": result.compiled_prompt.context.variant.model_dump(mode="json"),
                "canonical": result.compiled_prompt.context.canonical_context,
                "selected": result.compiled_prompt.context.selected_context,
                "text": result.compiled_prompt.context.context_text,
            },
        },
        "request": {
            "temperature": request.temperature,
            "seed": request.seed,
            "max_tokens": request.max_tokens,
            "reasoning_enabled": request.reasoning_enabled,
        },
        "output": generation.value,
        "validation": {"valid": result.schema_valid, "errors": result.schema_errors},
        "generation": {
            "model": generation.model,
            "provider": generation.provider,
            "duration_ms": generation.duration_ms,
            "cached": generation.cached,
            "usage": asdict(generation.usage) if generation.usage else None,
            "input_hash": generation.input_hash,
            "raw_response_hash": generation.raw_response_hash,
            "raw_response": generation.raw_response,
        },
    }


def _source_bound_preview_json(result: SourceBoundKnowledgePreviewResult) -> dict[str, Any]:
    request = result.generation_request
    return {
        "clause": result.clause.model_dump(mode="json"),
        "model": result.model.model_dump(mode="json") if result.model is not None else None,
        "source_package": source_package_request_payload(result.source_package),
        "interpretation_context": dict(result.interpretation_context),
        "request": {
            "task": request.task,
            "prompt_version": request.prompt_version,
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "max_tokens": request.max_tokens,
            "reasoning_enabled": request.reasoning_enabled,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "output_schema": request.output_schema,
            "metadata": request.metadata,
        },
        "stages": {
            "model_called": False,
            "schema_checked": False,
            "parser_applied": False,
            "ontology_checked": False,
            "grounding_checked": False,
            "semantic_quality_assessed": False,
        },
    }


def _source_bound_experiment_json(
    result: SourceBoundKnowledgeExperimentResult,
) -> dict[str, Any]:
    preview = _source_bound_preview_json(result.preview)
    generation = result.generation_result
    proposal = result.proposal_result
    violations = list(proposal.violations) if proposal is not None else []
    ontology_kinds = {"undeclared_class", "undeclared_property"}
    ontology_valid = (
        None
        if proposal is None
        else not any(item.kind.value in ontology_kinds for item in violations)
    )
    grounding_kinds = {"unresolved_grounding", "ambiguous_grounding"}
    grounding_valid = (
        None
        if proposal is None
        else not any(item.kind.value in grounding_kinds for item in violations)
    )
    technical_candidate_valid = bool(
        result.schema_valid
        and result.parser_error is None
        and proposal is not None
        and not violations
    )
    preview.update(
        {
            "output": generation.value,
            "validation": {
                "schema_valid": result.schema_valid,
                "schema_errors": result.schema_errors,
                "parser_valid": result.parser_error is None if result.schema_valid else None,
                "parser_error": result.parser_error,
                "ontology_valid": ontology_valid,
                "grounding_valid": grounding_valid,
                "technical_candidate_valid": technical_candidate_valid,
                "semantic_quality_assessed": False,
            },
            "proposal": (
                {
                    "source_binding": proposal.source_package_binding.model_dump(mode="json"),
                    "evidence_anchors": [
                        item.model_dump(mode="json") for item in proposal.evidence_anchors
                    ],
                    "entities": [
                        item.model_dump(mode="json") for item in proposal.entity_proposals
                    ],
                    "assertions": [
                        item.model_dump(mode="json") for item in proposal.assertion_proposals
                    ],
                    "violations": [item.model_dump(mode="json") for item in violations],
                }
                if proposal is not None
                else None
            ),
            "generation": {
                "model": generation.model,
                "provider": generation.provider,
                "duration_ms": generation.duration_ms,
                "cached": generation.cached,
                "usage": asdict(generation.usage) if generation.usage else None,
                "input_hash": generation.input_hash,
                "raw_response_hash": generation.raw_response_hash,
                "raw_response": generation.raw_response,
            },
            "stages": {
                "model_called": True,
                "schema_checked": True,
                "parser_applied": result.schema_valid,
                "ontology_checked": proposal is not None,
                "grounding_checked": proposal is not None,
                "semantic_quality_assessed": False,
            },
        }
    )
    return preview


def _query_limit(value: str | None) -> int:
    limit = int(value or 20)
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return limit


def _is_loopback_host(value: str) -> bool:
    if value.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _host_name(value: str) -> str:
    return (urlparse(f"//{value}").hostname or "").casefold()


async def _error_response(status: int, error: Exception, *, extra=None):
    from starlette.responses import JSONResponse

    payload: dict[str, Any] = {"error": str(error)}
    if extra:
        payload.update(extra)
    return JSONResponse(payload, status_code=status)


async def _ambiguous_handler(_request, error: AmbiguousClauseIdentifierError):
    return await _error_response(
        409,
        error,
        extra={"candidates": [_clause_summary(item) for item in error.candidates]},
    )


async def _not_found_handler(_request, error: Exception):
    return await _error_response(404, error)


async def _validation_handler(_request, error: ValidationError):
    return await _error_response(422, error, extra={"details": error.errors()})


async def _bad_request_handler(_request, error: Exception):
    return await _error_response(400, error)


async def _timeout_handler(_request, error: Exception):
    return await _error_response(504, error)


async def _unavailable_handler(_request, error: Exception):
    return await _error_response(503, error)


async def _gateway_handler(_request, error: LlmResponseError):
    return await _error_response(
        502,
        error,
        extra={"raw_content": error.raw_content, "finish_reason": error.finish_reason},
    )
