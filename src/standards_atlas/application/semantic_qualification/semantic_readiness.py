"""Small source-bound regression checks; not a semantic Golden qualification."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from standards_atlas.application.schema import require_current_payload, require_supported_schema
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash


def _value_key(value: Any) -> str:
    # These attribute collections are semantic sets; keep JSON scalar types distinct.
    if isinstance(value, list):
        return json.dumps(sorted(_value_key(item) for item in value))
    return json.dumps(value, sort_keys=True, allow_nan=False)


def evaluate_semantic_readiness(
    *, audit: Path, checks: Path, output_directory: Path
) -> dict[str, Any]:
    """Compare explicit process/plan sentinels with an audit, without repairing values."""
    output = output_directory.resolve()
    if output.exists() or any(output == p.resolve() for p in (audit, checks)):
        raise ValueError("readiness output must be new and separate from inputs")
    for protected in (
        "data",
        "src/standards_atlas/resources",
        ".atlas/data/documents",
        ".atlas/data/knowledge-evidence",
    ):
        if output.is_relative_to(Path(protected).resolve()):
            raise ValueError("readiness output must be separate from canonical/public data")
    audit_bytes, checks_bytes = audit.read_bytes(), checks.read_bytes()
    evidence, suite = json.loads(audit_bytes), json.loads(checks_bytes)
    if evidence.get("kind") != "partial-experiment-audit":
        raise ValueError("readiness needs a partial-audit result, not only a run summary")
    require_supported_schema("semantic-readiness-checks", suite.get("schema_version"))
    if suite.get("kind") != "semantic-readiness-checks":
        raise ValueError("unsupported semantic readiness checks")
    rows = evidence["cases"]
    by_id = {c["example_id"]: c for c in rows}
    if len(by_id) != len(rows) or not suite["cases"]:
        raise ValueError("readiness requires unique evidence and nonempty checks")
    check_ids = [c["example_id"] for c in suite["cases"]]
    if len(set(check_ids)) != len(check_ids):
        raise ValueError("duplicate readiness check identity")
    cases = []
    for check in suite["cases"]:
        result = {"example_id": check["example_id"], "status": "unavailable", "reasons": []}
        case = by_id.get(check["example_id"])
        if case is None:
            result["reasons"].append("case_missing_from_audit")
            cases.append(result)
            continue
        clause = case["clause"]
        if (
            clause["document_key"] != check["document_key"]
            or clause["content_hash"] != check["content_hash"]
        ):
            raise ValueError("readiness source identity/content hash mismatch")
        if (
            "source_text" in check
            and normalized_content_hash(check["source_text"]) != check["content_hash"]
        ):
            raise ValueError("readiness source text differs from pinned content hash")
        if case.get("integrity_errors") or case.get("plan_status") != "source_verified":
            result["reasons"].append("source_or_artifact_not_verified")
            cases.append(result)
            continue
        validation = case.get("response_validation") or {}
        result["grouped_contract_valid"] = validation.get("valid")
        result["status"] = "passed"
        if "expected_primary_state" in check:
            decisions = (case.get("decision_plan") or {}).get("decisions", [])
            primary = next((d for d in decisions if d["attribute"] == "primary_function"), None)
            if primary is None:
                result["status"] = "unavailable"
                result["reasons"].append("source_plan_unavailable")
            elif primary["state"] != check["expected_primary_state"] or (
                "expected_primary_value" in check
                and primary["value"] != check["expected_primary_value"]
            ):
                result["status"] = "failed"
                result["reasons"].append("unexpected_source_primary_decision")
        if "process_check" in check:
            expected = check["process_check"]
            if not (expected.get("must_include") or expected.get("must_be_empty") is True):
                raise ValueError("process check must specify required labels or an empty set")
            if expected.get("must_include") and expected.get("must_be_empty"):
                raise ValueError("contradictory process expectation")
            values = validation.get("response_values", {})
            requested = validation.get("requested_attributes", [])
            actual = values.get("process_functions")
            result["process_value"] = actual
            result["knowledge_primary"] = values.get("primary_knowledge_kind")
            invalid_process = any(
                set(i["attributes"]) & {"primary_process_function", "process_functions"}
                for i in validation.get("issues", [])
            )
            if (
                "process_functions" not in requested
                or not isinstance(actual, list)
                or invalid_process
            ):
                result["status"] = "unavailable"
                result["reasons"].append("process_value_missing_or_invalid")
            else:
                if expected.get("must_be_empty") and actual:
                    result["status"] = "failed"
                    result["reasons"].append("unexpected_process_semantics")
                missing = set(expected.get("must_include", [])) - set(actual)
                if missing:
                    result["status"] = "failed"
                    result["reasons"].append("missing_process_labels:" + ",".join(sorted(missing)))
        if "attribute_checks" in check:
            from standards_atlas.application.semantic_qualification.partial_observations import (
                PARTIAL_ATTRIBUTES,
            )

            predicates = check["attribute_checks"]
            if not isinstance(predicates, dict) or not predicates:
                raise ValueError("attribute checks must be a nonempty object")
            inspected = {}
            for attribute, expectation in predicates.items():
                if attribute not in PARTIAL_ATTRIBUTES or not isinstance(expectation, dict):
                    raise ValueError("unsupported semantic attribute check")
                if set(expectation) != {"equals"}:
                    raise ValueError("attribute checks require one explicit equals value")
                actual = validation.get("response_values", {}).get(attribute)
                invalid = any(
                    attribute in issue["attributes"] for issue in validation.get("issues", [])
                )
                if (
                    attribute not in validation.get("requested_attributes", [])
                    or attribute not in validation.get("response_values", {})
                    or invalid
                ):
                    status = "unavailable"
                else:
                    # JSON identity preserves false != 0 and null != missing.
                    status = (
                        "passed"
                        if _value_key(actual) == _value_key(expectation["equals"])
                        else "failed"
                    )
                inspected[attribute] = {
                    "status": status,
                    "value": actual,
                    "expected": expectation["equals"],
                }
                if status == "failed":
                    result["status"] = "failed"
                    result["reasons"].append("unexpected_attribute:" + attribute)
                elif status == "unavailable" and result["status"] != "failed":
                    result["status"] = "unavailable"
                    result["reasons"].append("attribute_missing_or_invalid:" + attribute)
            result["attribute_checks"] = inspected
        if not any(
            key in check for key in ("expected_primary_state", "process_check", "attribute_checks")
        ):
            raise ValueError("readiness case contains no checkable expectation")
        cases.append(result)
    report = {
        "schema_version": "1.0",
        "kind": "semantic-readiness-evaluation",
        "suite_id": suite["id"],
        "suite_version": suite["version"],
        "input_fingerprints": {
            "audit": hashlib.sha256(audit_bytes).hexdigest(),
            "checks": hashlib.sha256(checks_bytes).hexdigest(),
        },
        "suite_qualification_status": suite["qualification_status"],
        "selected_check_count": len(cases),
        "status_counts": dict(Counter(c["status"] for c in cases)),
        "all_checks_passed": all(c["status"] == "passed" for c in cases),
        "grouped_contract_valid_count": sum(c.get("grouped_contract_valid") is True for c in cases),
        "process_checks_do_not_imply_whole_observation_acceptance": True,
        "qualification_passed": False,
        "model_calls": 0,
        "acceptance_changed": False,
        "evidence_scope": "provided source-verified audit; original runtime not reattested",
        "cases": cases,
    }
    require_current_payload("semantic-readiness-evaluation", report)
    output.mkdir(parents=True)
    (output / "semantic-readiness.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "semantic-readiness.md").write_text(
        "# Semantic readiness checks\n\n"
        f"Suite: `{suite['id']}`; status: `{suite['qualification_status']}`.\n\n"
        f"Check results: {report['status_counts']}.\n\n"
        "These are scoped regression sentinels, not full semantic gold. Passing does not "
        "release a taxonomy rule, accept an invalid grouped response or certify the cascade.\n",
        encoding="utf-8",
    )
    return report
