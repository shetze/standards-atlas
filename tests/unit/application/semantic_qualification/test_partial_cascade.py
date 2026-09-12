"""Slice 5 operational routing, immutable evidence and canonical roundtrips."""

import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from test_mixed_consensus import VALUES
from test_partial_observations import RESOURCES, example
from test_partial_proposals import FakeGateway

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    CompletionProfile,
)
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
    verify_partial_cascade,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference, TextBlock
from standards_atlas.domain.model.enrichment_patch import merge_generated_enrichments


def matrix(*, policy=False):
    manifest = QualificationMatrixManifest.load(
        Path("manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml")
    )
    data = manifest.model_dump(mode="json")
    data.update(corpus_id="test-partial", dataset_version="1")
    data["applicability_decision_policy"]["enabled"] = policy
    return QualificationMatrixManifest.model_validate(data)


class Gateway(FakeGateway):
    def __init__(self, *, changes=None, errors=False):
        super().__init__()
        self.changes = changes or {}
        self.errors = errors

    def generate_structured(self, request):
        if self.errors:
            self.requests.append(request)
            raise ValueError("simulated invalid observation")
        self.responses = [
            {k: self.changes.get(k, VALUES[k]) for k in request.output_schema["required"]}
        ]
        return super().generate_structured(request)


class Gateways:
    def __init__(self, manifest=None, *, changes=None, errors=False):
        self.manifest = manifest or matrix()
        self.gateways = {
            m.id: Gateway(changes=(changes or {}).get(m.id), errors=errors)
            for m in self.manifest.models
        }
        self.started = []

    @contextmanager
    def context(self, model):
        self.started.append(model.id)
        yield self.gateways[model.id]

    @property
    def requests(self):
        return [r for gateway in self.gateways.values() for r in gateway.requests]


def run(tmp_path, *, items=None, manifest=None, gateways=None, execute=True, profile=None):
    manifest = manifest or matrix()
    gateways = gateways or Gateways(manifest)
    report = run_partial_cascade(
        manifest=manifest,
        examples=items or (example(),),
        resources=RESOURCES,
        output_directory=tmp_path / "run",
        execute=execute,
        gateway_context=gateways.context,
        completion_profile=profile,
    )
    return report, gateways


def verify(root):
    return verify_partial_cascade(
        read=lambda name: (root / name).read_bytes(),
        names={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()},
        resources=RESOURCES,
    )


def test_one_stage_really_exits_without_starting_intermediate_models(tmp_path):
    result, gateways = run(tmp_path)
    assert len(gateways.started) == 4 and len(gateways.requests) == 4
    assert len(result["stages"]) == 1
    assert result["stages"][0]["newly_completed"] == 1
    assert result["request_timing_current_invocation"]["request_count"] == 4
    mixed, _, _ = verify(tmp_path / "run")
    assert mixed.completed_count == 1
    assert mixed.clauses[0].decision("applicability_present").value is False


def test_predecided_focused_profile_calls_no_models_and_does_not_claim_benchmark(tmp_path):
    result, gateways = run(
        tmp_path,
        items=(example(confirmed=True),),
        profile=CompletionProfile(required_attributes=("primary_function",)),
    )
    assert not gateways.started and not gateways.requests
    assert result["metrics"]["benchmark_eligible"] is False
    assert result["stages"][0]["newly_completed"] == 1
    assert result["stages"][0]["models"] == []
    verify(tmp_path / "run")


def test_planning_never_starts_gateway_and_preserves_all_selected_clauses(tmp_path):
    result, gateways = run(
        tmp_path, items=(example("a"), example("b", confirmed=True)), execute=False
    )
    assert not gateways.started
    assert result["metrics"]["selected_clause_count"] == 2
    assert result["stages"][0]["newly_completed"] == 0
    assert len(result["stages"]) == 1
    verify(tmp_path / "run")


def test_planning_then_execution_and_resume_add_no_fake_votes(tmp_path):
    run(tmp_path, execute=False)
    first, gateways = run(tmp_path)
    original = (tmp_path / "run/mixed-consensus-report.json").read_bytes()
    resumed, _ = run(tmp_path, gateways=gateways)
    assert len(gateways.started) == 4
    assert resumed["request_timing_current_invocation"]["request_count"] == 0
    assert resumed["cascade_request_timing_all_executions"]["request_count"] == 4
    assert (tmp_path / "run/mixed-consensus-report.json").read_bytes() == original
    verify(tmp_path / "run")


def test_confirmed_primary_is_not_requested_and_not_counted_as_a_model_vote(tmp_path):
    _, gateways = run(tmp_path, items=(example(confirmed=True),))
    assert all("primary_function" not in r.output_schema["required"] for r in gateways.requests)
    mixed, _, _ = verify(tmp_path / "run")
    assert mixed.clauses[0].decision("primary_function").observed_model_count == 0
    assert mixed.clauses[0].decision("statement_functions").observed_model_count == 4


def test_second_stage_only_requests_the_attribute_still_open(tmp_path):
    manifest = matrix()
    first_model = manifest.execution.stages[0].models[0]
    gateways = Gateways(manifest, changes={first_model: {"applicability_present": True}})
    result, _ = run(tmp_path, manifest=manifest, gateways=gateways)
    assert len(result["stages"]) == 2
    assert result["stages"][0]["newly_completed"] == 0
    second = manifest.execution.stages[1]
    for model_id in second.models:
        required = gateways.gateways[model_id].requests[0].output_schema["required"]
        assert required == ["applicability_present"]
    mixed, _, _ = verify(tmp_path / "run")
    assert mixed.completed_count == 1
    assert mixed.clauses[0].decision("primary_knowledge_kind").stage == "efficient-local"
    assert mixed.clauses[0].decision("primary_knowledge_kind").observed_model_count == 4
    assert mixed.clauses[0].decision("applicability_present").observed_model_count == 7


def test_missing_observations_remain_open_in_all_stages(tmp_path):
    result, _ = run(tmp_path, gateways=Gateways(errors=True))
    assert len(result["stages"]) == 3
    assert all(s["unresolved"] == 1 for s in result["stages"])
    mixed, _, _ = verify(tmp_path / "run")
    assert mixed.clauses[0].decision("applicability_present").value is None


@pytest.mark.parametrize(
    "member",
    [
        "mixed-consensus-report.json",
        "partial-cascade-inputs.json",
        "partial-cascade-resources.json",
        "partial-cascade-report.json",
    ],
)
def test_modified_archive_sources_or_decisions_are_rejected_before_adoption(tmp_path, member):
    run(tmp_path)
    path = tmp_path / "run" / member
    payload = json.loads(path.read_bytes())
    if member.endswith("inputs.json"):
        payload[0]["input"]["content"]["text"] += " Changed."
    elif member.endswith("resources.json"):
        payload["modified"] = True
    elif member.endswith("report.json") and "metrics" in payload:
        payload["metrics"]["clause_count"] = 100
    else:
        payload["matrix_id"] = "modified"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        verify(tmp_path / "run")


def test_raw_response_change_cannot_be_hidden_by_summary_consensus(tmp_path):
    run(tmp_path)
    path = next((tmp_path / "run/stages").glob("*/models/*/*/cases/*/response.json"))
    payload = json.loads(path.read_bytes())
    payload["value"]["applicability_present"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="response"):
        verify(tmp_path / "run")


def test_archive_adoption_does_not_publish_a_negative_gate_without_policy(tmp_path):
    run(tmp_path)
    archive = archive_partial_cascade(
        root=tmp_path / "run", archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    batch = load_qualification_knowledge(archive)
    assert len(batch.candidates) == batch.selected_clause_count == 1
    candidate = batch.candidates[0]
    assert "applicability_present" not in candidate.patch.semantic.model_fields_set
    app = next(a for a in candidate.attributes if a.path.endswith(".applicability_present"))
    assert app.availability == "unknown" and app.decision.valid_votes is None
    primary = next(a for a in candidate.attributes if a.path.endswith(".primary_function"))
    assert primary.decision.valid_votes == 4


def test_pure_deterministic_archive_adopts_primary_without_inventing_complete_set(tmp_path):
    item = example(confirmed=True)
    run(
        tmp_path,
        items=(item,),
        profile=CompletionProfile(required_attributes=("primary_function",)),
    )
    archive = archive_partial_cascade(
        root=tmp_path / "run", archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    batch = load_qualification_knowledge(archive)
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.model_fields_set == {"primary_function"}
    attribute = candidate.attributes[0]
    assert attribute.method.value == "deterministic"
    assert attribute.decision.valid_votes is None and not attribute.decision.model_ids
    clause = Clause(
        id=ClauseId(value="a"),
        reference=StandardReference(standard="TEST", clause="3.1"),
        clause_type=ClauseType.TERM,
        heading="process",
        content=(TextBlock(id="text", text=item.input["content"]["text"]),),
    )
    merged = merge_generated_enrichments(clause, candidate.patch, candidate.attributes).clause
    assert merged.enrichments.semantic.primary_function.value == "definition"
    assert merged.enrichments.semantic.statement_functions == ()
    path = "enrichments.semantic.statement_functions"
    assert merged.provenance.availability(path) == "not_evaluated"
    restored = Clause.model_validate_json(merged.model_dump_json())
    assert restored == merged
    assert (
        merge_generated_enrichments(restored, candidate.patch, candidate.attributes).clause
        == merged
    )


def test_repaired_failure_preserves_old_stage_revisions_without_duplicate_votes(tmp_path):
    manifest = matrix()
    first = manifest.execution.stages[0].models
    gateways = Gateways(
        manifest, changes={key: {"applicability_present": True} for key in first[:2]}
    )
    gateways.gateways[first[3]].errors = True
    original, _ = run(tmp_path, manifest=manifest, gateways=gateways)
    assert len(original["stages"]) == 3
    initial_calls = len(gateways.requests)
    gateways.gateways[first[3]].errors = False
    resumed, _ = run(tmp_path, manifest=manifest, gateways=gateways)
    # One repaired + five changed-stage requests.
    assert len(gateways.requests) - initial_calls == 6
    second = manifest.execution.stages[1]
    for model_id in second.models:
        revisions = list((tmp_path / f"run/stages/{second.id}/models/{model_id}").glob("run-*"))
        assert len(revisions) == 2
    mixed, _, _ = verify(tmp_path / "run")
    assert mixed.clauses[0].decision("applicability_present").observed_model_count == 9
    recorded = resumed["cascade_request_timing_all_executions"]["request_count"]
    assert recorded == len(gateways.requests)


def test_stage_traversal_is_rejected_before_creating_files(tmp_path):
    data = matrix().model_dump(mode="json")
    data["execution"]["stages"][0]["id"] = "../unsafe"
    unsafe = QualificationMatrixManifest.model_validate(data)
    with pytest.raises(ValueError, match="unsafe"):
        run(tmp_path, manifest=unsafe)
    assert not (tmp_path / "run").exists()


def test_globally_repeated_clause_id_is_not_silently_overwritten(tmp_path):
    one = example("a")
    two = replace(
        one,
        id="another-example",
        input={**one.input, "context": {**one.input["context"], "document_key": "OTHER"}},
    )
    with pytest.raises(ValueError, match="globally unique"):
        run(tmp_path, items=(one, two), execute=False)
