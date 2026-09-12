"""Source pilot and Process sentinels are independent of model-format acceptance."""

import copy
import json
from dataclasses import asdict

import pytest
import test_partial_cascade as cascade_fixture
from test_partial_observations import RESOURCES, config, example
from test_partial_proposals import FakeGateway
from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.partial_audit import (
    audit_partial_experiment,
)
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_proposals import (
    load_partial_inputs,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialTaskResources,
    prepare_partial_request,
)
from standards_atlas.application.semantic_qualification.semantic_readiness import (
    evaluate_semantic_readiness,
)
from standards_atlas.application.semantic_qualification.taxonomy_pilot import (
    build_taxonomy_pilot,
    synthetic_pilot,
)
from standards_atlas.cli import app


def build(tmp_path, **options):
    return build_taxonomy_pilot(
        output_directory=tmp_path / "pilot",
        resources=RESOURCES,
        synthetic_smoke=True,
        dataset_version="1",
        **options,
    )


def test_synthetic_pilot_has_verified_fixed_and_conflicting_controls(tmp_path):
    result = build(tmp_path)
    assert result["selected_count"] == 12
    assert result["decision_plan_summary"]["fixed_attribute_count"] == 3
    assert result["decision_plan_summary"]["requested_attribute_count"] == 105
    assert result["ready_to_test_fixed_attributes"]
    assert result["fixture_authority_constructed"]
    assert not result["source_authority_modified"]
    assert not result["production_benchmark"]
    assert result["new_rule_qualifications"] == []
    data = json.loads((tmp_path / "pilot/dataset.json").read_bytes())
    checks = json.loads((tmp_path / "pilot/readiness-checks.json").read_bytes())
    assert all(e["expected"] == {} and e["tags"] == [] for e in data["examples"])
    plans = {c["example_id"]: c["plan"] for c in result["cases"]}
    for check in checks["cases"]:
        if "expected_primary_state" in check:
            primary = plans[check["example_id"]]["attributes"]["primary_function"]
            assert primary["state"] == check["expected_primary_state"]
    assert "pending" in (tmp_path / "pilot/source-review.csv").read_text()


def test_source_pilot_never_retroactively_confirms_legacy_values(tmp_path):
    dataset = tmp_path / "source.json"
    inputs = [asdict(example("legacy1")), asdict(example("legacy2", heading="Requirements"))]
    dataset.write_text(json.dumps({"version": "1", "examples": inputs}))
    before = dataset.read_bytes()
    result = build_taxonomy_pilot(
        output_directory=tmp_path / "pilot", resources=RESOURCES, dataset=dataset
    )
    assert not result["ready_to_test_fixed_attributes"]
    assert not result["fixture_authority_constructed"]
    assert result["decision_plan_summary"]["source_origins"] == {"legacy-context": 2}
    stored = json.loads((tmp_path / "pilot/dataset.json").read_bytes())
    actual = {e["id"]: e["input"] for e in stored["examples"]}
    assert actual == {e["id"]: e["input"] for e in inputs}
    assert dataset.read_bytes() == before


def test_current_confirmed_dataset_keeps_exact_source_authority(tmp_path):
    dataset = tmp_path / "source.json"
    data = {
        "version": "1",
        "examples": [asdict(example("confirmed", confirmed=True)), asdict(example("legacy"))],
    }
    dataset.write_text(json.dumps(data))
    result = build_taxonomy_pilot(
        output_directory=tmp_path / "pilot", resources=RESOURCES, dataset=dataset
    )
    assert result["decision_plan_summary"]["fixed_attribute_count"] == 1
    stored = json.loads((tmp_path / "pilot/dataset.json").read_bytes())
    assert [e["input"] for e in stored["examples"]] == [e["input"] for e in data["examples"]]


def test_fixture_expectations_do_not_enter_prompts(tmp_path):
    build(tmp_path)
    source = load_partial_inputs(dataset=tmp_path / "pilot/dataset.json")
    cfg = config(prompt_version="taxonomy-partial-v4")
    resources = PartialTaskResources.load(RESOURCES, cfg)
    for item in source.examples:
        request = prepare_partial_request(cfg, item.id, item.input, resources)
        assert item.expected == {}
        assert "process_check" not in request.request.user_prompt
        assert "expected_primary_state" not in request.request.user_prompt
        assert "fixture:taxonomy-readiness-v1" not in request.request.user_prompt


def test_fixture_run_is_not_reported_as_production_benchmark(tmp_path):
    source, _ = synthetic_pilot(RESOURCES, dataset_version="1")
    item = source.examples[0]
    manifest = cascade_fixture.matrix()
    changes = {
        m.id: {"primary_function": "definition", "statement_functions": ["definition"]}
        for m in manifest.models
    }
    gateways = cascade_fixture.Gateways(manifest, changes=changes)
    result = run_partial_cascade(
        manifest=manifest,
        examples=(item,),
        resources=RESOURCES,
        output_directory=tmp_path / "run",
        gateway_context=gateways.context,
        execute=True,
        prompt_version="taxonomy-partial-v4",
        require_taxonomy_decisions=True,
    )
    assert result["metrics"]["completed_clause_count"] == 1
    assert result["metrics"]["synthetic_fixture_sources"]
    assert not result["metrics"]["benchmark_eligible"]
    assert all(len(r.output_schema["required"]) == 8 for r in gateways.requests)
    cascade_fixture.verify(tmp_path / "run")


@pytest.mark.parametrize("limit", [1, 3, 5, 12, 24])
def test_pilot_limit_is_stable_and_checks_match_selection(tmp_path, limit):
    first = build(tmp_path, limit=limit)
    second = build_taxonomy_pilot(
        output_directory=tmp_path / "second",
        resources=RESOURCES,
        synthetic_smoke=True,
        dataset_version="1",
        limit=limit,
    )
    assert first == second
    cases = json.loads((tmp_path / "pilot/readiness-checks.json").read_bytes())["cases"]
    assert {c["example_id"] for c in cases} == {c["example_id"] for c in first["cases"]}
    assert first["selected_count"] == min(limit, 12)


@pytest.mark.parametrize("mode", ["mixed", "overwrite", "invalid_limit", "no_source"])
def test_pilot_rejects_invalid_modes(tmp_path, mode):
    options = {"synthetic_smoke": True}
    if mode == "mixed":
        options["dataset"] = tmp_path / "input.json"
    elif mode == "overwrite":
        (tmp_path / "pilot").mkdir()
    elif mode == "invalid_limit":
        options["limit"] = 0
    else:
        options["synthetic_smoke"] = False
    with pytest.raises(ValueError):
        build_taxonomy_pilot(output_directory=tmp_path / "pilot", resources=RESOURCES, **options)


def audited_pilot(tmp_path):
    build(tmp_path)
    source = load_partial_inputs(dataset=tmp_path / "pilot/dataset.json")
    cfg = config(prompt_version="taxonomy-partial-v4")
    checks = json.loads((tmp_path / "pilot/readiness-checks.json").read_bytes())
    by_id = {c["example_id"]: c for c in checks["cases"]}
    replies = []
    task = PartialTaskResources.load(RESOURCES, cfg)
    for item in source.examples:
        check = by_id[item.id]
        process = check.get("process_check", {}).get("must_include", [])
        values = {
            "primary_function": "definition",
            "statement_functions": ["definition"],
            "primary_knowledge_kind": "concept",
            "knowledge_kinds": ["concept"],
            "primary_process_function": process[0] if process else None,
            "process_functions": process,
            "applicability_present": False,
            "role_semantics_present": False,
            "role_relations": [],
        }
        plan = prepare_partial_request(cfg, item.id, item.input, task).plan
        replies.append({k: values[k] for k in plan.requested_attributes})
    gateway = FakeGateway(replies)
    run_partial_proposals(
        cfg,
        resources=RESOURCES,
        output_directory=tmp_path / "experiment",
        examples=source.examples,
        execute=True,
        gateway_factory=lambda: gateway,
    )
    audit = audit_partial_experiment(
        experiment=tmp_path / "experiment",
        output_directory=tmp_path / "audit",
        resources=RESOURCES,
        dataset=tmp_path / "pilot/dataset.json",
    )
    return audit, checks


def evaluate(tmp_path, audit, checks):
    audit_path, checks_path = tmp_path / "audit.json", tmp_path / "checks.json"
    audit_path.write_text(json.dumps(audit))
    checks_path.write_text(json.dumps(checks))
    return evaluate_semantic_readiness(
        audit=audit_path, checks=checks_path, output_directory=tmp_path / "evaluation"
    )


def test_source_bound_sentinels_detect_semantic_null_regression(tmp_path):
    audit, checks = audited_pilot(tmp_path)
    altered = copy.deepcopy(audit)
    for case in altered["cases"]:
        values = case["response_validation"]["response_values"]
        values["primary_process_function"] = None
        values["process_functions"] = []
    result = evaluate(tmp_path, altered, checks)
    assert not result["all_checks_passed"]
    assert result["status_counts"]["failed"] == 6
    assert result["grouped_contract_valid_count"] == 12
    assert not result["qualification_passed"]
    assert result["model_calls"] == 0


def test_positive_and_negative_sentinels_are_not_global_rule_qualification(tmp_path):
    audit, checks = audited_pilot(tmp_path)
    result = evaluate(tmp_path, audit, checks)
    assert result["all_checks_passed"]
    assert result["status_counts"] == {"passed": 12}
    assert not result["qualification_passed"]
    assert not result["acceptance_changed"]


@pytest.mark.parametrize("mode", ["missing", "unrequested", "invalid", "unverified"])
def test_missing_or_unvalidated_process_is_not_a_negative_answer(tmp_path, mode):
    audit, checks = audited_pilot(tmp_path)
    case = next(c for c in audit["cases"] if c["example_id"] == "pilot-technique-activity")
    if mode == "missing":
        audit["cases"].remove(case)
    elif mode == "unrequested":
        case["response_validation"]["requested_attributes"].remove("process_functions")
    elif mode == "invalid":
        case["response_validation"]["issues"] = [
            {"attributes": ["process_functions"], "code": "invalid"}
        ]
    else:
        case["plan_status"] = "stored_only"
    result = evaluate(tmp_path, audit, checks)
    row = next(c for c in result["cases"] if c["example_id"] == "pilot-technique-activity")
    assert row["status"] == "unavailable"
    assert not result["all_checks_passed"]


@pytest.mark.parametrize("mode", ["hash", "document", "duplicate", "contradictory"])
def test_readiness_rejects_wrong_source_or_ambiguous_suite(tmp_path, mode):
    audit, checks = audited_pilot(tmp_path)
    item = next(c for c in checks["cases"] if c["example_id"] == "pilot-technique-activity")
    if mode == "hash":
        item["content_hash"] = "sha256:" + "0" * 64
    elif mode == "document":
        item["document_key"] = "wrong"
    elif mode == "duplicate":
        checks["cases"].append(checks["cases"][0])
    else:
        item["process_check"]["must_be_empty"] = True
    with pytest.raises(ValueError):
        evaluate(tmp_path, audit, checks)
    assert not (tmp_path / "evaluation").exists()


def test_cli_pilot_and_evaluator_are_model_free(tmp_path):
    result = CliRunner().invoke(
        app,
        ["evaluation", "taxonomy-pilot", "--synthetic-smoke", "--output", str(tmp_path / "pilot")],
    )
    assert result.exit_code == 0, result.output
    assert "Fixed attributes: 3" in result.output
    for command in ("taxonomy-pilot", "semantic-readiness-evaluate"):
        result = CliRunner().invoke(app, ["evaluation", command, "--help"])
        assert result.exit_code == 0


def test_resource_sentinels_pin_positive_and_negative_original_source_hashes():
    from standards_atlas.application.semantic_qualification.annotations import (
        normalized_content_hash,
    )

    path = RESOURCES / "qualification/process-functions-sentinels-v1/checks.json"
    suite = json.loads(path.read_bytes())
    assert len(suite["cases"]) == 5
    assert any(c["process_check"].get("must_be_empty") for c in suite["cases"])
    for case in suite["cases"]:
        assert normalized_content_hash(case["source_text"]) == case["content_hash"]
