"""Protocol-level compatibility probe for Streamable HTTP MCP servers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_PROTOCOL_VERSION = "2025-11-25"
REQUIRED_TOOLS = (
    "list_standards",
    "get_clause",
    "list_clauses",
    "search_clauses",
    "sample_clauses",
)


class JsonRpcTransport(Protocol):
    """Minimal transport needed by the compatibility probe."""

    def request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        """Send one JSON-RPC request and return the decoded response."""


@dataclass(frozen=True)
class CompatibilityCheck:
    """Result of one interoperability check."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CompatibilityReport:
    """Structured result of an MCP compatibility probe."""

    server_name: str | None
    server_version: str | None
    protocol_version: str | None
    checks: tuple[CompatibilityCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "server": {
                "name": self.server_name,
                "version": self.server_version,
            },
            "protocol_version": self.protocol_version,
            "checks": [
                {"name": check.name, "passed": check.passed, "detail": check.detail}
                for check in self.checks
            ],
        }


class StreamableHttpJsonRpcTransport:
    """Small JSON-RPC client for stateless Streamable HTTP servers."""

    def __init__(
        self,
        url: str,
        *,
        bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    ) -> None:
        self.url = url if url.endswith("/") else f"{url}/"
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.protocol_version = protocol_version

    def request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        ).encode("utf-8")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": self.protocol_version,
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        request = urllib.request.Request(
            self.url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP request failed with {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MCP connection failed: {exc.reason}") from exc

        decoded = _decode_response_body(body)
        if "error" in decoded:
            raise RuntimeError(f"MCP JSON-RPC error: {decoded['error']}")
        return decoded


def _decode_response_body(body: str) -> dict[str, Any]:
    stripped = body.strip()
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise RuntimeError("MCP response must be a JSON object")
        return payload

    for line in stripped.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line.removeprefix("data:").strip())
            if isinstance(payload, dict):
                return payload
    raise RuntimeError("MCP response was neither JSON nor a supported SSE message")


class McpCompatibilityProbe:
    """Verify the interoperable, read-only Standards Atlas MCP contract."""

    def __init__(
        self,
        transport: JsonRpcTransport,
        *,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        required_tools: tuple[str, ...] = REQUIRED_TOOLS,
    ) -> None:
        self.transport = transport
        self.protocol_version = protocol_version
        self.required_tools = required_tools

    def run(self) -> CompatibilityReport:
        checks: list[CompatibilityCheck] = []
        server_name: str | None = None
        server_version: str | None = None
        negotiated_protocol: str | None = None

        initialize = self.transport.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "standards-atlas-probe", "version": "1"},
            },
            1,
        )
        result = initialize.get("result", {})
        negotiated_protocol = result.get("protocolVersion")
        server_info = result.get("serverInfo", {})
        server_name = server_info.get("name")
        server_version = server_info.get("version")
        protocol_ok = negotiated_protocol == self.protocol_version
        checks.append(
            CompatibilityCheck(
                "initialize",
                protocol_ok,
                f"negotiated protocol {negotiated_protocol!r}",
            )
        )

        tools_response = self.transport.request("tools/list", {}, 2)
        tools = tools_response.get("result", {}).get("tools", [])
        tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        missing = sorted(set(self.required_tools) - tool_names)
        checks.append(
            CompatibilityCheck(
                "required_tools",
                not missing,
                "all required tools registered" if not missing else f"missing tools: {missing}",
            )
        )

        standards_response = self.transport.request(
            "tools/call",
            {"name": "list_standards", "arguments": {}},
            3,
        )
        call_result = standards_response.get("result", {})
        is_error = bool(call_result.get("isError", False))
        content = call_result.get("content", [])
        checks.append(
            CompatibilityCheck(
                "list_standards",
                not is_error and isinstance(content, list),
                "tool call returned MCP content" if not is_error else "tool returned isError=true",
            )
        )

        resources_response = self.transport.request("resources/list", {}, 4)
        resources = resources_response.get("result", {}).get("resources", [])
        resource_uris = {
            str(resource.get("uri")) for resource in resources if isinstance(resource, dict)
        }
        documents_resource = "standards-atlas://documents"
        checks.append(
            CompatibilityCheck(
                "documents_resource",
                documents_resource in resource_uris,
                (
                    "documents resource registered"
                    if documents_resource in resource_uris
                    else "documents resource missing"
                ),
            )
        )

        return CompatibilityReport(
            server_name=server_name,
            server_version=server_version,
            protocol_version=negotiated_protocol,
            checks=tuple(checks),
        )


def token_from_environment(variable: str) -> str | None:
    """Read an optional bearer token without exposing it in reports."""
    return os.environ.get(variable)
