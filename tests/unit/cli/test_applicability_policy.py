from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.cli.commands.evaluation_commands import applicability_policy as policy_cli
from standards_atlas.cli.main import app

runner = CliRunner()


def test_evaluation_help_lists_applicability_policy_commands() -> None:
    result = runner.invoke(app, ["evaluation", "--help"])

    assert result.exit_code == 0
    assert "applicability-policy-replay" in result.stdout
    assert "applicability-policy-evaluate" in result.stdout
    assert "applicability-policy-run" in result.stdout


def test_fresh_policy_selection_ignores_persisted_selection(monkeypatch, tmp_path: Path) -> None:
    selection_path = tmp_path / "applicability-policy-selection.json"
    selection_path.write_text("stale\n", encoding="utf-8")
    expected = object()
    validate_called = False

    def validate(**_kwargs):
        nonlocal validate_called
        validate_called = True
        raise AssertionError("fresh selection must not validate stale persisted selection")

    monkeypatch.setattr(policy_cli, "validate_reused_applicability_detail_selection", validate)
    monkeypatch.setattr(
        policy_cli,
        "build_applicability_detail_selection",
        lambda **_kwargs: expected,
    )

    actual = policy_cli._resolve_policy_selection(
        selection_path=selection_path,
        fresh=True,
        run_selection=object(),
        examples=(),
        consensus=object(),
        coverage=object(),
    )

    assert actual is expected
    assert not validate_called


def test_resumed_policy_selection_validates_policy_owned_selection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "applicability-policy-selection.json"
    selection_path.write_text("persisted\n", encoding="utf-8")
    persisted = object()
    expected = object()
    build_called = False

    monkeypatch.setattr(
        policy_cli,
        "load_applicability_detail_selection",
        lambda path: persisted if path == selection_path else None,
    )
    monkeypatch.setattr(
        policy_cli,
        "validate_reused_applicability_detail_selection",
        lambda **kwargs: expected if kwargs["persisted_selection"] is persisted else None,
    )

    def build(**_kwargs):
        nonlocal build_called
        build_called = True
        raise AssertionError("resume must validate its persisted policy selection")

    monkeypatch.setattr(policy_cli, "build_applicability_detail_selection", build)

    actual = policy_cli._resolve_policy_selection(
        selection_path=selection_path,
        fresh=False,
        run_selection=object(),
        examples=(),
        consensus=object(),
        coverage=object(),
    )

    assert actual is expected
    assert not build_called
