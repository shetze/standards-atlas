from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.cli.main import app

runner = CliRunner()


def _write_profile(path: Path, *, group: str = "safety-lifecycle") -> None:
    path.write_text(
        f"""schema-version: 2
id: rail-onboard-sil2
version: 1.0.0
context:
  domain: railway
standards:
  include:
    - EN50716
selection:
  statement-functions: []
  subject-group-profile:
    id: functional-safety
    version: 1.0.0
  primary-subjects: []
  primary-subject-groups:
    - {group}
""",
        encoding="utf-8",
    )


def test_validate_resolves_packaged_subject_group_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    _write_profile(profile)

    result = runner.invoke(app, ["governance", "profile", "validate", str(profile)])

    assert result.exit_code == 0, result.output
    assert "Profile is valid" in result.output


def test_validate_rejects_unknown_subject_group(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    _write_profile(profile, group="not-defined")

    result = runner.invoke(app, ["governance", "profile", "validate", str(profile)])

    assert result.exit_code == 1
    assert "unknown primary-subject-groups" in result.output
