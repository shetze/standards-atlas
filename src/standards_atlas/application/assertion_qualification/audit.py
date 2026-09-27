"""Byte-bound review audits and deterministic, model-free AP01 fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import yaml

from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionReviewCase,
    AssertionReviewPilot,
    AssertionReviewStatus,
)
from standards_atlas.application.schema import require_supported_schema

SOURCE_FINGERPRINT_CONTRACT = "assertion-review-source-v1"
SNAPSHOT_FINGERPRINT_CONTRACT = "assertion-review-snapshot-v1"


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Reject overwritten keys, including collisions introduced by YAML merges."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        pairs = []
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError("audit mappings require string keys")
            pairs.append((key, self.construct_object(value_node, deep=deep)))
        return _unique_mapping(pairs)


def _unique_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate mapping key: {key!r}")
        result[key] = value
    return result


def canonical_json_bytes(payload: object) -> bytes:
    """UTF-8 JSON, sorted mapping keys, ordered lists, no NaN or normalization."""
    try:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("audit payload must be finite, acyclic JSON-compatible data") from exc


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_mapping_bytes(raw: bytes, *, json_format: bool = False) -> dict[str, Any]:
    """Parse once without silently replacing duplicate YAML/JSON mapping keys."""
    try:
        text = raw.decode("utf-8")
        payload = (
            json.loads(text, object_pairs_hook=_unique_mapping)
            if json_format
            else yaml.load(text, Loader=_UniqueKeySafeLoader)
        )
    except (UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise ValueError(f"invalid UTF-8 review/mapping input: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("expected mapping in assertion artifact")
    canonical_json_bytes(payload)
    return payload


def review_case_source_sha256(case: AssertionReviewCase) -> str:
    """Bind the frozen review source, not the historical rendered model input.

    The entire embedded context is retained, including headings and list order.
    Expected knowledge, proposal, review status and output metadata are excluded.
    """
    return canonical_sha256(
        {
            "contract": SOURCE_FINGERPRINT_CONTRACT,
            "document_key": case.document_key,
            "clause_id": case.clause_id,
            "reference": case.reference,
            "canonical_reference": case.canonical_reference,
            "text": case.text,
            "text_sha256": case.text_sha256,
            "context": case.context,
        }
    )


@dataclass(frozen=True)
class AssertionReviewAudit:
    """Validated original bytes; mutable parsed models are returned as fresh copies.

    Construction rejects incomplete reviews. The editable pilot loader remains
    available separately for review preparation and annotation.
    """

    original_bytes: bytes = field(repr=False)
    json_format: bool = field(default=False, repr=False)
    audit_sha256: str = field(init=False)
    _payload_json: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        payload = load_mapping_bytes(self.original_bytes, json_format=self.json_format)
        require_supported_schema("assertion-review-pilot", payload.get("schema_version"))
        review = AssertionReviewPilot.model_validate(payload)
        pending = [
            case.clause_id
            for case in review.cases
            if case.review_status is not AssertionReviewStatus.REVIEWED or case.expected is None
        ]
        if pending:
            raise ValueError(f"assertion review audit contains pending cases: {pending!r}")
        object.__setattr__(self, "audit_sha256", hashlib.sha256(self.original_bytes).hexdigest())
        object.__setattr__(self, "_payload_json", canonical_json_bytes(payload))

    @property
    def review(self) -> AssertionReviewPilot:
        return AssertionReviewPilot.model_validate_json(self._payload_json)

    def snapshot_sha256(self, document_key: str, clause_id: str) -> str | None:
        """Hash the actual embedded mapping, not a default-filled model dump.

        proposal_sha256 inside that mapping is only a historical declaration for
        the full document proposal; its original artifact is not available here.
        """
        for case in json.loads(self._payload_json)["cases"]:
            if (case["document_key"], case["clause_id"]) == (document_key, clause_id):
                snapshot = case.get("proposal")
                return canonical_sha256(snapshot) if snapshot is not None else None
        raise ValueError(f"unknown audit case: {(document_key, clause_id)!r}")
