"""Opt-in rejection of the private pre-R3 archive; no standards text in fixtures."""

import hashlib
import os
from pathlib import Path

import pytest

from standards_atlas.adapters.evaluation.qualification_context_source import (
    load_qualification_context,
)


@pytest.mark.qualification
def test_run074_obsolete_consensus_is_rejected_without_rewriting_evidence() -> None:
    source = os.environ.get("STANDARDS_ATLAS_RUN074_ARCHIVE")
    if not source:
        pytest.skip("set STANDARDS_ATLAS_RUN074_ARCHIVE to the original obsolete private ZIP")
    archive = Path(source)
    with archive.open("rb") as stream:
        before = hashlib.file_digest(stream, "sha256").hexdigest()
    with pytest.raises(ValueError, match="5.0"):
        load_qualification_context(archive)
    with archive.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == before
