"""Compare response labels without changing the requested cache/voter identity.

A repository label returned by RamaLama is not an attestation of model bytes or
quantization. Only explicitly recognised HF transport aliases are tolerated;
conflicting selectors, opaque aliases and prompt changes are never normalised.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

RESPONSE_IDENTITY_POLICY = "hf-response-identity-v1"
_HF_PREFIXES = (
    "https://huggingface.co/",
    "https://hf.co/",
    "huggingface://",
    "huggingface.co/",
    "hf.co://",
    "hf.co/",
    "hf://",
)
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
_QUANTIZATION = re.compile(r"(?:I?Q[1-8](?:_[A-Z0-9]+)*|BF16|F16|F32)")


class ResponseIdentityError(ValueError):
    """A response cannot be associated with its requested model and prompt."""

    def __init__(self, identity: dict[str, Any]):
        self.identity = identity
        super().__init__(
            "provider response identity mismatch: "
            f"model requested={identity['requested_model']!r}, "
            f"reported={identity['reported_model']!r}; "
            f"prompt requested={identity['requested_prompt']!r}, "
            f"reported={identity['reported_prompt']!r}; {identity['reason']}"
        )


def _hf_reference(value: str) -> tuple[str, str | None] | None:
    for prefix in _HF_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    repository, separator, selector = value.partition(":")
    if not _REPOSITORY.fullmatch(repository):
        return None
    if separator and not _QUANTIZATION.fullmatch(selector):
        return None  # Do not drop revisions, filenames, URLs or arbitrary tags.
    return repository, selector if separator else None


def response_identity(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    prompt_version: str,
    provider: str,
) -> dict[str, Any]:
    """Return an auditable label comparison, not a model-artifact verification.

    The configured provider is a routing identity (e.g. ``ramalama``); the
    adapter may report ``openai-compatible``. Preserve both without redefining
    either. This policy only relaxes model *labels* for that local HF path.
    """
    reported = response.get("model")
    reported_prompt = response.get("prompt_version")
    requested_ref = _hf_reference(requested_model)
    reported_ref = _hf_reference(reported) if isinstance(reported, str) else None
    match = "mismatch"
    selector_check = "not_compared" if requested_ref and requested_ref[1] else "not_requested"
    reason = "reported model does not match the requested model"
    if reported == requested_model:
        match, reason = "exact", "identical model labels"
        if requested_ref and requested_ref[1]:
            selector_check = "matching_labels"
    elif provider in {"ramalama", "openai-compatible"} and requested_ref and reported_ref:
        repository, selector = requested_ref
        reported_repository, reported_selector = reported_ref
        if repository != reported_repository:
            reason = "different Hugging Face repositories"
        elif selector == reported_selector:
            match, reason = "hf_transport_alias", "same repository and selector"
            selector_check = "matching_labels" if selector else "not_requested"
        elif selector and reported_selector is None and repository.lower().endswith("-gguf"):
            match = "hf_repository_label"
            selector_check = "not_reported"
            reason = "same GGUF repository; response does not attest the requested quantization"
        else:
            reason = "different or unexpected quantization selectors"
            selector_check = "mismatch"
    raw = response.get("raw_response")
    raw_model = raw.get("model") if isinstance(raw, Mapping) else None
    if provider in {"ramalama", "openai-compatible"} and raw_model and raw_model != reported:
        match = "mismatch"
        reason = "structured result model differs from the raw provider response"
    prompt_matches = reported_prompt == prompt_version
    if not prompt_matches:
        reason = "prompt version differs from request; " + reason
    return {
        "policy": RESPONSE_IDENTITY_POLICY,
        "requested_provider": provider,
        "reported_provider": response.get("provider"),
        "requested_model": requested_model,
        "reported_model": reported,
        "raw_provider_model": raw_model,
        "model_label_source": "provider_response" if raw_model else "adapter_result",
        "requested_prompt": prompt_version,
        "reported_prompt": reported_prompt,
        "requested_selector": requested_ref[1] if requested_ref else None,
        "reported_selector": reported_ref[1] if reported_ref else None,
        "model_match": match,
        "prompt_matches": prompt_matches,
        "selector_check": selector_check,
        "accepted": match != "mismatch" and prompt_matches,
        "runtime_artifact_verified": False,
        "reason": reason,
    }


def require_response_identity(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    prompt_version: str,
    provider: str,
) -> dict[str, Any]:
    """Apply the same decision to fresh responses, resume and archive adoption."""
    identity = response_identity(
        response,
        requested_model=requested_model,
        prompt_version=prompt_version,
        provider=provider,
    )
    if not identity["accepted"]:
        raise ResponseIdentityError(identity)
    return identity
