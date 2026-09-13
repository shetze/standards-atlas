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


def test_review_service_starts_without_llm_config_or_manifests(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.chdir(tmp_path)
    review_workspace = tmp_path / "reviews"
    review_workspace.mkdir()
    built = object()

    def build(**kwargs):
        captured.update(kwargs)
        return built

    def run(web_app, http_config):
        captured["web_app"] = web_app
        captured["http_config"] = http_config

    monkeypatch.setattr("standards_atlas.cli.commands.chat.build_review_workbench_web_app", build)
    monkeypatch.setattr("standards_atlas.cli.commands.chat.run_review_workbench_server", run)
    result = runner.invoke(
        app,
        [
            "chat",
            "serve",
            "--service",
            "review-workbench",
            "--review-workspace",
            str(review_workspace),
            "--port",
            "8089",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["web_app"] is built
    assert captured["http_config"].port == 8089
    assert captured["review_workspace"] == review_workspace
    assert "No LLM is started" in result.output


def test_review_service_rejects_network_bind_before_composition(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "standards_atlas.cli.commands.chat.build_review_workbench_web_app",
        lambda **kwargs: calls.append(kwargs),
    )
    result = runner.invoke(
        app, ["chat", "serve", "--service", "review-workbench", "--host", "192.168.0.77"]
    )
    assert result.exit_code == 2
    assert "loopback" in result.output
    assert not calls


def test_review_service_missing_registry_reports_actionable_error(tmp_path):
    result = runner.invoke(
        app,
        [
            "chat",
            "serve",
            "--service-type",
            "review-workbench",
            "--review-workspace",
            str(tmp_path / "missing"),
        ],
    )
    assert result.exit_code == 2
    assert "existing directory" in result.output
