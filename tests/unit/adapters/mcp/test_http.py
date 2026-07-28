import json

import pytest

pytest.importorskip("mcp")
pytest.importorskip("starlette")

from starlette.testclient import TestClient

from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.http import create_http_app


class FakeSessionManager:
    class Context:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    def run(self):
        return self.Context()


class FakeServer:
    session_manager = FakeSessionManager()

    def streamable_http_app(self):
        from starlette.responses import JSONResponse

        async def app(scope, receive, send):
            await JSONResponse({"mcp": "ok"})(scope, receive, send)

        return app


def test_health_endpoint_is_available_without_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_MCP_TOKEN", "secret")
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "auth": {"enabled": True, "token_environment_variable": "TEST_MCP_TOKEN"},
            "audit": {"path": tmp_path / "audit.jsonl"},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_missing_token_and_records_audit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_MCP_TOKEN", "secret")
    audit_path = tmp_path / "audit.jsonl"
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "auth": {"enabled": True, "token_environment_variable": "TEST_MCP_TOKEN"},
            "audit": {"path": audit_path},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.post("/mcp")

    assert response.status_code == 401
    record = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["status"] == 401
    assert record["path"] == "/mcp"


def test_accepts_bearer_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_MCP_TOKEN", "secret")
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "auth": {"enabled": True, "token_environment_variable": "TEST_MCP_TOKEN"},
            "audit": {"path": tmp_path / "audit.jsonl"},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.post("/mcp/", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200


def test_rejects_unapproved_origin(tmp_path) -> None:
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "http": {"allowed_origins": ["https://allowed.example"]},
            "audit": {"path": tmp_path / "audit.jsonl"},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.post("/mcp", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


def test_rejects_request_body_above_configured_limit(tmp_path) -> None:
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "limits": {"max_request_body_bytes": 1024},
            "audit": {"path": tmp_path / "audit.jsonl"},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.post("/mcp/", content=b"x" * 1025)

    assert response.status_code == 413
    assert response.json() == {"detail": "request body is too large"}


def test_accepts_origin_matching_configured_port_wildcard(tmp_path) -> None:
    config = McpServerConfig.model_validate(
        {
            "transport": "streamable-http",
            "http": {"allowed_origins": ["http://192.168.0.77:*"]},
            "audit": {"path": tmp_path / "audit.jsonl"},
        }
    )

    with TestClient(create_http_app(FakeServer(), config)) as client:
        response = client.post(
            "/mcp/",
            headers={"Origin": "http://192.168.0.77:8765"},
        )

    assert response.status_code == 200
