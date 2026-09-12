"""Fresh, cached, resumed and offline-recovered observations use one identity policy."""

import json
from dataclasses import replace

import pytest
import test_partial_proposals as fixtures
from test_partial_observations import RESOURCES, config, example
from typer.testing import CliRunner

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification import partial_proposals
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import (
    PartialProposalConfig,
)
from standards_atlas.cli import app

REPOSITORY = "ibm-granite/granite-3.3-8b-instruct-GGUF"
REQUESTED = f"hf.co/{REPOSITORY}:Q4_K_M"


class AliasGateway(fixtures.FakeGateway):
    def __init__(self, *, reported=REPOSITORY, prompt=None, value=None):
        super().__init__(None if value is None else [value])
        self.reported = reported
        self.prompt = prompt

    def generate_structured(self, request):
        result = super().generate_structured(request)
        return replace(
            result,
            model=self.reported,
            prompt_version=self.prompt or result.prompt_version,
        )


def run(tmp_path, *, gateway=None, execute=True, revalidate=False, cfg=None):
    gateway = gateway or AliasGateway()
    cfg = cfg or config(selected_attributes=("applicability_present",)).model_copy(
        update={"model": REQUESTED, "provider": "ramalama"},
    )
    return run_partial_proposals(
        cfg,
        resources=RESOURCES,
        output_directory=tmp_path / "out",
        examples=(example(),),
        execute=execute,
        revalidate_responses=revalidate,
        gateway_factory=lambda: gateway,
    ), gateway


def case(tmp_path):
    return next((tmp_path / "out/cases").iterdir())


def emulate_legacy_failure(tmp_path, monkeypatch, *, gateway=None):
    def legacy_check(response, *, requested_model, prompt_version, provider):
        if response["model"] != requested_model or response["prompt_version"] != prompt_version:
            raise ValueError("provider response model or prompt identity differs from request")
        return {}

    with monkeypatch.context() as old:
        old.setattr(partial_proposals, "require_response_identity", legacy_check)
        result, gateway = run(tmp_path, gateway=gateway)
    assert result["status_counts"] == {"failed": 1}
    return gateway


def test_alias_fresh_resume_and_voter_key_keep_requested_identity(tmp_path):
    first, gateway = run(tmp_path)
    directory = case(tmp_path)
    response = json.loads((directory / "response.json").read_text())
    original = (directory / "partial-observation.json").read_bytes()
    obs = PartialObservation.model_validate_json(original)
    assert first["logical_model_observation_count"] == 1
    assert response["model"] == REPOSITORY
    assert obs.model == REQUESTED
    assert obs.voter_key == f"ramalama:{REQUESTED}"
    second, _ = run(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 1
    assert second["reused_observation_count"] == 1
    assert second["request_timing"]["request_count"] == 0
    assert (directory / "partial-observation.json").read_bytes() == original
    assert second["cases"][0]["response_identity"]["selector_check"] == "not_reported"


@pytest.mark.parametrize(
    "changes",
    [
        {"reported": f"{REPOSITORY}:Q5_K_M"},
        {"reported": "other/model-GGUF"},
        {"prompt": "taxonomy-partial-v2"},
    ],
)
def test_bad_identities_produce_diagnostic_and_no_model_vote(tmp_path, changes):
    result, _ = run(tmp_path, gateway=AliasGateway(**changes))
    assert result["status_counts"] == {"failed": 1}
    assert result["logical_model_observation_count"] == 0
    identity = result["cases"][0]["response_identity"]
    assert not identity["accepted"]
    assert identity["requested_model"] == REQUESTED
    assert "reported=" in result["cases"][0]["error"]


def test_offline_recovery_preserves_response_attempts_and_old_failure_bytes(tmp_path, monkeypatch):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch)
    directory = case(tmp_path)
    original = (directory / "partial-observation.json").read_bytes()
    raw = (directory / "response.json").read_bytes()
    old_report = (tmp_path / "out/partial-run-report.json").read_bytes()
    history = {p: p.read_bytes() for p in directory.glob("executions/**/*") if p.is_file()}
    before = PartialObservation.model_validate_json(original)
    report, _ = run(tmp_path, gateway=gateway, execute=False, revalidate=True)
    recovered = PartialObservation.model_validate_json(
        (directory / "partial-observation.json").read_bytes(),
    )
    assert report["status_counts"] == {"evaluated": 1}
    assert report["new_observation_count"] == report["reused_observation_count"] == 0
    assert report["revalidated_observation_count"] == 1
    assert report["logical_model_observation_count"] == 1
    assert report["request_timing"]["request_count"] == 0
    assert len(gateway.requests) == 1
    assert (directory / "response.json").read_bytes() == raw
    assert {p: p.read_bytes() for p in history} == history
    previous_path = next(directory.glob("revalidations/*/previous-observation.json"))
    assert previous_path.read_bytes() == original
    assert old_report in [p.read_bytes() for p in (tmp_path / "out/report-history").glob("*.json")]
    assert recovered.observation_id == before.observation_id
    assert recovered.model == before.model == REQUESTED
    after = (directory / "partial-observation.json").read_bytes()
    again, _ = run(tmp_path, gateway=gateway, execute=False, revalidate=True)
    assert again["revalidated_observation_count"] == 0
    assert again["reused_observation_count"] == 1
    assert (directory / "partial-observation.json").read_bytes() == after
    assert len(list(directory.glob("revalidations/*"))) == 1


def test_default_resume_does_not_silently_recover_failed_answers(tmp_path, monkeypatch):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch)
    before = (case(tmp_path) / "partial-observation.json").read_bytes()
    result, _ = run(tmp_path, gateway=gateway, execute=False)
    assert result["revalidated_observation_count"] == 0
    assert result["status_counts"] == {"planned": 1}
    assert (case(tmp_path) / "partial-observation.json").read_bytes() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"reported": f"{REPOSITORY}:Q5_K_M"},
        {"prompt": "other-prompt"},
        {"value": {}},
        {"value": {"applicability_present": "false"}},
    ],
)
def test_recovery_rejects_real_identity_and_schema_errors_without_gateway(
    tmp_path,
    monkeypatch,
    changes,
):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch, gateway=AliasGateway(**changes))
    before = (case(tmp_path) / "partial-observation.json").read_bytes()
    result, _ = run(tmp_path, gateway=gateway, execute=False, revalidate=True)
    assert result["status_counts"] == {"failed": 1}
    assert result["failed_observation_count"] == 1
    assert result["revalidated_observation_count"] == 0
    assert result["logical_model_observation_count"] == 0
    assert result["request_timing"]["request_count"] == 0
    assert len(gateway.requests) == 1
    assert result["cases"][0]["response_revalidation"]["status"] == "failed"
    assert (case(tmp_path) / "partial-observation.json").read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "different"),
        ("prompt_version", "changed"),
        ("user_prompt", "changed"),
        ("seed", 99),
    ],
)
def test_recovery_refuses_changed_stored_request_instead_of_overwriting(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch)
    path = case(tmp_path) / "request.json"
    payload = json.loads(path.read_bytes())
    payload[field] = value
    path.write_text(json.dumps(payload))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="stored partial request differs"):
        run(tmp_path, gateway=gateway, execute=False, revalidate=True)
    assert path.read_bytes() == original
    assert len(gateway.requests) == 1


def test_recovery_refuses_corrupt_response_before_reinterpretation(tmp_path, monkeypatch):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch)
    path = case(tmp_path) / "response.json"
    payload = json.loads(path.read_bytes())
    payload["value"]["applicability_present"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum mismatch"):
        run(tmp_path, gateway=gateway, execute=False, revalidate=True)
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("missing", ["response", "checksum"])
def test_incomplete_recovery_evidence_stays_failed(tmp_path, monkeypatch, missing):
    gateway = emulate_legacy_failure(tmp_path, monkeypatch)
    directory = case(tmp_path)
    if missing == "response":
        (directory / "response.json").unlink()
    else:
        path = directory / "partial-observation.json"
        payload = json.loads(path.read_bytes())
        payload["response_sha256"] = None
        path.write_text(json.dumps(payload))
    result, _ = run(tmp_path, execute=False, revalidate=True)
    assert result["status_counts"] == {"failed": 1}
    assert result["revalidated_observation_count"] == 0
    assert len(gateway.requests) == 1


def test_successful_resume_rechecks_model_identity_even_with_consistent_updated_checksum(tmp_path):
    _, gateway = run(tmp_path)
    directory = case(tmp_path)
    response = json.loads((directory / "response.json").read_bytes())
    response["model"] = "other/model-GGUF"
    (directory / "response.json").write_text(json.dumps(response))
    obs = json.loads((directory / "partial-observation.json").read_bytes())
    obs["response_sha256"] = structure_fingerprint(response)
    (directory / "partial-observation.json").write_text(json.dumps(obs))
    with pytest.raises(ValueError, match="identity mismatch"):
        run(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 1


def test_revalidation_and_execute_only_infers_the_still_failed_case(tmp_path, monkeypatch):
    gateway = AliasGateway(value={})
    emulate_legacy_failure(tmp_path, monkeypatch, gateway=gateway)
    report, _ = run(tmp_path, gateway=gateway, execute=True, revalidate=True)
    assert report["status_counts"] == {"evaluated": 1}
    assert report["revalidated_observation_count"] == 0
    assert report["new_observation_count"] == 1
    assert "error" not in report["cases"][0]
    assert len(gateway.requests) == 2


def test_cli_offline_revalidation_does_not_read_runtime_configuration(tmp_path, monkeypatch):
    dataset = fixtures.write_dataset(tmp_path)
    args = [
        "evaluation",
        "partial-proposals",
        "--dataset",
        str(dataset),
        "--output",
        str(tmp_path / "out"),
        "--model",
        REQUESTED,
        "--attributes",
        "applicability_present",
        "--config",
        str(tmp_path / "missing.yaml"),
    ]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    # The CLI has written the exact plan. Insert a faithfully bound historical failure.
    payload = json.loads((tmp_path / "out/partial-run-plan.json").read_bytes())
    cfg = PartialProposalConfig.model_validate(payload["config"])
    selection = partial_proposals.load_partial_inputs(dataset=dataset)
    with monkeypatch.context() as old:

        def reject(*args, **kwargs):
            raise ValueError("provider response model or prompt identity differs from request")

        old.setattr(partial_proposals, "require_response_identity", reject)
        run_partial_proposals(
            cfg,
            resources=RESOURCES,
            output_directory=tmp_path / "out",
            examples=selection.examples,
            source_fingerprints=selection.fingerprints,
            execute=True,
            gateway_factory=lambda: AliasGateway(),
        )
    result = runner.invoke(app, [*args, "--revalidate-responses"])
    assert result.exit_code == 0, result.output
    assert "Gateway calls this time  : 0" in result.output
    assert "Revalidated responses    : 1" in result.output
