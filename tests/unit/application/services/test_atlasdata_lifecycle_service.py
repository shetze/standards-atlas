from pathlib import Path

import pytest

from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus, parse_metadata
from standards_atlas.application.services import AtlasDataLifecycleService
from standards_atlas.application.services.atlasdata_lifecycle_service import AtlasDataLifecycleError


def _write(path: Path, status: str) -> None:
    path.write_text(
        f'name="Example"\ndigits=8\nlifecycle_status="{status}"\n\nstructure=(\n "2026 1"\n)\n',
        encoding="utf-8",
    )


def test_advance_proposed_to_reviewed_and_published(tmp_path: Path) -> None:
    path = tmp_path / "Example"
    _write(path, "proposed")
    service = AtlasDataLifecycleService()

    service.transition(path, AtlasDataLifecycleStatus.REVIEWED)
    result = service.transition(path, AtlasDataLifecycleStatus.PUBLISHED)

    assert result.previous is AtlasDataLifecycleStatus.REVIEWED
    assert parse_metadata(path.read_text()).lifecycle_status is AtlasDataLifecycleStatus.PUBLISHED


def test_reject_skipped_transition(tmp_path: Path) -> None:
    path = tmp_path / "Example"
    _write(path, "proposed")

    with pytest.raises(AtlasDataLifecycleError, match="Invalid AtlasData lifecycle"):
        AtlasDataLifecycleService().transition(path, AtlasDataLifecycleStatus.PUBLISHED)
