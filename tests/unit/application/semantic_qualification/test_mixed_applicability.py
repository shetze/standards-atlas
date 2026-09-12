"""Sparse gates retain the existing selective D4 OR (D3 AND D1) policy."""

import json
from contextlib import contextmanager

import pytest
from test_partial_cascade import Gateways, matrix, run, verify
from test_partial_observations import RESOURCES
from test_partial_proposals import FakeGateway

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.application.semantic_qualification.mixed_applicability import (
    run_mixed_applicability,
    verify_mixed_applicability,
)
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)


def detail_value(present, *, version):
    function = ["exclusion"] if present else []
    evidence = (
        [{"function": "exclusion", "text": "The requirements of 7 do not apply."}]
        if present
        else []
    )
    return (
        {
            "contains_clause_or_requirement_applicability": present,
            "other_applicability_targets": [],
            "applicability_functions": function,
            "evidence": evidence,
        }
        if version == 2
        else {
            "applicability_target": "clause_or_requirement" if present else "none",
            "applicability_functions": function,
            "evidence": evidence,
        }
    )


class DetailGateway(FakeGateway):
    def __init__(self, responses=None, failure=False):
        super().__init__()
        self.by_prompt = responses or {"detail-structure-aware-v4": True}
        self.failure = failure

    def generate_structured(self, request):
        if self.failure:
            self.requests.append(request)
            raise ValueError("simulated detail failure")
        present = self.by_prompt.get(request.prompt_version, False)
        self.responses = [
            detail_value(present, version=1 if request.prompt_version.endswith("-v1") else 2)
        ]
        return super().generate_structured(request)


@contextmanager
def detail_context(gateway, started, model):
    started.append(model.id)
    yield gateway


def policy_run(tmp_path, *, positive=False, responses=None, execute=True, failed=False):
    manifest = matrix(policy=True)
    changes = {m.id: {"applicability_present": positive} for m in manifest.models}
    run(tmp_path, manifest=manifest, gateways=Gateways(manifest, changes=changes), execute=execute)
    report, examples, _ = verify(tmp_path / "run")
    gateway = DetailGateway(responses, failure=failed)
    started = []
    policy = run_mixed_applicability(
        report=report,
        examples=examples,
        manifest=manifest,
        root=tmp_path / "run",
        resources=RESOURCES,
        gateway_context=lambda model: detail_context(gateway, started, model),
    )
    return policy, report, gateway, started


def verify_policy(root):
    report, examples, manifest = verify(root)
    return verify_mixed_applicability(
        read=lambda name: (root / name).read_bytes(),
        names={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()},
        report=report,
        examples=examples,
        manifest=manifest,
    )


def test_accepted_negative_gate_needs_no_detail_model_and_adopts_final_false(tmp_path):
    policy, report, gateway, started = policy_run(tmp_path)
    assert not gateway.requests and not started
    assert len(policy.cases) == 1 and policy.cases[0].final_present is False
    assert verify_policy(tmp_path / "run") == policy
    archive = archive_partial_cascade(
        root=tmp_path / "run", archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    candidate = load_qualification_knowledge(archive).candidates[0]
    assert candidate.patch.semantic.applicability_present is False
    assert "applicability_present" in candidate.patch.semantic.model_fields_set
    assert "applicability_functions" not in candidate.patch.semantic.model_fields_set


@pytest.mark.parametrize(
    "primary,rescue,confirmation,calls,result",
    [
        (True, False, False, 1, True),
        (False, True, True, 3, True),
        (False, True, False, 3, False),
        (False, False, True, 2, False),
    ],
)
def test_existing_selective_three_role_policy_is_unchanged(
    tmp_path, primary, rescue, confirmation, calls, result
):
    responses = {
        "detail-structure-aware-v4": primary,
        "detail-structure-aware-v3": rescue,
        "detail-structure-aware-v1": confirmation,
    }
    policy, _, gateway, _ = policy_run(tmp_path, positive=True, responses=responses)
    assert len(gateway.requests) == calls
    assert policy.cases[0].final_present is result
    assert verify_policy(tmp_path / "run") == policy


def test_unknown_gates_are_excluded_not_coerced_to_false(tmp_path):
    policy, mixed, gateway, started = policy_run(tmp_path, execute=False)
    assert not policy.cases and not gateway.requests and not started
    assert mixed.clauses[0].decision("applicability_present").value is None
    assert verify_policy(tmp_path / "run") == policy
    archive = archive_partial_cascade(
        root=tmp_path / "run", archive_directory=tmp_path / "archives", resources=RESOURCES
    )
    candidate = load_qualification_knowledge(archive).candidates[0]
    assert "applicability_present" not in candidate.patch.semantic.model_fields_set
    assert "enrichments.semantic.applicability_present" in candidate.not_evaluated


def test_detail_failures_stay_three_valued_and_do_not_overwrite_with_gate(tmp_path):
    policy, _, gateway, _ = policy_run(tmp_path, positive=True, failed=True)
    assert policy.cases[0].final_present is None
    assert verify_policy(tmp_path / "run") == policy


def test_completed_detail_resume_starts_no_gateway(tmp_path):
    policy, _, _, _ = policy_run(tmp_path, positive=True)
    report, examples, manifest = verify(tmp_path / "run")

    def never(model):
        pytest.fail("finished detail reports must be reused without starting a server")

    resumed = run_mixed_applicability(
        report=report,
        examples=examples,
        manifest=manifest,
        root=tmp_path / "run",
        resources=RESOURCES,
        gateway_context=never,
    )
    assert resumed.cases == policy.cases
    assert verify_policy(tmp_path / "run") == resumed


def test_tampered_detail_config_is_rejected(tmp_path):
    policy_run(tmp_path)
    path = tmp_path / "run/policy/primary/applicability-detail-enrichment.json"
    payload = json.loads(path.read_bytes())
    payload["config_sha256"] = "f" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="provenance"):
        verify_policy(tmp_path / "run")


def test_cost_report_includes_detail_calls_without_counting_them_as_cascade_votes(tmp_path):
    _, report, gateway, _ = policy_run(
        tmp_path,
        positive=True,
        responses={
            "detail-structure-aware-v4": False,
            "detail-structure-aware-v3": True,
            "detail-structure-aware-v1": True,
        },
    )
    costs = json.loads((tmp_path / "run/partial-cascade-costs.json").read_bytes())
    assert costs["cascade"]["request_count"] == 4
    assert costs["applicability_detail"]["request_count"] == len(gateway.requests) == 3
    assert costs["total"]["request_count"] == 7
    assert report.clauses[0].decision("applicability_present").observed_model_count == 4
