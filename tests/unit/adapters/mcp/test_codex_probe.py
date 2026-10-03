from standards_atlas.adapters.mcp.codex_probe import CodexClientMcpProbe


def test_missing_codex_client_is_reported_as_not_executed() -> None:
    report = CodexClientMcpProbe("definitely-not-installed-codex").run(
        url="http://127.0.0.1:8765/mcp",
        server_name="standards-atlas",
        token_environment_variable="STANDARDS_ATLAS_MCP_TOKEN",
        allow_synthetic_model_call=False,
        model=None,
    )

    assert report.status == "not_executed"
    assert report.tool_read is None
    assert report.as_dict()["real_norm_text_used"] is False
