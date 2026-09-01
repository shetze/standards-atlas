import pytest

from standards_atlas.adapters.gemara.mapper import gemara_id


def test_gemara_id_is_stable_and_conservative() -> None:
    assert gemara_id("EN 50716/clause-ABC_1") == "en-50716-clause-abc-1"


def test_gemara_id_rejects_empty_normalization() -> None:
    with pytest.raises(ValueError):
        gemara_id("---")
