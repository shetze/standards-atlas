from standards_atlas.application.assertion_qualification.reference_corpus import (
    ExposureKind,
    ReferenceCandidate,
    ReferenceCorpusRequest,
    ReferenceExposure,
    build_reference_corpus_plan,
)


def candidate(clause, group, *, bearing=None, exposures=(), traits=()):
    return ReferenceCandidate(
        document_key="DOC",
        clause_id=clause,
        reference=clause,
        clause_type="requirement",
        primary_source_group=group,
        bearing_source_groups=tuple(bearing or (group,)),
        exposures=tuple(exposures),
        traits=tuple(traits),
    )


def test_grouped_partition_is_reproducible_and_context_disjoint():
    request = ReferenceCorpusRequest(
        plan_id="p",
        plan_version="1",
        seed=42,
        development_limit=2,
        holdout_limit=2,
        candidates=(
            candidate(
                "1",
                "g1",
                bearing=("g1", "intro"),
                exposures=(
                    ReferenceExposure(kind=ExposureKind.LEGACY_DEVELOPMENT, reference="old20"),
                ),
                traits=("work_product",),
            ),
            candidate("2", "intro", traits=("condition",)),
            candidate("3", "g3", traits=("empty",)),
            candidate("4", "g4", traits=("entity_only",)),
            candidate("5", "g5", traits=("note",)),
        ),
    )
    first = build_reference_corpus_plan(request)
    second = build_reference_corpus_plan(request)
    assert first == second
    assert first.plan_sha256 == second.plan_sha256
    assert not (
        {case.source_group for case in first.development}
        & {case.source_group for case in first.holdout}
    )
    exposed = next(e for e in first.exposure_register if e.clause_id == "1")
    linked = next(e for e in first.exposure_register if e.clause_id == "2")
    assert not exposed.holdout_independence_eligible
    assert not linked.holdout_independence_eligible
    assert all(c.expected_status == "pending" for c in (*first.development, *first.holdout))


def test_unknown_exposure_can_never_claim_independent_holdout():
    plan = build_reference_corpus_plan(
        ReferenceCorpusRequest(
            plan_id="p",
            plan_version="1",
            seed=1,
            development_limit=1,
            holdout_limit=1,
            candidates=(
                candidate(
                    "1",
                    "g1",
                    exposures=(
                        ReferenceExposure(kind=ExposureKind.UNKNOWN, reference="legacy session"),
                    ),
                ),
                candidate("2", "g2"),
                candidate("3", "g3"),
            ),
        )
    )
    row = next(e for e in plan.exposure_register if e.clause_id == "1")
    assert not row.holdout_independence_eligible
    assert "unknown" in row.blockers


def test_plan_hash_detects_tampering():
    from pydantic import ValidationError

    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusPlan,
    )

    plan = build_reference_corpus_plan(
        ReferenceCorpusRequest(
            plan_id="p",
            plan_version="1",
            seed=7,
            development_limit=1,
            holdout_limit=1,
            candidates=(
                candidate(
                    "1",
                    "g1",
                    exposures=(
                        ReferenceExposure(kind=ExposureKind.LEGACY_DEVELOPMENT, reference="old"),
                    ),
                ),
                candidate("2", "g2"),
            ),
        )
    )
    payload = plan.model_dump(mode="json")
    payload["development"][0]["source_group"] = "tampered"
    try:
        ReferenceCorpusPlan.model_validate(payload)
    except ValidationError as exc:
        assert "plan_sha256 does not match plan content" in str(exc)
    else:
        raise AssertionError("tampered plan was accepted")


def test_plan_hash_verification_uses_serialized_payload_and_reports_recovery() -> None:
    import json

    from pydantic import ValidationError

    from standards_atlas.application.assertion_qualification.reference_corpus import (
        ReferenceCorpusPlan,
    )

    plan = build_reference_corpus_plan(
        ReferenceCorpusRequest(
            plan_id="roundtrip",
            plan_version="1",
            seed=42,
            development_limit=1,
            holdout_limit=1,
            candidates=(candidate("1", "g1"), candidate("2", "g2")),
        )
    )
    serialized = (
        json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    )
    assert ReferenceCorpusPlan.model_validate_json(serialized).plan_sha256 == plan.plan_sha256

    tampered = json.loads(serialized)
    tampered["blockers"].append("manually changed")
    try:
        ReferenceCorpusPlan.model_validate(tampered)
    except ValidationError as exc:
        message = str(exc)
        assert "stored=" in message
        assert "expected=" in message
        assert "Regenerate partition-and-exposure.json" in message
    else:
        raise AssertionError("tampered serialized plan was accepted")
