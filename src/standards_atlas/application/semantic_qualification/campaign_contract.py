"""Current campaign wire contract; review provenance is not a schema-version axis.

All three supported input paths use format 2.0. Evidence is validated against the
suite references, manifest and exact frozen inventory, never inferred as a fallback
when a member is missing. This module does not grant qualification or release.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.qualification_campaign_model import (
    CampaignModel,
    QualificationCampaign,
)

CAMPAIGN_SCHEMA_VERSION = "2.0"
REVIEW_BINDINGS_NAME = "inputs/semantic-review-bindings.json"
REVIEW_ARCHIVE_NAME = "inputs/review-package.zip"
BASE_INPUT_NAMES = frozenset(
    {
        "inputs/population.json",
        "inputs/golden.json",
        "inputs/semantic-suites.json",
        "inputs/sentinel-suites.json",
        "selection.json",
    }
)
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CampaignReviewEvidence(CampaignModel):
    """Declared evidence level, checked against the actual frozen source bindings."""

    model_config = ConfigDict(revalidate_instances="always")

    kind: Literal["external_suites", "atlas_publication", "archived_handoff"]

    @property
    def input_names(self) -> frozenset[str]:
        if self.kind == "external_suites":
            return BASE_INPUT_NAMES
        names = BASE_INPUT_NAMES | {REVIEW_BINDINGS_NAME}
        return names | {REVIEW_ARCHIVE_NAME} if self.kind == "archived_handoff" else names


class QualificationCampaignArtifact(CampaignModel):
    """Explicit version markers also apply to direct/nested model validation."""

    model_config = ConfigDict(revalidate_instances="always")

    schema_version: Literal["2.0"]
    kind: Literal["partial-qualification-campaign"]
    specification: QualificationCampaign
    review_evidence: CampaignReviewEvidence
    variants: dict[str, dict[str, Any]]
    files: dict[str, Digest]
    source_fingerprints: dict[str, str]
    declared_published_golden_count: int = Field(ge=0, strict=True)
    expected_fresh_modes: tuple[Literal["fresh_end_to_end"], Literal["fresh_detail_fixed_presence"]]
    default_workflow_changed: Literal[False]
    campaign_sha256: Digest

    @model_validator(mode="after")
    def inventory_and_specification(self):
        if set(self.files) != self.review_evidence.input_names:
            raise ValueError(
                "campaign review evidence inventory differs from declared review evidence"
            )
        archived = self.review_evidence.kind == "archived_handoff"
        if archived != (self.specification.review_bundle is not None):
            raise ValueError("review handoff requires archived_handoff evidence and archive")
        if set(self.variants) != {v.id for v in self.specification.variants}:
            raise ValueError("campaign variant inventory differs from the specification")
        return self


def classify_review_evidence(spec, suites, *, has_bindings: bool, has_archive: bool):
    """Classify actual bound inputs for writing or comparison, never missing-file recovery.

    Atlas publications may be combined with external suites. Every Atlas reference
    must still have its complete immutable suite pair, checked by the shared replay.
    A Handoff is a single archived publication pair, not a mixed source collection.
    """
    atlas_suites = [s for s in suites if (s.review_reference or "").startswith("atlas-review:")]
    if bool(atlas_suites) != has_bindings:
        raise ValueError("campaign review evidence inventory differs from bound suites")
    if has_archive != (spec.review_bundle is not None):
        raise ValueError("review handoff requires the archived snapshot")
    if has_archive:
        if len(atlas_suites) != 2 or len(suites) != 2:
            raise ValueError("review handoff must bind exactly one published review suite pair")
        kind = "archived_handoff"
    else:
        kind = "atlas_publication" if has_bindings else "external_suites"
    return CampaignReviewEvidence(kind=kind)


def verify_review_evidence(*, evidence, spec, suites, bindings, archive, examples, resources):
    """Same source/rules/archive replay at preparation and every frozen campaign read."""
    from standards_atlas.application.semantic_qualification.review_package.publication import (
        verify_campaign_bindings,
    )

    if not isinstance(bindings, list):
        raise ValueError("campaign review bindings must be a list of publications")
    observed = classify_review_evidence(
        spec, suites, has_bindings=bool(bindings), has_archive=archive is not None
    )
    if observed != evidence:
        raise ValueError("campaign declared review evidence differs from bound inputs")
    verify_campaign_bindings(suites, bindings, examples, resources)
    if archive is not None:
        from standards_atlas.application.semantic_qualification.review_package.handoff import (
            verify_archive_publication,
        )
        from standards_atlas.application.semantic_qualification.review_package.model import (
            ReviewPublication,
        )

        if len(bindings) != 1:
            raise ValueError("review handoff must bind exactly one published review snapshot")
        publication = ReviewPublication.model_validate(bindings[0])
        if publication.status != "published":
            raise ValueError("archived_handoff requires a published human-reviewed suite pair")
        verify_archive_publication(archive, publication)
