from standards_atlas.adapters.mcp import McpServerConfig


def test_loads_mcp_configuration(tmp_path) -> None:
    path = tmp_path / "mcp.yaml"
    path.write_text(
        """
mcp:
  name: test-atlas
  workspace: local-atlas
  allowed_document_keys: [EN50716]
  limits:
    max_results: 7
  expose:
    clause_text: false
""",
        encoding="utf-8",
    )

    config = McpServerConfig.load(path)

    assert config.name == "test-atlas"
    assert config.workspace.name == "local-atlas"
    assert config.allowed_document_keys == ("EN50716",)
    assert config.limits.max_results == 7
    assert not config.expose.clause_text
