"""Execute an observational normalization-quality review over an existing corpus."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.evaluation.schema import validate_schema
from standards_atlas.application.normalization_quality.models import (
    FindingType,
    NormalizationQualityCase,
    NormalizationQualityFinding,
    NormalizationQualityRun,
    QualityStatus,
    Severity,
)
from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest

ProgressCallback = Callable[[int, int, NormalizationQualityCase], None]


class NormalizationQualityRunner:
    """Review every text-bearing corpus clause without modifying source artifacts."""

    TASK = "linguistic-integrity-review"
    PROMPT_VERSION = "v1"

    def __init__(self, resources: Path) -> None:
        self._prompt = PromptRepository(resources / "prompts").load(self.TASK, self.PROMPT_VERSION)

    def run(
        self,
        corpus_path: Path,
        *,
        gateway: LlmGateway,
        model_id: str,
        model_ref: str,
        max_tokens: int = 384,
        limit: int | None = None,
        progress: ProgressCallback | None = None,
    ) -> NormalizationQualityRun:
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
        examples = payload.get("examples")
        if not isinstance(examples, list):
            raise ValueError("corpus dataset must contain an examples list")
        selected = examples[:limit] if limit is not None else examples
        cases: list[NormalizationQualityCase] = []
        total = len(selected)
        for index, item in enumerate(selected, start=1):
            case = self._run_case(
                item,
                gateway=gateway,
                model_id=model_id,
                model_ref=model_ref,
                max_tokens=max_tokens,
            )
            cases.append(case)
            if progress is not None:
                progress(index, total, case)
        provider = next((case.provider for case in cases if case.succeeded), "unknown")
        return NormalizationQualityRun(
            corpus_path=str(corpus_path),
            prompt_version=self.PROMPT_VERSION,
            model_id=model_id,
            model_ref=model_ref,
            provider=provider,
            cases=tuple(cases),
        )

    def _run_case(
        self,
        item: Any,
        *,
        gateway: LlmGateway,
        model_id: str,
        model_ref: str,
        max_tokens: int,
    ) -> NormalizationQualityCase:
        example_id, text, context = _corpus_input(item)
        document_key = str(context.get("document_key", ""))
        reference = str(context.get("reference", example_id))
        title_value = context.get("title")
        title = str(title_value) if title_value else None
        if not text.strip():
            return _failed_case(
                example_id,
                document_key,
                reference,
                title,
                text,
                model_id,
                model_ref,
                "corpus item has no normalized clause text",
            )
        user_prompt = self._prompt.user_template.format(
            document_key=document_key or "unknown",
            reference=reference or "unknown",
            title=title or "",
            ancestor_headings=json.dumps(context.get("ancestor_headings", []), ensure_ascii=False),
            content_profile=str(context.get("content_profile", "unknown")),
            text=text,
        )
        request = StructuredGenerationRequest(
            task=self.TASK,
            system_prompt=self._prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=self._prompt.output_schema,
            prompt_version=self.PROMPT_VERSION,
            model=model_ref,
            temperature=0.0,
            seed=0,
            max_tokens=max_tokens,
            reasoning_enabled=False,
            metadata={"example_id": example_id, "review_kind": "normalization_quality"},
        )
        try:
            result = gateway.generate_structured(request)
            value = dict(result.value)
            valid, error = validate_schema(value, self._prompt.output_schema)
            if not valid:
                raise ValueError(f"response schema validation failed: {error}")
            status = QualityStatus(str(value["status"]))
            findings = tuple(_parse_finding(value) for value in value.get("findings", []))
            if status is QualityStatus.OK and findings:
                raise ValueError("status 'ok' must not contain findings")
            if status is QualityStatus.SUSPICIOUS and not findings:
                raise ValueError("status 'suspicious' must contain at least one finding")
            return NormalizationQualityCase(
                example_id=example_id,
                document_key=document_key,
                reference=reference,
                title=title,
                text=text,
                status=status,
                findings=findings,
                model_id=model_id,
                model_ref=model_ref,
                provider=result.provider,
                duration_ms=result.duration_ms,
                cached=result.cached,
                input_hash=result.input_hash,
                raw_response_hash=result.raw_response_hash,
            )
        except Exception as exc:
            return _failed_case(
                example_id,
                document_key,
                reference,
                title,
                text,
                model_id,
                model_ref,
                f"{type(exc).__name__}: {exc}",
            )


def _corpus_input(item: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(item, dict):
        raise ValueError("corpus example must be a JSON object")
    example_id = str(item.get("id", ""))
    value = item.get("input", {})
    if not isinstance(value, dict):
        raise ValueError(f"corpus example {example_id!r} input must be an object")
    content = value.get("content", {})
    context = value.get("context", {})
    if not isinstance(content, dict) or not isinstance(context, dict):
        raise ValueError(f"corpus example {example_id!r} has invalid content/context")
    text = str(content.get("text", ""))
    return example_id, text, context


def _parse_finding(value: Any) -> NormalizationQualityFinding:
    return NormalizationQualityFinding(
        type=FindingType(str(value["type"])),
        severity=Severity(str(value["severity"])),
        evidence=str(value["evidence"]),
        explanation=str(value["explanation"]),
        confidence=float(value["confidence"]),
    )


def _failed_case(
    example_id: str,
    document_key: str,
    reference: str,
    title: str | None,
    text: str,
    model_id: str,
    model_ref: str,
    error: str,
) -> NormalizationQualityCase:
    return NormalizationQualityCase(
        example_id=example_id,
        document_key=document_key,
        reference=reference,
        title=title,
        text=text,
        status=None,
        findings=(),
        model_id=model_id,
        model_ref=model_ref,
        provider="unknown",
        duration_ms=0,
        cached=False,
        input_hash="",
        raw_response_hash="",
        error=error,
    )
