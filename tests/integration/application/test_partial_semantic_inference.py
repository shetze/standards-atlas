"""Source CBox -> planned partial requests -> real adapter/schema/cache -> sparse artifact."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_taxonomy_grounded_inputs import descriptor

from standards_atlas.adapters.llm import LlmConfig, OpenAICompatibleLlmGateway
from standards_atlas.application.context.canonical_cbox import canonical_cbox_context
from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseEvaluationAnnotation,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
)

RESOURCES = Path("src/standards_atlas/resources/semantic")


def test_confirmed_source_predecision_and_gateway_cache_remain_sparse(tmp_path, monkeypatch):
    clause = descriptor()
    item = EvaluationExample(
        id=clause.id,
        expected={"primary_function": "LEAK-GOLD"},
        input={
            "content": {"text": clause.text, "hash": clause.content_hash},
            "context": canonical_cbox_context(clause),
        },
    )
    cfg = PartialProposalConfig(
        corpus_id="test",
        dataset_version="1",
        provider="ramalama",
        model="small",
        selected_attributes=("primary_function", "statement_functions", "applicability_present"),
    )
    llm = LlmConfig(model="small", cache_directory=tmp_path / "cache")
    gateway = OpenAICompatibleLlmGateway(llm)
    calls = []

    def provider_reply(method, path, payload=None):
        calls.append(payload)
        schema = payload["response_format"]["json_schema"]["schema"]
        assert "primary_function" not in schema["properties"]
        assert schema["required"] == ["statement_functions", "applicability_present"]
        assert "LEAK-GOLD" not in json.dumps(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "statement_functions": ["definition", "note"],
                                "applicability_present": False,
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 25, "completion_tokens": 12},
        }

    monkeypatch.setattr(gateway, "_request_json", provider_reply)
    report = run_partial_proposals(
        cfg,
        resources=RESOURCES,
        output_directory=tmp_path / "first",
        examples=(item,),
        execute=True,
        gateway_factory=lambda: gateway,
    )
    assert report["status_counts"] == {"evaluated": 1}
    record = next((tmp_path / "first" / "cases").glob("*/partial-observation.json"))
    result = PartialObservation.model_validate_json(record.read_text())
    assert result.plan.fixed_attributes == {"primary_function": "definition"}
    assert result.model_evidence() == {
        "statement_functions": ["definition", "note"],
        "applicability_present": False,
    }
    with pytest.raises(ValidationError):
        ClauseEvaluationAnnotation.model_validate_json(record.read_text())
    assert not list((tmp_path / "first").rglob("evaluation.yaml"))

    # New experimental output, same semantic input: provider cache, not another fresh inference.
    second = run_partial_proposals(
        cfg,
        resources=RESOURCES,
        output_directory=tmp_path / "second",
        examples=(replace(item, expected={"other": True}, tags=("LEAK-TAGS",)),),
        execute=True,
        gateway_factory=lambda: gateway,
    )
    assert len(calls) == 1
    assert second["request_timing"]["cached_response_count"] == 1
    assert second["logical_model_observation_count"] == 1


def test_adapter_schema_failure_cannot_be_published_as_negative(tmp_path, monkeypatch):
    clause = descriptor()
    item = EvaluationExample(
        id=clause.id,
        expected={},
        input={
            "content": {"text": clause.text, "hash": clause.content_hash},
            "context": canonical_cbox_context(clause),
        },
    )
    cfg = PartialProposalConfig(
        corpus_id="test",
        dataset_version="1",
        provider="ramalama",
        model="small",
        selected_attributes=("applicability_present",),
    )
    gateway = OpenAICompatibleLlmGateway(LlmConfig(cache_directory=None))
    monkeypatch.setattr(
        gateway,
        "_request_json",
        lambda *a, **kw: {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        },
    )
    report = run_partial_proposals(
        cfg,
        resources=RESOURCES,
        output_directory=tmp_path / "out",
        examples=(item,),
        execute=True,
        gateway_factory=lambda: gateway,
    )
    assert report["status_counts"] == {"failed": 1}
    record = next((tmp_path / "out" / "cases").glob("*/partial-observation.json"))
    assert PartialObservation.model_validate_json(record.read_text()).model_evidence() == {}
    attempt = next((tmp_path / "out").rglob("attempt-001.json"))
    assert json.loads(attempt.read_text())["error"]["raw_content"] == "{}"
