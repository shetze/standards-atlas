"""Gateway-count, durability, resume, isolation and CLI tests for Slice 4."""

import copy
import hashlib
import json
from dataclasses import asdict, replace

import pytest
from test_partial_observations import RESOURCES, config, example
from typer.testing import CliRunner

from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
    StructuredGenerationResult,
    TokenUsage,
)
from standards_atlas.application.schema import SCHEMA_POLICIES
from standards_atlas.application.semantic_qualification.partial_observations import (
    PartialObservation,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    load_partial_inputs,
    run_partial_proposals,
)
from standards_atlas.application.semantic_qualification.proposals import BaselineProposalGenerator
from standards_atlas.cli import app


class FakeGateway:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.requests = []

    def health(self):
        return LlmHealth(available=True, models=("small",))

    def generate_structured(self, request):
        self.requests.append(request)
        response = (
            self.responses.pop(0)
            if self.responses
            else {
                key: (
                    False
                    if key.endswith("_present")
                    else []
                    if key
                    in {
                        "statement_functions",
                        "knowledge_kinds",
                        "process_functions",
                        "role_relations",
                    }
                    else None
                )
                for key in request.output_schema["required"]
            }
        )
        if isinstance(response, BaseException):
            raise response
        return StructuredGenerationResult(
            value=response,
            model=request.model,
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="provider-hash",
            raw_response_hash="raw-hash",
            duration_ms=250,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=12, total_tokens=112),
            raw_response=json.dumps(response),
        )


def experiment(tmp_path, *, cfg=None, items=None, gateway=None, execute=True):
    gateway = gateway or FakeGateway()
    report = run_partial_proposals(
        cfg or config(selected_attributes=("applicability_present",)),
        resources=RESOURCES,
        output_directory=tmp_path / "out",
        examples=items or (example(),),
        execute=execute,
        gateway_factory=lambda: gateway,
    )
    return report, gateway


def observations(tmp_path):
    return [
        PartialObservation.model_validate_json(path.read_text())
        for path in sorted((tmp_path / "out" / "cases").glob("*/partial-observation.json"))
    ]


def test_all_open_attributes_are_one_grouped_request_not_nine_calls(tmp_path):
    report, gateway = experiment(tmp_path, cfg=config())
    assert len(gateway.requests) == 1
    assert len(gateway.requests[0].output_schema["required"]) == 9
    assert report["logical_model_observation_count"] == 1
    assert report["request_timing"]["request_count"] == 1
    assert len(observations(tmp_path)) == 1
    assert not list((tmp_path / "out").rglob("evaluation.yaml"))
    assert not list((tmp_path / "out").rglob("consensus-report.json"))
    assert report["production_early_exit_count"] is None


def test_selected_fixed_primary_never_constructs_gateway_or_fallback_request(tmp_path):
    def never_called():
        pytest.fail("gateway should not be constructed")

    report = run_partial_proposals(
        config(selected_attributes=("primary_function",)),
        resources=RESOURCES,
        output_directory=tmp_path / "out",
        examples=(example(confirmed=True),),
        execute=True,
        gateway_factory=never_called,
    )
    assert report["status_counts"] == {"not_requested": 1}
    assert report["planned_request_count"] == 0
    assert report["logical_model_observation_count"] == 0
    assert report["request_timing"]["request_count"] == 0
    assert not list((tmp_path / "out").rglob("request.json"))
    assert observations(tmp_path)[0].model_evidence() == {}


def test_confirmed_primary_skips_only_primary_not_other_work(tmp_path):
    report, gateway = experiment(
        tmp_path,
        cfg=config(),
        items=(example(confirmed=True),),
        gateway=FakeGateway(
            [
                {
                    "statement_functions": ["definition", "note"],
                    "primary_knowledge_kind": "process",
                    "knowledge_kinds": ["process"],
                    "primary_process_function": None,
                    "process_functions": [],
                    "applicability_present": True,
                    "role_semantics_present": False,
                    "role_relations": [],
                }
            ]
        ),
    )
    assert report["status_counts"] == {"evaluated": 1}
    assert len(gateway.requests) == 1
    assert len(gateway.requests[0].output_schema["required"]) == 8
    assert "primary_function" not in observations(tmp_path)[0].model_evidence()


def test_planning_is_model_free_and_identical_plan_can_then_execute(tmp_path):
    first, gateway = experiment(tmp_path, execute=False)
    assert first["planned_request_count"] == 1
    assert first["status_counts"] == {"planned": 1}
    assert not gateway.requests
    assert not observations(tmp_path)
    before = (tmp_path / "out" / "partial-run-plan.json").read_bytes()
    report, _ = experiment(tmp_path, gateway=gateway)
    assert report["status_counts"] == {"evaluated": 1}
    assert len(gateway.requests) == 1
    assert before == (tmp_path / "out" / "partial-run-plan.json").read_bytes()


def test_resume_has_no_gateway_calls_no_extra_voters_and_preserves_observation_bytes(tmp_path):
    first, gateway = experiment(tmp_path)
    before = observations(tmp_path)[0]
    path = next((tmp_path / "out" / "cases").glob("*/partial-observation.json"))
    before_bytes = path.read_bytes()
    report, _ = experiment(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 1
    assert report["request_timing"]["request_count"] == 0
    assert report["new_observation_count"] == 0
    assert report["reused_observation_count"] == 1
    assert report["logical_model_observation_count"] == 1
    assert first["logical_model_observation_count"] == 1
    assert observations(tmp_path)[0].observation_id == before.observation_id
    assert path.read_bytes() == before_bytes


def test_retry_records_two_attempts_but_only_one_logical_voter(tmp_path):
    gateway = FakeGateway(
        [
            LlmUnavailableError("temporary"),
            {"applicability_present": True},
        ]
    )
    report, gateway = experiment(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 2
    assert report["request_timing"]["failed_request_count"] == 1
    assert report["request_timing"]["fresh_measured_request_count"] == 1
    assert report["logical_model_observation_count"] == 1
    assert len(list((tmp_path / "out").rglob("attempt-*.json"))) == 2
    assert len(observations(tmp_path)) == 1
    assert observations(tmp_path)[0].model_evidence() == {"applicability_present": True}


def test_truncation_retry_changes_budget_but_not_question_group_or_voter(tmp_path):
    gateway = FakeGateway(
        [
            LlmResponseError(
                "truncated",
                finish_reason="length",
                raw_content='{"applicability_present":',
                raw_response={"incomplete": True},
            ),
            {"applicability_present": False},
        ]
    )
    report, _ = experiment(
        tmp_path,
        cfg=config(
            selected_attributes=("applicability_present",),
            max_tokens=128,
            truncation_retry_max_tokens=512,
        ),
        gateway=gateway,
    )
    assert [r.max_tokens for r in gateway.requests] == [128, 512]
    assert gateway.requests[0].output_schema == gateway.requests[1].output_schema
    assert report["logical_model_observation_count"] == 1
    assert report["request_timing"]["request_count"] == 2
    assert len({o.voter_key for o in observations(tmp_path)}) == 1


def test_cached_response_is_not_fresh_inference_or_a_second_voter(tmp_path):
    class CachedGateway(FakeGateway):
        def generate_structured(self, request):
            return replace(super().generate_structured(request), cached=True)

    report, _ = experiment(tmp_path, gateway=CachedGateway())
    assert report["request_timing"]["fresh_response_count"] == 0
    assert report["request_timing"]["cached_response_count"] == 1
    assert report["request_timing"]["fresh_inference_duration_seconds"] is None
    assert report["logical_model_observation_count"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"applicability_present": "false"},
        {"applicability_present": False, "role_semantics_present": False},
        LlmTimeoutError("timeout"),
    ],
)
def test_invalid_group_does_not_vote_and_next_clause_still_runs(tmp_path, bad):
    gateway = FakeGateway([bad, {"applicability_present": True}])
    report, _ = experiment(tmp_path, gateway=gateway, items=(example("a"), example("b")))
    assert report["accounted_count"] == report["selected_count"] == 2
    assert report["status_counts"] == {"failed": 1, "evaluated": 1}
    failed = next(o for o in observations(tmp_path) if o.outcome == "failed")
    assert failed.model_evidence() == {}
    assert failed.values == {}
    assert report["request_timing"]["request_count"] == 2
    expected_timed = 1 if isinstance(bad, Exception) else 2
    assert report["request_timing"]["fresh_measured_request_count"] == expected_timed


def test_resume_retries_only_failed_cases_without_losing_attempt_history(tmp_path):
    gateway = FakeGateway([{}, {"applicability_present": True}])
    first, _ = experiment(tmp_path, gateway=gateway, items=(example("a"), example("b")))
    assert first["failed_observation_count"] == 1
    second, _ = experiment(tmp_path, gateway=gateway, items=(example("a"), example("b")))
    assert second["reused_observation_count"] == 1
    assert second["new_observation_count"] == 1
    assert second["logical_model_observation_count"] == 2
    assert second["status_counts"] == {"evaluated": 2}
    assert len(list((tmp_path / "out").rglob("attempt-*.json"))) == 3
    assert len(observations(tmp_path)) == 2


def test_interrupt_keeps_attempt_trace_and_does_not_leave_lock(tmp_path):
    gateway = FakeGateway([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        experiment(tmp_path, gateway=gateway)
    assert not (tmp_path / "out" / ".partial-run.lock").exists()
    assert len(list((tmp_path / "out").rglob("attempt-*.json"))) == 1
    report, gateway = experiment(tmp_path, gateway=gateway)
    assert report["status_counts"] == {"evaluated": 1}


@pytest.mark.parametrize(
    "change",
    [
        {"seed": 42},
        {"max_tokens": 1536},
        {"selected_attributes": ("role_semantics_present",)},
        {"temperature": 0.5},
        {"truncation_retry_max_tokens": 2048},
    ],
)
def test_changed_experiment_rejects_stale_reuse_before_gateway_calls(tmp_path, change):
    _, gateway = experiment(tmp_path)
    kwargs = {"selected_attributes": ("applicability_present",), **change}
    before = (tmp_path / "out" / "partial-run-plan.json").read_bytes()
    with pytest.raises(ValueError, match="identity changed"):
        experiment(tmp_path, cfg=config(**kwargs), gateway=gateway)
    assert len(gateway.requests) == 1
    assert (tmp_path / "out" / "partial-run-plan.json").read_bytes() == before


def test_changed_source_rejects_stale_reuse(tmp_path):
    _, gateway = experiment(tmp_path)
    with pytest.raises(ValueError, match="identity changed"):
        experiment(tmp_path, items=(example(heading="other"),), gateway=gateway)
    assert len(gateway.requests) == 1


def test_corrupted_success_is_not_silently_reused(tmp_path):
    _, gateway = experiment(tmp_path)
    path = next((tmp_path / "out" / "cases").glob("*/response.json"))
    payload = json.loads(path.read_text())
    payload["value"]["applicability_present"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum mismatch"):
        experiment(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 1


def test_corrupted_request_fingerprint_is_not_silently_rewritten(tmp_path):
    _, gateway = experiment(tmp_path)
    path = next((tmp_path / "out" / "cases").glob("*/request.json"))
    payload = json.loads(path.read_text())
    payload["metadata"]["qualification_input_fingerprint"] = "bad"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="request fingerprint mismatch"):
        experiment(tmp_path, gateway=gateway)


def test_existing_full_answer_directory_is_never_reused_or_overwritten(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    (root / "evaluation.yaml").write_text("old complete proposal")
    with pytest.raises(ValueError, match="without a matching run plan"):
        experiment(tmp_path)
    assert (root / "evaluation.yaml").read_text() == "old complete proposal"


def test_full_generator_rejects_new_partial_task(tmp_path):
    with pytest.raises(ValueError, match="partial-proposals"):
        BaselineProposalGenerator(FakeGateway()).run(
            config(),
            resources=RESOURCES,
            corpus_root=tmp_path,
            output_root=tmp_path,
        )


def test_ineligible_clauses_remain_bilanaced_without_inference_or_negative_votes(tmp_path):
    report, gateway = experiment(tmp_path, items=(example(content_profile="table_dominant"),))
    assert report["status_counts"] == {"ineligible": 1}
    assert report["accounted_count"] == report["selected_count"] == 1
    assert report["planned_request_count"] == report["logical_model_observation_count"] == 0
    assert not gateway.requests
    assert not observations(tmp_path)


def test_limit_is_an_explicit_subset_with_original_population_visible(tmp_path):
    report, gateway = experiment(
        tmp_path,
        cfg=config(limit=1, selected_attributes=("applicability_present",)),
        items=(example("a"), example("b")),
    )
    assert report["input_count"] == 2
    assert report["selected_count"] == 1
    assert report["accounted_count"] == 1
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("case", ["duplicate_example", "duplicate_clause", "bad_hash"])
def test_invalid_inputs_fail_before_writing_or_creating_gateway(tmp_path, case):
    first = example()
    if case == "duplicate_example":
        items = (first, first)
    elif case == "duplicate_clause":
        items = (first, replace(first, id="other"))
    else:
        data = copy.deepcopy(first.input)
        data["content"]["hash"] = "sha256:" + "0" * 64
        items = (replace(first, input=data),)
    with pytest.raises(ValueError):
        experiment(tmp_path, items=items)
    assert not (tmp_path / "out").exists()


def test_schema_inventory_registers_new_internal_contracts_without_document_bump():
    for family in ("partial-request-plan", "partial-semantic-observation"):
        assert SCHEMA_POLICIES[family].current == "1.1"
    assert SCHEMA_POLICIES["partial-proposal-run"].current == "1.0"
    assert SCHEMA_POLICIES["engineering-document"].current == 9


def write_dataset(tmp_path, **options):
    item = example(**options)
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {"task": "semantic-profile-classification", "version": "1", "examples": [asdict(item)]}
        )
    )
    return path


def test_dataset_loader_removes_expected_and_tags(tmp_path):
    path = write_dataset(tmp_path)
    loaded = load_partial_inputs(dataset=path)
    assert loaded.examples[0].expected == {}
    assert loaded.examples[0].tags == ()
    assert loaded.dataset_version == "1"
    assert loaded.fingerprints[str(path)] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_cli_defaults_to_no_inference_even_with_nonexistent_runtime_config(tmp_path):
    path = write_dataset(tmp_path)
    before = path.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Grouped requests planned : 1" in result.output
    assert "Gateway calls this time  : 0" in result.output
    assert path.read_bytes() == before


def test_cli_zero_question_execute_does_not_read_runtime_configuration(tmp_path):
    path = write_dataset(tmp_path, confirmed=True)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--execute",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
            "--attributes",
            "primary_function",
            "--config",
            str(tmp_path / "nonexistent.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Grouped requests planned : 0" in result.output
    assert "not_requested" in result.output


@pytest.mark.parametrize(
    "attributes",
    [
        "applicability_functions",
        "role_relation_types",
        "",
        "foo",
    ],
)
def test_cli_rejects_old_or_invalid_attributes(tmp_path, attributes):
    path = write_dataset(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
            "--attributes",
            attributes,
        ],
    )
    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_cli_requires_exactly_one_input(tmp_path):
    path = write_dataset(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(path),
            "--run",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
        ],
    )
    assert result.exit_code == 2
    assert "exactly one" in result.output


def test_archive_loader_retains_selection_and_source_versions(tmp_path):
    from test_taxonomy_diagnostics import run_archive

    path = run_archive(tmp_path)
    before = path.read_bytes()
    source = load_partial_inputs(run=path)
    assert len(source.examples) == 2  # Frozen archive selection, not all dataset clauses.
    assert source.corpus_id == "corpus"
    assert source.dataset_version == "1.0.0"
    assert all(not e.expected and not e.tags for e in source.examples)
    assert path.read_bytes() == before


def test_provider_cannot_claim_a_different_model_under_the_requested_voter(tmp_path):
    class WrongModelGateway(FakeGateway):
        def generate_structured(self, request):
            return replace(super().generate_structured(request), model="different-model")

    report, _ = experiment(tmp_path, gateway=WrongModelGateway())
    assert report["status_counts"] == {"failed": 1}
    assert observations(tmp_path)[0].model_evidence() == {}


def test_corrupted_source_plan_is_not_silently_replaced(tmp_path):
    _, gateway = experiment(tmp_path)
    path = next((tmp_path / "out" / "cases").glob("*/partial-request-plan.json"))
    payload = json.loads(path.read_text())
    payload["selected_attributes"] = []
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="source-bound identity"):
        experiment(tmp_path, gateway=gateway)
    assert len(gateway.requests) == 1


def test_active_writer_lock_prevents_parallel_resume(tmp_path):
    _, gateway = experiment(tmp_path, execute=False)
    lock = tmp_path / "out" / ".partial-run.lock"
    lock.write_text("another-process")
    with pytest.raises(ValueError, match="locked"):
        experiment(tmp_path, gateway=gateway)
    assert lock.read_text() == "another-process"
    assert not gateway.requests


def test_cli_execute_uses_requested_model_and_stops_only_a_new_server(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from standards_atlas.adapters.llm import LlmConfig
    from standards_atlas.cli.commands.evaluation_commands import partial_proposals as command

    path = write_dataset(tmp_path)
    gateway = FakeGateway()
    events = []

    class Manager:
        def __init__(self, cfg):
            assert cfg.model == cfg.server.model == "small"

        def status(self):
            return SimpleNamespace(running=False)

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(command.LlmConfig, "load", lambda path: LlmConfig())
    monkeypatch.setattr(command, "RamaLamaServerManager", Manager)
    monkeypatch.setattr(command, "OpenAICompatibleLlmGateway", lambda cfg: gateway)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
            "--attributes",
            "applicability_present",
            "--execute",
        ],
    )
    assert result.exit_code == 0, result.output
    assert events == ["start", "stop"]
    assert len(gateway.requests) == 1
    events.clear()
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "partial-proposals",
            "--dataset",
            str(path),
            "--output",
            str(tmp_path / "out"),
            "--model",
            "small",
            "--attributes",
            "applicability_present",
            "--execute",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not events
    assert len(gateway.requests) == 1
