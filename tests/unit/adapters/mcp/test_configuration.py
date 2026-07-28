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
  http:
    allowed_hosts: [localhost:*, 192.168.0.77:*]
""",
        encoding="utf-8",
    )

    config = McpServerConfig.load(path)

    assert config.name == "test-atlas"
    assert config.workspace.name == "local-atlas"
    assert config.allowed_document_keys == ("EN50716",)
    assert config.limits.max_results == 7
    assert not config.expose.clause_text
    assert config.http.allowed_hosts == ("localhost:*", "192.168.0.77:*")


def test_requires_authentication_for_public_http_binding() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="authentication is required"):
        McpServerConfig.model_validate(
            {
                "transport": "streamable-http",
                "http": {"host": "0.0.0.0"},
            }
        )


def test_accepts_authenticated_public_http_binding() -> None:
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "http": {"host": "0.0.0.0", "port": 9000, "path": "/atlas"},
            "auth": {"enabled": True},
        }
    )

    assert config.http.port == 9000
    assert config.http.path == "/atlas"


def test_rejects_unknown_http_configuration_fields() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unknown_option"):
        McpServerConfig.model_validate({"http": {"unknown_option": True}})
