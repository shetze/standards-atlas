from pathlib import Path

from standards_atlas.adapters.atlasdata.metadata import AtlasDataLifecycleStatus, parse_metadata


def test_all_versioned_atlasdata_baselines_are_reviewed_or_published() -> None:
    files = [
        path
        for path in Path("data").iterdir()
        if path.is_file()
        and "structure=("
        in path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    ]

    assert files

    accepted_statuses = {
        AtlasDataLifecycleStatus.REVIEWED,
        AtlasDataLifecycleStatus.PUBLISHED,
    }

    invalid: dict[str, str] = {}

    for path in files:
        metadata = parse_metadata(path.read_text(encoding="utf-8"))
        if metadata.lifecycle_status not in accepted_statuses:
            invalid[str(path)] = metadata.lifecycle_status.value

    assert not invalid, (
        f"Versioned AtlasData baselines must be reviewed or published. Invalid files: {invalid}"
    )
