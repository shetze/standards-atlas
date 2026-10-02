from __future__ import annotations

import json

from standards_atlas.application.evaluation.source_bound_prompt import (
    build_source_bound_generation_request,
    semantic_prompt_repository,
)


def _request(payload: dict[str, object]):
    return build_source_bound_generation_request(
        repository=semantic_prompt_repository(),
        task="formal-semantic-knowledge-proposal",
        prompt_version="ontology-guided-assertions-source-bound-v1",
        task_schema_version="1.0.0",
        payload=payload,
        model="test-model",
        temperature=0.0,
        metadata={"source_package_sha256": "sha256:" + "a" * 64},
    )


def test_b0_request_template_preserves_exact_pre_migration_json_body() -> None:
    payload = {
        "request_contract_id": "source-bound-knowledge-proposal-request-v1",
        "document_key": "TEST",
        "source_package": {
            "source_surfaces": [
                {
                    "source_ref": "heading:parent",
                    "source_kind": "heading",
                    "text": "Safety plan confirmation review",
                }
            ]
        },
        "allowed_classes": ["urn:test:Activity"],
    }

    request = _request(payload)

    assert request.user_prompt == json.dumps(payload, ensure_ascii=False)
    assert request.task == "formal-semantic-knowledge-proposal"
    assert request.prompt_version == "ontology-guided-assertions-source-bound-v1"
    assert request.metadata["prompt_task_schema_version"] == "1.0.0"


def test_source_heading_change_changes_actual_b0_request_without_changing_prompt_contract() -> None:
    before = _request(
        {"source_package": {"source_surfaces": [{"source_kind": "heading", "text": "A"}]}}
    )
    after = _request(
        {"source_package": {"source_surfaces": [{"source_kind": "heading", "text": "B"}]}}
    )

    assert before.user_prompt != after.user_prompt
    assert before.system_prompt == after.system_prompt
    assert before.output_schema == after.output_schema
