"""Protocol-level compatibility probe for Streamable HTTP MCP servers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from standards_atlas.application.schema import SCHEMA_POLICIES

DEFAULT_PROTOCOL_VERSION = "2025-11-25"
REQUIRED_TOOLS = (
    "get_server_info",
    "list_standards",
    "get_clause",
    "list_clauses",
    "search_clauses",
    "sample_clauses",
)

FORMULA_TOOLS = (
    "list_untranscribed_formulas",
    "get_formula",
    "submit_formula_transcription",
)
RESTART_HINT = (
    "Restart the MCP server from the updated checkout/environment "
    "(managed HTTP: standards-atlas mcp restart --config <server-config>)."
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
    runtime: dict[str, Any] | None = None

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
            "runtime": self.runtime,
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
        document_keys: tuple[str, ...] = (),
    ) -> None:
        self.transport = transport
        self.protocol_version = protocol_version
        self.required_tools = required_tools
        self.document_keys = tuple(sorted(set(document_keys)))

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
        required = set(self.required_tools)
        if self.document_keys:
            required.update(FORMULA_TOOLS)
        missing = sorted(required - tool_names)
        checks.append(
            CompatibilityCheck(
                "required_tools",
                not missing,
                "all required tools registered" if not missing else f"missing tools: {missing}",
            )
        )

        schema_check, runtime = self._check_runtime(tool_names)
        checks.append(schema_check)

        try:
            self._call_tool("list_standards", {}, 4)
            check = CompatibilityCheck("list_standards", True, "tool call returned MCP content")
        except (OSError, RuntimeError, ValueError) as exc:
            check = CompatibilityCheck("list_standards", False, str(exc))
        checks.append(check)

        resources_response = self.transport.request("resources/list", {}, 5)
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

        if self.document_keys:
            checks.append(self._check_formulas(tool_names))

        return CompatibilityReport(
            server_name=server_name,
            server_version=server_version,
            protocol_version=negotiated_protocol,
            checks=tuple(checks),
            runtime=runtime,
        )

    def _call_tool(self, name: str, arguments: dict[str, Any], request_id: int) -> dict[str, Any]:
        response = self.transport.request(
            "tools/call", {"name": name, "arguments": arguments}, request_id
        )
        if "error" in response:
            raise RuntimeError(f"{name}: MCP JSON-RPC error: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            raise RuntimeError(f"{name}: malformed MCP tool result")
        if result.get("isError"):
            detail = " ".join(
                item["text"]
                for item in result["content"]
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
            raise RuntimeError(f"{name}: {detail[:2000] or 'tool returned isError=true'}")
        return result

    def _check_runtime(
        self, tool_names: set[str]
    ) -> tuple[CompatibilityCheck, dict[str, Any] | None]:
        if "get_server_info" not in tool_names:
            return (
                CompatibilityCheck(
                    "engineering_document_schema",
                    False,
                    f"Server does not expose loaded runtime/schema information. {RESTART_HINT}",
                ),
                None,
            )
        try:
            result = self._call_tool("get_server_info", {}, 3)
            runtime = _runtime_payload(result)
            schema = runtime.get("engineering_document_schema", {})
            if not isinstance(schema, dict):
                raise ValueError("malformed engineering_document_schema metadata")
            expected = SCHEMA_POLICIES["engineering-document"].current
            readable = schema.get("readable")
            compatible = (
                schema.get("current") == expected
                and schema.get("writer") == expected
                and isinstance(readable, list)
                and expected in readable
            )
            detail = (
                f"server current={schema.get('current')!r}, writer={schema.get('writer')!r}, "
                f"readable={readable!r}; local writer={expected!r}"
            )
            if not compatible:
                detail += f". {RESTART_HINT}"
            return CompatibilityCheck("engineering_document_schema", compatible, detail), runtime
        except (OSError, RuntimeError, ValueError) as exc:
            return (
                CompatibilityCheck("engineering_document_schema", False, f"{exc}. {RESTART_HINT}"),
                None,
            )

    def _check_formulas(self, tool_names: set[str]) -> CompatibilityCheck:
        name = "list_untranscribed_formulas"
        if name not in tool_names:
            return CompatibilityCheck(name, False, f"formula listing tool missing. {RESTART_HINT}")
        try:
            self._call_tool(name, {"document_keys": list(self.document_keys), "limit": 1}, 6)
            # Never copy source images, clause text or transcription artifacts into the report.
            return CompatibilityCheck(
                name, True, f"formula listing succeeded: {self.document_keys!r}"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return CompatibilityCheck(name, False, str(exc))


def _runtime_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Accept both MCP structured content and the standard JSON text fallback."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in result["content"]:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            try:
                payload = json.loads(item["text"])
            except ValueError:
                continue
            if isinstance(payload, dict):
                return payload
    raise ValueError("get_server_info returned no runtime JSON object")


def token_from_environment(variable: str) -> str | None:
    """Read an optional bearer token without exposing it in reports."""
    return os.environ.get(variable)
