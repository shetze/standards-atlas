from standards_atlas.adapters.llm.codex_cli import CodexCliConfig, CodexCliLlmGateway


def test_codex_health_reports_missing_executable():
    health = CodexCliLlmGateway(CodexCliConfig(executable="definitely-not-codex")).health()
    assert not health.available
