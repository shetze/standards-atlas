from __future__ import annotations

import pytest

from standards_atlas.application.schema import SchemaDeprecationWarning, SchemaPolicy


def test_policy_accepts_current_without_warning() -> None:
    policy = SchemaPolicy("example", 3, (1, 2, 3), "example/*.json")

    with warnings_not_emitted():
        policy.require_readable(3)


def test_policy_warns_for_previous_schema() -> None:
    policy = SchemaPolicy("example", 3, (1, 2, 3), "example/*.json")

    with pytest.warns(SchemaDeprecationWarning, match="deprecated"):
        policy.require_readable(2)


def test_policy_marks_oldest_supported_schema() -> None:
    policy = SchemaPolicy("example", 3, (1, 2, 3), "example/*.json")

    with pytest.warns(SchemaDeprecationWarning, match="oldest supported"):
        policy.require_readable(1)


def test_policy_rejects_schema_outside_window() -> None:
    policy = SchemaPolicy("example", 3, (1, 2, 3), "example/*.json")

    with pytest.raises(ValueError, match="Unsupported example schema version"):
        policy.require_readable(0)


def test_policy_rejects_more_than_three_regular_versions() -> None:
    with pytest.raises(ValueError, match="three-version window"):
        SchemaPolicy("example", 4, (1, 2, 3, 4), "example/*.json")


def test_policy_allows_four_versions_only_for_major_transition() -> None:
    SchemaPolicy("example", 4, (1, 2, 3, 4), "example/*.json", major_transition=True)


def test_writer_accepts_only_current_schema() -> None:
    policy = SchemaPolicy("example", 3, (1, 2, 3), "example/*.json")

    policy.require_current_for_write(3)
    with pytest.raises(ValueError, match="writers may only emit current schema"):
        policy.require_current_for_write(2)


class warnings_not_emitted:
    def __enter__(self) -> None:
        import warnings

        self._catcher = warnings.catch_warnings(record=True)
        self._caught = self._catcher.__enter__()
        warnings.simplefilter("always")

    def __exit__(self, exc_type, exc, tb) -> None:
        assert not self._caught
        self._catcher.__exit__(exc_type, exc, tb)
