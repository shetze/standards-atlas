"""Shared Gemara interchange contract for Standards Atlas projections."""

from __future__ import annotations

import re

from standards_atlas.application.model import PublicationDocument

# Gemara main currently publishes examples and validation fixtures against 1.1.0.
# Keep this in one place so every Gemara artifact declares the same contract.
GEMARA_SPEC_VERSION = "1.1.0"


def gemara_id(value: str) -> str:
    """Return a stable, conservative Gemara identifier."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not normalized:
        raise ValueError(f"Cannot derive Gemara id from {value!r}.")
    return normalized


def guidance_catalog_id(document_key: str) -> str:
    """Return the stable Layer-1 catalog id for a Standards Atlas document."""
    return gemara_id(document_key)


def control_catalog_id(document_key: str) -> str:
    """Return the stable Layer-3 catalog id for a Standards Atlas document."""
    return gemara_id(f"{document_key}-controls")


def artifact_version(document: PublicationDocument) -> str:
    """Return the source version used for linked Gemara artifacts.

    Gemara mapping references require a version. Governance graph linking must not
    invent one, so a document without either an explicit version or publication year
    is rejected instead of producing an unresolvable cross-layer reference.
    """
    if document.version:
        return document.version
    if document.year is not None:
        return str(document.year)
    raise ValueError(f"Document {document.key.value!r} needs a version or year for Gemara export.")
