"""Model label association must not weaken prompt or requested voter identity."""

import pytest

from standards_atlas.application.semantic_qualification.response_identity import (
    ResponseIdentityError,
    require_response_identity,
    response_identity,
)

REPOSITORY = "ibm-granite/granite-3.3-8b-instruct-GGUF"
REQUESTED = f"hf.co/{REPOSITORY}:Q4_K_M"


def validate(reported, *, model=REQUESTED, prompt="taxonomy-partial-v1", provider="ramalama"):
    return require_response_identity(
        {"model": reported, "prompt_version": prompt, "provider": "openai-compatible"},
        requested_model=model,
        prompt_version="taxonomy-partial-v1",
        provider=provider,
    )


@pytest.mark.parametrize("model", [REQUESTED, "small", "gpt-local", "oci://registry/model:q4"])
def test_identical_labels_remain_valid_without_artifact_attestation(model):
    identity = validate(model, model=model)
    assert identity["accepted"] and identity["model_match"] == "exact"
    assert identity["runtime_artifact_verified"] is False
    assert identity["requested_model"] == model


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "hf://",
        "hf.co/",
        "hf.co://",
        "huggingface://",
        "huggingface.co/",
        "https://huggingface.co/",
        "https://hf.co/",
    ],
)
def test_known_transport_forms_keep_the_exact_selector(prefix):
    label = f"{prefix}{REPOSITORY}:Q4_K_M"
    identity = validate(label)
    assert identity["model_match"] in {"exact", "hf_transport_alias"}
    assert identity["selector_check"] == "matching_labels"
    assert identity["reported_model"] == label
    assert identity["requested_model"] == REQUESTED


@pytest.mark.parametrize("selector", ["Q4_K_M", "Q6_K", "IQ4_XS", "Q8_0", "BF16", "F16"])
def test_missing_quantization_is_explicitly_unattested_not_a_different_model(selector):
    identity = validate(REPOSITORY, model=f"hf.co/{REPOSITORY}:{selector}")
    assert identity["model_match"] == "hf_repository_label"
    assert identity["selector_check"] == "not_reported"
    assert identity["requested_selector"] == selector
    assert identity["reported_selector"] is None
    assert identity["runtime_artifact_verified"] is False


@pytest.mark.parametrize(
    "reported",
    [
        f"{REPOSITORY}:Q5_K_M",
        f"{REPOSITORY}:F16",
        f"{REPOSITORY}:main",
        f"{REPOSITORY}@main",
        f"other/{REPOSITORY.split('/')[1]}",
        "granite-3.3-8b-instruct-GGUF",
        "granite",
        f"/tmp/{REPOSITORY}",
        f"oci://{REPOSITORY}",
        f"{REPOSITORY}/weights.Q4_K_M.gguf",
        f"{REPOSITORY}-other",
        f"{REPOSITORY}:Q4_K_S",
        "",
        None,
        5,
    ],
)
def test_unrelated_ambiguous_or_conflicting_labels_are_rejected(reported):
    with pytest.raises(ResponseIdentityError) as exc:
        validate(reported)
    assert exc.value.identity["accepted"] is False
    assert REQUESTED in str(exc.value)
    assert "reported=" in str(exc.value)


@pytest.mark.parametrize(
    "model,reported",
    [
        (f"hf.co/{REPOSITORY}:revision1", REPOSITORY),
        ("hf.co/org/model:Q4_K_M", "org/model"),
        (f"hf.co/{REPOSITORY}", f"{REPOSITORY}:Q4_K_M"),
        ("oci://org/model:Q4_K_M", "org/model"),
    ],
)
def test_unreported_revisions_non_gguf_tags_and_unrequested_selectors_are_not_dropped(
    model,
    reported,
):
    with pytest.raises(ResponseIdentityError):
        validate(reported, model=model)


@pytest.mark.parametrize("reported", [REQUESTED, REPOSITORY])
def test_prompt_identity_is_never_normalized(reported):
    with pytest.raises(ResponseIdentityError, match="prompt version differs") as exc:
        validate(reported, prompt="taxonomy-partial-v2")
    assert exc.value.identity["reported_prompt"] == "taxonomy-partial-v2"
    assert exc.value.identity["requested_prompt"] == "taxonomy-partial-v1"


def test_hf_relaxation_does_not_apply_to_codex_or_unknown_provider():
    for provider in ("codex", "unknown"):
        with pytest.raises(ResponseIdentityError):
            validate(REPOSITORY, provider=provider)
        assert validate(REQUESTED, provider=provider)["accepted"]


def test_diagnostic_exposes_missing_identity_instead_of_filling_request_values():
    identity = response_identity(
        {},
        requested_model=REQUESTED,
        prompt_version="taxonomy-partial-v1",
        provider="ramalama",
    )
    assert identity["reported_model"] is None
    assert identity["reported_prompt"] is None
    assert identity["accepted"] is False


def test_raw_provider_model_cannot_be_hidden_by_relabeling_the_structured_result():
    with pytest.raises(ResponseIdentityError, match="raw provider response"):
        require_response_identity(
            {
                "model": REQUESTED,
                "prompt_version": "v1",
                "raw_response": {"model": "other/model-GGUF"},
            },
            requested_model=REQUESTED,
            prompt_version="v1",
            provider="ramalama",
        )


def test_missing_provider_model_is_not_presented_as_artifact_attestation():
    identity = require_response_identity(
        {"model": REQUESTED, "prompt_version": "v1", "raw_response": {"choices": []}},
        requested_model=REQUESTED,
        prompt_version="v1",
        provider="ramalama",
    )
    assert identity["raw_provider_model"] is None
    assert identity["model_label_source"] == "adapter_result"
    assert identity["runtime_artifact_verified"] is False
