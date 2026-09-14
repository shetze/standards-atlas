"""Slice 2 contracts. All texts, model votes and reviewers below are synthetic fixtures."""

import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from test_mixed_consensus import evaluate, votes
from test_partial_observations import config, observation, prepared
from test_review_package import complete, decide, make_review, publish
from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.review_package.assistance import (
    record_model_recommendations,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
    candidate_page,
    index_path,
    load_candidate_index,
)
from standards_atlas.application.semantic_qualification.review_package.preparation_model import (
    AnnotationBatch,
    SelectionRequest,
)
from standards_atlas.application.semantic_qualification.review_package.selection import (
    apply_selection,
    review_queue,
    selection_path,
    submit_selection,
)
from standards_atlas.application.semantic_qualification.review_package.service import load_review
from standards_atlas.cli import app


def indexed(tmp_path, **kwargs):
    root, manifest, items, spec = make_review(tmp_path)
    result = build_candidate_index(root, **kwargs)
    _, _, index = load_candidate_index(root, result["index_sha256"])
    return root, manifest, items, spec, index


def selection_request(package, index, *, count=1):
    entries = sorted(
        (e for e in index.entries if e.membership == "candidate"),
        key=lambda e: (-e.priority, e.example_id),
    )[:count]
    return SelectionRequest(
        actor="synthetic-codex",
        model="synthetic-model",
        rationale="Cover additional boundaries.",
        additional_development_ids=tuple(e.example_id for e in entries),
        priorities=tuple(
            dict(
                example_id=e.example_id,
                source_sha256=e.source_sha256,
                priority=95,
                rationale="Synthetic difficult case.",
            )
            for e in entries
        ),
    )


def selected(root, index, tmp_path):
    package, state = load_review(root)
    request = selection_request(package, index)
    receipt = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=request,
    )
    output = tmp_path / "selected"
    apply_selection(
        root, selection_sha256=receipt["selection_sha256"], output=output, review_id="selected"
    )
    return output, receipt


def annotation_batch(
    package,
    *,
    case=None,
    request_id="synthetic-batch-1",
    value=False,
    attribute="role_semantics_present",
    evidence=None,
):
    case = case or next(c for c in package.cases if c.split == "development")
    source = next(s for s in package.population if s.example_id == case.example_id)
    return AnnotationBatch.model_validate(
        {
            "request_id": request_id,
            "actor": "synthetic-codex",
            "model": "synthetic-model",
            "recommendations": [
                {
                    "example_id": case.example_id,
                    "source_sha256": source.source_sha256,
                    "attribute": attribute,
                    "predicate": {"equals": value},
                    "rationale": "Synthetic recommendation, not a human decision.",
                    "evidence": evidence if evidence is not None else [{"quote": source.text}],
                }
            ],
        }
    )


def report_file(path, items, *, disagree=False):
    obs = tuple(
        o
        for item in items
        for o in votes(item, changes={0: {"role_semantics_present": True}} if disagree else None)
    )
    report = evaluate(items=tuple(items), observations=obs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json())
    return report


def test_index_deterministic_complete_source_bound_and_no_new_reviews(tmp_path):
    root, _, items, _, index = indexed(tmp_path)
    before = (root / "review-state.json").read_bytes()
    repeated = build_candidate_index(root)
    assert repeated["index_sha256"] == index.index_sha256
    assert len(index.entries) == len(items)
    assert len(index.artifacts) == 3  # Golden + declared Development and Holdout suites
    assert before == (root / "review-state.json").read_bytes()
    assert load_review(root)[1].decisions == ()
    golden = next(e for e in index.entries if e.example_id == items[0].id)
    assert golden.history[0].attribute == "applicability_present"
    assert golden.history[0].status == "published"
    assert golden.confirmed_attributes == ()


def test_history_disagreement_rank_and_filters(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    history = tmp_path / "mixed-consensus-report.json"
    report_file(history, items[:2], disagree=True)
    built = build_candidate_index(root, histories=(history,))
    page = candidate_page(root, built["index_sha256"], limit=1)
    assert page["entries"][0]["example_id"] == items[0].id
    assert page["entries"][0]["priority"] >= 80
    assert "role_semantics_present" in page["entries"][0]["disagreement_attributes"]
    assert page["next_offset"] == 1
    filtered = candidate_page(
        root,
        built["index_sha256"],
        reason="reported-value-disagreement",
        document_key="TEST",
        clause_type_filter="term",
        query="Entry 1",
    )
    assert [e["example_id"] for e in filtered["entries"]] == [items[1].id]
    assert candidate_page(root, built["index_sha256"], offset=999)["entries"] == []


def test_technical_failure_is_not_a_negative_or_semantic_disagreement(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    req = prepared(cfg=config(selected_attributes=("role_semantics_present",)), item=items[0])
    obs = observation(req, {}, outcome="failed", error="synthetic timeout").model_dump(mode="json")
    # A failed observation does not claim a successful response checksum.
    obs["response_sha256"] = None
    history = tmp_path / "partial-observation.json"
    history.write_text(json.dumps(obs))
    base = build_candidate_index(root)
    built = build_candidate_index(root, histories=(history,))
    _, _, first = load_candidate_index(root, base["index_sha256"])
    _, _, second = load_candidate_index(root, built["index_sha256"])
    before = next(e for e in first.entries if e.example_id == items[0].id)
    after = next(e for e in second.entries if e.example_id == items[0].id)
    assert before.priority == after.priority
    assert after.technical_failure_count == 1
    assert after.disagreement_attributes == after.unresolved_attributes == ()
    failures = [s for s in after.history if s.status == "failed"]
    assert len(failures) == 1 and failures[0].predicate is None and not failures[0].model_values


def test_archive_and_standalone_reports_deduplicate_and_bind_checksums(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    history = tmp_path / "mixed-consensus-report.json"
    report_file(history, items[:2])
    archive = tmp_path / "run.zip"
    member = "experiment/mixed-consensus-report.json"
    raw = history.read_bytes()
    with ZipFile(archive, "w") as zipfile:
        zipfile.writestr(member, raw)
        zipfile.writestr(
            "archive-manifest.json",
            json.dumps({"files": [{"path": member, "sha256": hashlib.sha256(raw).hexdigest()}]}),
        )
        zipfile.writestr("irrelevant/huge-response.json", "this is not parsed")
    result = build_candidate_index(root, histories=(history, archive, history))
    _, _, index = load_candidate_index(root, result["index_sha256"])
    assert sum(a.kind == "mixed" for a in index.artifacts) == 1
    with ZipFile(archive, "w") as zipfile:
        zipfile.writestr(member, raw)
        zipfile.writestr(
            "archive-manifest.json", json.dumps({"files": [{"path": member, "sha256": "0" * 64}]})
        )
    with pytest.raises(ValueError, match="checksum mismatch"):
        build_candidate_index(root, histories=(archive,))


def test_changed_historical_text_never_attaches_to_current_source(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    item = copy.deepcopy(items[0])
    item.input["content"]["text"] += " different historical source"
    from standards_atlas.application.semantic_qualification.annotations import (
        normalized_content_hash,
    )

    item.input["content"]["hash"] = normalized_content_hash(item.input["content"]["text"])
    history = tmp_path / "mixed-consensus-report.json"
    report_file(history, (item,))
    result = build_candidate_index(root, histories=(history,))
    assert f"unbound-or-changed-source:{item.id}" in result["diagnostics"]
    _, _, index = load_candidate_index(root, result["index_sha256"])
    assert not any(s.artifact_kind == "mixed" for e in index.entries for s in e.history)


def test_aggregate_only_history_rejected_before_index_write(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    path = tmp_path / "qualification-evaluation.json"
    path.write_text('{"passed":true,"metrics":{"accuracy":0.99}}')
    with pytest.raises(ValueError, match="aggregate"):
        build_candidate_index(root, histories=(path,))
    assert not (root / "preparation").exists()


def test_new_golden_overlapping_holdout_refused_without_reselection(tmp_path):
    root, _, _, spec = make_review(tmp_path)
    package, _ = load_review(root)
    case = next(c for c in package.cases if c.split == "holdout")
    source = next(s for s in package.population if s.example_id == case.example_id)
    data = yaml.safe_load(Path(spec["golden"]).read_bytes())
    data["cases"][0].update(
        document_key=source.document_key,
        clause_id=source.clause_id,
        reference=source.reference,
        text=source.text,
    )
    path = tmp_path / "new-golden.yaml"
    path.write_text(yaml.safe_dump(data))
    before = (root / "review-package.json").read_bytes()
    with pytest.raises(ValueError, match="overlaps frozen holdout"):
        build_candidate_index(root, references=(path,))
    assert before == (root / "review-package.json").read_bytes()


def test_holdout_history_cannot_change_candidate_ranking_or_be_paged(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    package, _ = load_review(root)
    holdout = {c.example_id for c in package.cases if c.split == "holdout"}
    history = tmp_path / "mixed-consensus-report.json"
    report_file(history, tuple(i for i in items if i.id in holdout), disagree=True)
    result = build_candidate_index(root, histories=(history,))
    _, _, index = load_candidate_index(root, result["index_sha256"])
    assert all(e.priority == 0 for e in index.entries if e.membership == "holdout")
    assert not holdout & {
        e["example_id"] for e in candidate_page(root, index.index_sha256, limit=100)["entries"]
    }
    with pytest.raises(ValueError, match="holdout"):
        candidate_page(root, index.index_sha256, membership="holdout")


def test_selection_proposal_does_not_change_package_or_review_state(tmp_path):
    root, _, _, _, index = indexed(tmp_path)
    package, state = load_review(root)
    request = selection_request(package, index)
    first = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=request,
    )
    second = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=request,
    )
    assert first == second and first["human_decisions_added"] == 0
    assert load_review(root) == (package, state)


def test_materialization_preserves_holdout_reviews_and_import_bindings(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    old_package, old_state = complete(root)
    built = build_candidate_index(root)
    _, _, index = load_candidate_index(root, built["index_sha256"])
    output, receipt = selected(root, index, tmp_path)
    new_package, new_state = load_review(output)
    assert {c.example_id for c in old_package.cases if c.split == "holdout"} == {
        c.example_id for c in new_package.cases if c.split == "holdout"
    }
    assert set(old_package.known_development_ids) < set(new_package.known_development_ids)
    assert old_state.decisions == new_state.decisions
    assert old_state.proposals == new_state.proposals
    assert old_state.revision == new_state.revision
    assert review_queue(output, new_package) == tuple(receipt["review_order"])
    assert new_package.population == old_package.population
    assert new_package.rules == old_package.rules
    complete(output)
    published = publish(output, tmp_path / "published")
    assert published["importable"]
    # Neither new suite may contain source-less or unconfirmed attributes.
    for split in ("development", "holdout"):
        assert (tmp_path / "published" / f"{split}.yaml").is_file()


@pytest.mark.parametrize("change", ["budget", "holdout", "known", "source", "duplicate"])
def test_invalid_selection_refused(tmp_path, change):
    root, _, _, _, index = indexed(
        tmp_path, additional_development_budget=0 if change == "budget" else 20
    )
    package, state = load_review(root)
    data = selection_request(package, index).model_dump(mode="json")
    if change in {"holdout", "known"}:
        entry = next(
            e
            for e in index.entries
            if e.membership == ("holdout" if change == "holdout" else "development")
        )
        data["additional_development_ids"] = [entry.example_id]
        data["priorities"][0].update(example_id=entry.example_id, source_sha256=entry.source_sha256)
    elif change == "source":
        data["priorities"][0]["source_sha256"] = "0" * 64
    elif change == "duplicate":
        data["additional_development_ids"] *= 2
    with pytest.raises(ValueError):
        submit_selection(
            root,
            index_sha256=index.index_sha256,
            expected_state_sha256=state.state_sha256,
            request=SelectionRequest.model_validate(data),
        )
    assert not (root / "preparation" / "selections").exists()


def test_review_after_index_requires_explicit_reindex(tmp_path):
    root, _, _, _, index = indexed(tmp_path)
    package, _ = load_review(root)
    request = selection_request(package, index)
    case = next(c for c in package.cases if c.split == "development")
    state = decide(root, case.example_id, "role_semantics_present", False)
    assert candidate_page(root, index.index_sha256)["state_changed_since_index"]
    with pytest.raises(ValueError, match="stale"):
        submit_selection(
            root,
            index_sha256=index.index_sha256,
            expected_state_sha256=state.state_sha256,
            request=request,
        )


@pytest.mark.parametrize(
    "value,attribute",
    [(False, "role_semantics_present"), (None, "primary_function"), ([], "process_functions")],
)
def test_model_batch_retains_explicit_values_and_unicode_offsets(tmp_path, value, attribute):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    batch = annotation_batch(package, value=value, attribute=attribute)
    record_model_recommendations(
        root, package_sha256=package.package_sha256, expected_revision=state.revision, batch=batch
    )
    _, updated = load_review(root)
    proposal = updated.proposals[-1]
    assert proposal.predicate.model_dump() == {"equals": value}
    assert proposal.producer_kind == "model" and proposal.model == "synthetic-model"
    assert proposal.evidence[0].start == 0
    assert proposal.evidence[0].end == len(proposal.evidence[0].quote)
    assert updated.decisions == state.decisions


def test_batch_network_retry_idempotent_even_after_human_review(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    batch = annotation_batch(package)
    first = record_model_recommendations(
        root, package_sha256=package.package_sha256, expected_revision=state.revision, batch=batch
    )
    case = next(c for c in package.cases if c.split == "development")
    decide(
        root,
        case.example_id,
        "role_semantics_present",
        status="confirmed",
        proposal=first["proposal_sha256s"][0],
    )
    before = (root / "review-state.json").read_bytes()
    retry = record_model_recommendations(
        root, package_sha256=package.package_sha256, expected_revision=state.revision, batch=batch
    )
    assert retry["idempotent_replay"]
    assert retry["proposal_sha256s"] == first["proposal_sha256s"]
    assert before == (root / "review-state.json").read_bytes()


def test_batch_invalid_second_quote_is_atomic(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    data = annotation_batch(package).model_dump(mode="json")
    second = copy.deepcopy(data["recommendations"][0])
    second.update(
        attribute="primary_function",
        predicate={"equals": None},
        evidence=[{"quote": "invented evidence absent from source"}],
    )
    data["recommendations"].append(second)
    before = (root / "review-state.json").read_bytes()
    with pytest.raises(ValueError, match="exactly one"):
        record_model_recommendations(
            root,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=AnnotationBatch.model_validate(data),
        )
    assert before == (root / "review-state.json").read_bytes()
    assert not (root / "history").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer", "model-as-human"),
        ("status", "confirmed"),
        ("html", "<script>alert(1)</script>"),
        ("producer_kind", "historical"),
    ],
)
def test_model_submission_contract_forbids_approval_and_html_fields(tmp_path, field, value):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    data = annotation_batch(package).model_dump(mode="json")
    data["recommendations"][0][field] = value
    with pytest.raises(ValueError, match="Extra inputs"):
        AnnotationBatch.model_validate(data)


@pytest.mark.parametrize("change", ["package", "revision", "source", "outside", "attribute"])
def test_model_submission_wrong_binding_fails_without_write(tmp_path, change):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    data = annotation_batch(package).model_dump(mode="json")
    if change == "source":
        data["recommendations"][0]["source_sha256"] = "0" * 64
    elif change == "outside":
        data["recommendations"][0]["example_id"] = "not-selected"
    elif change == "attribute":
        data["recommendations"][0]["attribute"] = "unrelated"
    with pytest.raises(ValueError):
        record_model_recommendations(
            root,
            package_sha256="0" * 64 if change == "package" else package.package_sha256,
            expected_revision=state.revision + (1 if change == "revision" else 0),
            batch=AnnotationBatch.model_validate(data),
        )
    assert load_review(root)[1] == state


def test_request_id_reuse_with_different_payload_is_rejected(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    record_model_recommendations(
        root,
        package_sha256=package.package_sha256,
        expected_revision=state.revision,
        batch=annotation_batch(package),
    )
    with pytest.raises(ValueError, match="request_id already used"):
        record_model_recommendations(
            root,
            package_sha256=package.package_sha256,
            expected_revision=state.revision,
            batch=annotation_batch(package, value=True),
        )


def test_preparation_tamper_and_path_traversal_rejected(tmp_path):
    root, _, _, _, index = indexed(tmp_path)
    with pytest.raises(ValueError, match="fingerprint"):
        load_candidate_index(root, "../review-state.json")
    path = index_path(root, index.index_sha256)
    data = json.loads(path.read_bytes())
    data["entries"][0]["priority"] = 99
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        load_candidate_index(root, index.index_sha256)


def test_selection_after_changed_state_is_not_applied(tmp_path):
    root, _, _, _, index = indexed(tmp_path)
    package, state = load_review(root)
    receipt = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=selection_request(package, index),
    )
    decide(root, package.known_development_ids[0], "role_semantics_present", False)
    with pytest.raises(ValueError, match="stale"):
        apply_selection(
            root,
            selection_sha256=receipt["selection_sha256"],
            output=tmp_path / "changed",
            review_id="changed",
        )
    assert not (tmp_path / "changed").exists()


def test_cli_index_candidates_and_apply_selection(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-index",
            "--package",
            str(root),
            "--additional-development-budget",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    built = json.loads(result.stdout)
    page = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-candidates",
            "--package",
            str(root),
            "--index",
            built["index_sha256"],
            "--limit",
            "2",
        ],
    )
    assert page.exit_code == 0 and len(json.loads(page.stdout)["entries"]) == 2
    package, state, index = load_candidate_index(root, built["index_sha256"])
    receipt = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=selection_request(package, index),
    )
    applied = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-apply-selection",
            "--package",
            str(root),
            "--selection",
            receipt["selection_sha256"],
            "--output",
            str(tmp_path / "selected"),
            "--id",
            "selected",
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.stdout)["human_decisions_added"] == 0


def test_selection_artifact_tamper_fails(tmp_path):
    root, _, _, _, index = indexed(tmp_path)
    package, state = load_review(root)
    receipt = submit_selection(
        root,
        index_sha256=index.index_sha256,
        expected_state_sha256=state.state_sha256,
        request=selection_request(package, index),
    )
    path = selection_path(root, receipt["selection_sha256"])
    data = json.loads(path.read_bytes())
    data["review_order"].reverse()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        apply_selection(
            root,
            selection_sha256=receipt["selection_sha256"],
            output=tmp_path / "selected",
            review_id="selected",
        )


def consensus_history(path, item, **changes):
    clause = {
        "clause_id": item.input["context"]["clause_id"],
        "document_key": item.input["context"]["document_key"],
        "clause_text": item.input["content"]["text"],
        "category": "insufficient_evidence",
        "confidence": 0.0,
        "participating_models": 0,
        "votes": [],
        "role_semantics_present": False,
        "role_semantics_category": "insufficient_evidence",
        **changes,
    }
    data = {
        "schema_version": "5.0",
        "matrix_id": "synthetic",
        "corpus_id": "synthetic",
        "prompt_id": "synthetic",
        "reasoning_mode_id": "synthetic",
        "generated_at": "2026-09-13T00:00:00Z",
        "model_count": 0,
        "clause_count": 1,
        "categories": {},
        "review_count": 1,
        "clauses": [clause],
    }
    path.write_text(json.dumps(data))
    return data


def test_historical_unobserved_defaults_do_not_create_negative_votes_or_disagreements(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    history = tmp_path / "consensus-report.json"
    consensus_history(history, items[0])
    result = build_candidate_index(root, histories=(history,))
    _, _, index = load_candidate_index(root, result["index_sha256"])
    row = next(e for e in index.entries if e.example_id == items[0].id)
    signal = next(s for s in row.history if s.artifact_kind == "consensus")
    assert signal.status == "not_evaluated"
    assert signal.predicate is None and not signal.model_values
    assert not row.unresolved_attributes and not row.disagreement_attributes


def test_historical_actual_model_disagreement_is_preserved(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    history = tmp_path / "consensus-report.json"
    model_votes = [
        {
            "model_id": "synthetic-a",
            "role_semantics_present": True,
            "repetitions": 1,
            "stability": 1.0,
        },
        {
            "model_id": "synthetic-b",
            "role_semantics_present": False,
            "repetitions": 1,
            "stability": 1.0,
        },
    ]
    consensus_history(
        history,
        items[0],
        votes=model_votes,
        participating_models=2,
        role_semantics_category="disputed",
    )
    result = build_candidate_index(root, histories=(history,))
    _, _, index = load_candidate_index(root, result["index_sha256"])
    row = next(e for e in index.entries if e.example_id == items[0].id)
    assert row.disagreement_attributes == ("role_semantics_present",)
    signal = next(s for s in row.history if s.artifact_kind == "consensus")
    assert signal.predicate is None and signal.status == "unresolved"
    assert signal.model_values == {"synthetic-a": True, "synthetic-b": False}


@pytest.mark.parametrize("change", ["count", "duplicate"])
def test_historical_inconsistent_identity_counts_rejected(tmp_path, change):
    root, _, items, _ = make_review(tmp_path)
    history = tmp_path / "consensus-report.json"
    data = consensus_history(history, items[0])
    data["clause_count"] = 2
    if change == "duplicate":
        data["clauses"] *= 2
    history.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identities are inconsistent"):
        build_candidate_index(root, histories=(history,))


def test_index_reads_bound_references_not_an_edited_live_manifest(tmp_path):
    root, manifest, _, _ = make_review(tmp_path)
    manifest.write_text("not: the original campaign manifest anymore\n")
    result = build_candidate_index(root)
    _, _, index = load_candidate_index(root, result["index_sha256"])
    assert len(index.artifacts) == 3
