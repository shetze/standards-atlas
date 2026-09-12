"""Original-value diagnostics, versioned prompt improvements and immutable plan audits."""

import copy
import hashlib
import json
import zipfile

import pytest
import test_partial_observations as fixtures
import test_partial_proposals as runs
from typer.testing import CliRunner

from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.semantic_qualification.partial_audit import (
    audit_partial_experiment,
)
from standards_atlas.application.semantic_qualification.partial_diagnostics import (
    describe_partial_plan,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
    PartialResponseValidationError,
    inspect_partial_response,
    validate_partial_response,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.cli import app


def valid_values():
    return {
        "primary_function": "requirement",
        "statement_functions": ["requirement"],
        "primary_knowledge_kind": "process",
        "knowledge_kinds": ["process"],
        "primary_process_function": "activity",
        "process_functions": ["activity"],
        "applicability_present": False,
        "role_semantics_present": False,
        "role_relations": [],
    }


def conflicting_values():
    return {
        **valid_values(),
        "statement_functions": ["description"],
        "knowledge_kinds": ["artifact", "artifact"],
        "process_functions": ["output"],
        "role_relations": [
            {"actor": "reviewer", "relation_class": "performance", "target": "review"}
        ],
    }


def stored_run(tmp_path, *, value=None, confirmed=False):
    item = fixtures.example(confirmed=confirmed)
    cfg = fixtures.config(prompt_version="taxonomy-partial-v3")
    value = valid_values() if value is None else value
    if confirmed:
        value = {k: v for k, v in value.items() if k != "primary_function"}
        value["statement_functions"] = ["definition"]
    report, gateway = runs.experiment(
        tmp_path,
        cfg=cfg,
        items=(item,),
        gateway=runs.FakeGateway([value]),
    )
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"examples": [{"id": item.id, "input": item.input}]}))
    return report, gateway, dataset


def audit(tmp_path, *, experiment=None, dataset=None, output="audit"):
    return audit_partial_experiment(
        experiment=experiment or tmp_path / "out",
        output_directory=tmp_path / output,
        dataset=dataset,
        resources=fixtures.RESOURCES,
    )


def digest_tree(path):
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*")
        if p.is_file()
    }


def test_all_pairs_and_schema_errors_are_reported_without_mutation():
    prepared = fixtures.prepared()
    value = conflicting_values()
    before = copy.deepcopy(value)
    issues = inspect_partial_response(value, prepared.request.output_schema, prepared.plan)
    assert value == before
    assert [i.code for i in issues] == [
        "schema.uniqueItems",
        "primary_not_in_set",
        "primary_not_in_set",
        "primary_not_in_set",
        "negative_presence_with_relations",
    ]
    assert issues[1].observed_values == {
        "primary_function": "requirement",
        "statement_functions": ["description"],
    }
    with pytest.raises(PartialResponseValidationError) as exc:
        validate_partial_response(value, prepared.request.output_schema, prepared.plan)
    assert len(exc.value.issues) == 5
    assert "primary_function must belong" in str(exc.value)
    assert "primary_process_function must belong" in str(exc.value)


@pytest.mark.parametrize("value", [None, 42, [], "no JSON object"])
def test_invalid_root_is_a_schema_error_not_a_crash(value):
    prepared = fixtures.prepared()
    issues = inspect_partial_response(value, prepared.request.output_schema, prepared.plan)
    assert issues and issues[0].code == "schema.type"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("statement_functions", None),
        ("knowledge_kinds", True),
        ("process_functions", "activity"),
        ("role_relations", {}),
    ],
)
def test_malformed_field_does_not_hide_other_pairs(field, bad):
    prepared = fixtures.prepared()
    value = {**conflicting_values(), field: bad}
    issues = inspect_partial_response(value, prepared.request.output_schema, prepared.plan)
    assert any(i.code == "schema.type" and field in i.attributes for i in issues)
    assert sum(i.code == "primary_not_in_set" for i in issues) >= 2


@pytest.mark.parametrize(
    "primary,collection",
    [
        ("primary_function", "statement_functions"),
        ("primary_knowledge_kind", "knowledge_kinds"),
        ("primary_process_function", "process_functions"),
    ],
)
@pytest.mark.parametrize("null_primary", [False, True])
def test_correct_members_and_absent_primary_remain_accepted(primary, collection, null_primary):
    prepared = fixtures.prepared()
    value = valid_values()
    if null_primary:
        value[primary], value[collection] = None, []
    assert validate_partial_response(value, prepared.request.output_schema, prepared.plan) == value


def test_source_constraint_is_not_misreported_as_model_value():
    prepared = fixtures.prepared(item=fixtures.example(confirmed=True))
    value = {k: v for k, v in valid_values().items() if k != "primary_function"}
    issues = inspect_partial_response(value, prepared.request.output_schema, prepared.plan)
    issue = next(i for i in issues if i.code == "primary_not_in_set")
    assert issue.observed_values == {"statement_functions": ["requirement"]}
    assert issue.constraint_values == {"primary_function": "definition"}


def test_unrequested_companion_is_not_invented():
    prepared = fixtures.prepared(cfg=fixtures.config(selected_attributes=("primary_function",)))
    value = {"primary_function": "definition"}
    assert validate_partial_response(value, prepared.request.output_schema, prepared.plan) == value


@pytest.mark.parametrize(
    "prompt", ["taxonomy-partial-v1", "taxonomy-partial-v2", "taxonomy-partial-v3"]
)
def test_prompt_schema_parity_and_versioned_identity(prompt):
    config = fixtures.config(prompt_version=prompt)
    prepared = fixtures.prepared(cfg=config)
    base = fixtures.prepared()
    assert prepared.request.output_schema == base.request.output_schema
    assert prepared.request.prompt_version == prompt
    if prompt != "taxonomy-partial-v1":
        assert prepared.fingerprint != base.fingerprint
        assert prepared.plan.schema_version == "1.1"
    if prompt == "taxonomy-partial-v3":
        assert "NOT a list of secondary members" in prepared.request.system_prompt
        assert '"primary_function":"requirement","statement_functions":["requirement"]' in (
            prepared.request.system_prompt
        )


def test_v3_carried_primary_retains_sparse_set_question():
    cfg = fixtures.config(prompt_version="taxonomy-partial-v3")
    item = fixtures.example()
    prepared = prepare_partial_request(
        cfg,
        item.id,
        item.input,
        PartialTaskResources.load(fixtures.RESOURCES, cfg),
        accepted_attributes={"primary_function": "definition"},
        accepted_state_sha256="a" * 64,
    )
    assert "primary_function" not in prepared.plan.requested_attributes
    assert "statement_functions" in prepared.plan.requested_attributes
    assert prepared.plan.fixed_primary_constraints == {"primary_function": "definition"}


@pytest.mark.parametrize("confirmed", [False, True])
def test_decision_diagnostics_distinguish_hints_from_fixes(confirmed):
    prepared = fixtures.prepared(item=fixtures.example(confirmed=confirmed))
    description = describe_partial_plan(prepared.plan)
    assert description["fixed_attribute_count"] == int(confirmed)
    assert description["requested_attribute_count"] == 9 - int(confirmed)
    decision = description["attributes"]["primary_function"]
    assert decision["state"] == ("fixed" if confirmed else "hint")
    assert decision["fix_blockers"] == ([] if confirmed else ["source_not_confirmed"])


def test_live_report_contains_all_original_conflicts_without_salvage(tmp_path):
    report, gateway, _ = stored_run(tmp_path, value=conflicting_values())
    case = report["cases"][0]
    assert report["status_counts"] == {"failed": 1}
    assert report["logical_model_observation_count"] == 0
    assert len(case["response_validation"]["issues"]) == 5
    assert case["response_validation"]["response_values"] == conflicting_values()
    obs = PartialObservation.model_validate_json(
        (tmp_path / "out" / case["case_directory"] / "partial-observation.json").read_text()
    )
    assert not obs.values and not obs.model_evidence()
    assert len(gateway.requests) == 1


def test_audit_original_response_and_exact_request_plan_is_immutable(tmp_path):
    _, gateway, dataset = stored_run(tmp_path, value=conflicting_values())
    before = digest_tree(tmp_path / "out")
    result = audit(tmp_path, dataset=dataset)
    assert result["response_status_counts"] == {"inspected": 1}
    assert result["plan_status_counts"] == {"source_verified": 1}
    assert result["cases"][0]["request_check"] == "source_regenerated"
    assert result["response_issue_counts"]["primary_not_in_set"] == 3
    assert result["integrity_error_case_count"] == 0
    assert digest_tree(tmp_path / "out") == before
    assert len(gateway.requests) == 1
    second = audit(tmp_path, dataset=dataset, output="audit2")
    assert result == second
    assert (tmp_path / "audit/partial-audit.json").read_bytes() == (
        tmp_path / "audit2/partial-audit.json"
    ).read_bytes()


def test_report_only_is_missing_evidence_not_a_success_or_a_guessed_response(tmp_path):
    report, _, dataset = stored_run(tmp_path, value=conflicting_values())
    isolated = tmp_path / "summary"
    isolated.mkdir()
    (isolated / "partial-run-report.json").write_text(json.dumps(report))
    result = audit(tmp_path, experiment=isolated, dataset=dataset)
    assert result["plan_status_counts"] == {"reconstructed_from_source": 1}
    assert result["response_status_counts"] == {"unavailable": 1}
    assert result["response_issue_counts"] == {}
    assert "response_validation" not in result["cases"][0]
    assert "response.json" in result["cases"][0]["missing_artifacts"]


def test_report_without_corpus_does_not_make_up_a_decision_plan(tmp_path):
    report, _, _ = stored_run(tmp_path)
    isolated = tmp_path / "summary"
    isolated.mkdir()
    (isolated / "partial-run-report.json").write_text(json.dumps(report))
    result = audit(tmp_path, experiment=isolated)
    assert result["plan_status_counts"] == {"unavailable": 1}
    assert result["decision_plan_summary"]["plan_count"] == 0


@pytest.mark.parametrize("artifact", ["request", "response", "partial-request-plan"])
def test_tampered_artifact_is_not_verified(tmp_path, artifact):
    report, _, dataset = stored_run(tmp_path)
    path = tmp_path / "out" / report["cases"][0]["case_directory"] / f"{artifact}.json"
    payload = json.loads(path.read_text())
    if artifact == "request":
        payload["user_prompt"] += "changed"
    elif artifact == "response":
        payload["value"]["primary_function"] = "definition"
    else:
        payload["decision_plan"]["source_sha256"] = "f" * 64
    path.write_text(json.dumps(payload))
    result = audit(tmp_path, dataset=dataset)
    assert result["integrity_error_case_count"] == 1
    assert result["cases"][0]["response_status"] == "not_verified"


def test_archive_wrapper_audits_same_cases_without_extraction(tmp_path):
    _, _, dataset = stored_run(tmp_path)
    archive = tmp_path / "experiment.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for path in (tmp_path / "out").rglob("*"):
            if path.is_file():
                handle.write(path, "wrapper/" + path.relative_to(tmp_path / "out").as_posix())
    original = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = audit(tmp_path, experiment=archive, dataset=dataset)
    assert result["response_status_counts"] == {"inspected": 1}
    assert result["integrity_error_case_count"] == 0
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original


def test_refuse_duplicate_archive_members(tmp_path):
    report, _, _ = stored_run(tmp_path)
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("partial-run-report.json", json.dumps(report))
        with pytest.warns(UserWarning):
            handle.writestr("partial-run-report.json", json.dumps(report))
    with pytest.raises(ValueError, match="duplicate"):
        audit(tmp_path, experiment=archive)


@pytest.mark.parametrize("target", ["out/audit", "out"])
def test_audit_cannot_write_into_experiment(tmp_path, target):
    _, _, dataset = stored_run(tmp_path)
    with pytest.raises(ValueError):
        audit(tmp_path, dataset=dataset, output=target)


def test_cannot_follow_case_symlink_outside_run(tmp_path):
    report, _, _ = stored_run(tmp_path)
    case = tmp_path / "out" / report["cases"][0]["case_directory"]
    real = case / "response.json"
    outside = tmp_path / "external-response.json"
    real.rename(outside)
    real.symlink_to(outside)
    result = audit(tmp_path)
    assert result["integrity_error_case_count"] == 1
    assert "escapes source" in result["cases"][0]["integrity_errors"][0]


def test_snapshot_with_active_writer_is_refused(tmp_path):
    stored_run(tmp_path)
    (tmp_path / "out/.partial-run.lock").write_text("123")
    with pytest.raises(ValueError, match="active writer"):
        audit(tmp_path)


def test_report_identity_mismatch_isolated_and_no_reconstruction(tmp_path):
    report, _, dataset = stored_run(tmp_path)
    report["cases"][0]["clause"]["content_hash"] = "sha256:" + "e" * 64
    (tmp_path / "out/partial-run-report.json").write_text(json.dumps(report))
    result = audit(tmp_path, dataset=dataset)
    assert result["integrity_error_case_count"] == 1
    assert result["decision_plan_summary"]["plan_count"] == 0


def test_failed_gateway_attempt_keeps_all_checkable_errors_separate(tmp_path):
    item = fixtures.example()
    exc = LlmResponseError("invalid schema", raw_content=json.dumps(conflicting_values()))
    report, gateway = runs.experiment(
        tmp_path,
        cfg=fixtures.config(),
        items=(item,),
        gateway=runs.FakeGateway([exc]),
    )
    result = audit(tmp_path)
    assert report["failed_observation_count"] == 1
    assert result["response_status_counts"] == {"unavailable": 1}
    assert result["failed_attempt_issue_counts"]["primary_not_in_set"] == 3
    assert not result["response_issue_counts"]
    assert len(gateway.requests) == 1


def test_audit_cli_and_prompt_opt_in(tmp_path):
    _, _, dataset = stored_run(tmp_path)
    cli = CliRunner()
    result = cli.invoke(
        app,
        [
            "evaluation",
            "partial-audit",
            "--experiment",
            str(tmp_path / "out"),
            "--dataset",
            str(dataset),
            "--output",
            str(tmp_path / "audit"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Read-only" in result.output
    planning = cli.invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(dataset),
            "--model",
            "small",
            "--prompt",
            "taxonomy-partial-v3",
            "--output",
            str(tmp_path / "planned-v3"),
        ],
    )
    assert planning.exit_code == 0, planning.output
    payload = json.loads(next((tmp_path / "planned-v3/cases").glob("*/request.json")).read_text())
    assert payload["prompt_version"] == "taxonomy-partial-v3"
    assert "NOT a list of secondary members" in payload["system_prompt"]


def test_rules_pending_review_are_not_promoted_for_better_exit_numbers(tmp_path):
    _, _, dataset = stored_run(tmp_path, confirmed=True)
    result = audit(tmp_path, dataset=dataset)
    assert result["rules_eligible_to_fix"] == ["term-definition"]
    assert {"requirement-character", "objective-section", "technique-entry"}.issubset(
        result["pending_rules"]
    )
    assert result["decision_plan_summary"]["fixed_attribute_count"] == 1
    assert result["decision_plan_summary"]["requested_attribute_count"] == 8
    assert result["decision_plan_summary"]["production_early_exit_count"] is None
