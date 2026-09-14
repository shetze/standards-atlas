"""Atomic human-reviewed handoff to the existing qualification workflow.

No campaign is executed, no decision is inferred, and no release gate is changed.
The portable bundle contains a manifest, both confirmed suites and the full review archive.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

import yaml
from pydantic import Field

from standards_atlas.application.schema import require_current_schema, require_supported_schema
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.campaign_selection import build_cohorts
from standards_atlas.application.semantic_qualification.partial_comparison import (
    _output_is_separate,
)
from standards_atlas.application.semantic_qualification.partial_proposals import (
    _json_bytes,
    load_partial_inputs,
)
from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    QUALIFICATION_MANIFEST_SCHEMA_VERSION,
    CampaignModel,
    QualificationCampaign,
    SemanticReferenceSuite,
)

from .archive import (
    MAX_ARCHIVE_BYTES,
    MAX_MEMBER_BYTES,
    ArchiveMember,
    build_archive_bytes,
    verify_archive_bytes,
)
from .candidates import safe_read
from .model import Digest, NonBlank, ReviewPublication
from .publication import (
    compile_publication,
    publication_files,
    verify_publication,
    verify_publication_rules,
)
from .service import load_review
from .sources import duplicate_key, fingerprint
from .storage import new_directory, review_lock
from .validation import seal
from .workbench import workbench_summary

HANDOFF_NAME = "review-handoff.json"
ARCHIVE_NAME = "review-package.zip"
CAMPAIGN_ARCHIVE_NAME = "inputs/review-package.zip"
MEMBERS = frozenset(
    {
        "campaign.yaml",
        "source-campaign.yaml",
        ARCHIVE_NAME,
        "review/development.yaml",
        "review/holdout.yaml",
        "review/review-evidence.json",
        "review/review-report.json",
    }
)


class ReviewHandoff(CampaignModel):
    SCHEMA_FAMILY: ClassVar[str] = "partial-review-handoff"

    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["partial-review-handoff"] = "partial-review-handoff"
    project_root: NonBlank
    campaign_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    package_sha256: Digest
    state_sha256: Digest
    publication_sha256: Digest
    archive_sha256: Digest
    files: dict[str, ArchiveMember]
    handoff_sha256: Digest


@dataclass(frozen=True)
class ReviewHandoffSnapshot:
    definition: ReviewHandoff
    specification: QualificationCampaign
    publication: ReviewPublication
    archive: bytes
    suite_paths: tuple[Path, Path]

    def summary(self, *, live: bool) -> dict:
        return {
            "handoff_sha256": self.definition.handoff_sha256,
            "package_sha256": self.definition.package_sha256,
            "state_sha256": self.definition.state_sha256,
            "publication_sha256": self.publication.evidence_sha256,
            "archive_sha256": self.definition.archive_sha256,
            "campaign_id": self.specification.id,
            "semantic_suites": [str(p) for p in self.suite_paths],
            "workbench": workbench_summary(self.publication.workbench),
            "live_sources_verified": live,
            "models_started": False,
            "activation_performed": False,
            "human_decisions_added": 0,
        }


def _canonical_specification(spec: QualificationCampaign, base: Path) -> dict:
    """Normalize project-relative inputs without depending on external file contents."""
    data = spec.model_dump(mode="json")

    def absolute(value):
        return os.path.abspath(base / value) if value is not None else None

    for name in ("run", "dataset", "golden"):
        data[name] = absolute(data[name])
    for name in ("semantic_suites", "sentinel_suites"):
        data[name] = [absolute(p) for p in data[name]]
    for variant in data["variants"]:
        for name in ("matrix", "acceptance_profile"):
            variant[name] = absolute(variant[name])
    return data


def _handoff_specification(raw: bytes, base: Path, campaign_id: str) -> dict:
    original = QualificationCampaign.model_validate(yaml.safe_load(raw))
    if original.review_bundle is not None:
        raise ValueError("build a new handoff from the source manifest, not an existing handoff")
    data = _canonical_specification(original, base)
    require_current_schema("partial-qualification-manifest", QUALIFICATION_MANIFEST_SCHEMA_VERSION)
    data.update(id=campaign_id, semantic_suites=[], review_bundle=".")
    # The source must already be current; never rewrite a version marker as an upgrade.
    require_current_schema("partial-qualification-manifest", data["schema_version"])
    # Model validation catches any invalid source/variant/quality-policy input before writing.
    return QualificationCampaign.model_validate(data).model_dump(mode="json")


def _check_live(spec, publication, examples, resources) -> None:
    suites = verify_publication(publication, examples)
    if resources is not None:
        verify_publication_rules(publication, resources)
    if not set(spec.required_semantic_attributes) <= set(publication.package.profile.attributes):
        raise ValueError("review profile does not cover all campaign-required semantic attributes")
    golden = ApplicabilityGoldenCorpus.load(spec.golden)
    sentinels = tuple(json.loads(p.read_bytes()) for p in spec.sentinel_suites)
    # Include draft Golden entries and equivalent content, not only published example IDs.
    sources = {s.example_id: s for s in publication.package.population}
    coordinates = {(s.document_key, s.clause_id): s for s in sources.values()}
    exposed = {
        duplicate_key(coordinates[(case.document_key, case.clause_id)])
        for case in golden.cases
        if (case.document_key, case.clause_id) in coordinates
    }
    exposed.update(
        duplicate_key(sources[case["example_id"]])
        for sentinel in sentinels
        for case in sentinel["cases"]
        if case["example_id"] in sources
    )
    if any(
        duplicate_key(sources[case.example_id]) in exposed
        for case in publication.package.cases
        if case.split == "holdout"
    ):
        raise ValueError("current Golden/Sentinel content overlaps the frozen review Holdout")
    # The generated pair replaces semantic_suites. Never drop newly supplied known cases
    # when a reviewer reuses an older package with a changed source campaign manifest.
    reviewed = {case.example_id: case for case in publication.package.cases}
    for path in spec.semantic_suites:
        previous = SemanticReferenceSuite.model_validate(yaml.safe_load(safe_read(path)))
        for case in previous.cases:
            selected = reviewed.get(case.example_id)
            source = sources.get(case.example_id)
            if (
                selected is None
                or selected.split != previous.split
                or source is None
                or source.document_key != case.document_key
                or source.content_hash != case.content_hash
                or not set(case.attributes) <= set(selected.attributes)
            ):
                raise ValueError("current semantic suite has unreviewed or changed known cases")
    if any(
        case["example_id"] not in reviewed or reviewed[case["example_id"]].split != "development"
        for sentinel in sentinels
        for case in sentinel["cases"]
    ):
        raise ValueError("current sentinels contain unreviewed Development cases")
    # Detect newly introduced Golden/Sentinel overlaps before an expensive campaign starts.
    build_cohorts(examples, golden, suites, sentinels, sample_size=spec.sample_size, seed=spec.seed)


def verify_archive_publication(archive: bytes, publication: ReviewPublication) -> None:
    frozen = verify_archive_bytes(archive)
    if (
        frozen.package != publication.package
        or frozen.state != publication.state
        or frozen.workbench != publication.workbench
    ):
        raise ValueError(
            "review archive differs from the published source/decision/exposure snapshot"
        )


def _verify_files(
    files: dict[str, bytes], root: Path, *, requested=None, examples=None, resources=None
) -> ReviewHandoffSnapshot:
    if set(files) != MEMBERS | {HANDOFF_NAME}:
        raise ValueError("review handoff inventory is incomplete or unexpected")
    definition = ReviewHandoff.model_validate_json(files[HANDOFF_NAME])
    require_supported_schema("partial-review-handoff", definition.schema_version)
    if fingerprint(definition, "handoff_sha256") != definition.handoff_sha256:
        raise ValueError("review handoff fingerprint mismatch")
    if set(definition.files) != MEMBERS or not Path(definition.project_root).is_absolute():
        raise ValueError("review handoff input inventory or project origin is invalid")
    for name, binding in definition.files.items():
        if (
            len(files[name]) != binding.size
            or hashlib.sha256(files[name]).hexdigest() != binding.sha256
        ):
            raise ValueError(f"review handoff member changed: {name}")
    expected = _handoff_specification(
        files["source-campaign.yaml"], Path(definition.project_root), definition.campaign_id
    )
    generated = QualificationCampaign.model_validate(yaml.safe_load(files["campaign.yaml"]))
    if generated.model_dump(mode="json") != expected:
        raise ValueError("handoff changed campaign comparison, source or quality policy")
    spec = QualificationCampaign.model_validate({**expected, "review_bundle": root.absolute()})
    if requested is not None and requested != spec:
        raise ValueError("requested campaign differs from the immutable review handoff")
    publication = ReviewPublication.model_validate_json(files["review/review-evidence.json"])
    suites = verify_publication(publication)
    if publication.status != "published":
        raise ValueError("handoff requires a published suite pair with captured Workbench evidence")
    for suite in suites:
        supplied = SemanticReferenceSuite.model_validate(
            yaml.safe_load(files[f"review/{suite.split}.yaml"])
        )
        if supplied != suite:
            raise ValueError("handoff suite differs from confirmed human decisions")
    if (
        definition.publication_sha256 != publication.evidence_sha256
        or definition.package_sha256 != publication.package.package_sha256
        or definition.state_sha256 != publication.state.state_sha256
    ):
        raise ValueError("review handoff publication binding mismatch")
    frozen = verify_archive_bytes(files[ARCHIVE_NAME])
    if frozen.manifest.archive_sha256 != definition.archive_sha256:
        raise ValueError("review handoff archive binding mismatch")
    if (
        frozen.package != publication.package
        or frozen.state != publication.state
        or frozen.workbench != publication.workbench
    ):
        raise ValueError("review archive differs from published source/decision/exposure snapshot")
    report = json.loads(files["review/review-report.json"])
    if (
        not report.get("importable")
        or report.get("requested_status") != "published"
        or report.get("workbench") != workbench_summary(publication.workbench)
        or any(report.get(k) != v for k, v in publication.report.items())
    ):
        raise ValueError("handoff review report differs from verified human coverage")
    if examples is not None:
        _check_live(spec, publication, examples, resources)
    elif resources is not None:
        verify_publication_rules(publication, resources)
    return ReviewHandoffSnapshot(
        definition,
        spec,
        publication,
        files[ARCHIVE_NAME],
        (root / "review/development.yaml", root / "review/holdout.yaml"),
    )


def load_review_handoff(
    root: Path, *, requested=None, examples=None, resources=None, live: bool = False
) -> ReviewHandoffSnapshot:
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("unsafe review handoff root")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlink in review handoff")
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        if name not in MEMBERS | {HANDOFF_NAME} or not path.is_file():
            raise ValueError("unexpected/unsafe member in immutable review handoff")
        limit = MAX_ARCHIVE_BYTES if name == ARCHIVE_NAME else MAX_MEMBER_BYTES
        if path.stat().st_size > limit:
            raise ValueError("oversized review handoff member")
        raw = safe_read(path)
        if len(raw) > limit:
            raise ValueError("review handoff member grew beyond size limit")
        files[name] = raw
    result = _verify_files(files, root, requested=requested, examples=examples, resources=resources)
    if live and examples is None:
        spec = result.specification
        source = load_partial_inputs(run=spec.run, dataset=spec.dataset)
        _check_live(spec, result.publication, source.examples, resources)
    return result


def create_review_handoff(
    *,
    package: Path,
    manifest: Path,
    output: Path | None,
    resources: Path,
    holdout_declaration: str | None = None,
    campaign_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    # Parse exactly the bytes archived as the original policy, not a second file read.
    raw_manifest = safe_read(manifest)
    source_manifest = yaml.safe_load(raw_manifest)
    if not isinstance(source_manifest, dict):
        raise ValueError("qualification campaign manifest must contain a mapping")
    require_supported_schema(
        "partial-qualification-manifest", source_manifest.get("schema_version")
    )
    original = QualificationCampaign.model_validate(source_manifest)
    if original.review_bundle is not None:
        raise ValueError("handoff needs the source campaign manifest, not a previous handoff")
    with review_lock(package / ".review.lock"):
        contract, state = load_review(package)
        result, publication = compile_publication(
            package,
            contract,
            state,
            publish=True,
            holdout_declaration=holdout_declaration,
            run=original.run,
            dataset=original.dataset,
        )
        if publication is None:
            if dry_run:
                return result
            raise ValueError("review handoff blocked: " + "; ".join(result["import_blockers"]))
        generated = _handoff_specification(raw_manifest, Path.cwd(), campaign_id or original.id)
        source = load_partial_inputs(run=original.run, dataset=original.dataset)
        _check_live(original, publication, source.examples, resources)
        if output is None and not dry_run:
            raise ValueError("review handoff requires a new output directory")
        if output is not None:
            _output_is_separate(
                output.resolve(),
                (
                    package,
                    manifest,
                    *(Path(p) for p in contract.input_files),
                    original.run or original.dataset,
                ),
            )
        archive, snapshot = build_archive_bytes(package, contract, state)
        files = {
            "campaign.yaml": yaml.safe_dump(generated, sort_keys=False, allow_unicode=True).encode(
                "utf-8"
            ),
            "source-campaign.yaml": raw_manifest,
            ARCHIVE_NAME: archive,
            **{"review/" + n: raw for n, raw in publication_files(publication, result).items()},
        }
        definition = seal(
            ReviewHandoff,
            {
                "project_root": str(Path.cwd()),
                "campaign_id": generated["id"],
                "package_sha256": contract.package_sha256,
                "state_sha256": state.state_sha256,
                "publication_sha256": publication.evidence_sha256,
                "archive_sha256": snapshot.manifest.archive_sha256,
                "files": {
                    name: {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
                    for name, raw in sorted(files.items())
                },
            },
            "handoff_sha256",
        )
        files[HANDOFF_NAME] = _json_bytes(definition.model_dump(mode="json"))
        checked = _verify_files(
            files,
            output or package / ".handoff-preview",
            examples=source.examples,
            resources=resources,
        )
        if dry_run:
            return {
                **result,
                "handoff_ready": True,
                "dry_run": True,
                "archive_sha256": snapshot.manifest.archive_sha256,
                "frozen_evidence_verified": True,
                "models_started": False,
                "activation_performed": False,
                "human_decisions_added": 0,
            }
        new_directory(output, files, idempotent=True)
        return {
            **result,
            **checked.summary(live=True),
            "output": str(output),
            "manifest": str(output / "campaign.yaml"),
        }
