"""Slice 5.1: prompt binding, report semantics and immutable cause diagnostics."""

import hashlib
import json
import zipfile

import pytest
import test_partial_cascade as cascade_fixture
import yaml
from test_partial_observations import RESOURCES, config, example, prepared
from typer.testing import CliRunner

from standards_atlas.application.ports.llm_gateway import LlmResponseError
from standards_atlas.application.semantic_qualification.cascade_diagnostics import (
    classify_error,
    describe_mixed_consensus,
    value_shape,
)
from standards_atlas.application.semantic_qualification.partial_cascade import (
    _source_resources,
    partial_config_for_model,
    run_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_cascade_audit import (
    audit_partial_cascade,
)
from standards_atlas.cli import app

PROMPTS = (
    "taxonomy-partial-v2",
    "taxonomy-partial-v3",
    "taxonomy-partial-v3-no-process-null",
    "taxonomy-partial-v4",
)


def execute(
    root,
    prompt="taxonomy-partial-v2",
    *,
    items=None,
    execute=True,
    gateways=None,
    **kwargs,
):
    manifest = cascade_fixture.matrix()
    gateways = gateways or cascade_fixture.Gateways(manifest)
    result = run_partial_cascade(
        manifest=manifest,
        examples=items or (example(),),
        resources=RESOURCES,
        output_directory=root,
        execute=execute,
        gateway_context=gateways.context,
        prompt_version=prompt,
        **kwargs,
    )
    return result, gateways


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("prompt", PROMPTS)
def test_selected_prompt_reaches_requests_resume_verification_and_archive(tmp_path, prompt):
    root = tmp_path / "run"
    result, gateways = execute(root, prompt)
    assert {r.prompt_version for r in gateways.requests} == {prompt}
    assert result["effective_configuration"]["prompt_version"] == prompt
    assert result["run_mode"] == "executed"
    assert result["metrics"]["completion_rate"] == 1
    mixed, _, _ = cascade_fixture.verify(root)
    assert mixed.completed_count == 1
    resumed, _ = execute(root, prompt, gateways=gateways)
    assert resumed["request_timing_current_invocation"]["request_count"] == 0
    assert len(gateways.requests) == 4
    archive = archive_partial_cascade(
        root=root, archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    with zipfile.ZipFile(archive) as z:
        names = [n for n in z.namelist() if n.endswith("qualification-manifest.yaml")]
        assert len(names) == 1
        manifest = yaml.safe_load(z.read(names[0]))
        assert {p["prompt_version"] for p in manifest["prompts"]} == {prompt}
    audit = audit_partial_cascade(
        experiment=archive, resources=RESOURCES, output_directory=tmp_path / "audit"
    )
    assert audit["source_evidence_verified"]
    assert audit["effective_configuration"]["prompt_version"] == prompt


@pytest.mark.parametrize("prompt", PROMPTS[1:])
def test_prompt_change_refuses_existing_run_before_inference_or_mutation(tmp_path, prompt):
    root = tmp_path / "run"
    _, gateways = execute(root, execute=False)
    before = hashes(root)
    with pytest.raises(ValueError, match="identity changed"):
        execute(root, prompt, gateways=gateways)
    assert hashes(root) == before
    assert not gateways.started


@pytest.mark.parametrize("prompt", ["taxonomy-partial-v1", "structure-aware-v10", "unknown"])
def test_invalid_or_constraint_incapable_prompt_rejected_before_writes(tmp_path, prompt):
    root = tmp_path / "run"
    with pytest.raises(ValueError):
        execute(root, prompt)
    assert not root.exists()


def test_run_plan_keeps_its_own_schema_and_v1_point_requests_stay_supported(tmp_path):
    root = tmp_path / "run"
    result, _ = execute(root, execute=False)
    plan = json.loads((root / "partial-cascade-plan.json").read_bytes())
    assert "prompt_version" not in plan
    assert plan["schema_version"] == "1.0"
    assert result["effective_configuration"]["prompt_version"] == "taxonomy-partial-v2"
    assert prepared(cfg=config()).request.prompt_version == "taxonomy-partial-v1"


def test_planned_completion_is_not_measured_zero_and_obsolete_report_is_rejected(tmp_path):
    root = tmp_path / "run"
    result, gateways = execute(root, execute=False)
    assert result["metrics"]["completion_rate"] is None
    assert not result["metrics"]["benchmark_eligible"]
    assert result["metrics"]["completion_profile_eligible"]
    assert result["metrics"]["measurement_status"] == "not_executed"
    mixed, _, _ = cascade_fixture.verify(root)
    assert mixed.metrics["completion_rate"] == 0
    for field in ("run_mode", "effective_configuration"):
        result.pop(field)
    result["schema_version"] = "1.0"
    result["metrics"] = mixed.metrics
    (root / "partial-cascade-report.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Unsupported partial cascade report schema"):
        cascade_fixture.verify(root)
    assert not gateways.started


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_mode", "planned"),
        ("effective_configuration", {"prompt_version": "taxonomy-partial-v4"}),
        ("schema_version", "9.9"),
    ],
)
def test_archive_verifier_rejects_false_prompt_or_measurement_metadata(tmp_path, field, value):
    root = tmp_path / "run"
    execute(root)
    path = root / "partial-cascade-report.json"
    data = json.loads(path.read_bytes())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cascade_fixture.verify(root)


def test_prompt_hash_is_bound_to_selection_and_changed_bytes_fail_archive_read(tmp_path):
    root = tmp_path / "run"
    execute(root, "taxonomy-partial-v3")
    path = root / "partial-cascade-plan.json"
    plan = json.loads(path.read_bytes())
    plan["prompt_version"] = "taxonomy-partial-v4"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="supported versions"):
        cascade_fixture.verify(root)


def test_taxonomy_guard_rejects_legacy_inputs_before_any_write_or_gateway(tmp_path):
    root = tmp_path / "run"
    with pytest.raises(ValueError, match="no qualified fixed"):
        execute(root, require_taxonomy_decisions=True)
    assert not root.exists()


def test_confirmed_source_primary_skips_question_but_not_unasked_set(tmp_path):
    manifest = cascade_fixture.matrix()
    changes = {
        m.id: {"primary_function": "definition", "statement_functions": ["definition"]}
        for m in manifest.models
    }
    gateways = cascade_fixture.Gateways(manifest, changes=changes)
    result, gateways = execute(
        tmp_path / "run",
        items=(example(confirmed=True),),
        gateways=gateways,
        require_taxonomy_decisions=True,
    )
    assert len(gateways.requests) == 4
    assert all("primary_function" not in r.output_schema["required"] for r in gateways.requests)
    assert all("statement_functions" in r.output_schema["required"] for r in gateways.requests)
    assert result["diagnostics"]["source_plans"]["fixed_attribute_count"] == 1
    mixed, _, _ = cascade_fixture.verify(tmp_path / "run")
    assert mixed.clauses[0].decision("primary_function").source == "deterministic"
    assert mixed.clauses[0].decision("primary_function").observed_model_count == 0


def test_all_stage_requests_use_new_prompt_even_with_carried_values(tmp_path):
    manifest = cascade_fixture.matrix()
    changes = {m.id: {"role_semantics_present": i % 2 == 0} for i, m in enumerate(manifest.models)}
    gateways = cascade_fixture.Gateways(manifest, changes=changes)
    result, gateways = execute(tmp_path / "run", "taxonomy-partial-v4", gateways=gateways)
    assert len(result["stages"]) == 3
    assert {r.prompt_version for r in gateways.requests} == {"taxonomy-partial-v4"}
    assert any(len(r.output_schema["required"]) < 9 for r in gateways.requests[4:])
    cascade_fixture.verify(tmp_path / "run")


def test_diagnostics_distinguish_post_gateway_rejection_and_values(tmp_path):
    manifest = cascade_fixture.matrix()
    first = manifest.execution.stages[0].models[0]
    gateways = cascade_fixture.Gateways(manifest, changes={first: {"statement_functions": []}})
    result, _ = execute(tmp_path / "run", gateways=gateways)
    model = result["stages"][0]["diagnostics"]["models"][0]
    assert model["logical_status_counts"] == {"failed": 1}
    assert model["failed_with_saved_response"] == 1
    assert model["recorded_gateway_error_count"] == 0
    assert model["response_issue_counts"] == {"primary_not_in_set": 1}
    assert model["attempt_timing_count_matches"]
    attrs = result["diagnostics"]["attributes"]
    assert attrs["role_relations"]["accepted_value_shapes"] == {"empty_set": 1}
    assert attrs["role_semantics_present"]["accepted_value_shapes"] == {"false": 1}


def test_retry_attempts_explained_without_counting_extra_votes(tmp_path):
    manifest = cascade_fixture.matrix()
    first = manifest.execution.stages[0].models[0]
    gateways = cascade_fixture.Gateways(manifest)
    gateway = gateways.gateways[first]
    original = gateway.generate_structured
    state = {"calls": 0}

    def transient(request):
        state["calls"] += 1
        if state["calls"] == 1:
            raise LlmResponseError("truncated output", finish_reason="length")
        return original(request)

    gateway.generate_structured = transient
    result, _ = execute(tmp_path / "run", gateways=gateways)
    model = result["stages"][0]["diagnostics"]["models"][0]
    assert model["recorded_attempt_count"] == 2
    assert model["additional_attempts_within_executions"] == 1
    assert model["logical_observation_count"] == 1
    assert model["gateway_error_count_matches"]
    audit = audit_partial_cascade(
        experiment=tmp_path / "run", output_directory=tmp_path / "audit", resources=RESOURCES
    )
    work = audit["physical_work"]
    assert work["cascade_total"]["request_count"] == 5
    assert work["nominal_stage_model_clause_combinations"] == 4
    assert work["active_additional_attempts_within_executions"] == 1
    assert work["attempt_counts_reconciled"]


def test_offline_audit_reconstructs_counts_and_does_not_change_sources(tmp_path):
    root = tmp_path / "run"
    execute(root)
    before = hashes(root)
    one = audit_partial_cascade(
        experiment=root, output_directory=tmp_path / "audit1", resources=RESOURCES
    )
    two = audit_partial_cascade(
        experiment=root, output_directory=tmp_path / "audit2", resources=RESOURCES
    )
    assert one == two
    assert hashes(root) == before
    assert one["gateway_request_count"] == 0
    assert one["physical_work"]["source_summary_timing_matches"]


@pytest.mark.parametrize("mode", ["missing", "locked", "unsafe", "summary_only"])
def test_audit_rejects_missing_or_unsafe_artifacts(tmp_path, mode):
    root = tmp_path / "run"
    execute(root)
    source = root
    if mode == "missing":
        (root / "partial-cascade-inputs.json").unlink()
    elif mode == "locked":
        (root / ".partial-run.lock").write_text("123")
    elif mode == "unsafe":
        path = root / "partial-cascade-resources.json"
        outside = tmp_path / "outside.json"
        path.rename(outside)
        path.symlink_to(outside)
    else:
        source = root / "partial-cascade-report.json"
    with pytest.raises(ValueError):
        audit_partial_cascade(
            experiment=source, output_directory=tmp_path / "audit", resources=RESOURCES
        )
    assert not (tmp_path / "audit").exists()


def test_v3_ablation_changes_only_null_shape_and_v4_adds_independence():
    base = RESOURCES / "prompts/semantic-attribute-observation"
    v3 = (base / "taxonomy-partial-v3/system.txt").read_text()
    ablation = (base / "taxonomy-partial-v3-no-process-null/system.txt").read_text()
    assert ablation == v3.replace(
        "- No process-model role after actually evaluating the text:\n"
        '  {"primary_process_function":null,"process_functions":[]}\n',
        "",
    )
    candidate = (base / "taxonomy-partial-v4/system.txt").read_text()
    assert "NO gate requiring primary_knowledge_kind=process" in candidate
    assert len({_source_resources(RESOURCES, p)["prompt"]["system"] for p in PROMPTS}) == 4
    assert len({(base / p / "schema.json").read_bytes() for p in PROMPTS}) == 1


@pytest.mark.parametrize(
    "value,shape",
    [
        (None, "null"),
        (False, "false"),
        (True, "true"),
        ([], "empty_set"),
        (["activity"], "nonempty_set"),
        ("process", "scalar"),
    ],
)
def test_value_distribution_does_not_conflate_negative_null_and_empty(value, shape):
    assert value_shape(value) == shape


@pytest.mark.parametrize(
    "text,kind",
    [
        ("primary must belong to set", "primary_set_contract"),
        ("non-unique items", "duplicate_set_member"),
        ("role relation presence", "role_contract"),
        ("response identity mismatch", "response_identity"),
        ("truncated", "truncation"),
        ("request timed out", "timeout"),
        ("invalid schema", "schema_or_json"),
        ("other error", "other"),
    ],
)
def test_error_families(text, kind):
    assert classify_error(text) == kind


def test_open_blocker_overlap_exclusive_and_case_voters_are_recomputed(tmp_path):
    result, _ = execute(tmp_path / "run", execute=False, items=(example("a"), example("b")))
    mixed, _, _ = cascade_fixture.verify(tmp_path / "run")
    detail = describe_mixed_consensus(mixed, include_cases=True)
    assert set(detail["open_required_attribute_counts"].values()) == {2}
    assert set(detail["pairwise_blocker_overlap"].values()) == {2}
    assert set(detail["exclusive_blocker_counts"].values()) == {0}
    assert len(detail["cases"]) == 2
    assert result["diagnostics"]["clause_count"] == 2


def test_cli_advertises_prompt_guard_and_model_free_audit():
    runner = CliRunner()
    for command, option in [
        ("partial-cascade", "--prompt"),
        ("partial-cascade", "--require-taxonomy-decisions"),
        ("partial-cascade-audit", "--experiment"),
    ]:
        result = runner.invoke(
            app, ["evaluation", command, "--help"], color=False, env={"COLUMNS": "180"}
        )
        assert result.exit_code == 0, result.output
        assert option in result.output


def test_prompt_selection_does_not_change_model_or_generation_settings():
    manifest = cascade_fixture.matrix()
    for stage in manifest.execution.stages:
        for key in stage.models:
            model = next(m for m in manifest.models if m.id == key)
            baseline = partial_config_for_model(manifest, stage, model)
            candidate = partial_config_for_model(
                manifest, stage, model, prompt_version="taxonomy-partial-v4"
            )
            assert baseline.model_dump(exclude={"prompt_version"}) == candidate.model_dump(
                exclude={"prompt_version"}
            )


def test_plan_only_does_not_overwrite_executed_cascade(tmp_path):
    root = tmp_path / "run"
    execute(root)
    before = hashes(root)
    with pytest.raises(ValueError, match="planning must not replace executed"):
        execute(root, execute=False)
    assert hashes(root) == before


def test_failed_response_and_request_are_still_integrity_bound(tmp_path):
    manifest = cascade_fixture.matrix()
    first = manifest.execution.stages[0].models[0]
    gateways = cascade_fixture.Gateways(manifest, changes={first: {"statement_functions": []}})
    result, _ = execute(tmp_path / "run", gateways=gateways)
    prefix = result["stages"][0]["models"][0]["prefix"]
    path = next((tmp_path / "run" / prefix / "cases").glob("*/response.json"))
    payload = json.loads(path.read_bytes())
    payload["value"]["statement_functions"] = ["requirement"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum"):
        cascade_fixture.verify(tmp_path / "run")
