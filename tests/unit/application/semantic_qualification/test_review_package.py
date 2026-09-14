"""Synthetic contract/integration evidence, never HITL labels for production sources."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from test_partial_observations import RESOURCES
from test_qualification_campaign import source_files
from typer.testing import CliRunner

from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.campaign_selection import (
    load_campaign,
    prepare_campaign,
    verify_prepared_campaign,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    SemanticReferenceSuite,
)
from standards_atlas.application.semantic_qualification.review_package.build import (
    build_review_package,
)
from standards_atlas.application.semantic_qualification.review_package.model import (
    EvidenceQuote,
    ReviewPackage,
    ReviewProfile,
    ReviewPublication,
    SemanticPredicate,
    predicate_data,
    validate_predicate,
)
from standards_atlas.application.semantic_qualification.review_package.publication import (
    import_review_package,
    load_bound_suite,
    verify_publication,
)
from standards_atlas.application.semantic_qualification.review_package.service import (
    load_review,
    record_decision,
    record_proposal,
)
from standards_atlas.application.semantic_qualification.review_package.sources import (
    duplicate_key,
    resolve_evidence,
)
from standards_atlas.application.semantic_qualification.review_package.validation import (
    confirmed_decisions,
    review_report,
    seal,
    verify_package,
)
from standards_atlas.cli import app


def inputs(tmp_path, *, count=10):
    manifest, items, spec = source_files(tmp_path / "inputs", count=count, reviews=True)
    golden_path = Path(spec["golden"])
    golden = yaml.safe_load(golden_path.read_bytes())
    golden["cases"] = golden["cases"][:2]
    golden_path.write_text(yaml.safe_dump(golden))
    return manifest, items, spec


def make_review(tmp_path, **kwargs):
    manifest, items, spec = inputs(tmp_path)
    root = tmp_path / "review"
    build_review_package(
        manifest=manifest, output=root, resources=RESOURCES, holdout_size=2, **kwargs
    )
    return root, manifest, items, spec


def decide(
    root,
    case,
    attribute,
    value=None,
    *,
    status="corrected",
    proposal=None,
    reviewer="synthetic-test-reviewer",
    comment="Synthetic contract decision.",
):
    _, state = load_review(root)
    return record_decision(
        root,
        expected_revision=state.revision,
        example_id=case,
        attribute=attribute,
        status=status,
        reviewer=reviewer,
        proposal_sha256=proposal,
        predicate=SemanticPredicate(equals=value) if status == "corrected" else None,
        comment=comment,
    )


def complete(root):
    package, state = load_review(root)
    values = {
        "primary_function": None,
        "primary_knowledge_kind": None,
        "role_semantics_present": False,
        "process_functions": [],
        "statement_functions": [],
        "role_relations": [],
        "primary_process_function": None,
        "knowledge_kinds": [],
        "applicability_present": False,
    }
    for case in package.cases:
        for attribute in case.attributes:
            state = decide(root, case.example_id, attribute, values[attribute])
    return package, state


def publish(root, output):
    return import_review_package(
        package=root,
        output=output,
        publish=True,
        holdout_declaration="Synthetic test only; no independence claim.",
    )


def write_dataset(spec, mutate):
    path = Path(spec["dataset"])
    data = json.loads(path.read_bytes())
    mutate(data)
    path.write_text(json.dumps(data))
    return data


def test_build_real_source_context_known_development_and_separate_proposals(tmp_path):
    root, _, items, spec = make_review(tmp_path)
    package, state = load_review(root)
    assert package.known_development_ids == (items[-2].id,)
    assert set(package.excluded_holdout_ids) == {items[0].id, items[1].id, items[-2].id}
    assert len([c for c in package.cases if c.split == "holdout"]) == 2
    assert len(state.proposals) == 8
    assert state.decisions == ()
    assert not review_report(package, state)["ready_for_publication"]
    for source in package.population:
        original = next(e for e in items if e.id == source.example_id)
        assert source.text == original.input["content"]["text"]
        assert source.clause_id == original.input["context"]["clause_id"]
        assert source.structure.origin == "legacy-context"
        assert all(f.origin == "unattributed" for f in source.structure.facts)
        assert "expected" not in source.model_dump()
    assert spec["dataset"] in package.source_location.values()
    assert "guidelines.md" in " ".join(package.rules)


def test_rebuild_never_overwrites_started_review(tmp_path):
    root, manifest, _, _ = make_review(tmp_path)
    before = (root / "review-state.json").read_bytes()
    with pytest.raises(ValueError, match="never overwrites"):
        build_review_package(manifest=manifest, output=root, resources=RESOURCES)
    assert (root / "review-state.json").read_bytes() == before


def test_sampling_is_order_and_expected_label_independent(tmp_path):
    root, manifest, _, spec = make_review(tmp_path)
    original, _ = load_review(root)

    def mutate(data):
        data["examples"].reverse()
        for case in data["examples"]:
            case["expected"] = {"primary_function": "UNTRUSTED-GOLD"}
            case["input"]["context"]["semantic"] = {"primary_function": "UNTRUSTED-MODEL"}

    write_dataset(spec, mutate)
    second = tmp_path / "second"
    build_review_package(manifest=manifest, output=second, resources=RESOURCES, holdout_size=2)
    current, _ = load_review(second)
    assert original.cases == current.cases
    assert original.population == current.population
    assert "UNTRUSTED" not in (second / "review-package.json").read_text()


def test_known_development_and_normalized_duplicates_excluded_from_holdout(tmp_path):
    manifest, items, spec = inputs(tmp_path)

    def mutate(data):
        source = data["examples"][-2]["input"]["content"]["text"]
        text = "  " + source.upper().replace(" ", "\n") + "  "
        data["examples"][2]["input"]["content"] = {
            "text": text,
            "hash": normalized_content_hash(text),
        }

    write_dataset(spec, mutate)
    root = tmp_path / "review"
    build_review_package(manifest=manifest, output=root, resources=RESOURCES, holdout_size=6)
    package, _ = load_review(root)
    holdout = {c.example_id for c in package.cases if c.split == "holdout"}
    assert items[2].id not in holdout
    assert len({duplicate_key(s) for s in package.population if s.example_id in holdout}) == 6


def test_too_large_or_overlapping_existing_holdout_fails_before_writing(tmp_path):
    manifest, _, spec = inputs(tmp_path)
    root = tmp_path / "review"
    with pytest.raises(ValueError, match="not enough disjoint"):
        build_review_package(manifest=manifest, output=root, resources=RESOURCES, holdout_size=100)
    holdout = Path(spec["semantic_suites"][1])
    dev = json.loads(Path(spec["semantic_suites"][0]).read_bytes())
    data = json.loads(holdout.read_bytes())
    data["cases"] = dev["cases"]
    holdout.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="overlaps"):
        build_review_package(manifest=manifest, output=root, resources=RESOURCES, holdout_size=1)
    assert not root.exists()


@pytest.mark.parametrize(
    "mutation",
    ["hash", "duplicate-id", "duplicate-clause", "duplicate-reference", "truncated", "empty"],
)
def test_invalid_sources_fail_before_artifacts(tmp_path, mutation):
    manifest, _, spec = inputs(tmp_path)

    def mutate(data):
        case, other = data["examples"][2:4]
        if mutation == "hash":
            case["input"]["content"]["text"] += " drift"
        elif mutation == "duplicate-id":
            case["id"] = other["id"]
        elif mutation.startswith("duplicate-"):
            key = "clause_id" if mutation == "duplicate-clause" else "reference"
            case["input"]["context"][key] = other["input"]["context"][key]
        elif mutation == "truncated":
            case["input"]["content"]["truncated"] = True
        else:
            case["input"]["content"] = {"text": "", "hash": normalized_content_hash("")}

    write_dataset(spec, mutate)
    with pytest.raises(ValueError):
        build_review_package(manifest=manifest, output=tmp_path / "review", resources=RESOURCES)
    assert not (tmp_path / "review").exists()


def test_unknown_development_ids_and_lost_existing_attributes_fail(tmp_path):
    manifest, _, spec = inputs(tmp_path)
    with pytest.raises(ValueError, match="known Development"):
        build_review_package(
            manifest=manifest,
            output=tmp_path / "review",
            resources=RESOURCES,
            holdout_size=1,
            development_ids=("missing",),
        )
    path = Path(spec["semantic_suites"][0])
    suite = json.loads(path.read_bytes())
    suite["cases"][0]["attributes"]["role_relations"] = {"equals": []}
    path.write_text(json.dumps(suite))
    with pytest.raises(ValueError, match="retain all existing"):
        build_review_package(
            manifest=manifest, output=tmp_path / "review", resources=RESOURCES, holdout_size=1
        )


def test_engineering_sentinels_become_development_suggestions_not_gold(tmp_path):
    manifest, items, spec = inputs(tmp_path)
    source = items[2]
    sentinel = tmp_path / "sentinels.json"
    sentinel.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "semantic-readiness-checks",
                "id": "test-sentinel",
                "cases": [
                    {
                        "example_id": source.id,
                        "document_key": "TEST",
                        "content_hash": source.input["content"]["hash"],
                        "source_text": source.input["content"]["text"],
                        "process_check": {"must_be_empty": True},
                    }
                ],
            }
        )
    )
    spec["sentinel_suites"] = [str(sentinel)]
    manifest.write_text(yaml.safe_dump(spec))
    root = tmp_path / "review"
    build_review_package(manifest=manifest, output=root, resources=RESOURCES, holdout_size=2)
    package, state = load_review(root)
    assert source.id in package.known_development_ids
    assert source.id in package.excluded_holdout_ids
    assert state.proposals[-1].producer_kind == "engineering"
    assert not state.decisions


def test_suggestions_never_count_as_confirmed_imports_and_dry_run_is_read_only(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    result = import_review_package(package=root, dry_run=True, publish=True)
    assert result["live_sources_verified"]
    assert not result["importable"]
    assert len(result["unresolved"]) == 12
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before
    with pytest.raises(ValueError, match="blocked"):
        publish(root, tmp_path / "published")
    assert not (tmp_path / "published").exists()


def test_confirmation_binds_exact_proposal_and_new_proposal_cannot_replace_review(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    old = state.proposals[0]
    state = decide(
        root,
        old.example_id,
        old.attribute,
        status="confirmed",
        proposal=old.proposal_sha256,
    )
    decision = state.decisions[-1]
    assert predicate_data(decision.predicate) == predicate_data(old.predicate)
    state = record_proposal(
        root,
        expected_revision=state.revision,
        example_id=old.example_id,
        attribute=old.attribute,
        predicate=SemanticPredicate(equals=None),
        producer="local-codex",
        producer_kind="model",
        model="synthetic-model",
        rationale="Alternate synthetic proposal",
        provenance="test-run",
    )
    assert state.decisions[-1] == decision
    assert confirmed_decisions(state)[(old.example_id, old.attribute)] == decision
    with pytest.raises(ValueError, match="stale review"):
        record_decision(
            root,
            expected_revision=0,
            example_id=old.example_id,
            attribute=old.attribute,
            status="confirmed",
            reviewer="tester",
            proposal_sha256=old.proposal_sha256,
        )
    assert (root / "history").is_dir()


def test_reject_defer_and_supersede_do_not_invent_negative_values(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    _, state = load_review(root)
    proposal = state.proposals[0]
    state = decide(
        root,
        proposal.example_id,
        proposal.attribute,
        status="rejected",
        proposal=proposal.proposal_sha256,
    )
    assert state.decisions[-1].predicate is None
    assert confirmed_decisions(state) == {}
    state = decide(root, proposal.example_id, proposal.attribute, value=None)
    previous = state.decisions[-1]
    with pytest.raises(ValueError, match="comment"):
        decide(root, proposal.example_id, proposal.attribute, status="deferred", comment="")
    state = decide(root, proposal.example_id, proposal.attribute, status="deferred")
    assert state.decisions[-1].supersedes == previous.decision_sha256
    assert not confirmed_decisions(state)
    assert len(state.decisions) == 3


@pytest.mark.parametrize(
    "attribute,payload",
    [
        ("role_semantics_present", {"equals": 0}),
        ("role_semantics_present", {"equals": "false"}),
        ("role_semantics_present", {"equals": None}),
        ("primary_function", {"must_be_empty": True}),
        ("primary_function", {"equals": "wrong-label"}),
        ("process_functions", {"equals": "activity"}),
        ("process_functions", {"equals": ["activity", "activity"]}),
        ("process_functions", {"must_include": ["wrong-label"]}),
        ("role_relation_types", {"equals": []}),
    ],
)
def test_invalid_typed_predicates_rejected(tmp_path, attribute, payload):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    with pytest.raises(ValueError):
        validate_predicate(
            attribute,
            SemanticPredicate.model_validate(payload),
            package.output_schema,
        )


@pytest.mark.parametrize(
    "payload",
    [{}, {"equals": False, "must_be_empty": True}, {"must_include": []}, {"must_be_empty": False}],
)
def test_missing_or_ambiguous_predicate_operator_rejected(payload):
    with pytest.raises(ValueError):
        SemanticPredicate.model_validate(payload)


def test_explicit_false_null_and_empty_roundtrip_in_both_suites(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    assert publish(root, output)["ready_for_publication"]
    for split in ("development", "holdout"):
        suite, binding = load_bound_suite(output / f"{split}.yaml", items, resources=RESOURCES)
        assert suite.schema_version == "1.0"
        assert suite.status == "published"
        assert binding is not None
        for case in suite.cases:
            assert predicate_data(case.attributes["primary_function"]) == {"equals": None}
            assert predicate_data(case.attributes["role_semantics_present"]) == {"equals": False}
            assert predicate_data(case.attributes["process_functions"]) == {"equals": []}
    # Idempotence must not even rewrite the pair/evidence timestamps.
    timestamps = {p.name: p.stat().st_mtime_ns for p in output.iterdir()}
    publish(root, output)
    assert timestamps == {p.name: p.stat().st_mtime_ns for p in output.iterdir()}


def test_partial_draft_contains_only_confirmed_attributes_and_lists_unresolved(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    for split in ("development", "holdout"):
        case = next(c for c in package.cases if c.split == split)
        decide(root, case.example_id, "role_semantics_present", False)
    output = tmp_path / "draft"
    result = import_review_package(package=root, output=output)
    assert result["importable"] and not result["ready_for_publication"]
    assert len(result["unresolved"]) == 10
    for split in ("development", "holdout"):
        suite = SemanticReferenceSuite.model_validate(
            yaml.safe_load((output / f"{split}.yaml").read_bytes())
        )
        assert suite.status == "draft"
        assert all(set(c.attributes) == {"role_semantics_present"} for c in suite.cases)
    with pytest.raises(ValueError, match="incomplete"):
        publish(root, tmp_path / "published")


def test_publication_needs_holdout_declaration_and_complete_predeclared_coverage(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    complete(root)
    with pytest.raises(ValueError, match="holdout-use declaration"):
        import_review_package(package=root, output=tmp_path / "published", publish=True)
    profile = ReviewProfile.model_validate(
        {
            "coverage": [
                {
                    "split": "holdout",
                    "attribute": "role_semantics_present",
                    "minimum": 1,
                    "predicate": {"equals": True},
                },
            ]
        }
    )
    package, state = load_review(root)
    modified = seal(
        ReviewPackage,
        {**package.model_dump(mode="json"), "profile": profile.model_dump(mode="json")},
        "package_sha256",
    )
    from standards_atlas.application.semantic_qualification.review_package.model import ReviewState

    state = seal(
        ReviewState,
        {**state.model_dump(mode="json"), "package_sha256": modified.package_sha256},
        "state_sha256",
    )
    report = review_report(modified, state)
    assert not report["ready_for_publication"]
    assert report["coverage_gaps"][-1]["observed"] == 0


@pytest.mark.parametrize("change", ["text", "heading", "ancestor", "reference"])
def test_import_rechecks_current_text_identity_and_context(tmp_path, change):
    root, _, _, spec = make_review(tmp_path)
    complete(root)

    def mutate(data):
        case = data["examples"][-2]["input"]
        if change == "text":
            text = case["content"]["text"] + " altered"
            case["content"] = {"text": text, "hash": normalized_content_hash(text)}
        elif change == "ancestor":
            case["context"]["ancestor_headings"] = [
                {"clause_id": "parent", "reference": "3", "heading": "Different parent"},
            ]
        else:
            case["context"][change] = "different"

    write_dataset(spec, mutate)
    with pytest.raises(ValueError, match="changed since build"):
        publish(root, tmp_path / "published")
    assert not (tmp_path / "published").exists()


def test_changed_instructions_and_golden_inputs_block_import(tmp_path):
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Explicit test instructions.")
    root, _, _, _ = make_review(tmp_path, instructions=instructions)
    complete(root)
    instructions.write_text("A different task definition.")
    with pytest.raises(ValueError, match="input/rules changed"):
        publish(root, tmp_path / "published")


def test_package_and_source_tampering_is_detected_even_after_outer_rehash(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    raw = package.model_dump(mode="json")
    raw["population"][0]["text"] += " tampered"
    bad = ReviewPackage.model_validate(raw)
    with pytest.raises(ValueError, match="package fingerprint"):
        verify_package(bad)
    bad = seal(ReviewPackage, raw, "package_sha256")
    with pytest.raises(ValueError, match="source binding"):
        verify_package(bad)


def test_quote_resolution_unicode_context_ambiguity_and_untrusted_markup(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    source = package.population[0]
    text = "α😀 repeated word; repeated word <script>data</script>"
    source = source.model_copy(update={"text": text})
    span = resolve_evidence(source, EvidenceQuote(quote="α😀"))
    assert (span.start, span.end) == (0, 2)  # Unicode code points, not UTF-16 units.
    with pytest.raises(ValueError, match="exactly one"):
        resolve_evidence(source, EvidenceQuote(quote="repeated word"))
    quote = EvidenceQuote(quote="repeated word", prefix="; ")
    span = resolve_evidence(source, quote)
    assert text[span.start : span.end] == quote.quote
    span = resolve_evidence(source, EvidenceQuote(quote="<script>data</script>"))
    assert span.quote == "<script>data</script>"  # Data only; no HTML rendering in this slice.
    with pytest.raises(ValueError, match="frozen source"):
        resolve_evidence(source, EvidenceQuote(target="semantic:rationale", quote="anything"))
    index = next(i for i, f in enumerate(source.structure.facts) if f.field == "heading")
    assert resolve_evidence(source, EvidenceQuote(target=f"fact:{index}", quote="process")).end == 7


def test_invalid_model_proposal_does_not_modify_state(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    case = package.cases[0]
    before = (root / "review-state.json").read_bytes()
    for model, quote in ((None, "process"), ("test-model", "not actually in the source")):
        with pytest.raises(ValueError):
            record_proposal(
                root,
                expected_revision=state.revision,
                example_id=case.example_id,
                attribute="primary_function",
                predicate=SemanticPredicate(equals=None),
                producer="codex",
                producer_kind="model",
                model=model,
                rationale="A proposal",
                provenance="synthetic",
                evidence=(EvidenceQuote(quote=quote),),
            )
    assert (root / "review-state.json").read_bytes() == before


def test_atomic_pair_failure_and_existing_publication_preserved(tmp_path, monkeypatch):
    root, _, _, _ = make_review(tmp_path)
    complete(root)
    from standards_atlas.application.semantic_qualification.review_package import storage

    def fail_rename(*args):
        raise OSError("simulated interrupted publication")

    with monkeypatch.context() as patch:
        patch.setattr(storage.os, "rename", fail_rename)
        with pytest.raises(OSError, match="simulated"):
            publish(root, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".failed-*"))
    output = tmp_path / "published"
    publish(root, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    package, _ = load_review(root)
    decide(root, package.cases[0].example_id, "role_semantics_present", True)
    with pytest.raises(ValueError, match="never overwritten"):
        publish(root, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


def test_locks_symlinks_and_public_data_outputs_are_rejected(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = complete(root)
    lock = root / ".review.lock"
    lock.write_text("9999")
    with pytest.raises(ValueError, match="writer is active"):
        publish(root, tmp_path / "published")
    lock.unlink()
    symlink = tmp_path / "alias"
    symlink.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        load_review(symlink)
    with pytest.raises(ValueError, match="canonical/public"):
        publish(root, Path("data/never-create-review-fixture"))
    assert not Path("data/never-create-review-fixture").exists()


def test_bound_suite_pair_tampering_and_current_context_drift(tmp_path):
    root, _, items, _ = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    modified = copy.deepcopy(items[-2].input)
    modified["context"]["heading"] = "Changed context but same text hash"
    sources = [replace(e, input=modified) if e.id == items[-2].id else e for e in items]
    with pytest.raises(ValueError, match="context drift"):
        load_bound_suite(output / "holdout.yaml", sources)
    path = output / "development.yaml"
    raw = yaml.safe_load(path.read_bytes())
    raw["cases"][0]["attributes"]["role_semantics_present"] = {"equals": True}
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="pair is inconsistent"):
        load_bound_suite(output / "holdout.yaml", items)


def test_frozen_campaign_carries_review_evidence_and_rejects_missing_pair(tmp_path):
    root, manifest, items, spec = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    spec["semantic_suites"] = [
        str(output / f"{split}.yaml") for split in ("development", "holdout")
    ]
    manifest.write_text(yaml.safe_dump(spec))
    campaign = tmp_path / "campaign"
    prepare_campaign(manifest=manifest, output=campaign, resources=RESOURCES)
    binding_path = campaign / "inputs/semantic-review-bindings.json"
    assert binding_path.is_file()
    load_campaign(campaign, RESOURCES)
    verify_prepared_campaign(manifest=manifest, campaign=campaign, resources=RESOURCES)
    # Execution remains reproducible after an external working review file disappears.
    (output / "review-evidence.json").unlink()
    load_campaign(campaign, RESOURCES)
    # Removing even the inventory entry cannot silently downgrade a bound suite to legacy.
    path = campaign / "campaign-plan.json"
    raw = json.loads(path.read_bytes())
    del raw["files"]["inputs/semantic-review-bindings.json"]
    raw["campaign_sha256"] = structure_fingerprint(
        {k: v for k, v in raw.items() if k != "campaign_sha256"}
    )
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="review evidence inventory"):
        load_campaign(campaign, RESOURCES)


def test_campaign_needs_both_exported_suites(tmp_path):
    root, manifest, _, spec = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    spec["semantic_suites"] = [str(output / "development.yaml")]
    manifest.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="both unchanged suites"):
        prepare_campaign(manifest=manifest, output=tmp_path / "campaign", resources=RESOURCES)


def test_recomputed_publication_report_cannot_hide_unresolved_checks(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    raw = json.loads((output / "review-evidence.json").read_bytes())
    raw["report"]["splits"]["holdout"]["complete_cases"] = 999
    bad = seal(ReviewPublication, raw, "evidence_sha256")
    with pytest.raises(ValueError, match="coverage/report"):
        verify_publication(bad)


def test_cross_attribute_contradiction_blocks_even_draft_import(tmp_path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "attributes": [
                    "primary_function",
                    "primary_knowledge_kind",
                    "role_semantics_present",
                    "process_functions",
                    "statement_functions",
                    "role_relations",
                ],
            }
        )
    )
    root, _, _, _ = make_review(tmp_path, profile_path=profile)
    package, _ = complete(root)
    case = package.cases[0].example_id
    decide(root, case, "primary_function", "requirement")
    decide(
        root,
        case,
        "role_relations",
        [{"actor": "reviewer", "relation_class": "performs", "target": "inspection"}],
    )
    result = import_review_package(package=root, dry_run=True)
    assert len(result["conflicts"]) == 2
    assert not result["importable"]
    with pytest.raises(ValueError, match="contradictory"):
        import_review_package(package=root, output=tmp_path / "draft")


def test_cli_build_show_decide_and_dry_run(tmp_path):
    runner = CliRunner()
    manifest, _, _ = inputs(tmp_path)
    root = tmp_path / "review"
    result = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-build",
            "--manifest",
            str(manifest),
            "--output",
            str(root),
            "--holdout-size",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    shown = runner.invoke(app, ["evaluation", "partial-review-show", "--package", str(root)])
    assert shown.exit_code == 0, shown.output
    data = json.loads(shown.output)
    case = data["cases"][0]["example_id"]
    result = runner.invoke(
        app,
        [
            "evaluation",
            "partial-review-decide",
            "--package",
            str(root),
            "--case",
            case,
            "--attribute",
            "role_semantics_present",
            "--status",
            "corrected",
            "--reviewer",
            "synthetic tester",
            "--revision",
            str(data["revision"]),
            "--equals",
            "false",
            "--comment",
            "synthetic explicit negative",
        ],
    )
    assert result.exit_code == 0, result.output
    decision = json.loads(result.output)["decision"]
    assert decision["predicate"] == {"equals": False}
    result = runner.invoke(
        app, ["evaluation", "partial-review-show", "--package", str(root), "--case", case]
    )
    assert result.exit_code == 0, result.output
    assert "source" in json.loads(result.output)
    result = runner.invoke(
        app,
        ["evaluation", "partial-review-import", "--package", str(root), "--publish", "--dry-run"],
    )
    assert result.exit_code == 1
    assert not json.loads(result.output)["importable"]


@pytest.mark.parametrize(
    "command",
    [
        "partial-review-build",
        "partial-review-show",
        "partial-review-decide",
        "partial-review-import",
    ],
)
def test_cli_help(command):
    result = CliRunner().invoke(app, ["evaluation", command, "--help"])
    assert result.exit_code == 0, result.output


def test_future_schemas_and_blank_reviewers_are_not_accepted(tmp_path):
    with pytest.raises(ValueError):
        ReviewProfile.model_validate({"schema_version": "99"})
    with pytest.raises(ValueError):
        ReviewProfile.model_validate({"attributes": ["primary_function"]})
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    with pytest.raises(ValueError):
        decide(root, package.cases[0].example_id, "primary_function", reviewer=" ")
    raw = package.model_dump(mode="json")
    raw["schema_version"] = "99"
    with pytest.raises(ValueError):
        ReviewPackage.model_validate(raw)


def test_strict_empty_operator_and_review_timestamps(tmp_path):
    for value in (1, "true", "false"):
        with pytest.raises(ValueError):
            SemanticPredicate(must_be_empty=value)
    root, _, _, _ = make_review(tmp_path)
    package, _ = complete(root)
    _, state = load_review(root)
    raw = state.decisions[0].model_dump(mode="json")
    raw["reviewed_at"] = "2026-09-13T12:00:00"
    from standards_atlas.application.semantic_qualification.review_package.model import (
        ReviewDecision,
    )

    with pytest.raises(ValueError):
        ReviewDecision.model_validate(raw)


def test_campaign_manifest_hand_off_does_not_prevent_idempotent_reimport(tmp_path):
    root, manifest, _, spec = make_review(tmp_path)
    complete(root)
    output = tmp_path / "published"
    publish(root, output)
    spec["semantic_suites"] = [
        str(output / f"{split}.yaml") for split in ("development", "holdout")
    ]
    manifest.write_text(yaml.safe_dump(spec))
    assert publish(root, output)["importable"]
    plan = prepare_campaign(manifest=manifest, output=tmp_path / "campaign", resources=RESOURCES)
    assert plan["schema_version"] == "2.0"
    assert plan["review_evidence"] == {"kind": "atlas_publication"}


def test_campaign_additional_dimensions_are_inherited_by_default_review_profile(tmp_path):
    manifest, _, spec = inputs(tmp_path)
    spec["required_semantic_attributes"] = [
        "primary_function",
        "primary_knowledge_kind",
        "role_semantics_present",
        "process_functions",
        "applicability_present",
    ]
    manifest.write_text(yaml.safe_dump(spec))
    root = tmp_path / "review"
    build_review_package(manifest=manifest, output=root, resources=RESOURCES, holdout_size=2)
    package, _ = load_review(root)
    assert "applicability_present" in package.profile.attributes
    profile = tmp_path / "core-only.yaml"
    profile.write_text(yaml.safe_dump(ReviewProfile().model_dump(mode="json")))
    with pytest.raises(ValueError, match="omit required campaign"):
        build_review_package(
            manifest=manifest,
            output=tmp_path / "other",
            resources=RESOURCES,
            holdout_size=2,
            profile_path=profile,
        )


def test_confirming_unrelated_proposal_or_changing_confirmed_value_is_rejected(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    proposal = state.proposals[0]
    other = next(c for c in package.cases if c.example_id != proposal.example_id)
    with pytest.raises(ValueError, match="unrelated proposal"):
        decide(
            root,
            other.example_id,
            proposal.attribute,
            status="confirmed",
            proposal=proposal.proposal_sha256,
        )
    with pytest.raises(ValueError, match="not a replacement predicate"):
        record_decision(
            root,
            expected_revision=state.revision,
            example_id=proposal.example_id,
            attribute=proposal.attribute,
            status="confirmed",
            reviewer="synthetic",
            proposal_sha256=proposal.proposal_sha256,
            predicate=SemanticPredicate(equals=None),
        )


def test_review_state_rehash_cannot_turn_confirmation_into_a_different_value(tmp_path):
    from standards_atlas.application.semantic_qualification.review_package.model import (
        ReviewDecision,
        ReviewState,
    )
    from standards_atlas.application.semantic_qualification.review_package.validation import (
        verify_state,
    )

    root, _, _, _ = make_review(tmp_path)
    package, state = load_review(root)
    proposal = state.proposals[0]
    state = decide(
        root,
        proposal.example_id,
        proposal.attribute,
        status="confirmed",
        proposal=proposal.proposal_sha256,
    )
    raw = state.model_dump(mode="json")
    bad = {**raw["decisions"][0], "predicate": {"equals": None}}
    raw["decisions"][0] = seal(ReviewDecision, bad, "decision_sha256").model_dump(mode="json")
    changed = seal(ReviewState, raw, "state_sha256")
    with pytest.raises(ValueError, match="exact reviewed proposal"):
        verify_state(package, changed)


def test_history_symlink_is_rejected_before_state_write(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "history").symlink_to(outside, target_is_directory=True)
    before = (root / "review-state.json").read_bytes()
    with pytest.raises(ValueError, match="history symlink"):
        decide(root, package.cases[0].example_id, "primary_function", None)
    assert (root / "review-state.json").read_bytes() == before
    assert not list(outside.iterdir())


@pytest.mark.parametrize(
    "actual,required,expected",
    [
        ({"must_include": ["activity"]}, {"equals": ["activity"]}, False),
        ({"equals": ["activity", "output"]}, {"must_include": ["activity"]}, True),
        ({"equals": []}, {"must_be_empty": True}, True),
        ({"must_be_empty": True}, {"equals": []}, True),
        ({"equals": False}, {"equals": True}, False),
        ({"equals": None}, {"equals": []}, False),
    ],
)
def test_coverage_counts_only_predicates_that_prove_the_requirement(actual, required, expected):
    from standards_atlas.application.semantic_qualification.review_package.validation import _covers

    assert (
        _covers(
            SemanticPredicate.model_validate(actual), SemanticPredicate.model_validate(required)
        )
        is expected
    )


def test_review_rule_inventory_cannot_escape_resource_root(tmp_path):
    root, _, _, _ = make_review(tmp_path)
    package, _ = load_review(root)
    raw = package.model_dump(mode="json")
    raw["rules"]["../../outside.txt"] = "untrusted file target"
    raw["rules_sha256"] = structure_fingerprint(raw["rules"])
    changed = seal(ReviewPackage, raw, "package_sha256")
    with pytest.raises(ValueError, match="closed contract"):
        verify_package(changed)
