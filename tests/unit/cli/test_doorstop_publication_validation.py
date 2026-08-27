from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from standards_atlas.cli.commands.document_commands.publication import (
    _ensure_doorstop_hierarchy_repository,
    _validate_doorstop_hierarchy,
)


def test_validate_doorstop_hierarchy_runs_once_at_hierarchy_root(tmp_path: Path) -> None:
    with patch(
        "standards_atlas.cli.commands.document_commands.publication.subprocess.run",
        return_value=CompletedProcess(("doorstop",), 0, stdout="", stderr=""),
    ) as run:
        _validate_doorstop_hierarchy(tmp_path, "functional-safety")

    run.assert_called_once_with(
        ("doorstop",),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_doorstop_hierarchy_preserves_doorstop_diagnostics(tmp_path: Path) -> None:
    with patch(
        "standards_atlas.cli.commands.document_commands.publication.subprocess.run",
        return_value=CompletedProcess(
            ("doorstop",),
            1,
            stdout="building tree...\n",
            stderr="ERROR: no root document\n",
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            _validate_doorstop_hierarchy(tmp_path, "functional-safety")

    message = str(exc_info.value)
    assert "Doorstop hierarchy validation failed: functional-safety" in message
    assert "building tree..." in message
    assert "ERROR: no root document" in message


def test_ensure_doorstop_hierarchy_repository_initializes_git_once(tmp_path: Path) -> None:
    with patch(
        "standards_atlas.cli.commands.document_commands.publication.subprocess.run",
        return_value=CompletedProcess(
            ("git", "init", "--quiet", "."),
            0,
            stdout="",
            stderr="",
        ),
    ) as run:
        _ensure_doorstop_hierarchy_repository(tmp_path)

    run.assert_called_once_with(
        ("git", "init", "--quiet", "."),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ensure_doorstop_hierarchy_repository_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    with patch("standards_atlas.cli.commands.document_commands.publication.subprocess.run") as run:
        _ensure_doorstop_hierarchy_repository(tmp_path)

    run.assert_not_called()


def test_ensure_doorstop_hierarchy_repository_preserves_git_diagnostics(
    tmp_path: Path,
) -> None:
    with patch(
        "standards_atlas.cli.commands.document_commands.publication.subprocess.run",
        return_value=CompletedProcess(
            ("git", "init", "--quiet", "."),
            1,
            stdout="",
            stderr="fatal: cannot initialize repository\n",
        ),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            _ensure_doorstop_hierarchy_repository(tmp_path)

    message = str(exc_info.value)
    assert "Could not initialize Git repository for Doorstop hierarchy" in message
    assert "fatal: cannot initialize repository" in message
