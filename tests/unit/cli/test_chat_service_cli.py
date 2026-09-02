from __future__ import annotations

from typer.testing import CliRunner

from standards_atlas.cli.main import app

runner = CliRunner()


def test_chat_serve_requires_an_explicit_service_type() -> None:
    result = runner.invoke(app, ["chat", "serve"])

    assert result.exit_code == 2
    assert "--service" in result.output


def test_chat_serve_dispatches_prompt_workbench(monkeypatch, tmp_path) -> None:
    config = tmp_path / "llm.yaml"
    config.write_text("llm: {}\n", encoding="utf-8")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    built = object()
    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return built

    def run(web_app, http_config):
        captured["web_app"] = web_app
        captured["http_config"] = http_config

    monkeypatch.setattr("standards_atlas.cli.commands.chat.build_prompt_workbench_web_app", build)
    monkeypatch.setattr("standards_atlas.cli.commands.chat.run_prompt_workbench_server", run)

    result = runner.invoke(
        app,
        [
            "chat",
            "serve",
            "--service",
            "prompt-workbench",
            "--llm-config",
            str(config),
            "--manifest-directory",
            str(manifests),
            "--port",
            "9876",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["web_app"] is built
    assert captured["http_config"].port == 9876
    assert "http://127.0.0.1:9876" in result.output


def test_chat_serve_accepts_service_type_alias() -> None:
    result = runner.invoke(app, ["chat", "serve", "--service-type", "not-registered"])

    assert result.exit_code == 2
    assert "prompt-workbench" in result.output
