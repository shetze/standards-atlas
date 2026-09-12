"""Bounded focused answers reuse original voters, prompts and archive contracts."""

import json

import pytest
import test_partial_cascade as fixtures

from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    FocusedResolutionPolicy,
    PartialAcceptanceProfile,
)
from standards_atlas.application.semantic_qualification.focused_resolution import FOCUSED_PROMPT
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_cascade_audit import (
    audit_partial_cascade,
)


class ReconsideringGateway(fixtures.Gateway):
    def __init__(self, *, changes=None, focus_changes=None, focus_error=False):
        super().__init__(changes=changes)
        self.focus_changes = focus_changes or {}
        self.focus_error = focus_error

    def generate_structured(self, request):
        if request.prompt_version != FOCUSED_PROMPT:
            return super().generate_structured(request)
        if self.focus_error:
            self.requests.append(request)
            raise ValueError("deliberate focused contract failure")
        prior = self.changes
        self.changes = self.focus_changes
        try:
            return super().generate_structured(request)
        finally:
            self.changes = prior


def setup(*, attribute="primary_function", focus_changes=None, error=False):
    manifest = fixtures.matrix()
    gateways = fixtures.Gateways(manifest)
    values = (
        {"primary_function": "description", "statement_functions": ["description"]}
        if attribute == "primary_function"
        else {
            "primary_knowledge_kind": "technique_or_measure",
            "knowledge_kinds": ["technique_or_measure"],
        }
    )
    for index, mid in enumerate(manifest.execution.stages[0].models):
        gateways.gateways[mid] = ReconsideringGateway(
            changes=values if index < 2 else {},
            focus_changes=focus_changes,
            focus_error=error,
        )
    return manifest, gateways


def profile(**budget):
    return PartialAcceptanceProfile(
        id="focused-test-v1", focused_resolution=FocusedResolutionPolicy(**budget)
    )


def execute(root, *, manifest=None, gateways=None, candidate=None, items=None, do_execute=True):
    manifest, gateways = (manifest, gateways) if manifest else setup()
    return run_partial_cascade(
        manifest=manifest,
        examples=items or (fixtures.example(),),
        output_directory=root,
        resources=fixtures.RESOURCES,
        execute=do_execute,
        gateway_context=gateways.context,
        acceptance_profile=candidate or profile(),
    ), gateways


def test_focused_answer_can_finish_efficient_without_extra_voters(tmp_path):
    root = tmp_path / "run"
    result, gateways = execute(root)
    assert len(result["stages"]) == 1 and result["metrics"]["completed_clause_count"] == 1
    assert len(gateways.requests) == 6
    focused = [r for r in gateways.requests if r.prompt_version == FOCUSED_PROMPT]
    assert len(focused) == 2
    assert all(
        r.output_schema["required"] == ["primary_function", "statement_functions"] for r in focused
    )
    mixed, _, _ = fixtures.verify(root)
    for key in ("primary_function", "primary_knowledge_kind", "applicability_present"):
        assert mixed.clauses[0].decision(key).observed_model_count == 4
        assert mixed.clauses[0].decision(key).stage == "efficient-local"
    costs = json.loads((root / "partial-cascade-costs.json").read_bytes())
    assert costs["focused_resolution"]["request_count"] == 2
    assert costs["cascade"]["request_count"] == 6
    assert costs["total"]["request_count"] == 6


def test_focused_successful_resume_has_no_additional_calls(tmp_path):
    manifest, gateways = setup()
    root = tmp_path / "run"
    execute(root, manifest=manifest, gateways=gateways)
    before = (root / "mixed-consensus-report.json").read_bytes()
    result, _ = execute(root, manifest=manifest, gateways=gateways)
    assert result["request_timing_current_invocation"]["request_count"] == 0
    assert len(gateways.requests) == 6
    assert (root / "mixed-consensus-report.json").read_bytes() == before
    fixtures.verify(root)


def test_failed_focus_is_not_retried_on_resume_or_counted_as_evidence(tmp_path):
    manifest, gateways = setup(error=True)
    root = tmp_path / "run"
    execute(root, manifest=manifest, gateways=gateways)
    total = len(gateways.requests)
    execute(root, manifest=manifest, gateways=gateways)
    assert len(gateways.requests) == total
    mixed, _, _ = fixtures.verify(root)
    value = mixed.clauses[0].decision("primary_function")
    # Four original + three intermediate voters, not attempts.
    assert value.observed_model_count <= 7


@pytest.mark.parametrize(
    "budget,expected",
    [
        ({"max_requests": 0}, 0),
        ({"max_cases": 0}, 0),
        ({"max_total_output_tokens": 0}, 0),
        ({"max_requests": 1}, 1),
        ({"max_total_output_tokens": 384}, 1),
        ({"max_requests": 2}, 2),
    ],
)
def test_focused_budget_is_a_hard_request_and_output_cap(tmp_path, budget, expected):
    result, gateways = execute(tmp_path / "run", candidate=profile(**budget))
    assert len([r for r in gateways.requests if r.prompt_version == FOCUSED_PROMPT]) == expected
    fixtures.verify(tmp_path / "run")
    record = result["stages"][0]["focused_resolution"]
    plan = json.loads((tmp_path / "run" / record["plan"]).read_bytes())
    assert plan["planned_request_count"] == expected


def test_max_cases_bounds_selection_across_multiple_clauses(tmp_path):
    _, gateways = execute(
        tmp_path / "run",
        candidate=profile(max_cases=1),
        items=(fixtures.example("a"), fixtures.example("b"), fixtures.example("c")),
    )
    assert len([r for r in gateways.requests if r.prompt_version == FOCUSED_PROMPT]) == 2
    fixtures.verify(tmp_path / "run")


def test_planning_does_not_create_focused_answers_or_start_server(tmp_path):
    report, gateways = execute(tmp_path / "run", do_execute=False)
    assert not gateways.started and report["metrics"]["completion_rate"] is None
    assert "focused_resolution" not in report["stages"][0]
    fixtures.verify(tmp_path / "run")


def test_known_taxonomy_primary_is_never_reasked_by_a_resolver(tmp_path):
    _, gateways = execute(tmp_path / "run", items=(fixtures.example(confirmed=True),))
    # Invalid companion sets can leave other attributes short of evidence;
    # a focused query may repair those, but never re-ask the fixed primary.
    assert all("primary_function" not in r.output_schema["required"] for r in gateways.requests)
    fixtures.verify(tmp_path / "run")


def test_knowledge_resolver_can_choose_other_category_or_abstain(tmp_path):
    for suffix, value in (("alternative", "role"), ("abstain", None)):
        manifest, gateways = setup(
            attribute="primary_knowledge_kind",
            focus_changes={
                "primary_knowledge_kind": value,
                "knowledge_kinds": [value] if value else [],
            },
        )
        result, _ = execute(tmp_path / suffix, manifest=manifest, gateways=gateways)
        assert all(
            j["target_attribute"] == "primary_knowledge_kind"
            for j in result["stages"][0]["focused_resolution"]["jobs"]
        )
        assert len([r for r in gateways.requests if r.prompt_version == FOCUSED_PROMPT]) == 2
        fixtures.verify(tmp_path / suffix)


def test_focused_audit_does_not_call_refinements_retired_or_independent_voters(tmp_path):
    root = tmp_path / "run"
    execute(root)
    audit = audit_partial_cascade(
        experiment=root, output_directory=tmp_path / "audit", resources=fixtures.RESOURCES
    )
    work = audit["physical_work"]
    assert work["cascade_total"]["request_count"] == 6
    assert work["nominal_stage_model_clause_combinations"] == 4
    assert work["focused_planned_model_clause_combinations"] == 2
    assert work["retired_revisions"]["request_count"] == 0
    assert work["source_summary_timing_matches"]
    assert all(m["same_voter_refinement"] for m in audit["stages"][0]["focused_models"])


@pytest.mark.parametrize("target", ["profile", "before", "plan", "attempt"])
def test_focused_archive_rejects_tampered_policy_plan_source_or_extra_work(tmp_path, target):
    root = tmp_path / "run"
    report, _ = execute(root)
    focus = report["stages"][0]["focused_resolution"]
    if target == "profile":
        path = root / "partial-cascade-plan.json"
        value = json.loads(path.read_bytes())
        value["acceptance_profile"]["statement_two_thirds"] = True
    elif target == "before":
        path = root / focus["before_report"]
        value = json.loads(path.read_bytes())
        value["matrix_id"] += "changed"
    elif target == "plan":
        path = root / focus["plan"]
        value = json.loads(path.read_bytes())
        value["jobs"][0]["attributes"] = ["applicability_present"]
    else:
        original = next(root.glob("stages/*/focused/**/attempt-001.json"))
        path = original.with_name("attempt-002.json")
        value = json.loads(original.read_bytes())
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        fixtures.verify(root)


def test_profile_identity_must_not_change_on_resume(tmp_path):
    root = tmp_path / "run"
    execute(root)
    with pytest.raises(ValueError, match="identity changed"):
        execute(root, candidate=profile(max_requests=1))


def test_global_focus_budget_survives_repaired_base_revision(tmp_path):
    manifest, gateways = setup(error=True)
    first_id = manifest.execution.stages[0].models[0]
    gateways.gateways[first_id].errors = True
    root = tmp_path / "run"
    policy = profile(max_requests=2)
    execute(root, manifest=manifest, gateways=gateways, candidate=policy)
    before = sum(r.prompt_version == FOCUSED_PROMPT for r in gateways.requests)
    assert before == 2
    gateways.gateways[first_id].errors = False
    for mid in manifest.execution.stages[0].models:
        gateways.gateways[mid].focus_error = False
    execute(root, manifest=manifest, gateways=gateways, candidate=policy)
    assert sum(r.prompt_version == FOCUSED_PROMPT for r in gateways.requests) == before
    fixtures.verify(root)


def test_focused_archive_adoption_preserves_voter_count_and_gate_boundary(tmp_path):
    root = tmp_path / "run"
    execute(root)
    archive = fixtures.archive_partial_cascade(
        root=root, archive_directory=tmp_path / "archives", resources=fixtures.RESOURCES
    )
    batch = fixtures.load_qualification_knowledge(archive)
    candidate = batch.candidates[0]
    primary = next(a for a in candidate.attributes if a.path.endswith(".primary_function"))
    assert primary.decision.valid_votes == 4
    assert "applicability_present" not in candidate.patch.semantic.model_fields_set
