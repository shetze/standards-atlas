import json
from types import SimpleNamespace

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.semantic_qualification.request_builder import (
    build_clause_reference,
    build_proposal_request,
    serialize_generation_request,
)


def test_builds_and_serializes_proposal_request() -> None:
    config = SimpleNamespace(
        task="semantic-profile",
        prompt_version="structure-aware-v1",
        model="test-model",
        temperature=0.0,
        seed=7,
        max_tokens=512,
        reasoning_enabled=False,
        corpus_id="corpus",
        dataset_version="1.0.0",
    )
    prompt = PromptDefinition(
        task="semantic-profile",
        version="structure-aware-v1",
        system_prompt="system",
        user_template="{content}\n{document_key}",
        output_schema={"type": "object"},
    )
    item_input = {
        "content": {"text": "The supplier shall verify.", "hash": "sha256:" + "a" * 64},
        "context": {
            "knowledge_domain": "functional-safety",
            "document_key": "IEC61508-3",
            "clause_id": "clause-1",
        },
    }

    request = build_proposal_request(
        config,
        prompt,
        item_input,
        SimpleNamespace(version="1.0.0"),
    )

    assert request.user_prompt == "The supplier shall verify.\nIEC61508-3"
    assert serialize_generation_request(request)["metadata"]["content_hash"] == "sha256:" + "a" * 64
    assert build_clause_reference(item_input).clause_id == "clause-1"


def test_builds_natural_language_context_projection_for_prompt() -> None:
    config = SimpleNamespace(
        task="semantic-profile",
        prompt_version="structure-aware-v6",
        model="test-model",
        temperature=0.0,
        seed=7,
        max_tokens=512,
        reasoning_enabled=False,
        corpus_id="corpus",
        dataset_version="1.0.0",
    )
    prompt = PromptDefinition(
        task="semantic-profile",
        version="structure-aware-v6",
        system_prompt="system",
        user_template="{content}\n\nContextual evidence:\n{context_text}",
        output_schema={"type": "object"},
    )
    item_input = {
        "content": {"text": "The supplier shall verify.", "hash": "sha256:" + "a" * 64},
        "context": {
            "knowledge_domain": "functional-safety",
            "document_key": "IEC61508-3",
            "clause_id": "clause-1",
            "reference": "7.4.2",
            "heading": "Software verification",
            "eligibility": {"eligible": True},
        },
    }

    request = build_proposal_request(config, prompt, item_input, SimpleNamespace(version="1.0.0"))

    assert 'This clause is IEC61508-3 7.4.2, "Software verification".' in request.user_prompt
    assert "eligible" not in request.user_prompt
    assert "clause-1" not in request.user_prompt


def test_request_metadata_records_resolved_cbox_frame_and_projection() -> None:
    config = SimpleNamespace(
        task="semantic-profile",
        prompt_version="structure-aware-v6",
        cbox_frame="full-context-v1",
        model="test-model",
        temperature=0.0,
        seed=7,
        max_tokens=512,
        reasoning_enabled=False,
        corpus_id="corpus",
        dataset_version="1.0.0",
    )
    prompt = PromptDefinition(
        task="semantic-profile",
        version="structure-aware-v6",
        system_prompt="system",
        user_template="{context_text}",
        output_schema={"type": "object"},
    )
    item_input = {
        "content": {"text": "Clause text.", "hash": "sha256:" + "b" * 64},
        "context": {
            "document_key": "EN50126-1",
            "reference": "6.2",
            "heading": "Life cycle",
            "clause_id": "opaque-id",
            "eligibility": {"eligible": True},
        },
    }

    request = build_proposal_request(config, prompt, item_input, SimpleNamespace(version="1.0.0"))

    assert request.metadata["cbox_frame"] == {"id": "full-context", "version": "1"}
    assert request.metadata["framed_cbox"] == {
        "document_key": "EN50126-1",
        "reference": "6.2",
        "heading": "Life cycle",
    }
    assert request.metadata["clause_context"]["clause_id"] == "opaque-id"


def test_context_json_uses_the_same_framed_cbox_as_context_text() -> None:
    config = SimpleNamespace(
        task="semantic-profile",
        prompt_version="structure-aware-v1",
        cbox_frame="full-context-v1",
        model="test-model",
        temperature=0.0,
        seed=7,
        max_tokens=512,
        reasoning_enabled=False,
        corpus_id="corpus",
        dataset_version="1.0.0",
    )
    prompt = PromptDefinition(
        task="semantic-profile",
        version="structure-aware-v1",
        system_prompt="system",
        user_template="{context_json}",
        output_schema={"type": "object"},
    )
    item_input = {
        "content": {"text": "Clause text.", "hash": "sha256:" + "c" * 64},
        "context": {
            "document_key": "IEC61508-3",
            "reference": "7.4.2",
            "clause_id": "opaque-id",
            "eligibility": {"eligible": True},
        },
    }

    request = build_proposal_request(config, prompt, item_input, SimpleNamespace(version="1.0.0"))
    rendered = json.loads(request.user_prompt)

    assert rendered == {"document_key": "IEC61508-3", "reference": "7.4.2"}
    assert "clause_id" not in rendered
    assert "eligibility" not in rendered
