"""Qualification never receives persisted answers; reuse follows selected facts."""

import copy
import json
from types import SimpleNamespace

import pytest

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.semantic_qualification import request_builder
from standards_atlas.application.semantic_qualification.context_framing import (
    frame_cbox_context,
    frame_qualification_context,
    list_cbox_frame_policies,
    resolve_cbox_frame_policy,
)


@pytest.fixture
def inputs():
    return {
        "content": {"text": "The supplier shall verify.", "hash": "sha256:" + "a" * 64},
        "context": {
            "document_key": "EXAMPLE",
            "clause_id": "clause-1",
            "reference": "1",
            "heading": "Verification",
            "clause_type": "clause",
            "semantic": {"applicability_present": True, "primary_function": "LEAK-SEMANTIC"},
            "attribute_sources": {
                "enrichments.semantic.primary_function": {
                    "availability": "known",
                    "origin": "generated",
                    "generated": {
                        "generator": "LEAK-GENERATOR",
                        "evidence": ["LEAK-EVIDENCE"],
                    },
                }
            },
            "structural_roles": ["LEAK-STRUCTURAL-ROLE"],
            "expected": {"primary_function": "LEAK-GOLD"},
            "eligibility": {"reason": "LEAK-GOLD"},
            "context_routing": {"scopes": [{"conditions": ["LEAK-ROUTING"]}]},
            "subject_context": {"primary_subject": {"normalized_label": "LEAK-SUBJECT"}},
        },
    }


def configuration(**kwargs):
    return SimpleNamespace(
        **{
            "task": "semantic-profile-classification",
            "prompt_version": "test-v1",
            "model": "model-a",
            "temperature": 0.0,
            "seed": 7,
            "max_tokens": 256,
            "reasoning_enabled": False,
            "corpus_id": "corpus",
            "dataset_version": "1.0.0",
            "cbox_frame": "effective-context-v1",
            **kwargs,
        }
    )


def request(inputs, template="{content}\n{context_text}\n{metadata}\n{structural_context}", **cfg):
    return request_builder.build_proposal_request(
        configuration(**cfg),
        PromptDefinition(
            task="semantic-profile-classification",
            version="test-v1",
            system_prompt="system",
            user_template=template,
            output_schema={"type": "object"},
        ),
        inputs,
        SimpleNamespace(version="1.0.0"),
    )


@pytest.mark.parametrize(
    "frame", [f"{policy.id}-v{policy.version}" for policy in list_cbox_frame_policies()]
)
def test_every_qualification_frame_masks_accepted_answers_and_gold(inputs, frame):
    result = request(inputs, cbox_frame=frame)
    for leak in (
        "LEAK-SEMANTIC",
        "LEAK-GENERATOR",
        "LEAK-EVIDENCE",
        "LEAK-GOLD",
        "LEAK-STRUCTURAL-ROLE",
    ):
        assert leak not in result.user_prompt
    assert "semantic" not in result.metadata["framed_cbox"]
    assert result.metadata["clause_context"] == inputs["context"]  # local audit only


@pytest.mark.parametrize("field", ["semantic", "expected", "attribute_sources", "structural_roles"])
def test_raw_context_cannot_bypass_selection_through_template_placeholders(inputs, field):
    with pytest.raises(ValueError, match="unavailable field"):
        request(inputs, template="{" + field + "}")


def test_applicability_isolation_masks_heading_even_in_direct_variables(inputs):
    result = request(
        inputs,
        template="{heading}|{metadata}|{context_json}",
        cbox_frame="applicability-isolated-v1",
    )
    for leak in ("Verification", "LEAK-SUBJECT", "LEAK-ROUTING", "clause_type"):
        assert leak not in result.user_prompt


@pytest.mark.parametrize(
    "task,masked",
    [
        ("context-routing-enrichment", "context_routing"),
        ("primary-subject-extraction", "subject_context"),
    ],
)
def test_task_targets_are_isolated_even_in_effective_frame(inputs, task, masked):
    selected = frame_qualification_context(
        inputs["context"],
        resolve_cbox_frame_policy("effective-context-v1"),
        task=task,
    )
    assert masked not in selected.values
    assert "semantic" not in selected.values
    assert "attribute_sources" not in selected.values


def test_effective_downstream_frame_retains_semantics_but_not_evidence(inputs):
    selected = frame_cbox_context(
        inputs["context"],
        resolve_cbox_frame_policy("effective-context-v1"),
    )
    assert selected.values["semantic"]["applicability_present"] is True
    assert "LEAK-EVIDENCE" not in json.dumps(selected.values)
    assert "LEAK-GENERATOR" in json.dumps(selected.values)


@pytest.mark.parametrize(
    "change",
    [
        "content",
        "hash",
        "heading",
        "subject",
        "model",
        "seed",
        "frame",
        "prompt",
    ],
)
def test_fingerprint_invalidates_changed_effective_inputs(inputs, change):
    before = request(inputs).metadata["qualification_input_fingerprint"]
    kwargs = {}
    if change == "content":
        inputs["content"]["text"] += " Changed."
    elif change == "hash":
        inputs["content"]["hash"] = "sha256:" + "b" * 64
    elif change == "heading":
        inputs["context"]["heading"] = "Changed"
    elif change == "subject":
        inputs["context"]["subject_context"]["primary_subject"]["normalized_label"] = "Changed"
    elif change == "model":
        kwargs["model"] = "model-b"
    elif change == "seed":
        kwargs["seed"] = 42
    elif change == "frame":
        kwargs["cbox_frame"] = "full-context-v1"
    else:
        kwargs["template"] = "{content}\nChanged prompt\n{context_json}"
    assert request(inputs, **kwargs).metadata["qualification_input_fingerprint"] != before


def test_renderer_and_hidden_predictions_do_not_invalidate_reuse(inputs, monkeypatch):
    first = request(inputs)
    second_input = copy.deepcopy(inputs)
    second_input["context"]["semantic"] = {"applicability_present": False}
    second_input["context"]["expected"] = {"primary_function": "different gold"}
    monkeypatch.setattr(request_builder, "render_cbox_context", lambda _: "New wording only")
    second = request(second_input)
    assert first.user_prompt != second.user_prompt
    assert (
        first.metadata["qualification_input_fingerprint"]
        == second.metadata["qualification_input_fingerprint"]
    )
