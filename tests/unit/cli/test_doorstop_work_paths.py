"""Regression coverage for the Doorstop adapter work-root contract."""

from pathlib import Path

from standards_atlas.application.workspace import WorkspaceLayout
from standards_atlas.cli import defaults as cli_defaults


def test_workspace_layout_places_doorstop_below_work_root(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)

    assert layout.doorstop_work == tmp_path / ".atlas" / "work" / "doorstop"
    assert layout.doorstop_hierarchy("functional-safety") == (
        tmp_path / ".atlas" / "work" / "doorstop" / "functional-safety"
    )


def test_cli_defaults_keep_data_and_doorstop_work_roots_separate() -> None:
    assert cli_defaults.DEFAULT_WORKSPACE == Path(".atlas/data")
    assert cli_defaults.DEFAULT_WORK_ROOT == Path(".atlas/work")
