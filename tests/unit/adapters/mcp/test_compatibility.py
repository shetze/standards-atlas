from typing import Any

from standards_atlas.adapters.mcp.compatibility import (
    DEFAULT_PROTOCOL_VERSION,
    McpCompatibilityProbe,
    _decode_response_body,
)


class FakeTransport:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any], int]] = []

    def request(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        self.calls.append((method, params, request_id))
        return self.responses[method]


def test_probe_verifies_protocol_tools_resource_and_read_only_call() -> None:
    transport = FakeTransport(
        {
            "initialize": {
                "result": {
                    "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                    "serverInfo": {"name": "standards-atlas", "version": "1.28.1"},
                }
            },
            "tools/list": {
                "result": {
                    "tools": [
                        {"name": "list_standards"},
                        {"name": "get_clause"},
                        {"name": "list_clauses"},
                        {"name": "search_clauses"},
                        {"name": "sample_clauses"},
                    ]
                }
            },
            "tools/call": {"result": {"content": [], "isError": False}},
            "resources/list": {"result": {"resources": [{"uri": "standards-atlas://documents"}]}},
        }
    )

    report = McpCompatibilityProbe(transport).run()

    assert report.passed
    assert report.server_name == "standards-atlas"
    assert [call[0] for call in transport.calls] == [
        "initialize",
        "tools/list",
        "tools/call",
        "resources/list",
    ]


def test_probe_reports_missing_required_tool() -> None:
    transport = FakeTransport(
        {
            "initialize": {
                "result": {
                    "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                    "serverInfo": {},
                }
            },
            "tools/list": {"result": {"tools": [{"name": "list_standards"}]}},
            "tools/call": {"result": {"content": [], "isError": False}},
            "resources/list": {"result": {"resources": [{"uri": "standards-atlas://documents"}]}},
        }
    )

    report = McpCompatibilityProbe(transport).run()

    assert not report.passed
    required_tools = next(check for check in report.checks if check.name == "required_tools")
    assert "get_clause" in required_tools.detail


def test_decodes_json_and_sse_responses() -> None:
    assert _decode_response_body('{"jsonrpc":"2.0","id":1,"result":{}}')["id"] == 1
    assert (
        _decode_response_body('event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n')[
            "id"
        ]
        == 2
    )
