"""Application contracts for versioned governance subject-group profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from standards_atlas.domain.model import (
    GovernanceSelectionProfile,
    GovernanceSubjectGroupProfile,
)


class GovernanceSubjectGroupProfileReader(Protocol):
    """Read one immutable subject-group profile by identity."""

    def load(self, profile_id: str, version: str) -> GovernanceSubjectGroupProfile:
        """Return the requested subject-group profile or raise ``KeyError``."""
        ...


@dataclass(frozen=True)
class ResolvedGovernanceSubjectSelection:
    """Deterministic expansion of explicit subjects and named subject groups."""

    profile: GovernanceSubjectGroupProfile | None
    requested_groups: tuple[str, ...]
    explicit_subjects: tuple[str, ...]
    effective_subjects: tuple[str, ...]


def resolve_governance_subject_selection(
    selection_profile: GovernanceSelectionProfile,
    reader: GovernanceSubjectGroupProfileReader,
) -> ResolvedGovernanceSubjectSelection:
    """Validate and expand subject-group references for one selection profile."""

    selection = selection_profile.selection
    ref = selection.subject_group_profile
    if ref is None:
        return ResolvedGovernanceSubjectSelection(
            profile=None,
            requested_groups=(),
            explicit_subjects=selection.primary_subjects,
            effective_subjects=selection.primary_subjects,
        )

    try:
        group_profile = reader.load(ref.id, ref.version)
    except KeyError as exc:
        raise ValueError(f"subject-group profile not found: {ref.id}@{ref.version}") from exc

    unknown = tuple(
        sorted(
            group_id
            for group_id in selection.primary_subject_groups
            if group_profile.group(group_id) is None
        )
    )
    if unknown:
        raise ValueError(
            f"unknown primary-subject-groups in {ref.id}@{ref.version}: {', '.join(unknown)}"
        )

    grouped_subjects = {
        subject
        for group_id in selection.primary_subject_groups
        for group in (group_profile.group(group_id),)
        if group is not None
        for subject in group.subjects
    }
    effective = tuple(sorted(set(selection.primary_subjects) | grouped_subjects))
    return ResolvedGovernanceSubjectSelection(
        profile=group_profile,
        requested_groups=selection.primary_subject_groups,
        explicit_subjects=selection.primary_subjects,
        effective_subjects=effective,
    )
