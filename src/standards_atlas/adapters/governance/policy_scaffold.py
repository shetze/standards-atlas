"""Build deterministic Gemara Policy authoring scaffolds from governance selection."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.adapters.gemara import GemaraControlMapper, GemaraGuidanceMapper
from standards_atlas.adapters.gemara.contract import (
    GEMARA_SPEC_VERSION,
    artifact_version,
    control_catalog_id,
    gemara_id,
    guidance_catalog_id,
)
from standards_atlas.adapters.gemara.models import (
    GemaraActor,
    GemaraCatalogImport,
    GemaraContact,
    GemaraGuidanceImport,
    GemaraMappingReference,
    GemaraMetadata,
    GemaraPolicy,
    GemaraPolicyAdherence,
    GemaraPolicyDimensions,
    GemaraPolicyImports,
    GemaraPolicyScope,
    GemaraRaci,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    GovernanceCandidateAnalysis,
    GovernanceCandidateDecision,
    GovernanceSelectionProfile,
)
from standards_atlas.shared.artifacts import write_json, write_yaml


class GovernancePolicyScaffoldManifest(BaseModel):
    """Standards Atlas sidecar preserving selection state not expressible in Gemara."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema-version")
    profile_id: str = Field(alias="profile-id", min_length=1)
    profile_version: str = Field(alias="profile-version", min_length=1)
    policy_id: str = Field(alias="policy-id", min_length=1)
    documents: tuple[str, ...]
    selected_controls: tuple[str, ...] = Field(alias="selected-controls")
    excluded_controls: tuple[str, ...] = Field(alias="excluded-controls")
    withheld_controls: tuple[str, ...] = Field(alias="withheld-controls")
    withheld_reasons: dict[str, tuple[str, ...]] = Field(alias="withheld-reasons")


class GovernancePolicyScaffoldExporter:
    """Project deterministic candidate decisions into a Gemara Policy scaffold."""

    def export(
        self,
        profile: GovernanceSelectionProfile,
        analysis: GovernanceCandidateAnalysis,
        documents: tuple[PublicationDocument, ...],
        target: Path,
        *,
        responsible: tuple[str, ...],
        accountable: tuple[str, ...],
        title: str | None = None,
        withhold_undetermined: bool = False,
        replace_existing: bool = True,
    ) -> tuple[Path, Path]:
        self._validate_inputs(profile, analysis, documents, withhold_undetermined)
        if not responsible or not accountable:
            raise ValueError("Gemara Policy requires responsible and accountable contacts")

        policy = self._build_policy(
            profile,
            analysis,
            documents,
            responsible=responsible,
            accountable=accountable,
            title=title,
        )
        manifest = self._manifest(profile, analysis, policy.metadata.id)
        manifest_target = target.with_suffix(target.suffix + ".scaffold.json")
        if not replace_existing:
            for path in (target, manifest_target):
                if path.exists():
                    raise FileExistsError(
                        f"Governance policy scaffold target already exists: {path}"
                    )
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(target, policy.model_dump(mode="json", by_alias=True, exclude_none=True))
        write_json(manifest_target, manifest.model_dump(mode="json", by_alias=True))
        return target, manifest_target

    def _build_policy(
        self,
        profile: GovernanceSelectionProfile,
        analysis: GovernanceCandidateAnalysis,
        documents: tuple[PublicationDocument, ...],
        *,
        responsible: tuple[str, ...],
        accountable: tuple[str, ...],
        title: str | None,
    ) -> GemaraPolicy:
        by_document = {document.key.value: document for document in documents}
        candidates_by_document = {
            key: tuple(item for item in analysis.candidates if item.document_key == key)
            for key in sorted(by_document)
        }
        references: list[GemaraMappingReference] = []
        catalog_imports: list[GemaraCatalogImport] = []
        guidance_imports: list[GemaraGuidanceImport] = []

        for key in sorted(by_document):
            document = by_document[key]
            version = artifact_version(document)
            control_catalog = GemaraControlMapper().map(document)
            guidance_catalog = GemaraGuidanceMapper().map(document)
            references.extend(
                (
                    GemaraMappingReference(
                        id=guidance_catalog_id(key),
                        title=guidance_catalog.title,
                        version=version,
                        description=f"Layer-1 guidance derived from {document.title}.",
                    ),
                    GemaraMappingReference(
                        id=control_catalog_id(key),
                        title=control_catalog.title,
                        version=version,
                        description=f"Layer-3 controls derived from {document.title}.",
                    ),
                )
            )
            candidates = candidates_by_document[key]
            excluded_control_ids = tuple(
                sorted(
                    item.control_id
                    for item in candidates
                    if item.decision is not GovernanceCandidateDecision.SELECTED
                )
            )
            selected_control_ids = {
                item.control_id
                for item in candidates
                if item.decision is GovernanceCandidateDecision.SELECTED
            }
            selected_guideline_ids = {
                entry.reference_id
                for control in control_catalog.controls or ()
                if control.id in selected_control_ids
                for mapping in control.guidelines or ()
                for entry in mapping.entries
            }
            all_guideline_ids = {item.id for item in guidance_catalog.guidelines or ()}
            excluded_guideline_ids = tuple(sorted(all_guideline_ids - selected_guideline_ids))
            catalog_imports.append(
                GemaraCatalogImport(
                    **{
                        "reference-id": control_catalog_id(key),
                        "exclusions": excluded_control_ids or None,
                    }
                )
            )
            guidance_imports.append(
                GemaraGuidanceImport(
                    **{
                        "reference-id": guidance_catalog_id(key),
                        "exclusions": excluded_guideline_ids or None,
                    }
                )
            )

        description = profile.description or (
            f"Draft policy scaffold for governance selection profile {profile.id}."
        )
        return GemaraPolicy(
            title=title or profile.description or profile.id,
            metadata=GemaraMetadata(
                id=gemara_id(f"{profile.id}-policy"),
                type="Policy",
                **{
                    "gemara-version": GEMARA_SPEC_VERSION,
                    "version": profile.version,
                    "description": description,
                    "author": GemaraActor(
                        id="standards-atlas",
                        name="Standards Atlas",
                        type="Software",
                        description="Generated governance policy authoring scaffold.",
                    ),
                    "mapping-references": tuple(references),
                    "draft": True,
                },
            ),
            contacts=GemaraRaci(
                responsible=tuple(GemaraContact(name=item) for item in responsible),
                accountable=tuple(GemaraContact(name=item) for item in accountable),
            ),
            scope=GemaraPolicyScope(**{"in": _scope_dimensions(profile)}),
            imports=GemaraPolicyImports(
                catalogs=tuple(catalog_imports) or None,
                guidance=tuple(guidance_imports) or None,
            ),
            adherence=GemaraPolicyAdherence(),
        )

    @staticmethod
    def _validate_inputs(
        profile: GovernanceSelectionProfile,
        analysis: GovernanceCandidateAnalysis,
        documents: tuple[PublicationDocument, ...],
        withhold_undetermined: bool,
    ) -> None:
        if analysis.profile_id != profile.id or analysis.profile_version != profile.version:
            raise ValueError("Candidate analysis does not match governance selection profile")
        document_keys = tuple(sorted(document.key.value for document in documents))
        if tuple(sorted(analysis.documents)) != document_keys:
            raise ValueError("Candidate analysis documents do not match policy scaffold documents")
        if analysis.undetermined and not withhold_undetermined:
            raise ValueError(
                "Candidate analysis contains undetermined controls; review them or use "
                "--withhold-undetermined to create a draft that excludes them"
            )

    @staticmethod
    def _manifest(
        profile: GovernanceSelectionProfile,
        analysis: GovernanceCandidateAnalysis,
        policy_id: str,
    ) -> GovernancePolicyScaffoldManifest:
        return GovernancePolicyScaffoldManifest(
            **{
                "profile-id": profile.id,
                "profile-version": profile.version,
                "policy-id": policy_id,
                "documents": tuple(sorted(analysis.documents)),
                "selected-controls": tuple(
                    item.control_id
                    for item in analysis.candidates
                    if item.decision is GovernanceCandidateDecision.SELECTED
                ),
                "excluded-controls": tuple(
                    item.control_id
                    for item in analysis.candidates
                    if item.decision is GovernanceCandidateDecision.EXCLUDED
                ),
                "withheld-controls": tuple(
                    item.control_id
                    for item in analysis.candidates
                    if item.decision is GovernanceCandidateDecision.UNDETERMINED
                ),
                "withheld-reasons": {
                    item.control_id: tuple(
                        signal.reason
                        for signal in item.signals
                        if signal.outcome is GovernanceCandidateDecision.UNDETERMINED
                    )
                    for item in analysis.candidates
                    if item.decision is GovernanceCandidateDecision.UNDETERMINED
                },
            }
        )


def _scope_dimensions(profile: GovernanceSelectionProfile) -> GemaraPolicyDimensions:
    context = profile.context
    groups = [f"domain:{context.domain}"]
    groups.extend(f"lifecycle:{item}" for item in context.lifecycle_phases)
    groups.extend(f"integrity:{item}" for item in context.integrity_levels)
    groups.extend(
        f"attribute:{key}={str(value).lower() if isinstance(value, bool) else value}"
        for key, value in sorted(context.attributes.items())
    )
    return GemaraPolicyDimensions(
        technologies=context.system_types or None,
        users=context.roles or None,
        groups=tuple(groups),
    )
