import json
from typing import Any

import pytest

from standards_atlas.adapters.mcp.compatibility import (
    DEFAULT_PROTOCOL_VERSION,
    FORMULA_TOOLS,
    REQUIRED_TOOLS,
    McpCompatibilityProbe,
    _decode_response_body,
)


class FakeTransport:
    def __init__(
        self,
        responses: dict[str, dict[str, Any]],
        tool_responses: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.responses = responses
        self.tool_responses = tool_responses or {}
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        self.calls.append((method, params, request_id))
        if method == "tools/call" and params["name"] in self.tool_responses:
            return self.tool_responses[params["name"]]
        return self.responses[method]


def _runtime(current: int = 9) -> dict[str, Any]:
    return {
        "application": {"name": "standards-atlas", "version": "0.8.7"},
        "engineering_document_schema": {
            "current": current,
            "readable": [8, 9] if current == 9 else [8],
            "writer": current,
        },
        "capabilities": {"formula_transcription": False},
    }


def _transport() -> FakeTransport:
    return FakeTransport(
        {
            "initialize": {
                "result": {
                    "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                    "serverInfo": {"name": "standards-atlas", "version": "1.28.1"},
                }
            },
            "tools/list": {
                "result": {"tools": [{"name": name} for name in (*REQUIRED_TOOLS, *FORMULA_TOOLS)]}
            },
            "tools/call": {"result": {"content": [], "isError": False}},
            "resources/list": {"result": {"resources": [{"uri": "standards-atlas://documents"}]}},
        },
        {"get_server_info": {"result": {"content": [], "structuredContent": _runtime()}}},
    )


def test_probe_verifies_protocol_tools_resource_and_read_only_call() -> None:
    transport = _transport()

    report = McpCompatibilityProbe(transport).run()

    assert report.passed
    assert report.server_name == "standards-atlas"
    assert report.as_dict()["runtime"] == _runtime()
    assert [call[0] for call in transport.calls] == [
        "initialize",
        "tools/list",
        "tools/call",
        "tools/call",
        "resources/list",
    ]
    assert [call[2] for call in transport.calls] == [1, 2, 3, 4, 5]
    assert [call[1]["name"] for call in transport.calls if call[0] == "tools/call"] == [
        "get_server_info",
        "list_standards",
    ]


def test_probe_reports_missing_required_tool() -> None:
    transport = _transport()
    transport.responses["tools/list"] = {"result": {"tools": [{"name": "list_standards"}]}}

    report = McpCompatibilityProbe(transport).run()

    assert not report.passed
    required_tools = next(check for check in report.checks if check.name == "required_tools")
    assert "get_clause" in required_tools.detail
    schema = next(check for check in report.checks if check.name == "engineering_document_schema")
    assert not schema.passed
    assert "Restart the MCP server" in schema.detail
    assert not any(call[1].get("name") == "get_server_info" for call in transport.calls)


def test_probe_rejects_old_server_schema_even_with_successful_handshake() -> None:
    transport = _transport()
    transport.tool_responses["get_server_info"]["result"]["structuredContent"] = _runtime(8)

    report = McpCompatibilityProbe(transport).run()

    assert not report.passed
    schema = next(check for check in report.checks if check.name == "engineering_document_schema")
    assert not schema.passed
    assert "server current=8" in schema.detail
    assert "local writer=9" in schema.detail
    assert "mcp restart" in schema.detail
    assert report.runtime == _runtime(8)
    assert next(check for check in report.checks if check.name == "initialize").passed


def test_probe_reads_runtime_json_text_fallback() -> None:
    transport = _transport()
    transport.tool_responses["get_server_info"] = {
        "result": {"content": [{"type": "text", "text": json.dumps(_runtime())}]}
    }

    report = McpCompatibilityProbe(transport).run()

    assert report.passed
    assert report.runtime == _runtime()


@pytest.mark.parametrize(
    "result",
    [
        {"content": []},
        {"content": [{"type": "text", "text": "not JSON"}]},
        {"content": [], "structuredContent": {"engineering_document_schema": None}},
        {"content": [], "structuredContent": {"engineering_document_schema": {"current": "9"}}},
    ],
)
def test_probe_does_not_accept_missing_or_malformed_runtime(result) -> None:
    transport = _transport()
    transport.tool_responses["get_server_info"] = {"result": result}

    report = McpCompatibilityProbe(transport).run()

    assert not report.passed
    assert not next(c for c in report.checks if c.name == "engineering_document_schema").passed


def test_probe_checks_formula_listing_without_writing_or_reporting_source_images() -> None:
    transport = _transport()
    transport.tool_responses["list_untranscribed_formulas"] = {
        "result": {"content": [{"type": "text", "text": "private-image-and-clause-content"}]}
    }

    report = McpCompatibilityProbe(
        transport, document_keys=("IEC61508-3", "IEC61508-2", "IEC61508-3")
    ).run()

    assert report.passed
    formula_call = transport.calls[-1]
    assert formula_call == (
        "tools/call",
        {
            "name": "list_untranscribed_formulas",
            "arguments": {"document_keys": ["IEC61508-2", "IEC61508-3"], "limit": 1},
        },
        6,
    )
    assert "private-image-and-clause-content" not in json.dumps(report.as_dict())
    assert all(call[1].get("name") != "submit_formula_transcription" for call in transport.calls)


def test_probe_reports_formula_schema_error_verbatim() -> None:
    error = (
        "Unsupported engineering document schema version: 9; readable versions are 8, current is 8"
    )
    transport = _transport()
    transport.tool_responses["list_untranscribed_formulas"] = {
        "result": {"isError": True, "content": [{"type": "text", "text": error}]}
    }

    report = McpCompatibilityProbe(transport, document_keys=("IEC61508-3",)).run()

    assert not report.passed
    formula = next(c for c in report.checks if c.name == "list_untranscribed_formulas")
    assert not formula.passed
    assert error in formula.detail


@pytest.mark.parametrize(
    "response",
    [
        {"error": {"code": -32603, "message": "schema mismatch"}},
        {},
        {"result": {}},
        {"result": {"content": "not MCP content"}},
    ],
)
def test_probe_never_reports_malformed_or_failed_tool_call_as_success(response) -> None:
    transport = _transport()
    transport.tool_responses["list_standards"] = response

    report = McpCompatibilityProbe(transport).run()

    assert not report.passed
    assert not next(c for c in report.checks if c.name == "list_standards").passed


def test_probe_requires_formula_tools_only_when_document_was_requested() -> None:
    transport = _transport()
    transport.responses["tools/list"] = {
        "result": {"tools": [{"name": name} for name in REQUIRED_TOOLS]}
    }

    assert McpCompatibilityProbe(transport).run().passed
    report = McpCompatibilityProbe(transport, document_keys=("IEC61508-3",)).run()
    assert not report.passed
    assert not next(c for c in report.checks if c.name == "list_untranscribed_formulas").passed


def test_decodes_json_and_sse_responses() -> None:
    assert _decode_response_body('{"jsonrpc":"2.0","id":1,"result":{}}')["id"] == 1
    assert (
        _decode_response_body('event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n')[
            "id"
        ]
        == 2
    )
