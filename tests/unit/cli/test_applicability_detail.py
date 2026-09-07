from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.cli.commands.evaluation_commands.applicability_detail import (
    _managed_detail_server,
)
from standards_atlas.cli.main import app

V6_MANIFEST = Path(
    "manifests/multidimensional-semantic-qualification-v6-applicability-presence-v1.yaml"
)


@dataclass(frozen=True)
class _Status:
    running: bool


class _Server:
    def __init__(self, *, running: bool) -> None:
        self.running = running
        self.status_calls = 0
        self.start_calls = 0
        self.stop_calls = 0

    def status(self) -> _Status:
        self.status_calls += 1
        return _Status(self.running)

    def start(self) -> None:
        self.start_calls += 1
        self.running = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False


def test_detail_server_preserves_preexisting_runtime() -> None:
    server = _Server(running=True)

    with _managed_detail_server(server, inference_required=True, enabled=True):
        assert server.running is True

    assert server.status_calls == 1
    assert server.start_calls == 0
    assert server.stop_calls == 0


def test_detail_server_stops_runtime_started_for_invocation() -> None:
    server = _Server(running=False)

    with _managed_detail_server(server, inference_required=True, enabled=True):
        assert server.running is True

    assert server.status_calls == 1
    assert server.start_calls == 1
    assert server.stop_calls == 1
    assert server.running is False


def test_detail_server_is_untouched_without_pending_inference() -> None:
    server = _Server(running=False)

    with _managed_detail_server(server, inference_required=False, enabled=True):
        pass

    assert server.status_calls == 0
    assert server.start_calls == 0
    assert server.stop_calls == 0


def test_detail_contract_override_requires_task_and_prompt_together(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "applicability-detail-enrich",
            "--manifest",
            str(V6_MANIFEST),
            "--run",
            str(tmp_path),
            "--task-version",
            "2.0.0",
        ],
    )

    assert result.exit_code == 2
    assert "--task-version and --prompt-version must be supplied together" in result.output


def test_detail_contract_override_requires_exact_reused_selection(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "applicability-detail-enrich",
            "--manifest",
            str(V6_MANIFEST),
            "--run",
            str(tmp_path),
            "--task-version",
            "2.0.0",
            "--prompt-version",
            "detail-structure-aware-v2",
        ],
    )

    assert result.exit_code == 2
    assert "detail experiments require --selection" in result.output


def test_detail_contract_override_requires_isolated_output_directory(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "applicability-detail-enrich",
            "--manifest",
            str(V6_MANIFEST),
            "--run",
            str(tmp_path),
            "--selection",
            str(V6_MANIFEST),
            "--task-version",
            "2.0.0",
            "--prompt-version",
            "detail-structure-aware-v2",
        ],
    )

    assert result.exit_code == 2
    assert "detail experiments require --output-directory" in result.output


def test_detail_model_override_requires_exact_reused_selection(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "applicability-detail-enrich",
            "--manifest",
            str(V6_MANIFEST),
            "--run",
            str(tmp_path),
            "--model",
            "mistral-small-3.2-24b-instruct-q4-k-m",
        ],
    )

    assert result.exit_code == 2
    assert "detail experiments require --selection" in result.output


def test_detail_model_override_requires_isolated_output_directory(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "applicability-detail-enrich",
            "--manifest",
            str(V6_MANIFEST),
            "--run",
            str(tmp_path),
            "--selection",
            str(V6_MANIFEST),
            "--model",
            "mistral-small-3.2-24b-instruct-q4-k-m",
        ],
    )

    assert result.exit_code == 2
    assert "detail experiments require --output-directory" in result.output
