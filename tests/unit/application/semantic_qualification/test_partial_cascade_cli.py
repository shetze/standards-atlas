"""Safe CLI defaults and complete sparse operational orchestration."""

import json
from dataclasses import asdict

import pytest
import yaml
from test_partial_cascade import Gateways, matrix
from test_partial_observations import RESOURCES, example
from typer.testing import CliRunner

from standards_atlas.cli import app

_GATEWAY = (
    "standards_atlas.cli.commands.evaluation_commands.partial_cascade.partial_gateway_context"
)


def inputs(tmp_path):
    manifest = matrix(policy=True)
    path = tmp_path / "matrix.yaml"
    path.write_text(yaml.safe_dump(manifest.model_dump(mode="json")))
    dataset = tmp_path / "dataset.json"
    # Real EvaluationDataset snapshots need not carry a separate corpus_id.
    dataset.write_text(json.dumps({"version": "1", "examples": [asdict(example())]}))
    return manifest, path, dataset


def arguments(tmp_path, path, dataset):
    return [
        "evaluation",
        "partial-cascade",
        "--manifest",
        str(path),
        "--dataset",
        str(dataset),
        "--output",
        str(tmp_path / "run"),
        "--resources",
        str(RESOURCES),
    ]


def test_help_exposes_execute_archive_and_no_reduced_attribute_profile():
    result = CliRunner().invoke(app, ["evaluation", "partial-cascade", "--help"], color=False)
    assert result.exit_code == 0
    assert "--execute" in result.output
    assert "--archive-output" in result.output
    assert "--attributes" not in result.output


def test_default_planning_never_creates_a_gateway(tmp_path, monkeypatch):
    _, path, dataset = inputs(tmp_path)

    def never(*args, **kwargs):
        pytest.fail("model lifecycle called during planning")

    monkeypatch.setattr(_GATEWAY, never)
    result = CliRunner().invoke(app, arguments(tmp_path, path, dataset))
    assert result.exit_code == 0, result.output
    assert "Fresh cascade gateway calls: 0" in result.output
    assert not (tmp_path / "run/policy").exists()
    assert not (tmp_path / "data").exists()


def test_execute_routes_and_archives_without_implicit_publication(tmp_path, monkeypatch):
    manifest, path, dataset = inputs(tmp_path)
    gateways = Gateways(manifest)
    monkeypatch.setattr(_GATEWAY, lambda model, **kwargs: gateways.context(model))
    result = CliRunner().invoke(
        app,
        arguments(tmp_path, path, dataset)
        + ["--execute", "--archive-output", str(tmp_path / "archives")],
    )
    assert result.exit_code == 0, result.output
    assert len(gateways.requests) == 4
    assert len(list((tmp_path / "archives").glob("qualification-run-*.zip"))) == 1
    assert (tmp_path / "run/policy/applicability-policy-run.json").is_file()
    assert not (tmp_path / "data").exists()


def test_changed_source_population_cannot_resume_same_directory(tmp_path):
    _, path, dataset = inputs(tmp_path)
    assert CliRunner().invoke(app, arguments(tmp_path, path, dataset)).exit_code == 0
    payload = json.loads(dataset.read_bytes())
    payload["examples"].append(asdict(example("b")))
    dataset.write_text(json.dumps(payload))
    result = CliRunner().invoke(app, arguments(tmp_path, path, dataset))
    assert result.exit_code == 2 and "identity changed" in result.output


def test_policy_disabled_does_not_adopt_raw_presence_as_final(tmp_path, monkeypatch):
    manifest, path, dataset = inputs(tmp_path)
    payload = yaml.safe_load(path.read_text())
    payload["applicability_decision_policy"]["enabled"] = False
    path.write_text(yaml.safe_dump(payload))
    gateways = Gateways(manifest)
    monkeypatch.setattr(_GATEWAY, lambda model, **kwargs: gateways.context(model))
    result = CliRunner().invoke(app, arguments(tmp_path, path, dataset) + ["--execute"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "run/policy").exists()
