"""First-stage comparison uses real stored observations, not accepted summary votes."""

import hashlib
import json

import pytest
import test_partial_cascade as fixtures
from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    PartialAcceptanceProfile,
)
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_comparison import (
    compare_efficient_prompts,
    compare_partial_profiles,
)
from standards_atlas.cli import app


def dataset(path):
    example = fixtures.example()
    path.write_text(
        json.dumps(
            {
                "corpus_id": "test-partial",
                "version": "1",
                "examples": [{"id": example.id, "input": example.input}],
            }
        )
    )
    return path


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_offline_profile_comparison_preserves_sources_and_explains_changed_decision(tmp_path):
    matrix = fixtures.matrix()
    first = matrix.execution.stages[0].models[0]
    gateway = fixtures.Gateways(
        matrix,
        changes={
            first: {
                "role_semantics_present": True,
                "role_relations": [
                    {"actor": "supplier", "relation_class": "responsibility", "target": "review"}
                ],
            }
        },
    )
    root = tmp_path / "source"
    run_partial_cascade(
        manifest=matrix,
        examples=(fixtures.example(),),
        output_directory=root,
        resources=fixtures.RESOURCES,
        execute=True,
        gateway_context=gateway.context,
    )
    before = hashes(root)
    calls = len(gateway.requests)
    result = compare_partial_profiles(
        experiment=root,
        profiles=(
            PartialAcceptanceProfile(id="role-test", role_evidence_mode="anchored_minority"),
        ),
        output_directory=tmp_path / "comparison",
        resources=fixtures.RESOURCES,
    )
    assert result["model_calls"] == 0 and len(gateway.requests) == calls
    assert hashes(root) == before
    assert result["variants"][0]["diagnostics"]["completed_clause_count"] == 0
    assert result["variants"][1]["diagnostics"]["completed_clause_count"] == 1
    assert not result["semantic_qualification_passed"]
    assert result["variants"][1]["changed_decisions"][0]["attribute"] == "role_semantics_present"


def test_offline_comparison_rejects_planning_or_summary_only(tmp_path):
    root = tmp_path / "source"
    fixtures.run_partial_cascade(
        manifest=fixtures.matrix(),
        examples=(fixtures.example(),),
        resources=fixtures.RESOURCES,
        output_directory=root,
    )
    profiles = (PartialAcceptanceProfile(id="test"),)
    with pytest.raises(ValueError, match="planned run"):
        compare_partial_profiles(
            experiment=root,
            profiles=profiles,
            output_directory=tmp_path / "out",
            resources=fixtures.RESOURCES,
        )
    with pytest.raises((ValueError, RuntimeError)):
        compare_partial_profiles(
            experiment=root / "partial-cascade-report.json",
            profiles=profiles,
            output_directory=tmp_path / "other",
            resources=fixtures.RESOURCES,
        )


def test_efficient_grid_stops_before_intermediate_and_reports_prompt_and_scope(tmp_path):
    source = dataset(tmp_path / "dataset.json")
    matrix = fixtures.matrix()
    gateway = fixtures.Gateways(
        matrix, changes={matrix.execution.stages[0].models[0]: {"applicability_present": True}}
    )
    prompts = ("taxonomy-partial-v2", "taxonomy-partial-v4")
    result = compare_efficient_prompts(
        manifest=matrix,
        run=None,
        dataset=source,
        prompts=prompts,
        output_directory=tmp_path / "compare",
        resources=fixtures.RESOURCES,
        execute=True,
        gateway_context=gateway.context,
    )
    assert len(gateway.requests) == 8
    assert set(gateway.started) == set(matrix.execution.stages[0].models)
    assert [row["prompt"] for row in result["variants"]] == list(prompts)
    for prompt in prompts:
        report, _, _ = fixtures.verify(tmp_path / "compare" / prompt)
        assert report.stage_id == matrix.execution.stages[0].id
        definition = json.loads(
            (tmp_path / "compare" / prompt / "partial-cascade-plan.json").read_bytes()
        )
        assert definition["stage_limit"] == 1
    assert result["qualification_passed"] is False


def test_grid_planning_then_execution_then_resume_stays_same_selection(tmp_path):
    source = dataset(tmp_path / "data.json")
    gateways = fixtures.Gateways()
    kwargs = dict(
        manifest=fixtures.matrix(),
        run=None,
        dataset=source,
        prompts=("taxonomy-partial-v2", "taxonomy-partial-v4"),
        output_directory=tmp_path / "out",
        resources=fixtures.RESOURCES,
        gateway_context=gateways.context,
    )
    report = compare_efficient_prompts(**kwargs)
    assert not gateways.requests and report["variants"][0]["metrics"]["completion_rate"] is None
    compare_efficient_prompts(**kwargs, execute=True)
    total = len(gateways.requests)
    compare_efficient_prompts(**kwargs, execute=True)
    assert len(gateways.requests) == total == 8
    with pytest.raises(ValueError, match="identity changed"):
        compare_efficient_prompts(**{**kwargs, "prompts": ("taxonomy-partial-v4",)})


def test_grid_source_sentinels_are_separate_from_format_success(tmp_path):
    source = dataset(tmp_path / "data.json")
    example = fixtures.example()
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "semantic-readiness-checks",
                "id": "test",
                "version": "1",
                "qualification_status": "test-only",
                "cases": [
                    {
                        "example_id": example.id,
                        "document_key": example.input["context"]["document_key"],
                        "content_hash": example.input["content"]["hash"],
                        "process_check": {"must_include": ["activity"]},
                    }
                ],
            }
        )
    )
    gateways = fixtures.Gateways()
    result = compare_efficient_prompts(
        manifest=fixtures.matrix(),
        run=None,
        dataset=source,
        prompts=("taxonomy-partial-v4",),
        output_directory=tmp_path / "out",
        resources=fixtures.RESOURCES,
        gateway_context=gateways.context,
        checks=checks,
        execute=True,
    )
    row = result["variants"][0]
    assert row["metrics"]["completion_rate"] == 1
    assert len(row["readiness"]) == 4
    assert all(r["report"]["status_counts"] == {"failed": 1} for r in row["readiness"])
    assert not result["qualification_passed"]


def test_grid_invalid_prompt_fails_before_any_output_or_server(tmp_path):
    gateways = fixtures.Gateways()
    with pytest.raises(ValueError):
        compare_efficient_prompts(
            manifest=fixtures.matrix(),
            run=None,
            dataset=dataset(tmp_path / "data.json"),
            prompts=("taxonomy-partial-v2", "invented"),
            output_directory=tmp_path / "out",
            resources=fixtures.RESOURCES,
            gateway_context=gateways.context,
            execute=True,
        )
    assert not (tmp_path / "out").exists() and not gateways.started


@pytest.mark.parametrize("command", ["partial-efficient-compare", "partial-profile-compare"])
def test_comparison_cli_is_registered(command):
    response = CliRunner().invoke(app, ["evaluation", command, "--help"])
    assert response.exit_code == 0
    assert "--output" in response.stdout


def test_cascade_profile_cli_is_exposed():
    response = CliRunner().invoke(app, ["evaluation", "partial-cascade", "--help"])
    assert response.exit_code == 0 and "--acceptance-profile" in response.stdout
