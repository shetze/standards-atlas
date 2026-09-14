"""R1: one current contract per family, with unchanged evidence and execution gates."""

import hashlib
import json
from typing import get_args

import pytest
import test_partial_cascade as cascade
from test_partial_observations import RESOURCES, config, example, observation, prepared
from test_partial_proposals import FakeGateway, experiment

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    SchemaPolicy,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)
from standards_atlas.application.semantic_qualification.partial_cascade_contract import (
    PARTIAL_CASCADE_REPORT_SCHEMA_VERSION,
    require_partial_cascade_report,
)
from standards_atlas.application.semantic_qualification.partial_observations import (
    PARTIAL_OBSERVATION_SCHEMA_VERSION,
    PARTIAL_REQUEST_SCHEMA_VERSION,
    PartialObservation,
    PartialRequestPlan,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _write_observation,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.partial_requests import PartialPromptVersion

pytestmark = pytest.mark.filterwarnings(
    "error:partial-(request-plan|semantic-observation|cascade-report) schema version"
    ":standards_atlas.application.schema.policy.SchemaDeprecationWarning"
)

FAMILIES = (
    "partial-request-plan",
    "partial-semantic-observation",
    "partial-cascade-report",
)
PROMPTS = get_args(PartialPromptVersion)
BAD_VERSIONS = ("1.0", "9.9", None, 1.1, True)


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def partial_payloads():
    request = prepared(cfg=config(selected_attributes=("applicability_present",)))
    observed = observation(request, {"applicability_present": False})
    return request.plan, observed


@pytest.mark.parametrize("family", FAMILIES)
def test_r1_families_have_no_legacy_reader_window(family):
    policy = SCHEMA_POLICIES[family]
    assert policy.current == "1.1"
    assert policy.readable == (policy.current,)
    assert policy.deprecated == ()
    require_supported_schema(family, "1.1")
    require_current_schema(family, "1.1")
    for value in BAD_VERSIONS:
        with pytest.raises(ValueError, match="Unsupported"):
            require_supported_schema(family, value)
        with pytest.raises(ValueError, match="writers may only emit"):
            require_current_schema(family, value)


def test_constants_and_required_model_markers_match_independent_families():
    assert PARTIAL_CASCADE_REPORT_SCHEMA_VERSION == SCHEMA_POLICIES[FAMILIES[2]].current
    for model, family, version in (
        (PartialRequestPlan, FAMILIES[0], PARTIAL_REQUEST_SCHEMA_VERSION),
        (PartialObservation, FAMILIES[1], PARTIAL_OBSERVATION_SCHEMA_VERSION),
    ):
        assert version == SCHEMA_POLICIES[family].current
        schema = model.model_json_schema()
        assert "schema_version" in schema["required"]
        assert schema["properties"]["schema_version"]["const"] == version
        assert "default" not in schema["properties"]["schema_version"]


@pytest.mark.parametrize("model_index", (0, 1))
@pytest.mark.parametrize("wire", ("mapping", "json"))
@pytest.mark.parametrize("version", (*BAD_VERSIONS, "missing"))
def test_direct_models_reject_obsolete_unknown_and_missing_versions(model_index, wire, version):
    original = partial_payloads()[model_index]
    payload = original.model_dump(mode="json")
    if version == "missing":
        del payload["schema_version"]
    else:
        payload["schema_version"] = version
    with pytest.raises(ValueError, match="schema_version"):
        if wire == "json":
            type(original).model_validate_json(json.dumps(payload))
        else:
            type(original).model_validate(payload)


@pytest.mark.parametrize("version", (*BAD_VERSIONS, "missing"))
def test_current_observation_cannot_wrap_an_obsolete_or_unversioned_plan(version):
    _, observed = partial_payloads()
    payload = observed.model_dump(mode="json")
    if version == "missing":
        del payload["plan"]["schema_version"]
    else:
        payload["plan"]["schema_version"] = version
    with pytest.raises(ValueError, match="plan.schema_version"):
        PartialObservation.model_validate(payload)


def test_unvalidated_model_copy_cannot_bypass_nested_current_contract():
    plan, observed = partial_payloads()
    invalid = plan.model_copy(update={"schema_version": "1.0"})
    payload = observed.model_dump()
    payload["plan"] = invalid
    with pytest.raises(ValueError, match="plan.schema_version"):
        PartialObservation.model_validate(payload)
    with pytest.raises(ValueError, match="schema_version"):
        PartialObservation.model_validate(observed.model_copy(update={"schema_version": "1.0"}))


def test_all_prompts_share_current_plan_format_but_not_request_identity():
    requests = [prepared(cfg=config(prompt_version=prompt)) for prompt in PROMPTS]
    assert len({item.plan.fingerprint for item in requests}) == 1
    assert len({item.fingerprint for item in requests}) == len(PROMPTS)
    assert {item.plan.schema_version for item in requests} == {"1.1"}
    for item in requests:
        payload = item.plan.model_dump(mode="json")
        assert payload["accepted_attributes"] == {}
        assert payload["accepted_state_sha256"] is None
        assert PartialRequestPlan.model_validate_json(item.plan.model_dump_json()) == item.plan
        obsolete = {k: v for k, v in payload.items() if not k.startswith("accepted_")}
        obsolete["schema_version"] = "1.0"
        assert structure_fingerprint(obsolete) != item.plan.fingerprint


@pytest.mark.parametrize("prompt", PROMPTS)
def test_current_writer_roundtrip_and_same_contract_resume_for_every_prompt(tmp_path, prompt):
    cfg = config(prompt_version=prompt, selected_attributes=("applicability_present",))
    report, gateway = experiment(tmp_path, cfg=cfg)
    path = next((tmp_path / "out" / "cases").glob("*/partial-observation.json"))
    result = PartialObservation.model_validate_json(path.read_bytes())
    assert result.schema_version == result.plan.schema_version == "1.1"
    assert result.model_evidence() == {"applicability_present": False}
    resumed, _ = experiment(tmp_path, cfg=cfg, gateway=gateway)
    assert report["status_counts"] == resumed["status_counts"] == {"evaluated": 1}
    assert resumed["request_timing"]["request_count"] == 0
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("prompt", tuple(p for p in PROMPTS if p != "taxonomy-partial-v1"))
def test_carry_stays_source_bound_and_is_not_observed_again(tmp_path, prompt):
    cfg = config(
        prompt_version=prompt,
        selected_attributes=("applicability_present", "role_semantics_present"),
    )
    gateway = FakeGateway()
    options = dict(
        resources=RESOURCES,
        output_directory=tmp_path / "out",
        examples=(example(),),
        execute=True,
        gateway_factory=lambda: gateway,
        accepted_decisions={"a": {"applicability_present": False}},
        accepted_state_sha256="a" * 64,
    )
    run_partial_proposals(cfg, **options)
    path = next((tmp_path / "out" / "cases").glob("*/partial-observation.json"))
    observed = PartialObservation.model_validate_json(path.read_bytes())
    state = next(s for s in observed.states if s.attribute == "applicability_present")
    assert (state.status, state.reason) == ("not_requested", "accepted")
    assert observed.model_evidence() == {"role_semantics_present": False}
    assert observed.plan.accepted_state_sha256 == "a" * 64
    assert run_partial_proposals(cfg, **options)["request_timing"]["request_count"] == 0
    before = hashes(tmp_path)
    with pytest.raises(ValueError, match="identity changed"):
        run_partial_proposals(cfg, **{**options, "accepted_state_sha256": "b" * 64})
    assert hashes(tmp_path) == before
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("artifact", ("plan", "observation", "nested_plan"))
@pytest.mark.parametrize("version", ("1.0", "missing"))
def test_resume_and_offline_revalidation_do_not_upgrade_old_artifacts(tmp_path, artifact, version):
    _, gateway = experiment(tmp_path)
    filename = "partial-request-plan.json" if artifact == "plan" else "partial-observation.json"
    path = next((tmp_path / "out" / "cases").glob(f"*/{filename}"))
    payload = json.loads(path.read_bytes())
    target = payload["plan"] if artifact == "nested_plan" else payload
    if version == "missing":
        target.pop("schema_version")
    else:
        target["schema_version"] = version
    path.write_text(json.dumps(payload))
    before = hashes(tmp_path)
    for execute in (False, True):
        with pytest.raises(ValueError):
            run_partial_proposals(
                config(selected_attributes=("applicability_present",)),
                resources=RESOURCES,
                output_directory=tmp_path / "out",
                examples=(example(),),
                execute=execute,
                revalidate_responses=True,
                gateway_factory=lambda: gateway,
            )
        assert hashes(tmp_path) == before
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("family", FAMILIES)
def test_writer_registry_drift_fails_before_inference_or_output(tmp_path, monkeypatch, family):
    monkeypatch.setitem(SCHEMA_POLICIES, family, SchemaPolicy(family, "2.0", ("2.0",), "test"))
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="writers may only emit"):
        if family == "partial-cascade-report":
            cascade.run(tmp_path)
        else:
            experiment(tmp_path, gateway=gateway)
    assert not list(tmp_path.iterdir())
    assert not gateway.requests


@pytest.mark.parametrize("nested", (False, True))
def test_observation_publication_guard_preserves_existing_bytes(tmp_path, nested):
    _, observed = partial_payloads()
    path = tmp_path / "partial-observation.json"
    _write_observation(path, observed)
    before = path.read_bytes()
    invalid = (
        observed.model_copy(
            update={"plan": observed.plan.model_copy(update={"schema_version": "1.0"})}
        )
        if nested
        else observed.model_copy(update={"schema_version": "1.0"})
    )
    with pytest.raises(ValueError, match="writers may only emit"):
        _write_observation(path, invalid)
    assert path.read_bytes() == before


REPORT_MUTATIONS = (
    ("schema_version", "1.0"),
    ("schema_version", "missing"),
    ("schema_version", "9.9"),
    ("executed", 0),
    ("executed", "false"),
    ("executed", "missing"),
    ("run_mode", "missing"),
    ("run_mode", "executed"),
    ("effective_configuration", "missing"),
    ("effective_configuration", {}),
    ("kind", "another-report"),
)


@pytest.mark.parametrize("field,value", REPORT_MUTATIONS)
def test_bad_reports_block_replay_and_resume_without_mutation_or_model_calls(
    tmp_path, field, value
):
    _, gateways = cascade.run(tmp_path, execute=False)
    root = tmp_path / "run"
    path = root / "partial-cascade-report.json"
    payload = json.loads(path.read_bytes())
    if value == "missing":
        del payload[field]
    else:
        payload[field] = value
    path.write_text(json.dumps(payload))
    before = hashes(root)
    with pytest.raises(ValueError):
        cascade.verify(root)
    for execute in (False, True):
        with pytest.raises(ValueError):
            cascade.run(tmp_path, gateways=gateways, execute=execute)
    assert hashes(root) == before
    assert not gateways.started and not gateways.requests


def test_current_report_cannot_present_a_planned_run_as_measured_zero(tmp_path):
    result, gateways = cascade.run(tmp_path, execute=False)
    root = tmp_path / "run"
    mixed, _, _ = cascade.verify(root)
    assert result["metrics"]["completion_rate"] is None
    assert result["metrics"]["benchmark_eligible"] is False
    result["metrics"] = mixed.metrics
    (root / "partial-cascade-report.json").write_text(json.dumps(result))
    before = hashes(root)
    with pytest.raises(ValueError, match="metrics/profile"):
        archive_partial_cascade(
            root=root, archive_directory=tmp_path / "archives", resources=RESOURCES
        )
    assert hashes(root) == before
    assert not (tmp_path / "archives").exists()
    assert not gateways.started


@pytest.mark.parametrize("artifact", ("plan", "observation", "nested_plan"))
def test_cascade_replay_rejects_obsolete_partial_artifacts(tmp_path, artifact):
    cascade.run(tmp_path)
    root = tmp_path / "run"
    filename = "partial-request-plan.json" if artifact == "plan" else "partial-observation.json"
    path = next(root.glob(f"stages/*/models/*/run-*/cases/*/{filename}"))
    payload = json.loads(path.read_bytes())
    target = payload["plan"] if artifact == "nested_plan" else payload
    target["schema_version"] = "1.0"
    path.write_text(json.dumps(payload))
    before = hashes(root)
    with pytest.raises(ValueError, match="schema_version"):
        cascade.verify(root)
    assert hashes(root) == before


def test_report_envelope_is_not_a_legacy_or_implicit_mode_reader():
    for payload in (None, [], "1.1", {}):
        with pytest.raises(ValueError):
            require_partial_cascade_report(payload)


@pytest.mark.parametrize("execute", (False, True))
def test_current_archive_keeps_measured_and_planned_results_distinct(tmp_path, execute):
    import zipfile

    from standards_atlas.application.semantic_qualification.partial_cascade_audit import (
        audit_partial_cascade,
    )

    result, gateways = cascade.run(tmp_path, execute=execute)
    archive = archive_partial_cascade(
        root=tmp_path / "run", archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    with zipfile.ZipFile(archive) as z:
        members = [name for name in z.namelist() if name.endswith("partial-cascade-report.json")]
        assert len(members) == 1
        summary = json.loads(z.read(members[0]))
        assert summary["metrics"] == result["metrics"]
        assert summary["metrics"]["completion_rate"] == (1 if execute else None)
        assert summary["metrics"]["measurement_status"] == (
            "observed_not_qualified" if execute else "not_executed"
        )
    calls = len(gateways.requests)
    audit = audit_partial_cascade(
        experiment=archive, resources=RESOURCES, output_directory=tmp_path / "audit"
    )
    assert audit["source_evidence_verified"] is True
    assert audit["source_execution_requested"] is execute
    assert audit["gateway_request_count"] == 0
    assert len(gateways.requests) == calls == (4 if execute else 0)


def test_history_reader_rejects_obsolete_observations_instead_of_emitting_signals(tmp_path):
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.review_package.history import (
        HistoryReader,
    )

    _, observed = partial_payloads()
    payload = observed.model_dump(mode="json")
    payload["schema_version"] = "1.0"
    reader = HistoryReader(SimpleNamespace(population=(), cases=()))
    with pytest.raises(ValueError, match="schema_version"):
        reader.consume(json.dumps(payload).encode(), location=tmp_path / "partial-observation.json")
    assert not reader.signals and not reader.artifacts


@pytest.mark.parametrize("version", ("1.1", "1.0"))
def test_focused_physical_budget_reader_does_not_accept_obsolete_plans(tmp_path, version):
    from types import SimpleNamespace

    from standards_atlas.application.semantic_qualification.focused_resolution import (
        _consumed,
        verify_global_focused_budget,
    )

    plan, _ = partial_payloads()
    payload = plan.model_dump(mode="json")
    payload["schema_version"] = version
    root = tmp_path / "stages/efficient/focused/model/question/run/cases/example"
    attempt = root / "executions/execution-1/attempt-001.json"
    attempt.parent.mkdir(parents=True)
    attempt.write_text("{}")
    (root / "partial-request-plan.json").write_text(json.dumps(payload))
    names = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    options = dict(
        read=lambda name: (tmp_path / name).read_bytes(),
        names=names,
        policy=SimpleNamespace(
            max_requests=1, max_cases=1, max_output_tokens=128, max_total_output_tokens=128
        ),
    )
    if version == "1.1":
        assert _consumed(tmp_path) == (1, {"a"})
        verify_global_focused_budget(**options)
    else:
        with pytest.raises(ValueError, match="schema_version"):
            _consumed(tmp_path)
        with pytest.raises(ValueError, match="schema_version"):
            verify_global_focused_budget(**options)
