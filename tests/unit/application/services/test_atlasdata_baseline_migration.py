from pathlib import Path

from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus, parse_metadata


def test_all_versioned_atlasdata_baselines_are_published() -> None:
    files = [
        path
        for path in Path("data").iterdir()
        if path.is_file() and "structure=(" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert files
    assert all(
        parse_metadata(path.read_text(encoding="utf-8")).lifecycle_status
        is AtlasDataLifecycleStatus.PUBLISHED
        for path in files
    )
