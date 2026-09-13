"""Only explicit human checks enter suites; replayable bindings follow them into campaigns."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_proposals import _json_bytes
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    SemanticReferenceSuite,
)

from .model import ReviewPublication, predicate_data
from .service import load_review
from .sources import fingerprint, freeze_population, verify_current_sources
from .storage import new_directory, review_lock
from .validation import confirmed_decisions, review_report, seal

REVIEW_REFERENCE_PREFIX = "atlas-review:sha256:"


def publication_suites(publication: ReviewPublication) -> tuple[SemanticReferenceSuite, ...]:
    package, state = publication.package, publication.state
    confirmed = confirmed_decisions(state)
    sources = {s.example_id: s for s in package.population}
    suites = []
    for split in ("development", "holdout"):
        cases, reviewers = [], set()
        for case in package.cases:
            if case.split != split:
                continue
            attributes = {}
            for attribute in case.attributes:
                decision = confirmed.get((case.example_id, attribute))
                if decision:
                    attributes[attribute] = predicate_data(decision.predicate)
                    reviewers.add(decision.reviewer)
            if attributes:
                source = sources[case.example_id]
                cases.append(
                    {
                        "example_id": case.example_id,
                        "document_key": source.document_key,
                        "content_hash": source.content_hash,
                        "attributes": attributes,
                    }
                )
        if not cases:
            raise ValueError(f"no confirmed decisions in {split}; cannot create a reference suite")
        suites.append(
            SemanticReferenceSuite.model_validate(
                {
                    "schema_version": "1.0",
                    "kind": "partial-semantic-reference",
                    "id": f"{package.id}-{split}",
                    "version": package.version,
                    "split": split,
                    "status": publication.status,
                    "reviewed_by": ", ".join(sorted(reviewers)),
                    "review_reference": REVIEW_REFERENCE_PREFIX + publication.evidence_sha256,
                    "cases": sorted(cases, key=lambda c: c["example_id"]),
                }
            )
        )
    return tuple(suites)


def verify_publication(publication: ReviewPublication, examples=None) -> tuple:
    require_supported_schema("partial-review-publication", publication.schema_version)
    if fingerprint(publication, "evidence_sha256") != publication.evidence_sha256:
        raise ValueError("review publication fingerprint mismatch")
    expected_report = review_report(publication.package, publication.state)
    if expected_report != publication.report:
        raise ValueError("review publication coverage/report differs from verified decisions")
    if expected_report["conflicts"]:
        raise ValueError("contradictory human decisions cannot be imported")
    if publication.status == "published" and (
        not expected_report["ready_for_publication"] or not publication.holdout_declaration
    ):
        raise ValueError(
            "publication requires complete coverage and a human holdout-use declaration"
        )
    if examples is not None and freeze_population(examples) != publication.package.population:
        raise ValueError("reference suite source population/text/structural context drift")
    return publication_suites(publication)


def verify_publication_rules(publication: ReviewPublication, resources: Path) -> None:
    for name, frozen in publication.package.rules.items():
        if name != "project-review-instructions":
            path = resources / name
            if path.read_text(encoding="utf-8") != frozen:
                raise ValueError(f"reference suite annotation rules changed: {name}")


def load_bound_suite(path: Path, examples, *, resources: Path | None = None) -> tuple:
    suite = SemanticReferenceSuite.model_validate(yaml.safe_load(path.read_bytes()))
    reference = suite.review_reference or ""
    if not reference.startswith("atlas-review:"):
        return suite, None  # Explicit legacy provenance, without a new context-binding claim.
    if not reference.startswith(REVIEW_REFERENCE_PREFIX):
        raise ValueError("unsupported Atlas review reference")
    evidence_path = path.parent / "review-evidence.json"
    if evidence_path.is_symlink():
        raise ValueError("unsafe review evidence symlink")
    publication = ReviewPublication.model_validate_json(evidence_path.read_bytes())
    expected = verify_publication(publication, examples)
    if resources is not None:
        verify_publication_rules(publication, resources)
    if suite != next(s for s in expected if s.split == suite.split):
        raise ValueError("suite differs from confirmed source-bound review decisions")
    for sibling in expected:
        sibling_path = path.parent / f"{sibling.split}.yaml"
        if (
            sibling_path.is_symlink()
            or SemanticReferenceSuite.model_validate(yaml.safe_load(sibling_path.read_bytes()))
            != sibling
        ):
            raise ValueError("Development/Holdout publication pair is inconsistent")
    return suite, publication


def verify_campaign_bindings(suites, bindings: list[dict], examples, resources: Path) -> None:
    """The frozen campaign copies evidence, never depends on mutable external review files."""
    bound = {
        s.review_reference: []
        for s in suites
        if (s.review_reference or "").startswith("atlas-review:")
    }
    if len(bindings) != len(bound):
        raise ValueError("campaign review evidence inventory is incomplete or duplicated")
    seen = set()
    for raw in bindings:
        publication = ReviewPublication.model_validate(raw)
        reference = REVIEW_REFERENCE_PREFIX + publication.evidence_sha256
        if reference in seen or reference not in bound:
            raise ValueError("unexpected or duplicate campaign review publication")
        seen.add(reference)
        expected = verify_publication(publication, examples)
        verify_publication_rules(publication, resources)
        supplied = sorted(
            (s for s in suites if s.review_reference == reference), key=lambda s: s.split
        )
        if supplied != sorted(expected, key=lambda s: s.split):
            raise ValueError(
                "campaign must include both unchanged suites of each review publication"
            )


def import_review_package(
    *,
    package: Path,
    output: Path | None = None,
    publish: bool = False,
    dry_run: bool = False,
    holdout_declaration: str | None = None,
    run: Path | None = None,
    dataset: Path | None = None,
) -> dict:
    # Reading and compiling a publication holds the same lock as human writes.
    with review_lock(package / ".review.lock"):
        contract, state = load_review(package)
        verify_current_sources(contract, run=run, dataset=dataset)
        report = review_report(contract, state)
        if holdout_declaration is not None and not holdout_declaration.strip():
            raise ValueError("holdout declaration cannot be blank")
        blockers = []
        if report["conflicts"]:
            blockers.append("contradictory confirmed decisions")
        for split, coverage in report["splits"].items():
            if not coverage["confirmed_attributes"]:
                blockers.append(f"no confirmed decisions in {split}")
        if publish and not report["ready_for_publication"]:
            blockers.append("selected review tasks/coverage are incomplete")
        if publish and not holdout_declaration:
            blockers.append("publication needs an explicit human holdout-use declaration")
        result = {
            **report,
            "live_sources_verified": True,
            "importable": not blockers,
            "import_blockers": blockers,
            "requested_status": "published" if publish else "draft",
        }
        if dry_run:
            return result
        if blockers:
            raise ValueError("review import blocked: " + "; ".join(blockers))
        if output is None:
            raise ValueError("review import requires a new output directory")
        _output_is_separate(
            output.resolve(),
            (
                package,
                *(Path(p) for p in contract.input_files),
                *(Path(p) for p in contract.source_location.values()),
            ),
        )
        publication = seal(
            ReviewPublication,
            {
                "package": contract.model_dump(mode="json"),
                "state": state.model_dump(mode="json"),
                "status": "published" if publish else "draft",
                "holdout_declaration": holdout_declaration,
                "report": report,
            },
            "evidence_sha256",
        )
        suites = verify_publication(publication)
        files = {
            f"{suite.split}.yaml": yaml.safe_dump(
                suite.model_dump(mode="json", exclude_unset=True),
                allow_unicode=True,
                sort_keys=False,
            ).encode("utf-8")
            for suite in suites
        }
        files["review-evidence.json"] = _json_bytes(publication.model_dump(mode="json"))
        files["review-report.json"] = _json_bytes(result)
        new_directory(output, files, idempotent=True)
        return result
