"""Adapters from structural-taxonomy output to generic routing signals."""

from __future__ import annotations

from standards_atlas.application.routing.model import (
    TaxonomyCategorySignal,
    TaxonomySignalProfile,
)
from standards_atlas.domain.model.structural_profile import StructuralProfile


def taxonomy_signal_profile(
    profile: StructuralProfile,
    *,
    heading: str = "",
    node_kind: str | None = None,
    content_profile: str | None = None,
) -> TaxonomySignalProfile:
    """Project a StructuralProfile into the stable routing evidence boundary."""

    return TaxonomySignalProfile(
        canonical_section=(
            profile.canonical_section.value if profile.canonical_section is not None else None
        ),
        annex_status=profile.annex_status.value if profile.annex_status is not None else None,
        document_categories=tuple(
            TaxonomyCategorySignal(
                taxonomy=item.taxonomy,
                category=item.category,
                version=item.version,
            )
            for item in profile.document_categories
        ),
        domain_categories=tuple(
            TaxonomyCategorySignal(
                taxonomy=item.taxonomy,
                category=item.category,
                version=item.version,
            )
            for item in profile.domain_categories
        ),
        node_kind=node_kind,
        content_profile=content_profile,
        heading=heading,
    )
