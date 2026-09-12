"""Typed, source-bound role/knowledge/applicability sentinels never qualify a profile."""

import json

import pytest

from standards_atlas.application.semantic_qualification.semantic_readiness import (
    evaluate_semantic_readiness,
)


def check(
    tmp_path,
    *,
    attribute="applicability_present",
    value=False,
    expected=False,
    invalid=False,
    requested=True,
    source_verified=True,
    grouped_valid=True,
):
    row = {
        "example_id": "a",
        "clause": {"document_key": "TEST", "content_hash": "sha256:test"},
        "plan_status": "source_verified" if source_verified else "unavailable",
        "response_validation": {
            "valid": grouped_valid,
            "requested_attributes": [attribute] if requested else [],
            "response_values": {attribute: value},
            "issues": [{"attributes": [attribute]}] if invalid else [],
        },
    }
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"kind": "partial-experiment-audit", "cases": [row]}))
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "semantic-readiness-checks",
                "id": "test",
                "version": "1",
                "qualification_status": "synthetic-smoke-not-domain-gold",
                "cases": [
                    {
                        "example_id": "a",
                        "document_key": "TEST",
                        "content_hash": "sha256:test",
                        "attribute_checks": {attribute: {"equals": expected}},
                    }
                ],
            }
        )
    )
    return evaluate_semantic_readiness(
        audit=audit, checks=checks, output_directory=tmp_path / "out"
    )


@pytest.mark.parametrize(
    "attribute,value,expected,status",
    [
        ("applicability_present", False, False, "passed"),
        ("applicability_present", True, False, "failed"),
        ("applicability_present", False, 0, "failed"),
        ("role_semantics_present", False, True, "failed"),
        ("role_semantics_present", True, True, "passed"),
        ("primary_knowledge_kind", "role", "role", "passed"),
        ("primary_knowledge_kind", "technique_or_measure", "role", "failed"),
        ("knowledge_kinds", ["process", "artifact"], ["artifact", "process"], "passed"),
        ("primary_process_function", None, None, "passed"),
    ],
)
def test_per_attribute_readiness_is_explicit_and_typed(
    tmp_path, attribute, value, expected, status
):
    result = check(tmp_path, attribute=attribute, value=value, expected=expected)
    assert result["status_counts"] == {status: 1}
    assert result["qualification_passed"] is False and result["model_calls"] == 0


@pytest.mark.parametrize("option", ["invalid", "requested", "source_verified"])
def test_missing_or_invalid_evidence_is_never_a_pass(tmp_path, option):
    values = {"invalid": False, "requested": True, "source_verified": True}
    values[option] = not values[option]
    assert check(tmp_path, **values)["status_counts"] == {"unavailable": 1}


def test_independent_sentinel_pass_does_not_accept_invalid_observation(tmp_path):
    result = check(tmp_path, grouped_valid=False)
    assert result["status_counts"] == {"passed": 1}
    assert result["grouped_contract_valid_count"] == 0
    assert not result["acceptance_changed"] and not result["qualification_passed"]


def test_unknown_attribute_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsupported semantic attribute"):
        check(tmp_path, attribute="invented")
