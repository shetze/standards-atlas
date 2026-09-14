"""Freeze source-only cohorts and all comparison resources before qualification."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.model.source_structure import structure_fingerprint
from standards_atlas.application.schema import (
    require_current_payload,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.application.semantic_qualification.acceptance_profiles import (
    PartialAcceptanceProfile,
)
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.campaign_contract import (
    CAMPAIGN_SCHEMA_VERSION,
    REVIEW_ARCHIVE_NAME,
    REVIEW_BINDINGS_NAME,
    QualificationCampaignArtifact,
    classify_review_evidence,
    verify_review_evidence,
)
from standards_atlas.application.semantic_qualification.mixed_consensus import (
    input_selection_fingerprint,
)
from standards_atlas.application.semantic_qualification.partial_cascade import (
    effective_cascade_configuration,
)
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _atomic_json,
    _json_bytes,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QualificationCampaign,
    SemanticReferenceSuite,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)


def stratum(example: EvaluationExample) -> str:
    context = example.input["context"]
    return (
        str(context.get("document_key", "unknown"))
        + "|"
        + str(context.get("clause_type", "unknown"))
    )


def stratified_sample(examples, count: int, seed: int) -> tuple:
    """Hamilton proportional quotas and hash ranking, independent of input order.

    Small strata may receive no slot: coverage and quotas are reported, not
    silently described as complete. No labels or model outputs select cases.
    """
    if count < 1 or count > len(examples):
        raise ValueError("sample size must be within the source population")
    groups = defaultdict(list)
    for example in examples:
        groups[stratum(example)].append(example)
    n = len(examples)
    quota = {key: count * len(items) // n for key, items in groups.items()}
    remainder = sorted(groups, key=lambda k: (-(count * len(groups[k]) % n), k))
    for key in remainder[: count - sum(quota.values())]:
        quota[key] += 1
    selected = []
    for key, items in sorted(groups.items()):
        ranked = sorted(
            items,
            key=lambda e: structure_fingerprint(
                {"seed": seed, "id": e.id, "content": e.input["content"]["hash"]}
            ),
        )
        selected.extend(ranked[: quota[key]])
    return tuple(sorted(selected, key=lambda e: e.id))


def _checked_examples(examples):
    ids, coordinates = set(), set()
    for item in examples:
        coordinate = (item.input["context"]["document_key"], item.input["context"]["clause_id"])
        if item.id in ids or coordinate in coordinates:
            raise ValueError("campaign sources require unique example and clause coordinates")
        if normalized_content_hash(item.input["content"]["text"]) != item.input["content"]["hash"]:
            raise ValueError(f"source text/content hash mismatch: {item.id}")
        ids.add(item.id)
        coordinates.add(coordinate)
    return {e.id: e for e in examples}


def _validate_check_source(case, by_id):
    example = by_id.get(case["example_id"])
    if example is None:
        raise ValueError(f"semantic check missing from source: {case['example_id']}")
    if (
        example.input["context"]["document_key"] != case["document_key"]
        or example.input["content"]["hash"] != case["content_hash"]
    ):
        raise ValueError(f"semantic check source drift: {example.id}")
    if (
        "source_text" in case
        and normalized_content_hash(case["source_text"]) != case["content_hash"]
    ):
        raise ValueError("sentinel source text does not match its hash")


def build_cohorts(examples, golden, suites, sentinels, *, sample_size, seed):
    by_id = _checked_examples(examples)
    by_coordinate = {
        (e.input["context"]["document_key"], e.input["context"]["clause_id"]): e for e in examples
    }
    cohorts = {
        key: [] for key in ("representative", "golden", "sentinels", "development", "holdout")
    }
    cohorts["representative"] = [e.id for e in stratified_sample(examples, sample_size, seed)]
    golden_text_comparisons = []
    for case in golden.cases:
        if case.status != "published":
            continue
        item = by_coordinate.get((case.document_key, case.clause_id))
        if item is None:
            raise ValueError(f"published Golden case missing: {case.document_key}/{case.clause_id}")
        exact = normalized_content_hash(case.text) == item.input["content"]["hash"]
        if not exact and case.text.rstrip("\r\n") != item.input["content"]["text"].rstrip("\r\n"):
            raise ValueError(f"published Golden text differs from source: {case.clause_id}")
        golden_text_comparisons.append(
            {
                "example_id": item.id,
                "source_hash": item.input["content"]["hash"],
                "golden_text_hash": normalized_content_hash(case.text),
                "match": "exact" if exact else "terminal_linebreaks_only",
            }
        )
        cohorts["golden"].append(item.id)
    for suite in suites:
        for case in suite.cases:
            _validate_check_source(case.model_dump(), by_id)
            cohorts[suite.split].append(case.example_id)
    for suite in sentinels:
        require_supported_schema("semantic-readiness-checks", suite.get("schema_version"))
        if suite.get("kind") != "semantic-readiness-checks" or not suite.get("cases"):
            raise ValueError("invalid or empty sentinel suite")
        for case in suite["cases"]:
            _validate_check_source(case, by_id)
            cohorts["sentinels"].append(case["example_id"])
    cohorts = {key: sorted(set(ids)) for key, ids in cohorts.items()}
    if set(cohorts["holdout"]) & set(
        cohorts["development"] + cohorts["golden"] + cohorts["sentinels"]
    ):
        raise ValueError("declared holdout overlaps Golden/development/sentinel cases")
    cohorts["evaluation_union"] = sorted({i for ids in cohorts.values() for i in ids})
    populations = Counter(stratum(e) for e in examples)
    sampled = Counter(stratum(by_id[i]) for i in cohorts["representative"])
    return {
        "cohorts": cohorts,
        "strata": [
            {"stratum": k, "population": n, "sample": sampled[k]}
            for k, n in sorted(populations.items())
        ],
        "selection_method": "proportional-document-type-hash-v1",
        "golden_text_comparisons": golden_text_comparisons,
        "source_population_count": len(examples),
        "source_population_sha256": input_selection_fingerprint(tuple(examples)),
        "sample_size": sample_size,
        "seed": seed,
        "all_strata_represented": all(sampled[k] for k in populations),
        "holdout_provenance": "declared by supplied review, not proof of no prior model exposure",
    }


def _detail_resources(resources: Path, matrix) -> dict[str, str]:
    """Bind the unchanged downstream prompts/tasks as well as the joint task."""
    policy = matrix.applicability_decision_policy
    task = matrix.applicability_detail_enrichment.task
    bound = {}
    for role in ("primary", "rescue", "confirmation"):
        spec = getattr(policy, role)
        for folder in (
            resources / "tasks" / task / spec.task_version,
            resources / "prompts" / task / spec.prompt_version,
        ):
            if not folder.is_dir():
                raise ValueError(f"missing detail resources: {folder}")
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    bound[path.relative_to(resources).as_posix()] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
    return bound


def _review_inputs(spec, examples, resources):
    from standards_atlas.application.semantic_qualification.review_package.publication import (
        load_bound_suite,
        publication_suites,
    )

    if spec.review_bundle is not None:
        from standards_atlas.application.semantic_qualification.review_package.handoff import (
            load_review_handoff,
        )

        handoff = load_review_handoff(
            spec.review_bundle, requested=spec, examples=examples, resources=resources
        )
        return (
            [(suite, handoff.publication) for suite in publication_suites(handoff.publication)],
            handoff.archive,
        )
    return [load_bound_suite(p, examples, resources=resources) for p in spec.semantic_suites], None


def prepare_campaign(*, manifest: Path, output: Path, resources: Path) -> dict:
    spec = QualificationCampaign.load(manifest)
    require_current_schema("partial-qualification-manifest", spec.schema_version)
    output = output.resolve()
    source_path = spec.run or spec.dataset
    inputs = (manifest, source_path, spec.golden, *spec.semantic_suites, *spec.sentinel_suites)
    if spec.review_bundle is not None:
        inputs += (spec.review_bundle,)
    _output_is_separate(output, inputs)
    if output.exists():
        raise ValueError("campaign preparation needs a new output; run resumes frozen campaigns")
    source = load_partial_inputs(run=spec.run, dataset=spec.dataset)
    examples = tuple(sorted(source.examples, key=lambda e: e.id))
    golden = ApplicabilityGoldenCorpus.load(spec.golden)
    loaded_suites, review_archive = _review_inputs(spec, examples, resources)
    suites = tuple(suite for suite, _ in loaded_suites)
    review_bindings = {
        binding.evidence_sha256: binding.model_dump(mode="json")
        for _, binding in loaded_suites
        if binding is not None
    }
    evidence = classify_review_evidence(
        spec, suites, has_bindings=bool(review_bindings), has_archive=review_archive is not None
    )
    verify_review_evidence(
        evidence=evidence,
        spec=spec,
        suites=suites,
        bindings=list(review_bindings.values()),
        archive=review_archive,
        examples=examples,
        resources=resources,
    )
    sentinels = tuple(json.loads(p.read_bytes()) for p in spec.sentinel_suites)
    if len({s.id for s in suites}) != len(suites):
        raise ValueError("semantic suite ids must be unique")
    selection = build_cohorts(
        examples, golden, suites, sentinels, sample_size=spec.sample_size, seed=spec.seed
    )
    variants = {}
    for variant in spec.variants:
        matrix = QualificationMatrixManifest.load(variant.matrix)
        if matrix.execution.mode != "cascade" or len(matrix.execution.stages) < 1:
            raise ValueError("campaign variants require existing cascade matrices")
        if matrix.dataset_version != source.dataset_version or (
            source.corpus_id != "source-dataset" and matrix.corpus_id != source.corpus_id
        ):
            raise ValueError("campaign matrix corpus/version differs from input")
        if spec.repetitions < matrix.applicability_decision_policy.required_fresh_repetitions:
            raise ValueError("campaign repetitions cannot weaken the matrix freshness requirement")
        if not matrix.applicability_decision_policy.enabled:
            raise ValueError("campaign qualification requires final applicability policy")
        profile = (
            PartialAcceptanceProfile.load(variant.acceptance_profile)
            if variant.acceptance_profile
            else None
        )
        variants[variant.id] = {
            "matrix": matrix.model_dump(mode="json"),
            "acceptance_profile": profile.model_dump(mode="json") if profile else None,
            "configuration": effective_cascade_configuration(
                matrix, resources, variant.prompt, profile
            ),
            "detail_resources": _detail_resources(resources, matrix),
        }
    # Comparing different voters/settings would confound the declared partial-policy experiment.
    baseline = variants[spec.baseline]
    for variant in variants.values():
        for key in (
            "models",
            "execution",
            "consensus",
            "applicability_decision_policy",
            "applicability_detail_enrichment",
        ):
            if variant["matrix"][key] != baseline["matrix"][key]:
                raise ValueError(f"comparison variants change nonexperimental matrix field: {key}")
    payloads = {
        "inputs/population.json": [{"id": e.id, "input": e.input} for e in examples],
        "inputs/golden.json": golden.model_dump(mode="json"),
        "inputs/semantic-suites.json": [
            s.model_dump(mode="json", exclude_unset=True) for s in suites
        ],
        "inputs/sentinel-suites.json": list(sentinels),
        "selection.json": selection,
    }
    if review_bindings:
        payloads[REVIEW_BINDINGS_NAME] = [review_bindings[key] for key in sorted(review_bindings)]
    serialized = {name: _json_bytes(payload) for name, payload in payloads.items()}
    if review_archive is not None:
        serialized[REVIEW_ARCHIVE_NAME] = review_archive
    files = {name: hashlib.sha256(raw).hexdigest() for name, raw in serialized.items()}
    require_current_schema("partial-qualification-campaign", CAMPAIGN_SCHEMA_VERSION)
    definition = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "review_evidence": evidence.model_dump(mode="json"),
        "kind": "partial-qualification-campaign",
        "specification": spec.model_dump(mode="json"),
        "variants": variants,
        "files": files,
        "source_fingerprints": source.fingerprints,
        "declared_published_golden_count": len(selection["cohorts"]["golden"]),
        "expected_fresh_modes": ["fresh_end_to_end", "fresh_detail_fixed_presence"],
        "default_workflow_changed": False,
    }
    definition["campaign_sha256"] = structure_fingerprint(definition)
    require_current_payload("partial-qualification-campaign", definition)
    QualificationCampaignArtifact.model_validate(definition)
    output.mkdir(parents=True)
    for name, raw in serialized.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    _atomic_json(output / "campaign-plan.json", definition)
    by_id = {e.id: e for e in examples}
    for cohort in ("evaluation_union", "representative", "golden"):
        _atomic_json(
            output / f"datasets/{cohort}.json",
            {
                "version": source.dataset_version,
                "corpus_id": source.corpus_id,
                "examples": [asdict(by_id[i]) for i in selection["cohorts"][cohort]],
            },
        )
    with (output / "review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "example_id",
                "document_key",
                "content_hash",
                "cohorts",
                "review_status",
                "reviewer",
                "reference",
            ]
        )
        for i in selection["cohorts"]["evaluation_union"]:
            e = by_id[i]
            writer.writerow(
                [
                    i,
                    e.input["context"]["document_key"],
                    e.input["content"]["hash"],
                    ",".join(
                        k
                        for k, ids in selection["cohorts"].items()
                        if i in ids and k != "evaluation_union"
                    ),
                    "pending",
                    "",
                    "",
                ]
            )
    return definition


def safe_files(root: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"symlink in qualification evidence: {p}")
        if p.is_file():
            if p.name.endswith(".lock"):
                raise ValueError("qualification evidence has an active writer")
            hashes[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def _verify_input_inventory(root: Path, expected_names: frozenset[str]) -> None:
    """Do not allow removed manifest entries to hide remaining frozen evidence files.

    Execution outputs/datasets live outside inputs and are not part of this closed
    inventory. Parent symlinks and special files inside inputs are never followed.
    """
    inputs = root / "inputs"
    if inputs.is_symlink() or not inputs.is_dir():
        raise ValueError("unsafe or missing campaign inputs")
    names = set()
    for path in inputs.rglob("*"):
        if path.is_symlink():
            raise ValueError("unsafe campaign input symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("unsafe campaign input")
        names.add(path.relative_to(root).as_posix())
    if names != {n for n in expected_names if n.startswith("inputs/")}:
        raise ValueError("campaign evidence inventory differs from frozen input files")


def load_campaign(root: Path, resources: Path):
    root = root.resolve()
    plan_path = root / "campaign-plan.json"
    if plan_path.is_symlink():
        raise ValueError("unsafe campaign plan")
    definition = json.loads(plan_path.read_bytes())
    if not isinstance(definition, dict):
        raise ValueError("qualification campaign artifact must contain a mapping")
    require_supported_schema("partial-qualification-campaign", definition.get("schema_version"))
    artifact = QualificationCampaignArtifact.model_validate(definition)
    claimed = definition["campaign_sha256"]
    if claimed != structure_fingerprint(
        {k: v for k, v in definition.items() if k != "campaign_sha256"}
    ):
        raise ValueError("campaign plan fingerprint mismatch")
    spec = artifact.specification
    files = definition["files"]
    review_name = REVIEW_BINDINGS_NAME
    archive_name = REVIEW_ARCHIVE_NAME
    _verify_input_inventory(root, artifact.review_evidence.input_names)
    payloads = {}
    for name, digest in files.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("unsafe campaign input")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"campaign input changed: {name}")
        payloads[name] = raw if name == archive_name else json.loads(raw)
    population = tuple(
        EvaluationExample(id=e["id"], input=e["input"], expected={})
        for e in payloads["inputs/population.json"]
    )
    if any(set(e) != {"id", "input"} for e in payloads["inputs/population.json"]):
        raise ValueError("campaign model inputs must not contain target labels")
    golden = ApplicabilityGoldenCorpus.model_validate(payloads["inputs/golden.json"])
    suites = tuple(
        SemanticReferenceSuite.model_validate(s) for s in payloads["inputs/semantic-suites.json"]
    )
    verify_review_evidence(
        evidence=artifact.review_evidence,
        spec=spec,
        suites=suites,
        bindings=payloads.get(review_name, []),
        archive=payloads.get(archive_name),
        examples=population,
        resources=resources,
    )
    expected = build_cohorts(
        population,
        golden,
        suites,
        payloads["inputs/sentinel-suites.json"],
        sample_size=spec.sample_size,
        seed=spec.seed,
    )
    if expected != payloads["selection.json"]:
        raise ValueError("campaign cohorts differ from deterministic source selection")
    for variant in spec.variants:
        stored = definition["variants"][variant.id]
        matrix = QualificationMatrixManifest.model_validate(stored["matrix"])
        profile = (
            PartialAcceptanceProfile.model_validate(stored["acceptance_profile"])
            if stored["acceptance_profile"]
            else None
        )
        if stored["configuration"] != effective_cascade_configuration(
            matrix, resources, variant.prompt, profile
        ) or stored["detail_resources"] != _detail_resources(resources, matrix):
            raise ValueError("installed qualification resources differ from frozen campaign")
    return (
        definition,
        spec,
        population,
        golden,
        suites,
        payloads["inputs/sentinel-suites.json"],
        expected,
    )


def verify_prepared_campaign(*, manifest: Path, campaign: Path, resources: Path) -> dict:
    """Resume the explicit workflow only if its requested sources/configuration still match."""
    definition, stored_spec, population, golden, suites, sentinels, _ = load_campaign(
        campaign, resources
    )
    requested = QualificationCampaign.load(manifest)
    if requested != stored_spec:
        raise ValueError("workflow manifest differs from frozen campaign; use a new campaign id")
    source = load_partial_inputs(run=requested.run, dataset=requested.dataset)
    if (
        tuple(sorted(source.examples, key=lambda e: e.id)) != population
        or ApplicabilityGoldenCorpus.load(requested.golden) != golden
    ):
        raise ValueError("workflow source or Golden corpus changed after campaign preparation")
    loaded_suites, current_archive = _review_inputs(requested, source.examples, resources)
    current_suites = tuple(suite for suite, _ in loaded_suites)
    if current_archive is not None and hashlib.sha256(current_archive).hexdigest() != (
        definition["files"].get(REVIEW_ARCHIVE_NAME)
    ):
        raise ValueError("workflow review archive changed after preparation")
    current_sentinels = tuple(json.loads(p.read_bytes()) for p in requested.sentinel_suites)
    if current_suites != suites or list(current_sentinels) != sentinels:
        raise ValueError("workflow semantic reference suite changed after preparation")
    for variant in requested.variants:
        snapshot = definition["variants"][variant.id]
        matrix = QualificationMatrixManifest.load(variant.matrix).model_dump(mode="json")
        profile = (
            PartialAcceptanceProfile.load(variant.acceptance_profile).model_dump(mode="json")
            if variant.acceptance_profile
            else None
        )
        if matrix != snapshot["matrix"] or profile != snapshot["acceptance_profile"]:
            raise ValueError("workflow variant changed after campaign preparation")
    return definition
