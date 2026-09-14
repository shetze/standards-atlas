"""Final qualification: frozen sources, real orchestration and explicit release gates.

All inference in this file is simulated. These tests are not qualification evidence
for the shipped prompts, models, acceptance profiles or independent human review.
"""

import copy
import json
import shutil
from contextlib import contextmanager
from dataclasses import asdict, replace

import pytest
import yaml
from test_mixed_applicability import detail_value
from test_mixed_consensus import VALUES
from test_partial_cascade import matrix
from test_partial_observations import RESOURCES, example
from test_partial_proposals import FakeGateway
from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.campaign_activation import (
    activate_campaign,
    archive_campaign,
    verify_activation,
)
from standards_atlas.application.semantic_qualification.campaign_evaluation import (
    evaluate_campaign,
)
from standards_atlas.application.semantic_qualification.campaign_execution import (
    FreshLedgerGateway,
    job_key,
    run_campaign,
    verify_job,
)
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    prepare_campaign,
    stratified_sample,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
    SemanticPredicate,
    SemanticReferenceSuite,
    predicate_passes,
)
from standards_atlas.cli import app


def source_files(root, *, count=4, reviews=False):
    root.mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(count):
        item = example(f"g{i:03}")
        data = copy.deepcopy(dict(item.input))
        text = (
            "POSITIVE-FIXTURE-CASE. NOTE: The requirements of 7 do not apply."
            if i == 0
            else f"A definition of a process concept. Entry {i}."
        )
        data["content"] = {"text": text, "hash": normalized_content_hash(text)}
        data["context"]["reference"] = f"3.{i + 1}"
        items.append(replace(item, input=data))
    (root / "dataset.json").write_text(
        json.dumps(
            {
                "version": "1",
                "corpus_id": "test-partial",
                "examples": [asdict(e) for e in items],
            }
        )
    )
    m = matrix(policy=True)
    (root / "matrix.yaml").write_text(yaml.safe_dump(m.model_dump(mode="json")))
    gold_items = items[:-2] if reviews else items
    golden = {
        "schema_version": "3.0",
        "cases": [
            {
                "document_key": "TEST",
                "clause_id": e.id,
                "reference": e.input["context"]["reference"],
                "text": e.input["content"]["text"],
                "category": "synthetic-unit-fixture",
                "status": "published",
                "expected": {"present": e.id == "g000"},
                "provenance": {
                    "source_archive": "synthetic-unit-fixture",
                    "source_archive_sha256": "0" * 64,
                },
            }
            for e in gold_items
        ],
    }
    (root / "golden.yaml").write_text(yaml.safe_dump(golden))
    suite_paths = []
    if reviews:
        for split, item in zip(("development", "holdout"), items[-2:], strict=True):
            path = root / f"{split}.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "kind": "partial-semantic-reference",
                        "id": split,
                        "version": "1.0.0",
                        "split": split,
                        "status": "published",
                        "reviewed_by": "unit-test-reviewer",
                        "review_reference": "synthetic-unit-test",
                        "cases": [
                            {
                                "example_id": item.id,
                                "document_key": "TEST",
                                "content_hash": item.input["content"]["hash"],
                                "attributes": {
                                    a: {"equals": VALUES[a]}
                                    for a in (
                                        "primary_function",
                                        "primary_knowledge_kind",
                                        "role_semantics_present",
                                        "process_functions",
                                    )
                                },
                            }
                        ],
                    }
                )
            )
            suite_paths.append(str(path))
    spec = {
        "schema_version": "1.1",
        "manifest_type": "partial_qualification",
        "id": "campaign-test",
        "dataset": str(root / "dataset.json"),
        "golden": str(root / "golden.yaml"),
        "sample_size": min(count, 4),
        "baseline": "base",
        "candidate": "candidate",
        "semantic_suites": suite_paths,
        "variants": [
            {
                "id": name,
                "matrix": str(root / "matrix.yaml"),
                "prompt": "taxonomy-partial-v2",
                "change": "synthetic control",
            }
            for name in ("base", "candidate")
        ],
    }
    spec_path = root / "campaign.yaml"
    spec_path.write_text(yaml.safe_dump(spec))
    return spec_path, items, spec


def prepare(tmp_path, **kwargs):
    spec, items, data = source_files(tmp_path / "inputs", **kwargs)
    root = tmp_path / "campaign"
    prepare_campaign(manifest=spec, output=root, resources=RESOURCES)
    return root, items, data


class PerfectGateway(FakeGateway):
    def __init__(self, *, cache=False):
        super().__init__()
        self.cache = cache

    def generate_structured(self, request):
        if request.task == "semantic-attribute-observation":
            values = dict(VALUES)
            values["applicability_present"] = "POSITIVE-FIXTURE-CASE" in request.user_prompt
            result = {k: values[k] for k in request.output_schema["required"]}
        else:
            result = detail_value(True, version=1 if request.prompt_version.endswith("-v1") else 2)
        self.responses = [result]
        return replace(super().generate_structured(request), cached=self.cache)


class FreshModels:
    def __init__(self, *, cache=False):
        self.gateway = PerfectGateway(cache=cache)
        self.starts = []

    @contextmanager
    def context(self, model):
        self.starts.append(model.id)
        yield self.gateway


@pytest.fixture(scope="module")
def completed_small(tmp_path_factory):
    root, *_ = prepare(tmp_path_factory.mktemp("qualification-small"))
    models = FreshModels()
    run = run_campaign(
        campaign=root, resources=RESOURCES, execute=True, gateway_context=models.context
    )
    assert all(j["status"] == "completed" for j in run["jobs"]), run
    return root


@pytest.fixture
def qualified_population(tmp_path, monkeypatch):
    # Small integration corpus: the separate population-gate tests enforce 116.
    # Only that minimum-count precondition is mocked here, not repeats or review.
    import standards_atlas.application.semantic_qualification.campaign_evaluation as evaluation

    check = evaluation.golden_coverage_eligible
    monkeypatch.setattr(
        evaluation, "golden_coverage_eligible", lambda gold, result, minimum: check(gold, result, 4)
    )
    root, *_ = prepare(tmp_path, count=6, reviews=True)
    models = FreshModels()
    run = run_campaign(
        campaign=root, resources=RESOURCES, execute=True, gateway_context=models.context
    )
    assert all(j["status"] == "completed" for j in run["jobs"]), run
    report = evaluate_campaign(campaign=root, resources=RESOURCES)
    assert report["pre_full_eligible"], [
        (r["job"], r.get("error"), r.get("qualifies")) for r in report["repetitions"]
    ]
    full = run_campaign(
        campaign=root,
        resources=RESOURCES,
        execute=True,
        phase="full",
        gateway_context=models.context,
    )
    assert full["jobs"][0]["status"] == "completed", full
    return root


def test_frozen_selection_is_reproducible_and_label_free(tmp_path):
    root, items, _ = prepare(tmp_path)
    frozen = load_campaign(root, RESOURCES)
    assert len(frozen[-1]["cohorts"]["golden"]) == len(items)
    assert frozen[-1]["cohorts"]["evaluation_union"] == [e.id for e in items]
    dataset = json.loads((root / "datasets/evaluation_union.json").read_bytes())
    assert all(e["expected"] == {} and e["tags"] == [] for e in dataset["examples"])
    assert all(e.expected == {} and not e.tags for e in frozen[2])
    assert all(
        set(e) == {"id", "input"}
        for e in json.loads((root / "inputs/population.json").read_bytes())
    )


@pytest.mark.parametrize("size", [1, 2, 7, 11])
def test_sampling_independent_of_order_and_proportional(size):
    items = tuple(example(str(i), document_key="A" if i < 7 else "B") for i in range(11))
    a = stratified_sample(items, size, 7)
    b = stratified_sample(tuple(reversed(items)), size, 7)
    assert a == b and len(a) == size and len({e.id for e in a}) == size


@pytest.mark.parametrize("size", [0, 12])
def test_invalid_sample_size_rejected(size):
    with pytest.raises(ValueError):
        stratified_sample((example(),), size, 7)


@pytest.mark.parametrize(
    "field,value",
    [
        ("repetitions", 2),
        ("minimum_published_golden_cases", 115),
        ("sample_size", True),
        ("seed", "7"),
        ("efficient_target", 0.5),
        ("max_request_ratio", float("nan")),
        ("candidate", "unknown"),
        ("baseline", "candidate"),
        ("schema_version", "99"),
    ],
)
def test_campaign_contract_rejects_invalid_or_weakened_fields(tmp_path, field, value):
    _, _, spec = source_files(tmp_path / "inputs")
    with pytest.raises(ValueError):
        QualificationCampaign.model_validate({**spec, field: value})


@pytest.mark.parametrize("change", ["missing", "text", "hash", "duplicate"])
def test_source_drift_or_missing_golden_fails_before_output(tmp_path, change):
    spec, _, _ = source_files(tmp_path / "inputs")
    p = tmp_path / "inputs/dataset.json"
    data = json.loads(p.read_bytes())
    if change == "missing":
        data["examples"].pop()
    elif change == "text":
        data["examples"][0]["input"]["content"]["text"] = "different"
    elif change == "hash":
        data["examples"][0]["input"]["content"]["hash"] = "sha256:" + "a" * 64
    else:
        data["examples"].append(data["examples"][0])
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare_campaign(manifest=spec, output=tmp_path / "campaign", resources=RESOURCES)
    assert not (tmp_path / "campaign").exists()


def test_terminal_linebreak_equivalence_is_explicit_not_text_repair(tmp_path):
    spec, _, _ = source_files(tmp_path / "inputs")
    p = tmp_path / "inputs/golden.yaml"
    data = yaml.safe_load(p.read_bytes())
    data["cases"][0]["text"] += "\n"
    p.write_text(yaml.safe_dump(data))
    prepare_campaign(manifest=spec, output=tmp_path / "campaign", resources=RESOURCES)
    selection = json.loads((tmp_path / "campaign/selection.json").read_bytes())
    assert selection["golden_text_comparisons"][0]["match"] == "terminal_linebreaks_only"
    frozen_gold = json.loads((tmp_path / "campaign/inputs/golden.json").read_bytes())
    assert frozen_gold["cases"][0]["text"].endswith("\n")


def test_holdout_must_be_disjoint_from_development_and_golden(tmp_path):
    spec, _, _ = source_files(tmp_path / "inputs", count=6, reviews=True)
    a = json.loads((tmp_path / "inputs/development.json").read_bytes())
    b = json.loads((tmp_path / "inputs/holdout.json").read_bytes())
    b["cases"] = a["cases"]
    (tmp_path / "inputs/holdout.json").write_text(json.dumps(b))
    with pytest.raises(ValueError, match="overlaps"):
        prepare_campaign(manifest=spec, output=tmp_path / "campaign", resources=RESOURCES)


def test_reviewed_suite_requires_explicit_provenance(tmp_path):
    _, _, _ = source_files(tmp_path / "inputs", count=6, reviews=True)
    suite = json.loads((tmp_path / "inputs/holdout.json").read_bytes())
    suite["reviewed_by"] = ""
    with pytest.raises(ValueError):
        SemanticReferenceSuite.model_validate(suite)


@pytest.mark.parametrize(
    "actual,expected,match",
    [
        (False, False, True),
        (0, False, False),
        (None, None, True),
        (["a", "b"], ["b", "a"], True),
        (["a"], [], False),
    ],
)
def test_predicates_preserve_json_types_and_semantic_sets(actual, expected, match):
    assert predicate_passes(actual, SemanticPredicate(equals=expected)) is match


@pytest.mark.parametrize(
    "raw",
    [{}, {"equals": "a", "must_be_empty": True}, {"must_include": []}, {"must_be_empty": False}],
)
def test_predicate_ambiguity_rejected(raw):
    with pytest.raises(ValueError):
        SemanticPredicate.model_validate(raw)


def test_plan_and_missing_results_never_qualify(tmp_path):
    root, *_ = prepare(tmp_path)
    result = run_campaign(campaign=root, resources=RESOURCES)
    assert len(result["jobs"]) == 12 and result["run_mode"] == "planned"
    assert not (root / "jobs").exists()
    evaluation = evaluate_campaign(campaign=root, resources=RESOURCES)
    assert not evaluation["activation_eligible"] and not evaluation["pre_full_eligible"]
    assert evaluation["full_population_efficient_rate"] is None
    assert len(evaluation["repetitions"]) == 13
    assert all(r["status"] == "missing" for r in evaluation["repetitions"])


def test_small_complete_run_does_not_substitute_for_complete_golden(completed_small):
    result = evaluate_campaign(campaign=completed_small, resources=RESOURCES)
    assert not result["pre_full_eligible"]
    r = result["repetitions"][0]
    assert r["status"] == "verified" and r["final_applicability"]["passed"]
    assert not r["golden_coverage_eligible"]
    assert r["semantic_gate"]["missing_reviewed_dimensions"]["holdout"]


def test_fixed_presence_repeats_use_verified_first_gate_and_no_joint_calls(completed_small):
    result = verify_job(
        campaign=completed_small,
        key=job_key("base", "fresh_detail_fixed_presence", 1),
        resources=RESOURCES,
    )
    assert len(result["events"]) == 1
    assert result["policy"].qualification_mode.value == "fresh_detail_fixed_presence"
    assert all(e["request"]["task"] != "semantic-attribute-observation" for e in result["events"])


def test_complete_resume_has_zero_new_calls_and_no_extra_repetition_votes(completed_small):
    def never(_):
        pytest.fail("sealed repetitions must not initialize models")

    result = run_campaign(
        campaign=completed_small, resources=RESOURCES, execute=True, gateway_context=never
    )
    assert all(j["status"] == "verified_existing" for j in result["jobs"])


@pytest.mark.parametrize(
    "artifact", ["repeat.json", "run/mixed-consensus-report.json", "run/gate-anchor.json"]
)
def test_tampered_repeat_rejected_without_modifying_source(tmp_path, completed_small, artifact):
    root = tmp_path / "copy"
    shutil.copytree(completed_small, root)
    mode = (
        "fresh_detail_fixed_presence"
        if artifact.endswith("gate-anchor.json")
        else "fresh_end_to_end"
    )
    key = job_key("base", mode, 1)
    path = root / key / artifact
    data = json.loads(path.read_bytes())
    if artifact == "repeat.json":
        data["binding"]["job"] = job_key("base", mode, 2)
    else:
        data["matrix_id"] = "forged"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify_job(campaign=root, key=key, resources=RESOURCES)


def test_copying_repeat_to_a_new_index_is_not_fresh(tmp_path, completed_small):
    root = tmp_path / "copy"
    shutil.copytree(completed_small, root)
    src = root / job_key("base", "fresh_end_to_end", 1)
    dst = root / job_key("base", "fresh_end_to_end", 2)
    shutil.rmtree(dst)
    shutil.copytree(src, dst)
    with pytest.raises(ValueError, match="another campaign/job"):
        verify_job(campaign=root, key=job_key("base", "fresh_end_to_end", 2), resources=RESOURCES)


def test_cached_response_is_recorded_but_cannot_qualify(tmp_path):
    from test_partial_observations import prepared

    request = prepared().request
    gateway = FreshLedgerGateway(
        PerfectGateway(cache=True), root=tmp_path, binding={"job": "test"}, model_id="test"
    )
    with pytest.raises(ValueError, match="cached"):
        gateway.generate_structured(request)
    event = json.loads(next((tmp_path / "qualification-events").glob("*.json")).read_bytes())
    assert event["cached"] and event["error"]


def test_missing_usage_is_unknown_not_zero(tmp_path):
    from test_partial_observations import prepared

    class NoUsage(PerfectGateway):
        def generate_structured(self, request):
            return replace(super().generate_structured(request), usage=None)

    gateway = FreshLedgerGateway(NoUsage(), root=tmp_path, binding={"job": "test"}, model_id="test")
    gateway.generate_structured(prepared().request)
    event = json.loads(next((tmp_path / "qualification-events").glob("*.json")).read_bytes())
    assert event["usage"] is None


def test_full_run_cannot_start_without_quality_evidence(completed_small):
    with pytest.raises(ValueError, match="full baseline blocked"):
        run_campaign(
            campaign=completed_small,
            resources=RESOURCES,
            phase="full",
            execute=True,
            gateway_context=lambda _: pytest.fail("must block before model start"),
        )


def test_campaign_schema_and_input_tampering_fail(tmp_path):
    root, *_ = prepare(tmp_path)
    p = root / "selection.json"
    d = json.loads(p.read_bytes())
    d["sample_size"] = 999
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="input changed"):
        load_campaign(root, RESOURCES)


def test_activation_refuses_incomplete_evidence(completed_small, tmp_path):
    with pytest.raises(ValueError, match="activation blocked"):
        activate_campaign(
            campaign=completed_small,
            output=tmp_path / "activation",
            resources=RESOURCES,
            reviewer="reviewer",
            review_reference="REF",
        )
    assert not (tmp_path / "activation").exists()


def test_full_independent_repetitions_and_activation_roundtrip(qualified_population, tmp_path):
    result = evaluate_campaign(campaign=qualified_population, resources=RESOURCES)
    assert result["pre_full_eligible"] and result["activation_eligible"]
    assert result["efficient_target_observed"] is True
    assert result["full_population_efficient_rate"] == 1.0
    assert all(r["qualifies"] for r in result["repetitions"])
    activated = activate_campaign(
        campaign=qualified_population,
        output=tmp_path / "activation",
        resources=RESOURCES,
        reviewer="unit-test",
        review_reference="TEST",
    )
    assert verify_activation(tmp_path / "activation/activation.json") == activated
    assert not activated["default_workflow_changed"] and not activated["new_rule_qualifications"]
    assert (qualified_population / "archives").is_dir()


def test_qualification_archive_uses_existing_hash_envelope(completed_small, tmp_path):
    from standards_atlas.application.semantic_qualification.cascade_replay_source import (
        CascadeReplaySource,
    )

    archive = archive_campaign(
        campaign=completed_small, output=tmp_path / "archives", resources=RESOURCES
    )
    source = CascadeReplaySource(archive)
    try:
        assert "archive-manifest.json" in source.names
        for name in source.expected:
            source.read(name)
        assert any(n.endswith("campaign-plan.json") for n in source.names)
        assert any(n.endswith("qualification-evaluation.json") for n in source.names)
    finally:
        source.close()


def test_cli_planning_workflow_and_new_commands(tmp_path):
    spec, _, _ = source_files(tmp_path / "inputs")
    runner = CliRunner()
    for command in (
        "partial-qualification-prepare",
        "partial-qualification-run",
        "partial-qualification-evaluate",
        "partial-qualification-activate",
    ):
        result = runner.invoke(app, ["evaluation", command, "--help"])
        assert result.exit_code == 0, result.output
    result = runner.invoke(
        app, ["workflow", "plan", "--task", "qualification", "--manifests", str(spec)]
    )
    assert result.exit_code == 0, result.output
    assert "partial-qualification-prepare" in result.output
    assert "partial-qualification-run" in result.output
    assert "partial-qualification-evaluate" in result.output
    assert "partial-qualification-activate" not in result.output


def test_cli_nonexecuted_campaign_never_invokes_gateway(tmp_path, monkeypatch):
    root, *_ = prepare(tmp_path)
    import standards_atlas.cli.commands.evaluation_commands.qualification_campaign as cli

    monkeypatch.setattr(cli, "partial_gateway_context", lambda *a, **kw: pytest.fail("no gateway"))
    runner = CliRunner()
    result = runner.invoke(
        app, ["evaluation", "partial-qualification-run", "--campaign", str(root)]
    )
    assert result.exit_code == 0 and "planned" in result.output
    result = runner.invoke(
        app,
        [
            "evaluation",
            "partial-qualification-evaluate",
            "--campaign",
            str(root),
            "--fail-on-rejection",
        ],
    )
    assert result.exit_code == 1


def test_workflow_resume_verifies_requested_frozen_configuration(tmp_path):
    from standards_atlas.application.semantic_qualification.campaign_selection import (
        verify_prepared_campaign,
    )

    root, *_ = prepare(tmp_path)
    manifest = tmp_path / "inputs/campaign.yaml"
    assert (
        verify_prepared_campaign(manifest=manifest, campaign=root, resources=RESOURCES)
        == load_campaign(root, RESOURCES)[0]
    )
    matrix_file = tmp_path / "inputs/matrix.yaml"
    payload = yaml.safe_load(matrix_file.read_bytes())
    payload["matrix_id"] = "different-requested-matrix"
    matrix_file.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="variant changed"):
        verify_prepared_campaign(manifest=manifest, campaign=root, resources=RESOURCES)


def test_workflow_prepare_reuses_only_unchanged_campaign(tmp_path):
    manifest, _, _ = source_files(tmp_path / "inputs")
    output = tmp_path / "campaign"
    command = [
        "evaluation",
        "partial-qualification-prepare",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--reuse-frozen",
    ]
    runner = CliRunner()
    first = runner.invoke(app, command)
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, command)
    assert second.exit_code == 0, second.output
    payload = yaml.safe_load(manifest.read_bytes())
    payload["seed"] = 42
    manifest.write_text(yaml.safe_dump(payload))
    third = runner.invoke(app, command)
    assert third.exit_code == 2 and "differs from frozen" in third.output


@pytest.mark.parametrize(
    "count,classes,expected",
    [
        (115, (True, False), False),
        (116, (True, False), True),
        (120, (False,), False),
        (120, (True,), False),
    ],
)
def test_complete_golden_requires_116_and_both_classes(count, classes, expected):
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.campaign_evaluation import (
        golden_coverage_eligible,
    )

    gold = SimpleNamespace(
        cases=[
            SimpleNamespace(status="published", expected=SimpleNamespace(present=value))
            for value in classes
        ]
    )
    assert golden_coverage_eligible(gold, SimpleNamespace(published_cases=count), 116) is expected


def test_semantic_coverage_cannot_be_reduced_to_only_easy_dimension(tmp_path):
    _, _, spec = source_files(tmp_path / "inputs")
    spec["required_semantic_attributes"] = ["primary_function"]
    with pytest.raises(ValueError, match="cannot omit core"):
        QualificationCampaign.model_validate(spec)


def test_campaign_cannot_weaken_matrix_fresh_repeat_requirement(tmp_path):
    manifest, _, _ = source_files(tmp_path / "inputs")
    p = tmp_path / "inputs/matrix.yaml"
    matrix_data = yaml.safe_load(p.read_bytes())
    matrix_data["applicability_decision_policy"]["required_fresh_repetitions"] = 4
    p.write_text(yaml.safe_dump(matrix_data))
    with pytest.raises(ValueError, match="freshness requirement"):
        prepare_campaign(manifest=manifest, output=tmp_path / "campaign", resources=RESOURCES)


@pytest.mark.parametrize("text", ["", "[]", "null"])
def test_empty_or_nonmapping_campaign_is_a_cli_error(tmp_path, text):
    manifest = tmp_path / "bad.yaml"
    manifest.write_text(text)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-qualification-prepare",
            "--manifest",
            str(manifest),
            "--output",
            str(tmp_path / "campaign"),
        ],
    )
    assert result.exit_code == 2 and "must contain a mapping" in result.output
    assert not (tmp_path / "campaign").exists()


def test_invalid_freshness_mode_fails_before_policy_output(tmp_path):
    from standards_atlas.application.semantic_qualification.mixed_applicability import (
        run_mixed_applicability,
    )

    with pytest.raises(ValueError):
        run_mixed_applicability(
            report=None,
            examples=(),
            manifest=matrix(policy=True),
            root=tmp_path,
            resources=RESOURCES,
            gateway_context=None,
            qualification_mode="invented",
        )
    assert not (tmp_path / "policy").exists()
