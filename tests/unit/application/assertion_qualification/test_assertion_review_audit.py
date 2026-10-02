from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.assertion_qualification.audit import (
    AssertionReviewAudit,
    canonical_sha256,
    review_case_source_sha256,
)
from standards_atlas.application.assertion_qualification.io import (
    copy_assertion_review_audit,
    ensure_distinct_output,
    load_assertion_review_audit,
    load_assertion_review_pilot,
)

STAT = "http://lunetix.org/standards-atlas#"


def review_payload() -> dict:
    """Entirely synthetic review: no private standards text or runtime required."""
    return {
        "schema_version": 1,
        "review_id": "test-audit",
        "review_version": "0.1.0",
        "target_suite": {
            "id": "test-development",
            "version": "0.1.0",
            "partition": "development",
            "ontology_versions": ["standards-atlas-core@2.0.0"],
        },
        "source_corpus": {
            "corpus_id": "selection",
            "corpus_version": "1",
            "corpus_sha256": "a" * 64,
        },
        "selection": {"strategy": "explicit", "selected_clause_ids": ["c1"]},
        "cases": [
            {
                "clause_id": "c1",
                "document_key": "DOC",
                "reference": "DOC:1",
                "canonical_reference": "DOC 1",
                "text": "Plan",
                "text_sha256": hashlib.sha256(b"Plan").hexdigest(),
                "applicability_source": {
                    "category": "test",
                    "present": False,
                    "source_archive": "selection.zip",
                    "source_archive_sha256": "b" * 64,
                    "selection_text_sha256": hashlib.sha256(b"Plan").hexdigest(),
                    "selection_text_matches_current": True,
                },
                "context": {
                    "document_key": "DOC",
                    "clause_id": "c1",
                    "reference": "1",
                    "heading": "Planning",
                    "ancestor_headings": ["Development", "Products"],
                },
                "review_status": "reviewed",
                "expected": {
                    "entities": [
                        {
                            "id": "plan",
                            "normalized_label": "Plan",
                            "class_iri": f"{STAT}Plan",
                        }
                    ],
                    "assertions": [
                        {
                            "id": "required",
                            "subject_id": "plan",
                            "predicate": f"{STAT}specifies",
                            "object": {"kind": "literal", "value": "Plan"},
                            "normative_force": "requirement",
                            "evidence": [{"start_offset": 0, "end_offset": 4}],
                        }
                    ],
                },
            }
        ],
    }


def audit_from_payload(payload: dict | None = None) -> AssertionReviewAudit:
    return AssertionReviewAudit(yaml.safe_dump(payload or review_payload()).encode())


def test_byte_binding_and_copy_do_not_reserialize(tmp_path: Path) -> None:
    raw = ("# Original review\n" + yaml.safe_dump(review_payload())).encode()
    source = tmp_path / "original.yaml"
    source.write_bytes(raw)
    audit = load_assertion_review_audit(source)
    assert audit.audit_sha256 == hashlib.sha256(raw).hexdigest()
    target = copy_assertion_review_audit(audit, tmp_path / "copied.yaml")
    assert source.read_bytes() == target.read_bytes() == raw
    assert copy_assertion_review_audit(audit, target) == target
    target.write_bytes(b"different")
    with pytest.raises(ValueError, match="overwrite"):
        copy_assertion_review_audit(audit, target)


def test_reformatting_changes_bytes_not_source_fingerprint() -> None:
    payload = review_payload()
    left = audit_from_payload(payload)
    right = AssertionReviewAudit(json.dumps(payload, indent=4).encode(), json_format=True)
    assert left.audit_sha256 != right.audit_sha256
    assert review_case_source_sha256(left.review.cases[0]) == review_case_source_sha256(
        right.review.cases[0]
    )


@pytest.mark.parametrize("kind", ["heading", "context_order", "proposal", "expected"])
def test_source_fingerprint_excludes_annotations_but_binds_context(kind: str) -> None:
    left = audit_from_payload()
    payload = review_payload()
    case = payload["cases"][0]
    if kind == "heading":
        case["context"]["heading"] = "Different heading"
    elif kind == "context_order":
        case["context"]["ancestor_headings"].reverse()
    elif kind == "expected":
        case["expected"]["entities"][0]["normalized_label"] = "Changed expected label"
    else:
        case["proposal"] = {
            "cascade_run_id": "run",
            "route": "escalated",
            "proposal_stage": "escalation",
            "proposal_run_id": "proposal",
            "proposal_sha256": "c" * 64,
            "entities": [],
            "assertions": [],
        }
    right = audit_from_payload(payload)
    equal = review_case_source_sha256(left.review.cases[0]) == review_case_source_sha256(
        right.review.cases[0]
    )
    assert equal == (kind in {"proposal", "expected"})
    if kind == "proposal":
        assert right.snapshot_sha256("DOC", "c1") == canonical_sha256(case["proposal"])
        assert right.snapshot_sha256("DOC", "c1") != case["proposal"]["proposal_sha256"]
    assert left.snapshot_sha256("DOC", "c1") is None


@pytest.mark.parametrize(
    "defect",
    [
        "pending",
        "text_hash",
        "duplicate_entity_id",
        "duplicate_assertion_id",
        "unknown_subject",
        "unknown_object",
        "span_bounds",
        "case_order",
        "duplicate_case",
        "context_identity",
        "reference",
    ],
)
def test_invalid_audit_is_rejected(defect: str) -> None:
    payload = review_payload()
    case = payload["cases"][0]
    expected = case["expected"]
    if defect == "pending":
        case["review_status"] = "pending"
    elif defect == "text_hash":
        case["text"] = "Changed source, not a repair opportunity"
    elif defect == "duplicate_entity_id":
        expected["entities"].append(copy.deepcopy(expected["entities"][0]))
    elif defect == "duplicate_assertion_id":
        expected["assertions"].append(copy.deepcopy(expected["assertions"][0]))
    elif defect == "unknown_subject":
        expected["assertions"][0]["subject_id"] = "unknown"
    elif defect == "unknown_object":
        expected["assertions"][0]["object"] = {"kind": "entity", "entity_id": "unknown"}
    elif defect == "span_bounds":
        expected["assertions"][0]["evidence"][0]["end_offset"] = 5
    elif defect == "case_order":
        payload["selection"]["selected_clause_ids"] = ["other"]
    elif defect == "duplicate_case":
        payload["cases"].append(copy.deepcopy(case))
    elif defect == "context_identity":
        case["context"]["clause_id"] = "another-clause"
    else:
        case["reference"] = "OTHER:1"
    with pytest.raises(ValueError):
        audit_from_payload(payload)


@pytest.mark.parametrize("json_format", [False, True])
def test_duplicate_mapping_keys_are_rejected(json_format: bool) -> None:
    raw = (
        b'{"schema_version": 1, "schema_version": 1}'
        if json_format
        else (b"cases:\n- expected:\n    entities: []\n    entities: []\n")
    )
    with pytest.raises(ValueError, match="duplicate mapping key"):
        AssertionReviewAudit(raw, json_format=json_format)


def test_editable_pending_pilot_still_loads(tmp_path: Path) -> None:
    payload = review_payload()
    payload["cases"][0]["review_status"] = "pending"
    path = tmp_path / "editable.yaml"
    path.write_text(yaml.safe_dump(payload))
    assert load_assertion_review_pilot(path).cases[0].review_status.value == "pending"
    with pytest.raises(ValueError, match="pending"):
        load_assertion_review_audit(path)


def test_parsed_context_cannot_mutate_the_bound_audit() -> None:
    audit = audit_from_payload()
    audit.review.cases[0].context["heading"] = "not persisted"
    assert audit.review.cases[0].context["heading"] == "Planning"


def test_input_protection_covers_same_path_symlinks_and_hardlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"audit")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(source)
    hardlink = tmp_path / "hardlink"
    hardlink.hardlink_to(source)
    for output in (source, symlink, hardlink):
        with pytest.raises(ValueError, match="overwrite input"):
            ensure_distinct_output(output, source)
    ensure_distinct_output(tmp_path / "new", source)


def test_publisher_keeps_ids_labels_spans_and_selection_order() -> None:
    from standards_atlas.application.assertion_qualification import publish_assertion_review_pilot

    payload = review_payload()
    second = copy.deepcopy(payload["cases"][0])
    second.update(clause_id="c2", reference="DOC:2", canonical_reference="DOC 2")
    second["context"].update(clause_id="c2", reference="2")
    second["expected"]["entities"][0]["normalized_label"] = "  PLAN  "
    second["expected"]["assertions"] = []
    payload["cases"].append(second)
    payload["selection"]["selected_clause_ids"].append("c2")
    audit = audit_from_payload(payload)
    suite = publish_assertion_review_pilot(audit)
    assert [case.case_key for case in suite.cases] == [("DOC", "c1"), ("DOC", "c2")]
    assert [case.entities[0].id for case in suite.cases] == ["plan", "plan"]
    assert suite.cases[1].entities[0].normalized_label == "  PLAN  "
    assert suite.cases[1].assertions == ()
    span = suite.cases[0].assertions[0].evidence[0]
    assert (span.start_offset, span.end_offset) == (0, 4)
    assert span.content_hash == hashlib.sha256(b"Plan").hexdigest()
    assert span.source_kind.value == "body"
    assert suite.audit.audit_sha256 == hashlib.sha256(audit.original_bytes).hexdigest()


def test_obsolete_document_wide_golden_is_not_a_current_schema() -> None:
    from standards_atlas.application.assertion_qualification import AssertionGoldenSuite

    payload = {
        "schema_version": 1,
        "id": "old",
        "version": "1",
        "partition": "development",
        "ontology_versions": ["standards-atlas-core@2.0.0"],
        "cases": [{"source_document_key": "DOC", "entities": [], "assertions": []}],
    }
    with pytest.raises(ValueError, match="clause_id"):
        AssertionGoldenSuite.model_validate(payload)


def test_suite_binding_rejects_changes_in_expected_source_or_selection() -> None:
    from standards_atlas.application.assertion_qualification import publish_assertion_review_pilot
    from standards_atlas.application.assertion_qualification.evaluation import (
        validate_audit_binding,
    )

    audit = audit_from_payload()
    suite = publish_assertion_review_pilot(audit)
    validate_audit_binding(suite, audit)
    changed_suite = suite.model_copy(update={"version": "other"})
    with pytest.raises(ValueError, match="content/selection"):
        validate_audit_binding(changed_suite, audit)
    changed = review_payload()
    changed["cases"][0]["context"]["heading"] = "changed"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_audit_binding(suite, audit_from_payload(changed))


def _native_proposal():
    from standards_atlas.domain.model import DocumentKnowledgeProposal

    return DocumentKnowledgeProposal.model_validate(
        {
            "proposal_run_id": "native-run",
            "source_document_key": "DOC",
            "ontology_versions": ["standards-atlas-core@2.0.0"],
            "proposal_provenance": {"extractor": "synthetic-test", "extractor_version": "1"},
            "evidence_anchors": [
                {
                    "id": "plan-anchor",
                    "source_clause_id": {"value": "c1"},
                    "source_kind": "body",
                    "start_offset": 0,
                    "end_offset": 4,
                    "content_hash": hashlib.sha256(b"Plan").hexdigest(),
                }
            ],
            "entity_proposals": [
                {
                    "id": "plan",
                    "proposal_clause_ids": [{"value": "c1"}],
                    "class_iri": f"{STAT}Plan",
                    "normalized_label": "Plan",
                    "source_anchor_ids": ["plan-anchor"],
                    "confidence": 0.5,
                }
            ],
            "assertion_proposals": [
                {
                    "id": "required",
                    "source_clause_id": {"value": "c1"},
                    "subject_id": "plan",
                    "predicate": f"{STAT}specifies",
                    "object": {"kind": "literal", "value": "Plan"},
                    "normative_force": "requirement",
                    "confidence": 0.1,
                    "evidence_anchor_ids": ["plan-anchor"],
                }
            ],
        }
    )


def _snapshot_payload(*, route: str = "escalated") -> dict:
    from standards_atlas.application.assertion_qualification.evaluation import proposal_sha256
    from standards_atlas.application.assertion_qualification.projection import (
        project_native_proposal,
    )

    native = _native_proposal()
    projected = project_native_proposal(native, "c1")
    payload = review_payload()
    payload["cases"][0]["proposal"] = {
        "cascade_run_id": "historical-test-run",
        "route": route,
        "proposal_stage": "efficient" if route == "efficient_accepted" else "escalation",
        "proposal_run_id": native.proposal_run_id,
        "proposal_sha256": proposal_sha256(native),
        "entities": [item.model_dump(mode="json") for item in projected.entities],
        "assertions": [item.model_dump(mode="json") for item in projected.assertions],
    }
    return payload


@pytest.mark.parametrize("route", ["efficient_accepted", "escalated"])
def test_review_and_native_inputs_have_identical_metrics_and_distinct_provenance(
    route: str,
) -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )

    audit = audit_from_payload(_snapshot_payload(route=route))
    suite = publish_assertion_review_pilot(audit)
    evaluator = AssertionQualificationEvaluator()
    native = evaluator.evaluate(suite, (_native_proposal(),), source_audit=audit)
    stored = evaluator.evaluate(suite, review_audit=audit)
    assert native.aggregate == stored.aggregate
    assert native.cases[0].model_dump(exclude={"provenance"}) == stored.cases[0].model_dump(
        exclude={"provenance"}
    )
    assert stored.aggregate.assertions.true_positive == 1  # no confidence/route filtering
    assert stored.candidate_mode == stored.cases[0].provenance.kind == "review_snapshot"
    assert native.candidate_mode == native.cases[0].provenance.kind == "native_proposal"
    assert stored.proposal_sources == ()
    origin = stored.cases[0].provenance
    assert origin.snapshot_sha256 != origin.declared_proposal_sha256
    assert origin.snapshot_sha256 == audit.snapshot_sha256("DOC", "c1")
    assert origin.original_proposal_verification == "unavailable"
    assert origin.historical_model_provenance == origin.historical_input_provenance == "unavailable"
    assert stored.source_binding == native.source_binding == "audit_verified"
    assert stored.aggregate.evidence_integrity.validity.value == 1.0
    assert stored.aggregate.evidence_span_exact_match.accuracy.value == 1.0
    assert stored.aggregate.semantic_evidence.status == "not_evaluated"
    assert stored.cases[0].clause_exact_match.value is True


def test_snapshot_keeps_diagnostics_and_unresolved_candidates_without_reconstruction() -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )
    from standards_atlas.application.assertion_qualification.projection import (
        project_review_snapshot,
    )

    payload = _snapshot_payload()
    snapshot = payload["cases"][0]["proposal"]
    snapshot.update(
        violations=["raw violation for discarded candidate"],
        failures=["raw technical failure"],
        reasons=["historical escalation reason"],
        verifier_dispositions={"discarded": "rejected"},
        missing_entity_detected=True,
        missing_assertion_detected=True,
    )
    snapshot["assertions"][0]["subject_id"] = "unknown"
    snapshot["assertions"][0]["evidence"][0]["start_offset"] = None
    audit = audit_from_payload(payload)
    view = project_review_snapshot(audit, document_key="DOC", clause_id="c1")
    assert len(view.entities) == len(view.assertions) == 1
    assert view.assertions[0].subject_id == "unknown"
    assert view.assertions[0].evidence[0].start_offset is None
    assert view.violations == ("raw violation for discarded candidate",)
    assert view.provenance.verifier_dispositions == {"discarded": "rejected"}
    report = AssertionQualificationEvaluator().evaluate(
        publish_assertion_review_pilot(audit),
        review_audit=audit,
    )
    assert report.aggregate.assertions.false_positive == 1
    assert report.cases[0].proposal_violations == report.cases[0].proposal_failures == 1
    assert report.cases[0].failure_details == ("raw technical failure",)
    assert report.cases[0].provenance.missing_entity_detected is True


@pytest.mark.parametrize("missing", [False, True])
def test_missing_snapshot_is_not_a_present_empty_snapshot(missing: bool) -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )

    payload = _snapshot_payload()
    snapshot = payload["cases"][0]["proposal"]
    snapshot.update(entities=[], assertions=[])
    payload["cases"][0]["expected"] = {"entities": [], "assertions": []}
    if missing:
        payload["cases"][0]["proposal"] = None
    audit = audit_from_payload(payload)
    suite = publish_assertion_review_pilot(audit)
    if missing:
        with pytest.raises(ValueError, match="missing proposal snapshot"):
            AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)
    else:
        report = AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)
        assert report.cases[0].candidate_status == "present"
        assert report.aggregate.candidate_clauses == 1
        assert report.aggregate.entities.expected == report.aggregate.entities.predicted == 0


def test_evaluator_candidate_sources_are_exclusive_and_source_audit_does_not_select() -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )

    audit = audit_from_payload(_snapshot_payload())
    suite = publish_assertion_review_pilot(audit)
    evaluator = AssertionQualificationEvaluator()
    with pytest.raises(ValueError, match="exactly one"):
        evaluator.evaluate(suite)
    with pytest.raises(ValueError, match="exactly one"):
        evaluator.evaluate(suite, (), review_audit=audit)
    with pytest.raises(ValueError, match="exactly one"):
        evaluator.evaluate(suite, source_audit=audit)
    with pytest.raises(ValueError, match="only valid for native"):
        evaluator.evaluate(suite, review_audit=audit, source_audit=audit)
    missing = evaluator.evaluate(suite, (), source_audit=audit)
    assert missing.candidate_mode == "native_proposal"
    assert missing.cases[0].candidate_status == "missing"


def test_review_report_cannot_enter_auto_adoption_policy() -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionAutoAdoptionPolicy,
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )
    from standards_atlas.application.assertion_qualification.policy import (
        _validate_partition_binding,
    )
    from standards_atlas.application.assertion_qualification.policy_models import (
        AssertionQualityThresholds,
    )

    audit = audit_from_payload(_snapshot_payload())
    suite = publish_assertion_review_pilot(audit)
    report = AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)
    thresholds = AssertionQualityThresholds(
        min_entity_precision=0,
        min_entity_recall=0,
        min_assertion_precision=0,
        min_assertion_recall=0,
        min_predicate_accuracy=0,
        min_normative_force_accuracy=0,
        min_evidence_span_exact_match_accuracy=0,
        min_exact_assertion_accuracy=0,
    )
    policy = AssertionAutoAdoptionPolicy(
        id="policy",
        version="1",
        ontology_versions=suite.ontology_versions,
        development=thresholds,
        holdout=thresholds,
    )
    with pytest.raises(ValueError, match="review_snapshot.*not auto-adoption"):
        _validate_partition_binding(
            suite=suite,
            report=report,
            expected=suite.partition,
            policy=policy,
        )


def test_review_report_validates_mode_audit_and_native_source_separation() -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        AssertionQualificationReport,
        publish_assertion_review_pilot,
    )

    audit = audit_from_payload(_snapshot_payload())
    report = AssertionQualificationEvaluator().evaluate(
        publish_assertion_review_pilot(audit),
        review_audit=audit,
    )
    payload = report.model_dump(mode="json")
    payload["cases"][0]["provenance"]["audit_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="snapshot provenance"):
        AssertionQualificationReport.model_validate(payload)
    payload = report.model_dump(mode="json")
    payload["candidate_mode"] = "native_proposal"
    with pytest.raises(ValueError, match="provenance kind"):
        AssertionQualificationReport.model_validate(payload)
    payload = report.model_dump(mode="json")
    payload["source_binding"] = "golden_declared"
    with pytest.raises(ValueError, match="verified audit"):
        AssertionQualificationReport.model_validate(payload)


def test_publish_and_both_evaluation_cli_inputs_run_with_model_and_network_calls_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from typer.testing import CliRunner

    from standards_atlas.adapters import llm
    from standards_atlas.application.assertion_qualification.cascade import (
        AssertionQualificationCascadeService,
    )
    from standards_atlas.application.assertion_qualification.io import (
        load_assertion_qualification_report,
    )
    from standards_atlas.cli.main import app

    review = tmp_path / "review.yaml"
    original = yaml.safe_dump(_snapshot_payload()).encode()
    review.write_bytes(original)
    proposal = tmp_path / "proposal.json"
    proposal.write_text(_native_proposal().model_dump_json())
    golden = tmp_path / "golden.yaml"
    stored_path = tmp_path / "stored.json"
    native_path = tmp_path / "native.json"
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append((args, kwargs))
        raise AssertionError("offline AP01 path attempted model/runtime/network execution")

    for component in (
        llm.OpenAICompatibleLlmGateway,
        llm.CodexCliLlmGateway,
        llm.ManagedRamaLamaGateway,
        llm.OntologyGuidedKnowledgeProposalExtractor,
        llm.OntologyGuidedAssertionProposalVerifier,
        AssertionQualificationCascadeService,
    ):
        monkeypatch.setattr(component, "__init__", forbidden)
    monkeypatch.setattr(llm.LlmConfig, "load", forbidden)
    monkeypatch.setattr(AssertionQualificationCascadeService, "run_document", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)

    runner = CliRunner()
    publish = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-review-pilot-publish",
            "--review",
            str(review),
            "--output",
            str(golden),
        ],
    )
    assert publish.exit_code == 0, publish.output
    stored = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--review",
            str(review),
            "--output",
            str(stored_path),
        ],
    )
    assert stored.exit_code == 0, stored.output
    native = runner.invoke(
        app,
        [
            "evaluation",
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--proposal",
            str(proposal),
            "--source-review",
            str(review),
            "--output",
            str(native_path),
        ],
    )
    assert native.exit_code == 0, native.output
    assert load_assertion_qualification_report(stored_path).aggregate == (
        load_assertion_qualification_report(native_path).aggregate
    )
    assert "review_snapshot" in stored.output
    assert review.read_bytes() == original
    assert attempts == []


@pytest.mark.parametrize("mode", ["neither", "both", "review_with_source", "source_only"])
def test_cli_rejects_ambiguous_or_missing_candidate_options(tmp_path: Path, mode: str) -> None:
    from typer.testing import CliRunner

    from standards_atlas.application.assertion_qualification import publish_assertion_review_pilot
    from standards_atlas.application.assertion_qualification.io import write_assertion_golden_suite
    from standards_atlas.cli.main import app

    review = tmp_path / "review.yaml"
    review.write_bytes(audit_from_payload(_snapshot_payload()).original_bytes)
    golden = tmp_path / "golden.yaml"
    write_assertion_golden_suite(
        publish_assertion_review_pilot(load_assertion_review_audit(review)),
        golden,
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text(_native_proposal().model_dump_json())
    output = tmp_path / "output.json"
    args = ["evaluation", "assertion-evaluate", "--golden", str(golden), "--output", str(output)]
    if mode == "both":
        args.extend(["--review", str(review), "--proposal", str(proposal)])
    elif mode == "review_with_source":
        args.extend(["--review", str(review), "--source-review", str(review)])
    elif mode == "source_only":
        args.extend(["--source-review", str(review)])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert not output.exists()


def test_publish_and_evaluate_cli_never_overwrite_their_sources(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from standards_atlas.application.assertion_qualification import publish_assertion_review_pilot
    from standards_atlas.application.assertion_qualification.io import write_assertion_golden_suite
    from standards_atlas.cli.main import app

    audit = audit_from_payload(_snapshot_payload())
    review = tmp_path / "review.yaml"
    review.write_bytes(audit.original_bytes)
    golden = tmp_path / "golden.yaml"
    write_assertion_golden_suite(publish_assertion_review_pilot(audit), golden)
    golden_bytes = golden.read_bytes()
    for args in (
        ["assertion-review-pilot-publish", "--review", str(review), "--output", str(review)],
        [
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--review",
            str(review),
            "--output",
            str(review),
        ],
        [
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--review",
            str(review),
            "--output",
            str(golden),
        ],
        [
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--review",
            str(review),
            "--output",
            str(tmp_path / "report.json"),
            "--summary-output",
            str(review),
        ],
        [
            "assertion-evaluate",
            "--golden",
            str(golden),
            "--review",
            str(review),
            "--output",
            str(tmp_path / "same-output"),
            "--summary-output",
            str(tmp_path / "same-output"),
        ],
    ):
        result = CliRunner().invoke(app, ["evaluation", *args])
        assert result.exit_code == 2, result.output
        assert "overwrite input" in result.output
    assert review.read_bytes() == audit.original_bytes
    assert golden.read_bytes() == golden_bytes


def _evaluate_snapshot_payload(payload: dict):
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )

    audit = audit_from_payload(payload)
    suite = publish_assertion_review_pilot(audit)
    return AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)


def test_heading_and_body_with_same_offsets_are_distinct_evidence_surfaces() -> None:
    payload = _snapshot_payload()
    evidence = payload["cases"][0]["proposal"]["assertions"][0]["evidence"][0]
    evidence.update(
        source_kind="heading",
        start_offset=0,
        end_offset=4,
        content_hash=hashlib.sha256(b"Plan").hexdigest(),
    )

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_integrity.valid == 2
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 0.0
    assert report.cases[0].clause_exact_match.value is False


def test_two_separate_evidence_spans_compare_exactly_without_merging() -> None:
    payload = _snapshot_payload()
    payload["cases"][0]["expected"]["assertions"][0]["evidence"] = [
        {"start_offset": 0, "end_offset": 2},
        {"start_offset": 2, "end_offset": 4},
    ]
    assertion = payload["cases"][0]["proposal"]["assertions"][0]
    assertion["evidence"] = [
        {
            "anchor_id": "plan-anchor-left",
            "source_clause_id": "c1",
            "source_kind": "body",
            "start_offset": 0,
            "end_offset": 2,
            "content_hash": hashlib.sha256(b"Pl").hexdigest(),
        },
        {
            "anchor_id": "plan-anchor-right",
            "source_clause_id": "c1",
            "source_kind": "body",
            "start_offset": 2,
            "end_offset": 4,
            "content_hash": hashlib.sha256(b"an").hexdigest(),
        },
    ]

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_integrity.valid == 3
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 1.0
    assert report.cases[0].clause_exact_match.value is True


def test_frozen_associative_context_body_can_resolve_foreign_evidence() -> None:
    payload = _snapshot_payload()
    payload["cases"][0]["context"]["associative_context"] = [
        {
            "clause_id": "ctx-1",
            "reference": "2",
            "heading": "Context heading",
            "text": "External",
        }
    ]
    evidence = payload["cases"][0]["proposal"]["assertions"][0]["evidence"][0]
    evidence.update(
        anchor_id="external-anchor",
        source_clause_id="ctx-1",
        source_kind="body",
        start_offset=0,
        end_offset=8,
        content_hash=hashlib.sha256(b"External").hexdigest(),
    )

    report = _evaluate_snapshot_payload(payload)

    finding = next(
        item
        for item in report.cases[0].evidence_integrity_findings
        if item.owner_kind == "assertion"
    )
    assert finding.status.value == "valid"
    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 0.0


def test_unavailable_foreign_body_is_not_reported_as_invalid_hash() -> None:
    payload = _snapshot_payload()
    evidence = payload["cases"][0]["proposal"]["assertions"][0]["evidence"][0]
    evidence.update(
        anchor_id="missing-anchor",
        source_clause_id="missing",
        source_kind="body",
        start_offset=0,
        end_offset=4,
        content_hash=hashlib.sha256(b"Else").hexdigest(),
    )

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_integrity.unavailable == 1
    assert report.aggregate.evidence_integrity.checked == 1
    assert report.aggregate.evidence_integrity.validity.value == 1.0
    assert report.aggregate.evidence_integrity.validity.status.value == "partial"


def test_longer_valid_source_passage_can_fail_strict_expected_span_match() -> None:
    payload = _snapshot_payload()
    case = payload["cases"][0]
    case["text"] = "Plan now"
    case["text_sha256"] = hashlib.sha256(b"Plan now").hexdigest()
    case["applicability_source"]["selection_text_sha256"] = case["text_sha256"]
    assertion_evidence = case["proposal"]["assertions"][0]["evidence"][0]
    assertion_evidence.update(
        start_offset=0,
        end_offset=8,
        content_hash=hashlib.sha256(b"Plan now").hexdigest(),
    )

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_integrity.valid == 2
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 0.0
    assert report.aggregate.semantic_evidence.status == "not_evaluated"


def test_conflicting_frozen_source_versions_are_visible_not_silently_selected() -> None:
    payload = _snapshot_payload()
    payload["cases"][0]["context"]["associative_context"] = [
        {
            "clause_id": "c1",
            "reference": "1",
            "heading": "Planning",
            "text": "Other",
        }
    ]

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.conflicting == 2
    assert report.aggregate.evidence_integrity.checked == 0
    assert report.aggregate.evidence_integrity.validity.value is None
    assert report.aggregate.evidence_integrity.validity.status.value == "not_evaluable"


def test_wrong_hash_on_available_frozen_surface_is_invalid_not_unavailable() -> None:
    payload = _snapshot_payload()
    evidence = payload["cases"][0]["proposal"]["assertions"][0]["evidence"][0]
    evidence["content_hash"] = hashlib.sha256(b"Nope").hexdigest()

    report = _evaluate_snapshot_payload(payload)

    assert report.aggregate.evidence_integrity.invalid == 1
    assert report.aggregate.evidence_integrity.unavailable == 0
    assert report.aggregate.evidence_integrity.conflicting == 0
    assert report.aggregate.evidence_integrity.validity.value == 0.5


def test_native_package_source_is_separate_from_historical_expectation_sources() -> None:
    from standards_atlas.application.assertion_qualification import (
        AssertionQualificationEvaluator,
        publish_assertion_review_pilot,
    )
    from standards_atlas.application.context import (
        build_context_source_package,
        build_structured_context_candidates,
        context_source_package_binding,
        select_structured_context,
    )
    from standards_atlas.domain.model import (
        Clause,
        ClauseId,
        ClauseType,
        DocumentKey,
        DocumentType,
        EngineeringDocument,
        EvidenceAnchor,
        EvidenceSourceKind,
        GeneratedAttribute,
        GenerationMethod,
        StandardReference,
        TextBlock,
    )

    audit = audit_from_payload(_snapshot_payload())
    suite = publish_assertion_review_pilot(audit)
    current_text = "Plan updated"
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="current", text=current_text),),
    ).mark_generated(
        GeneratedAttribute(
            path="baseline.content",
            generator="synthetic-source-extraction",
            method=GenerationMethod.SOURCE_EXTRACTION,
        )
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Synthetic current document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )
    inventory = build_structured_context_candidates(document, clause)
    selection = select_structured_context(inventory)
    package = build_context_source_package(document, inventory, selection)
    binding = context_source_package_binding(package)

    proposal = _native_proposal()
    current_anchor = EvidenceAnchor(
        id="current-only-anchor",
        source_clause_id=ClauseId(value="c1"),
        source_kind=EvidenceSourceKind.BODY,
        start_offset=5,
        end_offset=len(current_text),
        content_hash=hashlib.sha256(b"updated").hexdigest(),
    )
    proposal = proposal.model_copy(
        update={
            "evidence_anchors": (current_anchor,),
            "entity_proposals": tuple(
                item.model_copy(update={"source_anchor_ids": (current_anchor.id,)})
                for item in proposal.entity_proposals
            ),
            "assertion_proposals": tuple(
                item.model_copy(update={"evidence_anchor_ids": (current_anchor.id,)})
                for item in proposal.assertion_proposals
            ),
            "context_source_bindings": (binding,),
        }
    )

    report = AssertionQualificationEvaluator().evaluate(
        suite,
        (proposal,),
        source_audit=audit,
        source_packages=(package,),
    )

    assert report.source_binding == "native_package_verified"
    assert report.aggregate.evidence_integrity.valid == 2
    assert report.aggregate.evidence_integrity.invalid == 0
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 0.0
    comparison = report.cases[0].source_comparison
    assert comparison.status.value == "changed"
    assert comparison.basis == "historical_audit_overlap"
    assert comparison.changed_surfaces == 1
