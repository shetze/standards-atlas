from __future__ import annotations

from standards_atlas.application.assertion_qualification import (
    SERIES_F_PROMPTS,
    AssertionExperimentManifest,
    ExperimentBudget,
    ExperimentCaseBinding,
    build_series_f_plan,
    build_series_f_smoke_manifest,
)
from standards_atlas.domain.model import ContextInputFingerprints, ContextSourcePackageBinding


def _manifest(variant: str, prompt: str, *, cases: int = 2) -> AssertionExperimentManifest:
    bindings = tuple(
        ExperimentCaseBinding(
            document_key="DOC",
            clause_id=f"clause-{index}",
            source_package_binding=ContextSourcePackageBinding(
                package_sha256=f"sha256:{index + 1:064x}",
                document_key="DOC",
                document_revision="sha256:" + "d" * 64,
                target_clause_id=f"clause-{index}",
                target_reference=f"TEST:{index}",
                selection_contract_id="structured-context-selection-v1",
                selection_profile_id="assertion-context-selection-v1",
                selection_completeness="complete",
                fingerprints=ContextInputFingerprints(
                    source_state_sha256="sha256:" + "1" * 64,
                    candidate_space_sha256="sha256:" + "2" * 64,
                    selection_decision_sha256="sha256:" + "3" * 64,
                    actual_input_sha256="sha256:" + "4" * 64,
                ),
            ),
            rendered_request_sha256=f"{index + 10:064x}",
        )
        for index in range(cases)
    )
    return AssertionExperimentManifest(
        experiment_id=f"campaign-{variant}",
        code_revision="snapshot:abc",
        variant_id=variant,
        partition="development",
        golden_suite_id="suite",
        golden_suite_version="1.0.0",
        golden_suite_sha256="a" * 64,
        ontology_versions=("standards-atlas-core@2.0.0",),
        prompt_version=prompt,
        model_route="openai-compatible",
        runtime_config_sha256="b" * 64,
        requested_model="model",
        repetitions=1,
        conservative_call_upper_bound=cases,
        cases=bindings,
        budget=ExperimentBudget(max_calls=cases),
    )


def test_build_series_f_plan_binds_same_factor_prompt_comparison() -> None:
    manifests = tuple(_manifest(variant, prompt) for variant, prompt in SERIES_F_PROMPTS.items())
    smoke = _manifest("B0-AP02", SERIES_F_PROMPTS["B0-AP02"], cases=1).model_copy(
        update={"experiment_id": "campaign-b0-smoke"}
    )

    plan = build_series_f_plan(
        campaign_id="campaign",
        full_manifests=manifests,
        smoke_manifest=smoke,
    )

    assert [item.variant_id for item in plan.experiments] == ["B0-AP02", "B0-AP02", "P1", "P2"]
    assert [item.role for item in plan.experiments] == ["b0_smoke", "b0_full", "variant", "variant"]
    assert plan.holdout_access_permitted is False
    assert plan.automatic_knowledge_adoption is False
    assert plan.measured_results_present is False


def test_build_series_f_plan_rejects_non_prompt_factor_change() -> None:
    manifests = [_manifest(variant, prompt) for variant, prompt in SERIES_F_PROMPTS.items()]
    manifests[1] = manifests[1].model_copy(update={"requested_model": "other-model"})

    try:
        build_series_f_plan(campaign_id="campaign", full_manifests=tuple(manifests))
    except ValueError as exc:
        assert "non-prompt factors" in str(exc)
    else:
        raise AssertionError("expected non-prompt factor mismatch to be rejected")


def test_build_series_f_smoke_retains_full_golden_suite_binding() -> None:
    full = _manifest("B0-AP02", SERIES_F_PROMPTS["B0-AP02"], cases=3)
    smoke = build_series_f_smoke_manifest(
        full,
        experiment_id="campaign-b0-smoke",
        smoke_cases=1,
        budget=ExperimentBudget(max_calls=3),
    )

    assert len(smoke.cases) == 1
    assert smoke.golden_suite_sha256 == full.golden_suite_sha256
    assert smoke.golden_suite_id == full.golden_suite_id
    assert smoke.golden_suite_version == full.golden_suite_version
    assert smoke.ontology_versions == full.ontology_versions
    assert smoke.conservative_call_upper_bound == 1
